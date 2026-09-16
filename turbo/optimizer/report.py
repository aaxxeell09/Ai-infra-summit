"""Session reporting whose nouns cannot flatter the session.

The failure mode this module exists to prevent is a sentence like "we ran 500
experiments overnight". A generated configuration is a string of JSON. It is not
a test, not a run and not an experiment. Between construction and evidence there
are four separate narrowings, and a report that collapses them turns a night of
cheap static generation into a claim about hardware that nothing supports.

So the five populations are named, counted and printed separately, always with
these words:

    GENERATED_CANDIDATES         every candidate the engine constructed
    STATICALLY_VALID_CANDIDATES  those the guard admitted
    DIAGNOSTIC_CANDIDATES        those admissible only to a diagnostic lane
    HARDWARE_ATTEMPTS            candidates that actually reached hardware
    QUALIFIED_EXPERIMENTS        tracker archives that reached a qualified status

Only the last is evidence. Everything else is bookkeeping about intent, and the
renderer says so on the page so the distinction survives being pasted into a
message. A figure that was not measured is None here and prints as 'not
measured'; it never becomes 0.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import atomic
from turbo.json_io import parse_json

SCHEMA = 'local-turbo.autotune-session-summary.v1'

GENERATED_CANDIDATES = 'GENERATED_CANDIDATES'
STATICALLY_VALID_CANDIDATES = 'STATICALLY_VALID_CANDIDATES'
DIAGNOSTIC_CANDIDATES = 'DIAGNOSTIC_CANDIDATES'
HARDWARE_ATTEMPTS = 'HARDWARE_ATTEMPTS'
QUALIFIED_EXPERIMENTS = 'QUALIFIED_EXPERIMENTS'

COUNT_NAMES = (GENERATED_CANDIDATES, STATICALLY_VALID_CANDIDATES, DIAGNOSTIC_CANDIDATES,
               HARDWARE_ATTEMPTS, QUALIFIED_EXPERIMENTS)

#: Printed next to each count so the reader never has to trust the label alone.
COUNT_MEANINGS = {
    GENERATED_CANDIDATES: 'configurations the engine constructed. Not tests, not runs, not experiments.',
    STATICALLY_VALID_CANDIDATES: 'of those, the ones the guard admitted. Still no hardware involved.',
    DIAGNOSTIC_CANDIDATES: 'admissible only to a diagnostic lane; an elimination signal, never promotion evidence.',
    HARDWARE_ATTEMPTS: 'candidates that actually reached the device, including attempts that failed.',
    QUALIFIED_EXPERIMENTS: 'tracker archives that reached a qualified status. This is the only measured evidence.',
}

#: Manifest statuses turbo/experiments.py considers qualified.
QUALIFIED_STATUSES = ('completed_qualified',)

MEASUREMENT_FILE = 'session-summary'
NOT_MEASURED = 'not measured'

#: Control KPI fields, with the tracker key names they may arrive under.
CONTROL_FIELDS = {
    'success_rate_pct': ('success_rate_pct', 'success'),
    'correct_cases': ('correct_tasks', 'correct_cases'),
    'attempted_cases': ('total_tasks', 'attempted_cases'),
    'invalid_count': ('invalid_count',),
    'median_task_latency_ms': ('median_e2e_ms', 'median_task_latency_ms'),
    'p95_task_latency_ms': ('p95_e2e_ms', 'p95_task_latency_ms'),
    'failure_taxonomy': ('error_taxonomy', 'failure_taxonomy'),
}


def utilisation(busy_s, idle_s):
    """Percent of accounted hardware time that was busy, or None.

    None when either figure is missing or negative, and None when both are zero:
    a session that touched no hardware has no utilisation, and reporting 0.0 for
    it would read as an idle device rather than as an absent measurement.
    """
    if busy_s is None or idle_s is None:
        return None
    try:
        busy, idle = float(busy_s), float(idle_s)
    except (TypeError, ValueError):
        return None
    if busy < 0 or idle < 0 or busy + idle <= 0:
        return None
    return 100.0 * busy / (busy + idle)


def _duration_seconds(started_at, finished_at):
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(str(started_at))
        end = datetime.fromisoformat(str(finished_at))
    except ValueError:
        return None
    if (start.tzinfo is None) != (end.tzinfo is None):
        return None
    return (end - start).total_seconds()


def _pick(entry, names):
    """First present key, searching the record and its nested kpi block."""
    sources = [entry]
    kpi = entry.get('kpi')
    if isinstance(kpi, dict):
        sources.append(kpi)
    for source in sources:
        for name in names:
            if source.get(name) is not None:
                return source[name]
    return None


def control_view(entry):
    """Project a control record into reportable fields, unmeasured staying None."""
    entry = entry if isinstance(entry, dict) else {}
    view = {'name': entry.get('name'), 'config_hash': entry.get('config_hash'),
            'experiment_id': entry.get('experiment_id'),
            'config': entry.get('config') if isinstance(entry.get('config'), dict) else None}
    for field, names in CONTROL_FIELDS.items():
        view[field] = _pick(entry, names)
    view['measured'] = any(view[field] is not None for field in CONTROL_FIELDS)
    return view


def qualified_experiments(experiments):
    """Tracker records whose manifest status is qualified. Nothing else counts."""
    qualified = []
    for item in experiments or ():
        if not isinstance(item, dict):
            continue
        status = item.get('status') or (item.get('manifest') or {}).get('status')
        if status in QUALIFIED_STATUSES:
            qualified.append(item.get('experiment_id')
                             or (item.get('manifest') or {}).get('experiment_id'))
    return qualified


def counts(state, *, experiments=()):
    """The five populations, each independently sourced.

    Only one derivation is performed, and only when the session recorded both of
    its inputs: everything the guard did not reject was statically valid.
    Anything else the session did not count stays None, because a plausible
    arithmetic identity is not a measurement.
    """
    counters = state.get('counters') or {}
    generated = counters.get('generated')
    valid = counters.get('statically_valid')
    if valid is None and generated is not None and counters.get('static_rejected') is not None:
        valid = generated - counters['static_rejected']
    diagnostic = counters.get('diagnostic_admitted', counters.get('diagnostic'))
    attempts = counters.get('hardware_attempts')
    if attempts is None:
        # S1 is the first stage that loads a model on the device, so one S1
        # outcome is one candidate that reached hardware.
        attempts = counters.get('S1')
    return {GENERATED_CANDIDATES: generated,
            STATICALLY_VALID_CANDIDATES: valid,
            DIAGNOSTIC_CANDIDATES: diagnostic,
            HARDWARE_ATTEMPTS: attempts,
            QUALIFIED_EXPERIMENTS: len(qualified_experiments(experiments))}


def families_explored(state):
    """Per-family orchestration record, in the order the session touched them."""
    explored = []
    for name, record in (state.get('families') or {}).items():
        record = record if isinstance(record, dict) else {}
        explored.append({'family': name,
                         'attempted': record.get('attempted'),
                         'survived_s2': record.get('survived_s2'),
                         'survived_s3': record.get('survived_s3'),
                         'dev35_wins': record.get('dev35_wins'),
                         'confirmed_wins': record.get('confirmed_wins'),
                         'hardware_seconds_spent': record.get('hardware_seconds_spent')})
    return explored


def session_summary(state, *, started_at, finished_at, initial_control, final_control,
                    experiments=(), heldout_evaluation=None):
    """Build the session summary dict.

    ``initial_control`` and ``final_control`` are control records, optionally
    carrying a ``kpi`` block from the tracker. Success, correct cases, invalid
    count, median task latency, p95 and failure taxonomy are copied when present
    and are None otherwise. A zero is never substituted for an absent figure,
    and a control with no KPI block reports measured=False rather than a row of
    zeros.

    ``heldout_evaluation`` is absent from the output unless it is passed here.
    Only scripts/autotune_final.py may supply it: the heldout 15 are unreachable
    from the optimization loop, so a summary written by the loop that contained a
    heldout figure would either be a leak or an invention. Passing it records
    that a separate, explicitly heldout evaluation produced those numbers.
    """
    timing = state.get('timing') or {}
    counters = state.get('counters') or {}
    busy, idle = timing.get('hardware_busy_s'), timing.get('hardware_idle_s')
    summary = {
        'schema_version': SCHEMA,
        'session_id': state.get('session_id'),
        'backend': state.get('backend'),
        'split': state.get('split'),
        'started_at': started_at,
        'finished_at': finished_at,
        'duration_seconds': _duration_seconds(started_at, finished_at),
        'counts': counts(state, experiments=experiments),
        'count_meanings': dict(COUNT_MEANINGS),
        'qualified_experiment_ids': qualified_experiments(experiments),
        'families_explored': families_explored(state),
        'hardware_busy_seconds': busy,
        'hardware_idle_seconds': idle,
        'hardware_utilisation_pct': utilisation(busy, idle),
        'api_calls': counters.get('api_calls'),
        'api_seconds': timing.get('api_wait_s'),
        'promotions': counters.get('promotions'),
        'initial_control': control_view(initial_control),
        'final_control': control_view(final_control),
        'energy_commissioned': bool(state.get('energy_commissioned')),
        'energy_note': 'Energy is not commissioned; no candidate was ranked, selected or described by energy.',
    }
    if heldout_evaluation is not None:
        if not isinstance(heldout_evaluation, dict):
            raise TypeError('heldout_evaluation must be an object describing a separate evaluation')
        summary['heldout_evaluation'] = dict(heldout_evaluation)
    return summary


def _identity(value):
    """A name or an id that was never recorded is unknown, not 'not measured'."""
    return 'unknown' if value in (None, '') else str(value)


def _figure(value, unit=''):
    if value is None:
        return NOT_MEASURED
    if isinstance(value, float):
        return ('%.1f' % value) + unit
    return str(value) + unit


def render_markdown(summary):
    """Human-readable summary. The five counts stay five separate rows."""
    counts_block = summary.get('counts') or {}
    lines = ['# Autotune session ' + str(summary.get('session_id') or 'unknown'),
             '',
             'Backend: ' + str(summary.get('backend') or 'unknown')
             + ' | split: ' + str(summary.get('split') or 'unknown')
             + ' | duration: ' + _figure(summary.get('duration_seconds'), ' s'),
             '',
             '## Populations',
             '',
             'These are five different things. A generated candidate is a configuration, not a',
             'test, not a run and not an experiment. Only QUALIFIED_EXPERIMENTS is measured evidence.',
             '',
             '| population | count | meaning |',
             '| --- | --- | --- |']
    for name in COUNT_NAMES:
        lines.append('| ' + name + ' | ' + _figure(counts_block.get(name)) + ' | '
                     + COUNT_MEANINGS[name] + ' |')
    ids = summary.get('qualified_experiment_ids') or []
    lines += ['', 'Qualified archives: ' + (', '.join(str(i) for i in ids) if ids else 'none'), '',
              '## Session cost', '',
              '- Hardware busy: ' + _figure(summary.get('hardware_busy_seconds'), ' s'),
              '- Hardware idle: ' + _figure(summary.get('hardware_idle_seconds'), ' s'),
              '- Hardware utilisation: ' + _figure(summary.get('hardware_utilisation_pct'), ' %'),
              '- API calls: ' + _figure(summary.get('api_calls')),
              '- API time: ' + _figure(summary.get('api_seconds'), ' s'),
              '- Promotions: ' + _figure(summary.get('promotions')),
              '', '## Families explored', '']
    families = summary.get('families_explored') or []
    if not families:
        lines.append('None recorded.')
    else:
        lines += ['| family | attempted | survived S2 | survived S3 | dev35 wins | confirmed wins | hardware s |',
                  '| --- | --- | --- | --- | --- | --- | --- |']
        for record in families:
            lines.append('| ' + str(record.get('family')) + ' | '
                         + ' | '.join(_figure(record.get(key)) for key in
                                      ('attempted', 'survived_s2', 'survived_s3', 'dev35_wins',
                                       'confirmed_wins', 'hardware_seconds_spent')) + ' |')
    lines += ['', '## Control, initial versus final', '',
              '| field | initial | final |', '| --- | --- | --- |']
    initial, final = summary.get('initial_control') or {}, summary.get('final_control') or {}
    for label, key in (('name', 'name'), ('experiment id', 'experiment_id')):
        lines.append('| ' + label + ' | ' + _identity(initial.get(key)) + ' | '
                     + _identity(final.get(key)) + ' |')
    rows = (('success %', 'success_rate_pct'), ('correct cases', 'correct_cases'),
            ('attempted cases', 'attempted_cases'), ('invalid outputs', 'invalid_count'),
            ('median task latency ms', 'median_task_latency_ms'),
            ('p95 task latency ms', 'p95_task_latency_ms'))
    for label, key in rows:
        lines.append('| ' + label + ' | ' + _figure(initial.get(key)) + ' | ' + _figure(final.get(key)) + ' |')
    lines.append('| failure taxonomy | ' + _taxonomy(initial.get('failure_taxonomy'))
                 + ' | ' + _taxonomy(final.get('failure_taxonomy')) + ' |')
    lines += ['', str(summary.get('energy_note') or '')]
    if 'heldout_evaluation' in summary:
        lines += ['', '## Heldout evaluation', '',
                  'Supplied explicitly by a final evaluation, not by the optimization loop.', '',
                  '```json', json.dumps(summary['heldout_evaluation'], indent=2, sort_keys=True), '```']
    else:
        lines += ['', 'Heldout 15: not evaluated here. The optimization loop cannot reach those cases.']
    return '\n'.join(lines) + '\n'


def _taxonomy(value):
    if not isinstance(value, dict) or not value:
        return NOT_MEASURED
    return ', '.join(str(k) + '=' + str(v) for k, v in sorted(value.items()))


def write_summary(summary, directory):
    """Write session-summary.md and .json, refusing to overwrite another session.

    A summary directory belongs to one session. Overwriting the summary of a
    different session would destroy the only orchestration record that session
    left behind, so a mismatch is an error rather than a silent replacement.
    """
    session_id = summary.get('session_id')
    if not session_id:
        raise ValueError('Summary carries no session_id; refusing to write an unattributable summary')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / (MEASUREMENT_FILE + '.json')
    md_path = directory / (MEASUREMENT_FILE + '.md')

    if json_path.exists():
        existing = parse_json(json_path.read_bytes(), require_object=True).get('session_id')
        if existing != session_id:
            raise ValueError('Refusing to overwrite the summary of session ' + repr(existing)
                             + ' with session ' + repr(session_id) + ' in ' + str(directory))
    elif md_path.exists():
        raise ValueError('A session-summary.md exists in ' + str(directory) + ' with no JSON beside '
                         'it, so its session cannot be identified; refusing to overwrite it')

    atomic(json_path, json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
    atomic(md_path, render_markdown(summary).encode('utf-8'))
    return md_path, json_path
