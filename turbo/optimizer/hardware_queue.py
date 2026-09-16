"""One device, one job, and an explicit answer to "what runs next".

The device is the scarce resource: AGENTS.md allows exactly one hardware job at
a time, so every minute spent on a low value candidate is a minute the session
cannot get back. Two failure modes follow from that, and this module exists to
block both. The first is an unordered backlog, where whatever was generated most
recently runs next; the ordering here is an explicit, bounded, inspectable score
instead. The second is a lost claim, where a crash or a second scheduler starts
a job while one is already running; the claim is therefore held in one place and
a second claim is an error, not a queue.

The scores are heuristics for ordering work. They are not probabilities, they
are not measurements, and nothing here may be reported as evidence about a
candidate.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import search_space as space
from turbo.optimizer.budget import stage_mix

SCHEMA = 'local-turbo.autotune-queue.v1'

#: What an unknown hardware cost is worth. Not zero: a candidate with no
#: declared cost must not outrank a candidate that honestly declared an
#: expensive one. This is the session's declared default duration for a hardware
#: job, and a caller that knows better passes the real estimate.
DEFAULT_HARDWARE_SECONDS = 180.0

#: What an unknown reload cost is worth, for a candidate that needs a restart.
DEFAULT_RELOAD_SECONDS = 60.0

#: The cost a candidate is compared against when its seconds are turned into a
#: bounded score. A job at this duration scores 0.5 on the cost term.
REFERENCE_HARDWARE_SECONDS = 180.0

#: Neutral declared values for components a candidate did not declare. These are
#: stated defaults, not inferences about the candidate.
DEFAULT_IMPACT = 0.5
DEFAULT_RISK = 0.5


def _clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


def _bounded(value, default):
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return _clamp(float(value))


def _nonneg(value, default):
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return default
    return float(value)


def requires_restart(candidate):
    """Whether running this candidate needs a process or model reload.

    A candidate may declare it. Otherwise it is read from the search-space
    registry for the variable it changes, and an unrecognised variable is
    treated as requiring a restart, because assuming a hot swap that the runtime
    does not support would silently mix two runtime states in one measurement.
    """
    if not isinstance(candidate, dict):
        return True
    declared = candidate.get('requires_restart')
    if isinstance(declared, bool):
        return declared
    variable = candidate.get('variable')
    if not isinstance(variable, str) or not variable:
        return True
    return bool(space.parameter(variable).get('requires_restart', True))


def priority(candidate, *, family_stats, phase, reload_cost_s=None):
    """Bounded heuristic score in [0, 1] for scheduling order. Not a probability.

    Conceptually this is expected information gain times plausibility times
    product impact, divided by hardware seconds times implementation risk. Both
    divisions are expressed as multiplications by a bounded inverse, so the
    whole expression stays in [0, 1] and no component can blow up when a
    denominator approaches zero:

      gain          1 / (1 + attempts in this family): a family nobody has
                    tried teaches more than the fifth point of a family that
                    has already been mapped.
      plausibility  Laplace-smoothed S2 survival rate of the family, blended
                    with the candidate's declared prior when it has one.
      impact        the candidate's declared product impact, or a neutral
                    declared default.
      cost          REFERENCE / (REFERENCE + seconds), where seconds is the
                    estimated hardware time plus the reload cost when a restart
                    is required. An undeclared cost becomes the session's
                    declared default, never zero.
      risk          1 - risk/2, so a maximally risky candidate is halved rather
                    than zeroed.
      phase         the stage weight from the budget phase policy. A stage the
                    phase forbids scores zero, which is the point: in the
                    closing window nothing but a confirmation run may be picked.

    A candidate that declares no stage scores zero. That is deliberate: the
    phase policy cannot ration what does not say what it is, and silently
    scheduling it would defeat the budget policy.
    """
    if not isinstance(candidate, dict):
        raise ValueError('Candidate must be an object')
    stats = family_stats if isinstance(family_stats, dict) else {}

    attempted = _nonneg(stats.get('attempted'), 0.0)
    survived = _nonneg(stats.get('survived_s2'), 0.0)
    gain = 1.0 / (1.0 + attempted)
    plausibility = (survived + 1.0) / (attempted + 2.0)
    declared_prior = candidate.get('plausibility')
    if not (declared_prior is None or isinstance(declared_prior, bool)) and isinstance(declared_prior, (int, float)):
        plausibility = (plausibility + _clamp(float(declared_prior))) / 2.0

    impact = _bounded(candidate.get('impact'), DEFAULT_IMPACT)
    risk = _bounded(candidate.get('implementation_risk', candidate.get('risk')), DEFAULT_RISK)

    seconds = _nonneg(candidate.get('estimated_seconds', candidate.get('hardware_seconds')),
                      DEFAULT_HARDWARE_SECONDS)
    if requires_restart(candidate):
        seconds += _nonneg(reload_cost_s, DEFAULT_RELOAD_SECONDS)
    cost = REFERENCE_HARDWARE_SECONDS / (REFERENCE_HARDWARE_SECONDS + seconds)

    stage = candidate.get('stage')
    weight = stage_mix(phase).get(stage, 0.0) if isinstance(stage, str) else 0.0

    return _clamp(gain * plausibility * impact * cost * (1.0 - risk / 2.0) * weight)


class HardwareQueue:
    """A bounded backlog plus the single active hardware claim.

    Ordering is highest priority first, and first in first out among equal
    priorities, so a tie is resolved by age rather than by dict iteration order.
    """

    def __init__(self):
        self._entries = []
        self._sequence = 0
        self._active = None

    def push(self, candidate, priority):
        if priority is None or isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise ValueError('Priority must be a number')
        self._sequence += 1
        self._entries.append({'priority': float(priority), 'sequence': self._sequence,
                              'candidate': candidate})
        return self._sequence

    def _ordered(self):
        return sorted(self._entries, key=lambda e: (-e['priority'], e['sequence']))

    def pop(self):
        if not self._entries:
            return None
        entry = self._ordered()[0]
        self._entries.remove(entry)
        return entry['candidate']

    def peek(self):
        if not self._entries:
            return None
        return self._ordered()[0]['candidate']

    def __len__(self):
        return len(self._entries)

    def drain(self):
        """Every queued candidate in pop order, leaving the queue empty."""
        drained = [entry['candidate'] for entry in self._ordered()]
        self._entries = []
        return drained

    @property
    def active(self):
        return self._active

    def claim(self, candidate):
        """Take the single hardware slot. A second claim is an error, not a wait.

        Blocking here would hide a scheduling bug behind a hang, and queueing
        the second claim would let two jobs believe they own the device.
        """
        if self._active is not None:
            raise RuntimeError('Hardware already claimed by ' + repr(self._describe(self._active)))
        self._active = candidate
        return candidate

    def release(self, candidate):
        if self._active is None:
            raise RuntimeError('No hardware claim to release')
        if not (self._active is candidate or self._active == candidate):
            raise RuntimeError('Release does not match the active claim '
                               + repr(self._describe(self._active)))
        self._active = None
        return candidate

    @staticmethod
    def _describe(candidate):
        if isinstance(candidate, dict):
            return candidate.get('candidate_id') or candidate.get('config_hash') or 'unnamed candidate'
        return candidate

    def snapshot(self):
        """Queue contents in pop order, plus the claim, for crash recovery.

        Candidates are carried by reference and treated as opaque values; the
        caller owns serializing them.
        """
        return {'schema_version': SCHEMA, 'sequence': self._sequence,
                'active': self._active,
                'entries': [{'priority': e['priority'], 'sequence': e['sequence'],
                             'candidate': e['candidate']} for e in self._ordered()]}

    def restore(self, snapshot):
        """Replace the contents with a snapshot, preserving pop order exactly."""
        if not isinstance(snapshot, dict):
            raise ValueError('Queue snapshot must be an object')
        if snapshot.get('schema_version') != SCHEMA:
            raise ValueError('Unsupported queue snapshot schema: ' + repr(snapshot.get('schema_version')))
        entries = snapshot.get('entries')
        if not isinstance(entries, list):
            raise ValueError('Queue snapshot carries no entries list')
        restored = []
        for entry in entries:
            if not isinstance(entry, dict) or 'candidate' not in entry:
                raise ValueError('Malformed queue snapshot entry')
            restored.append({'priority': float(entry.get('priority', 0.0)),
                             'sequence': int(entry.get('sequence', len(restored) + 1)),
                             'candidate': entry['candidate']})
        self._entries = restored
        declared = snapshot.get('sequence')
        self._sequence = max([declared if isinstance(declared, int) else 0]
                             + [e['sequence'] for e in restored])
        self._active = snapshot.get('active')
        return self


def restart_keys():
    """Config keys whose value cannot change without a reload.

    Read from the registry rather than restated here, so a control that gains or
    loses its restart requirement does not leave a stale copy behind.
    """
    return tuple(name for name, spec in space.PARAMETERS.items() if spec.get('requires_restart'))


def _runtime_state_key(candidate):
    config = candidate.get('config') if isinstance(candidate, dict) else None
    config = config if isinstance(config, dict) else {}
    values = []
    for name in restart_keys():
        if name in config:
            value = config[name]
            # repr plus type name, because two values that compare equal across
            # types (0 and False) are different runtime states.
            values.append((name, type(value).__name__, repr(value)))
    return (bool(requires_restart(candidate)), tuple(values))


def group_by_runtime_state(candidates):
    """Cluster candidates that can share one loaded runtime state.

    Two candidates land in the same group when they agree on whether a restart
    is required and on every restart-requiring config value, so a scheduler can
    run them back to back without paying a reload between them.

    The grouping is a scheduling hint only. It changes the order in which work
    is done and nothing about what is measured: each candidate is still run and
    recorded exactly as it would have been alone, and no result is merged,
    averaged or attributed across a group.
    """
    groups = []
    index = {}
    for candidate in candidates:
        key = _runtime_state_key(candidate)
        if key not in index:
            index[key] = len(groups)
            groups.append([])
        groups[index[key]].append(candidate)
    return groups
