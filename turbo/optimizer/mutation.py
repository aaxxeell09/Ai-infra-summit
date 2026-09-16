"""Deterministic candidate generation, so a search can be replayed and audited.

Nothing here proposes anything: it enumerates what the declared search space
already permits. That matters because a hardware slot spent on an invented knob
is a slot spent proving nothing, and because a run nobody can reproduce is not
evidence. Every candidate is one field away from its control (turbo/campaign_plan.py
refuses more), carries the hash of the control it came from, and states a
hypothesis built from the evidence that put the parameter in the space at all.

An LLM may still be consulted, through from_llm_space: its proposal is data that
this module filters, never a source of new values. Out-of-space proposals are
rejected with a reason and are never clamped into range, because a clamped
proposal is a treatment nobody chose masquerading as one somebody did.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import search_space as space
from turbo.optimizer import state

SCHEMA = 'local-turbo.autotune-candidate.v1'

#: Sentinel for "the control does not carry this key at all". Distinct from any
#: value a config could hold, and never confused with a runner default: the
#: runner's default for an omitted key is its business, not a value we may claim
#: the control has.
MISSING = object()


def _same(left, right):
    """Type-aware equality, so True never matches 1 and 1.0 never matches 1."""
    return left is right or (left == right and type(left) is type(right))


def _label(value):
    return value if isinstance(value, str) else repr(value)


def _candidate_id(index):
    if type(index) is not int or index < 0:
        raise ValueError('Candidate index must be a non-negative integer')
    return 'C-%04d' % index


def _hypothesis(name, spec, backend, before, after):
    """One falsifiable sentence per candidate, built from declared evidence.

    It deliberately states attribution and not improvement: predicting a win
    before measuring one is how a search starts believing its own candidates.
    """
    origin = 'unset on the control' if before is MISSING else 'control ' + _label(before)
    sentence = ('Setting ' + name + ' to ' + _label(after) + ' (' + origin + ') is the only field that '
                'differs from the control, so any behaviour change measured on ' + str(backend) + ' is '
                'attributable to the ' + spec['family'] + ' family and to nothing else.')
    sentence += ' Declared support: ' + spec['evidence'] + '.'
    if spec['note']:
        sentence += ' ' + spec['note']
    return sentence


def _build(control_config, backend, name, value, index):
    spec = space.PARAMETERS[name]
    config = dict(control_config)
    before = config.get(name, MISSING)
    config[name] = value
    return {
        'candidate_id': _candidate_id(index),
        'parent_control': state.config_hash(control_config),
        'family': spec['family'],
        'variable': name,
        'treatment': name + '=' + _label(value),
        'config': config,
        'config_hash': state.config_hash(config),
        'hypothesis': _hypothesis(name, spec, backend, before, value),
        'stage': 'S0',
        'requires_restart': bool(spec['requires_restart']),
        # Unknown until this treatment has actually run on the device. A guessed
        # duration would be used for scheduling and then reported as if measured.
        'expected_hardware_seconds': None,
        'priority': None,
        'status': 'generated',
    }


def _checked_control(control_config):
    if not isinstance(control_config, dict) or not control_config:
        raise ValueError('Control config must be a nonempty JSON object')
    return control_config


def _checked_backend(backend):
    if backend not in space.BACKENDS:
        raise ValueError('Unknown backend: ' + repr(backend))
    return backend


def _selection(backend, families, parameters):
    """Parameter names to enumerate, in declaration order, after filtering.

    A filter naming something the repository never declared is an error rather
    than an empty result: a typo that silently generates nothing looks exactly
    like a space that legitimately has nothing in it.
    """
    # admissible_for_qualified_search, not supported_parameters: the space
    # declares statuses (diagnostic, protocol extension) that are visible on a
    # backend without being admissible into a tracker-backed experiment.
    names = tuple(name for name in space.PARAMETERS
                  if space.admissible_for_qualified_search(name, backend))
    if parameters is not None:
        wanted = list(parameters)
        unknown = [n for n in wanted if n not in space.PARAMETERS]
        if unknown:
            raise ValueError('Undeclared parameter filter: ' + ', '.join(map(str, unknown)))
        names = tuple(n for n in names if n in wanted)
    if families is not None:
        wanted = list(families)
        declared = {spec['family'] for spec in space.PARAMETERS.values()}
        unknown = [f for f in wanted if f not in declared]
        if unknown:
            raise ValueError('Undeclared family filter: ' + ', '.join(map(str, unknown)))
        names = tuple(n for n in names if space.PARAMETERS[n]['family'] in wanted)
    return names


def generate(control_config, backend, *, families=None, parameters=None, start_index=1):
    """Every single-variable treatment this backend can reach from the control.

    Declaration order of PARAMETERS, then declaration order of allowed_values,
    so identical inputs give identical candidates with identical ids. The value
    the control already holds is skipped; a key the control omits is not treated
    as holding the runner's default, so every declared value stays reachable.
    """
    _checked_control(control_config)
    _checked_backend(backend)
    candidates = []
    index = start_index
    for name in _selection(backend, families, parameters):
        allowed = space.PARAMETERS[name]['allowed_values']
        if not allowed:
            continue
        current = control_config.get(name, MISSING)
        for value in allowed:
            if current is not MISSING and _same(current, value):
                continue
            candidates.append(_build(control_config, backend, name, value, index))
            index += 1
    return candidates


def neighbourhood(control_config, backend, parameter, *, radius=1, start_index=1):
    """Values adjacent to the control's current value in the declared order.

    Adjacency is only meaningful for an ordered enumeration, so a boolean or
    string enumeration returns every other declared value regardless of radius.
    A control whose value is outside the enumeration has no neighbours to speak
    of, and saying so is better than picking an arbitrary anchor.
    """
    _checked_control(control_config)
    _checked_backend(backend)
    if type(radius) is not int or radius < 1:
        raise ValueError('radius must be a positive integer')
    if not space.admissible_for_qualified_search(parameter, backend):
        raise ValueError(str(parameter) + ' is not admissible for qualified search on backend '
                         + str(backend))
    allowed = space.PARAMETERS[parameter]['allowed_values']
    if not allowed:
        raise ValueError(str(parameter) + ' declares no bounded enumeration to step through')
    current = control_config.get(parameter, MISSING)
    if current is MISSING:
        raise ValueError('Control does not set ' + str(parameter) + ', so it has no neighbourhood')
    position = [i for i, value in enumerate(allowed) if _same(current, value)]
    if not position:
        raise ValueError('Control value ' + repr(current) + ' for ' + str(parameter)
                         + ' is outside the declared enumeration')
    anchor = position[0]
    if any(isinstance(value, (bool, str)) for value in allowed):
        chosen = [value for i, value in enumerate(allowed) if i != anchor]
    else:
        chosen = list(allowed[max(0, anchor - radius):anchor]) + list(allowed[anchor + 1:anchor + 1 + radius])
    return [_build(control_config, backend, parameter, value, start_index + offset)
            for offset, value in enumerate(chosen)]


def from_llm_space(control_config, backend, space_proposal, *, start_index=1):
    """Turn an LLM's proposed {parameter: [values]} into bounded candidates.

    Returns (candidates, rejected) where rejected is [(parameter, value, reason)].
    Nothing is clamped, rounded or renamed on the way in: a proposal outside the
    declared enumeration is a proposal the repository has no evidence for, and
    quietly moving it inside the fence would launder that absence into a number.
    """
    _checked_control(control_config)
    _checked_backend(backend)
    if not isinstance(space_proposal, dict):
        raise ValueError('Proposed space must be an object of parameter to values')
    candidates, rejected, seen_pairs = [], [], set()
    index = start_index
    for name, values in space_proposal.items():
        if not isinstance(name, str) or not name.strip():
            rejected.append((name, None, 'Parameter name must be a nonempty string'))
            continue
        if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
            rejected.append((name, values, 'Proposed values must be an array'))
            continue
        for value in values:
            errors = space.value_errors(name, value, backend)
            if errors:
                rejected.append((name, value, '; '.join(errors)))
                continue
            key = (name, repr(type(value)), repr(value))
            if key in seen_pairs:
                rejected.append((name, value, 'Repeated proposal of the same value'))
                continue
            seen_pairs.add(key)
            current = control_config.get(name, MISSING)
            if current is not MISSING and _same(current, value):
                rejected.append((name, value, 'Value is already the control value, so it is not a treatment'))
                continue
            candidates.append(_build(control_config, backend, name, value, index))
            index += 1
    return candidates, rejected


def deduplicate(candidates, seen=()):
    """Split candidates by state.config_hash into (unique, duplicates).

    ``seen`` is the set of hashes already known, typically state['tested_exact'],
    so a resumed session does not re-measure a treatment it already paid for.
    """
    known = set(seen)
    unique, duplicates = [], []
    for candidate in candidates:
        digest = candidate.get('config_hash')
        if not isinstance(digest, str) or not digest:
            raise ValueError('Candidate carries no config hash: ' + repr(candidate.get('candidate_id')))
        if digest in known:
            duplicates.append(candidate)
        else:
            known.add(digest)
            unique.append(candidate)
    return unique, duplicates
