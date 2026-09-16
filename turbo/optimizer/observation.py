"""Read a sealed archive and normalise it into one comparable observation.

The tracker is the authority on what was measured. This module only reads: it
opens a sealed archive, verifies it, and projects the evidence into the shape
the funnel compares. It never writes into an archive, never recomputes a score,
and never fills a missing field.

Failing closed matters more here than anywhere else in TurboLab. An observation
with an invented latency or a guessed case count would flow straight into a
promotion decision, so a missing field produces ``evidence_complete=False`` with
the reason, and every rule above treats that as unable to clear its gate rather
than as a pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import kpis, read_json, rows_of, verify

SCHEMA = 'local-turbo.autotune-observation.v1'

#: Manifest statuses that mean a clean, reproducible measurement. Anything else
#: is preserved evidence but not a qualified result, and the distinction has to
#: survive into the observation or a report will overstate what it has.
QUALIFIED_STATUSES = ('completed_qualified',)
MEASURED_STATUSES = ('completed_qualified', 'completed_diagnostic')

#: Fields a stage rule needs. A rule cannot compare what is not here, so their
#: absence is recorded rather than defaulted.
REQUIRED = ('attempted', 'correct', 'invalid', 'invalid_rate', 'rows', 'median_task_latency_ms')


class ArchiveEvidenceMissing(ValueError):
    """The archive exists but does not carry what a comparison needs."""


def case_identity(row):
    """Stable per-case key. Never an index: row order is not a case identity."""
    for key in ('case_id', 'case_sha256', 'id'):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def normalise_rows(report):
    """Case-level success, keyed by identity, or a reason it cannot be read."""
    try:
        raw = rows_of(report)
    except ValueError as exc:
        raise ArchiveEvidenceMissing('Archived result rows are unusable: ' + str(exc)) from exc
    rows, seen = [], set()
    for row in raw:
        identity = case_identity(row)
        if identity is None:
            raise ArchiveEvidenceMissing('An archived case row carries no case identity')
        if identity in seen:
            raise ArchiveEvidenceMissing('Duplicate case identity in the archived result: ' + identity)
        seen.add(identity)
        rows.append({'case_id': identity, 'task_success': row['task_success'],
                     'invalid_output': row.get('invalid_output'),
                     'expected_tool': row.get('expected_tool'),
                     'failure_reasons': list(row.get('failure_reasons') or [])})
        if row.get('case_sha256'):rows[-1]['case_sha256']=row['case_sha256']
    return rows


def from_archive(path, *, stage, hardware_seconds=None, verify_archive=True):
    """Project a sealed archive into one observation. Read only, fail closed.

    ``verify_archive`` is on by default because an unverified archive could have
    been edited after sealing, and an observation built from edited evidence is
    worse than no observation at all.
    """
    path = Path(path)
    record = {'schema_version': SCHEMA, 'stage': stage, 'archive': str(path),
              'archive_id': path.name.split('_', 1)[0], 'simulated': False,
              'hardware_seconds': hardware_seconds, 'evidence_complete': False,
              'missing': [], 'outcome': 'unknown'}
    if verify_archive:
        errors = verify(path)
        if errors:
            record['missing'].append('Archive verification failed: ' + '; '.join(errors[:3]))
            record['outcome'] = 'failed'
            return record
    try:
        manifest = read_json(path / 'manifest.json')
        report = read_json(path / 'result.json')
    except (OSError, ValueError) as exc:
        record['missing'].append('Archive is unreadable: ' + str(exc))
        record['outcome'] = 'failed'
        return record

    status = manifest.get('status') if isinstance(manifest, dict) else None
    record['tracker_status'] = status
    record['qualified'] = status in QUALIFIED_STATUSES
    record['experiment_id'] = (manifest or {}).get('experiment_id')
    if status not in MEASURED_STATUSES:
        record['missing'].append('Tracker status is ' + repr(status) + ', not a measured result')
        record['outcome'] = 'failed' if status in ('failed', 'incomplete') else 'timeout' \
            if status == 'timeout' else 'unknown'
        return record

    try:
        rows = normalise_rows(report)
    except ArchiveEvidenceMissing as exc:
        record['missing'].append(str(exc))
        record['outcome'] = 'failed'
        return record

    telemetry = None
    telemetry_path = path / 'telemetry.json'
    if telemetry_path.is_file():
        try:
            telemetry = read_json(telemetry_path)
        except (OSError, ValueError):
            telemetry = None
    # The tracker already computed these from the same rows. Recomputing them
    # here would create a second definition of the primary KPIs, which is
    # exactly the divergence the audit warned about, so they are read.
    metric = (manifest.get('primary_kpis') if isinstance(manifest.get('primary_kpis'), dict)
              else kpis(report, telemetry))

    record.update(
        protocol_version=report.get('protocol_version'),
        rows=rows,
        attempted=metric.get('total_tasks'),
        correct=metric.get('correct_tasks'),
        invalid=metric.get('invalid_count'),
        invalid_rate=metric.get('invalid_rate'),
        median_task_latency_ms=metric.get('median_e2e_ms'),
        latency_boundary=metric.get('latency_boundary'),
        latency_unavailable_reason=metric.get('latency_unavailable_reason'),
        success_rate_pct=metric.get('success_rate_pct'),
        error_taxonomy=metric.get('error_taxonomy'),
        # Energy is carried verbatim and never used to rank anything. It is here
        # so a session record is complete, not so a decision can read it.
        energy_comparable=False,
        gross_sys_j=metric.get('gross_sys_j'),
        energy_qualification=metric.get('energy_qualification'))

    missing = [name for name in REQUIRED if record.get(name) is None]
    if record.get('rows') == []:
        missing.append('rows')
    if record.get('latency_boundary') is None and record.get('median_task_latency_ms') is not None:
        missing.append('latency_boundary')
    record['missing'].extend('Archived evidence lacks ' + name for name in sorted(set(missing)))
    record['evidence_complete'] = not record['missing']
    record['outcome'] = 'completed' if record['evidence_complete'] else 'incomplete_evidence'
    return record


def latency_gate(observation, control, *, multiple=1.15):
    """Explicit pass, explicit fail, or None when either side is unknown.

    None is deliberate and is not a pass: the selector refuses a promotion whose
    latency gate is not an explicit True, so an unknown latency blocks rather
    than waves through.
    """
    observed = (observation or {}).get('median_task_latency_ms')
    baseline = (control or {}).get('median_task_latency_ms')
    if observed is None or baseline is None:
        return None
    if (observation or {}).get('latency_boundary') != (control or {}).get('latency_boundary'):
        # Two different boundaries are two different quantities. Comparing them
        # would be the exact substitution the tracking audit ruled out.
        return None
    return observed <= baseline * multiple


def annotate_gates(observation, control, *, multiple=1.15):
    """Attach the gate results a stage rule and the selector both read."""
    if not isinstance(observation, dict):
        return observation
    observation['latency_gate_ok'] = latency_gate(observation, control, multiple=multiple)
    observation.setdefault('deterministic_output', None)
    return observation
