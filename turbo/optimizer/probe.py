"""Cheap elimination probes that are structurally unable to qualify anything.

Two probes exist. The startup probe (S1) answers whether a configuration loads
and executes at all; it is not a correctness claim and its result must never be
compared with a benchmark score. The diagnostic canary (S2) runs a fixed subset
of development cases through a clearly labelled path that cannot produce a
tracker archive.

Both exist because the frozen runner exposes development, heldout and all, with
no supported way to ask for eight cases. Rather than widen the frozen runner for
a convenience, the cheap stages live outside it and are labelled loudly. The
cost of that choice is that a canary result is never promotion evidence, and the
code enforces that rather than trusting a reader to remember it.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import search_space as space

SCHEMA = 'local-turbo.autotune-probe.v1'

#: Stamped on every canary result. A consumer that does not understand this
#: label must refuse the record rather than read its numbers.
DIAGNOSTIC_LABEL = 'DIAGNOSTIC_CANARY'

#: Outcomes an S1 probe can report. 'unknown' is a real outcome: a probe that
#: could not run tells us nothing, and nothing is not a pass.
LOADED = 'loaded'
REFUSED = 'refused'
CRASHED = 'crashed'
TIMED_OUT = 'timed_out'
UNKNOWN = 'unknown'


class ProbeUnavailable(RuntimeError):
    """The probe could not execute, so it produced no evidence either way."""


def config_acceptable(config, backend):
    """Static pre-check mirroring the frozen runner and the native layer.

    Running a configuration the runner would reject wastes a hardware slot to
    learn something readable from the source, so the same refusals are applied
    here first. This never replaces the runner's own validation; it only avoids
    paying for it.
    """
    reasons = []
    unknown = sorted(set(config) - set(space.RUNNER_ALLOWED_KEYS))
    if unknown:
        reasons.append('Frozen runner rejects keys: ' + ', '.join(unknown))
    if config.get('grammar'):
        reasons.append('Frozen runner rejects a truthy grammar')
    if backend == 'qairt_npu':
        for key in ('threads', 'threads_batch', 'ubatch', 'n_batch'):
            if config.get(key):
                reasons.append('QAIRT rejects ' + key)
        if config.get('spec_type') not in (None, '', 'none'):
            reasons.append('QAIRT rejects spec_type ' + repr(config.get('spec_type')))
    if config.get('stop_after_tool_call') and backend != 'qairt_npu':
        reasons.append('stop_after_tool_call is a QAIRT-only candidate')
    return reasons


def startup_observation(*, loaded, startup_seconds=None, runtime_error=None, exit_code=None,
                        outcome=UNKNOWN, detail=None):
    """One S1 record. Missing timing stays None; it never becomes zero."""
    return {'schema_version': SCHEMA, 'kind': 'startup_probe', 'loaded': bool(loaded),
            'startup_seconds': startup_seconds, 'runtime_error': runtime_error,
            'exit_code': exit_code, 'outcome': outcome, 'detail': detail,
            'correctness_claim': False}


def run_startup_probe(command, *, timeout_s, cwd=None, env=None, runner=None):
    """Execute a bounded startup command and classify what happened.

    ``command`` is an argv list, never a shell string. ``runner`` is injectable
    so the whole classification is testable without a model, an SDK or a device.
    The elapsed time is wall clock around the child, which is the load cost the
    scheduler needs; it is not, and must not be reported as, inference latency.
    """
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError('Startup probe needs an argv list')
    effective_runner = subprocess.run if runner is None else runner
    started = time.monotonic()
    try:
        completed = effective_runner(list(command), cwd=cwd, env=env, timeout=timeout_s,
                           capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return startup_observation(loaded=False, startup_seconds=None, outcome=TIMED_OUT,
                                   detail='Startup exceeded ' + str(timeout_s) + ' s')
    except OSError as exc:
        raise ProbeUnavailable('Startup probe could not be launched: ' + str(exc)) from exc
    elapsed = round(time.monotonic() - started, 3)
    if completed.returncode == 0:
        return startup_observation(loaded=True, startup_seconds=elapsed, outcome=LOADED,
                                   exit_code=0)
    stderr = (completed.stderr or '').strip()
    refused = 'Unknown configuration keys' in stderr or 'conflicts with' in stderr or 'rejects' in stderr
    return startup_observation(loaded=False, startup_seconds=elapsed,
                               outcome=REFUSED if refused else CRASHED,
                               exit_code=completed.returncode,
                               runtime_error=stderr[-2000:] or None,
                               detail='Nonzero exit from the startup command')


def fixed_subset(case_ids, size, *, seed_label):
    """Choose a subset before a session starts, deterministically and once.

    The subset must not adapt to results: a canary re-chosen after seeing which
    cases a candidate passes stops being an eliminator and becomes a way to
    manufacture a favourable comparison. Selection is therefore a pure function
    of the case list, the size and a label recorded in the session.
    """
    if not isinstance(size, int) or size < 1:
        raise ValueError('Subset size must be a positive integer')
    ordered = sorted(case_ids)
    if size > len(ordered):
        raise ValueError('Subset size exceeds the available development cases')
    import hashlib
    ranked = sorted(ordered, key=lambda case: hashlib.sha256(
        (str(seed_label) + '|' + str(case)).encode('utf-8')).hexdigest())
    return sorted(ranked[:size])


def canary_result(*, subset, correct, attempted, invalid, median_latency_ms, failures=None):
    """One S2 record, labelled so it cannot be mistaken for a qualified result."""
    if attempted != len(subset):
        raise ValueError('A canary must attempt every case in its declared subset')
    return {'schema_version': SCHEMA, 'kind': 'diagnostic_canary', 'label': DIAGNOSTIC_LABEL,
            'split': 'development', 'subset': list(subset), 'attempted': attempted,
            'correct': correct, 'invalid': invalid,
            'median_latency_ms': median_latency_ms,
            'failures': dict(failures or {}),
            'qualified': False,
            'promotion_evidence': False,
            'note': 'Elimination signal only. A candidate is never promoted from this record; '
                    'promotion requires a tracked development run through the experiment tracker.'}


def refuse_as_evidence(record):
    """Reason a canary record may not be cited as promotion evidence."""
    label = record.get('label') if isinstance(record, dict) else None
    if label == DIAGNOSTIC_LABEL:
        return (DIAGNOSTIC_LABEL + ' over ' + str(len(record.get('subset') or []))
                + ' development cases is an elimination signal, not a measured result. '
                  'Promotion requires a tracked development run.')
    return 'Record is not a diagnostic canary'
