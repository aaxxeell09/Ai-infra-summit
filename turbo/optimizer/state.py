"""Durable autotune session state: orchestration metadata, never measurement.

The experiment tracker owns measured evidence. Everything here is bookkeeping
that lets a session resume, avoid repeating a treatment and explain its own
decisions. Losing this file must never invalidate an archive, and rebuilding it
must never alter one.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import atomic, digest
from turbo.json_io import parse_json

SCHEMA = 'local-turbo.autotune-state.v1'
DEFAULT_HOME = ROOT / 'local/autotune'

STAGES = ('S0', 'S1', 'S2', 'S3', 'S4', 'S5')
TERMINAL = ('promoted', 'dropped', 'rejected', 'failed')

#: Failure classes projected from evaluator rows. These are diagnostic
#: groupings of flags the frozen evaluator already produced; nothing here
#: rescores an output.
FAILURE_CLASSES = ('invalid_format', 'wrong_tool', 'wrong_arguments',
                   'clarify_failure', 'model_error', 'timeout', 'other')


def now():
    return datetime.now(timezone.utc).isoformat()


def config_hash(config):
    """Semantic hash of a candidate configuration, excluding machine paths.

    ``sdk_dir`` and ``model_path`` identify where an artifact lives on one
    machine, not what the treatment is. Two runs of the same treatment from
    different checkouts must deduplicate, so those keys are excluded, and the
    artifact identity is carried separately by the tracker.
    """
    if not isinstance(config, dict):
        raise ValueError('Config must be an object')
    return digest({k: v for k, v in config.items() if k not in ('sdk_dir', 'model_path', 'hardware_note')})


def new_session(*, backend, split, budget_minutes, control_name, control_config,
                search_space_sha256=None, session_id=None):
    """Create a fresh session record. Nothing is written to disk here."""
    if split != 'development':
        raise ValueError('Optimization sessions run on development cases only')
    if not isinstance(budget_minutes, (int, float)) or budget_minutes <= 0:
        raise ValueError('budget_minutes must be positive')
    return {
        'schema_version': SCHEMA,
        'session_id': session_id or ('AT-' + uuid.uuid4().hex[:12]),
        'created_at': now(),
        'updated_at': now(),
        'backend': backend,
        'split': split,
        'budget_minutes': float(budget_minutes),
        'elapsed_seconds': 0.0,
        'search_space_sha256': search_space_sha256,
        'current_control': {'name': control_name, 'config': dict(control_config),
                            'config_hash': config_hash(control_config),
                            'experiment_id': None, 'promoted_at': None},
        'controls_history': [],
        'tested_exact': {},
        'families': {},
        'rejected': [],
        'search_spaces_attempted': [],
        'case_history': {},
        'failure_history': {name: 0 for name in FAILURE_CLASSES},
        'counters': {'generated': 0, 'unique': 0, 'static_rejected': 0,
                     'S1': 0, 'S2': 0, 'S3': 0, 'S4': 0, 'S5': 0,
                     'promotions': 0, 'api_calls': 0},
        'timing': {'hardware_busy_s': 0.0, 'hardware_idle_s': 0.0, 'api_wait_s': 0.0,
                   'generation_s': 0.0, 'static_validation_s': 0.0, 'reload_s': 0.0,
                   'tracker_overhead_s': 0.0},
        'energy_commissioned': False,
        'owner_decisions': [],
        'finished_at': None,
    }


def family_record(name):
    return {'family': name, 'attempted': 0, 'survived_s2': 0, 'survived_s3': 0,
            'dev35_wins': 0, 'confirmed_wins': 0, 'net_case_deltas': [],
            'hardware_seconds_spent': 0.0}


def touch_family(state, name):
    return state['families'].setdefault(name, family_record(name))


def record_outcome(state, candidate, stage, outcome, *, hardware_seconds=0.0, net_cases=None):
    """Append one stage outcome for a candidate, keyed by its config hash.

    An outcome is never overwritten: a repeated treatment appends a second
    observation so variance stays visible instead of the last run silently
    replacing the first.
    """
    if stage not in STAGES:
        raise ValueError('Unknown stage: ' + str(stage))
    digest_key = candidate['config_hash']
    entry = state['tested_exact'].setdefault(digest_key, {'candidate_id': candidate.get('candidate_id'),
                                                          'family': candidate.get('family'),
                                                          'variable': candidate.get('variable'),
                                                          'observations': []})
    entry['observations'].append({'stage': stage, 'outcome': outcome, 'at': now(),
                                  'hardware_seconds': float(hardware_seconds),
                                  'net_cases': net_cases})
    family = touch_family(state, candidate.get('family') or 'unknown')
    family['hardware_seconds_spent'] += float(hardware_seconds)
    if stage == 'S2' and outcome == 'survive':
        family['survived_s2'] += 1
    if stage == 'S3' and outcome == 'survive':
        family['survived_s3'] += 1
    if stage == 'S4' and net_cases is not None:
        family['net_case_deltas'].append(net_cases)
        if net_cases > 0:
            family['dev35_wins'] += 1
    if stage == 'S5' and outcome == 'promote':
        family['confirmed_wins'] += 1
    state['counters'][stage] = state['counters'].get(stage, 0) + 1
    state['updated_at'] = now()
    return entry


def record_rejection(state, candidate, reasons):
    state['rejected'].append({'candidate_id': candidate.get('candidate_id'),
                              'config_hash': candidate.get('config_hash'),
                              'family': candidate.get('family'),
                              'reasons': list(reasons), 'at': now()})
    state['counters']['static_rejected'] += 1
    state['updated_at'] = now()


def promote(state, candidate, *, experiment_id=None):
    """Make a candidate the new control, keeping the previous one recoverable."""
    previous = dict(state['current_control'])
    state['controls_history'].append({**previous, 'replaced_at': now()})
    state['current_control'] = {'name': candidate.get('candidate_id') or candidate.get('name'),
                                'config': dict(candidate['config']),
                                'config_hash': candidate['config_hash'],
                                'experiment_id': experiment_id,
                                'promoted_at': now()}
    state['counters']['promotions'] += 1
    state['updated_at'] = now()
    return previous


def rollback(state):
    """Restore the previous control after a failed promotion."""
    if not state['controls_history']:
        raise ValueError('No previous control to roll back to')
    previous = state['controls_history'].pop()
    previous.pop('replaced_at', None)
    state['current_control'] = previous
    state['counters']['promotions'] = max(0, state['counters']['promotions'] - 1)
    state['updated_at'] = now()
    return previous


def already_tested(state, candidate_hash):
    return candidate_hash in state['tested_exact']


def home(root=None):
    path = Path(root) if root is not None else DEFAULT_HOME
    return path


def ensure_home(root=None):
    path = home(root)
    for name in ('analyses', 'candidates', 'reports', 'logs'):
        (path / name).mkdir(parents=True, exist_ok=True)
    return path


def save(state, path):
    """Write the state atomically. A crashed write leaves the previous state."""
    state = dict(state)
    state['updated_at'] = now()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    atomic(path, json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
    return path


def load(path):
    """Read a state file, refusing anything that is not this schema."""
    value = parse_json(Path(path).read_bytes(), require_object=True)
    if value.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported autotune state schema: ' + repr(value.get('schema_version')))
    if value.get('split') != 'development':
        raise ValueError('Refusing a state whose split is not development')
    for key in ('session_id', 'backend', 'current_control', 'tested_exact', 'counters', 'timing'):
        if key not in value:
            raise ValueError('Autotune state is missing ' + key)
    return value


def resume(path):
    """Load a state and mark it resumed, preserving every completed outcome."""
    state = load(path)
    if state.get('finished_at'):
        raise ValueError('Session already finished; start a new session instead of resuming')
    state.setdefault('resumed', []).append(now())
    return state


def failure_record(exc, *, where, candidate=None, stage=None):
    """Local recovery evidence, not an evaluator result or qualified observation."""
    import traceback
    text = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    message = str(exc)
    # Retain actionable tracebacks while removing configured credential values.
    for name, secret in os.environ.items():
        if secret and len(secret) >= 4 and any(marker in name.upper() for marker in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
            text = text.replace(secret, '[REDACTED]')
            message = message.replace(secret, '[REDACTED]')
    return {'at': now(), 'where': where, 'candidate_id': (candidate or {}).get('candidate_id'),
            'stage': stage, 'error_class': type(exc).__name__, 'message': message,
            'traceback': text, 'qualified': False, 'promotion_evidence': False,
            'hardware_observation': None}
