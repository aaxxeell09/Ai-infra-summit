"""Append-only experiment planning/evidence index; never a qualification authority."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from turbo.experiments import archive_lock, fsync_directory, now
from turbo.json_io import read_json

SCHEMA = 'turbolab.experiment-registry.v1'
STATUSES = ('DISCOVERED', 'READY', 'RUNNING', 'OBSERVED', 'REPEAT_NEEDED',
            'REJECTED', 'PROMOTED', 'COMBINATION_READY', 'CONFIRMED', 'FINALIST')
METRICS = ('correctness', 'invalid_rate', 'latency_ms', 'ttft_ms',
           'decode_tokens_per_second', 'energy_j', 'memory_bytes')
REQUIRED = {'node_id', 'parent_ids', 'config_hash', 'code_sha', 'protocol_version',
            'hypothesis', 'stage', 'status', 'decision', 'decision_reason'}
OPTIONAL = {'event_id', 'evidence_paths', 'control_ids', 'repeat_count', 'metrics', 'metric_boundaries'}


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _strings(value, name):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(name + ' must be a list of nonempty strings')
    if len(set(value)) != len(value):
        raise ValueError(name + ' contains duplicates')
    return value


def _validate(event):
    if not isinstance(event, dict) or not REQUIRED <= event.keys() or event.keys() - REQUIRED - OPTIONAL:
        raise ValueError('Event must contain required fields and only documented optional fields')
    value = json.loads(_bytes(event))
    if 'event_id' in value and (not isinstance(value['event_id'], str) or not value['event_id'].strip()):
        raise ValueError('event_id must be a nonempty string')
    for name in REQUIRED - {'parent_ids'}:
        if not isinstance(value[name], str) or not value[name].strip():
            raise ValueError(name + ' must be a nonempty string')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value['node_id']):
        raise ValueError('Invalid node_id')
    for name, length in (('config_hash', 64), ('code_sha', 40)):
        if not re.fullmatch('[0-9a-f]{' + str(length) + '}', value[name]):
            raise ValueError(name + ' must be a complete lowercase SHA')
    if value['stage'] not in ('S1','S2','S3','S4','S5') or value['status'] not in STATUSES:
        raise ValueError('Unknown stage/status')
    for name in ('parent_ids', 'evidence_paths', 'control_ids'):
        value[name] = _strings(value.get(name, []), name)
    if value['node_id'] in value['parent_ids']:
        raise ValueError('A node cannot parent itself')
    repeat = value.setdefault('repeat_count', None)
    if repeat is not None and (type(repeat) is not int or repeat < 0):
        raise ValueError('repeat_count must be a nonnegative integer or null')
    metrics = value.setdefault('metrics', {})
    if not isinstance(metrics, dict) or metrics.keys() - set(METRICS):
        raise ValueError('Unknown metrics')
    for name in METRICS:
        number = metrics.setdefault(name, None)
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number < 0):
            raise ValueError('Metrics must be finite nonnegative numbers or null')
        if name in ('correctness','invalid_rate') and number is not None and number > 1:
            raise ValueError('Correctness and invalid_rate are fractions')
    boundaries = value.setdefault('metric_boundaries', {})
    if not isinstance(boundaries, dict) or boundaries.keys() - set(METRICS):
        raise ValueError('Unknown metric boundaries')
    for name, boundary in boundaries.items():
        if not isinstance(boundary, str) or not boundary.strip():
            raise ValueError('Metric boundaries must be nonempty descriptions')
    if any(metrics[name] is not None and name not in boundaries for name in METRICS):
        raise ValueError('Every observed metric needs an explicit boundary')
    return value


def _read_unlocked(root):
    events, latest, previous = [], {}, None
    directory = root / 'events'
    if directory.is_symlink():
        raise ValueError('Event directory symlinks are unsupported')
    for index, path in enumerate(sorted(directory.glob('*.json')), 1):
        if path.name != f'{index:012d}.json' or path.is_symlink():
            raise ValueError('Registry sequence gap or unsupported event path')
        envelope = read_json(path, require_object=True)
        if set(envelope) != {'schema_version','sequence','previous_sha256','recorded_at','event','sha256','qualified'}:
            raise ValueError('Malformed registry envelope')
        unsigned = {k:v for k,v in envelope.items() if k != 'sha256'}
        if (envelope['schema_version'] != SCHEMA or type(envelope['sequence']) is not int
                or envelope['sequence'] != index or envelope['previous_sha256'] != previous
                or envelope['qualified'] is not False or not isinstance(envelope['recorded_at'], str)
                or _digest(unsigned) != envelope['sha256']):
            raise ValueError('Registry hash chain or envelope mismatch')
        event = _validate(envelope['event'])
        _lineage(event, latest)
        latest[event['node_id']] = event
        events.append(envelope)
        previous = envelope['sha256']
    return events


def _lineage(event, latest):
    if any(parent not in latest for parent in event['parent_ids']):
        raise ValueError('Parents must already exist in this registry')
    old = latest.get(event['node_id'])
    if old and any(event[key] != old[key] for key in ('parent_ids','config_hash','code_sha','protocol_version','hypothesis')):
        raise ValueError('Node identity is immutable; create a child for a changed treatment')


def read_events(root):
    """Validate every immutable event; refuse corruption instead of skipping it."""
    root = Path(root)
    with archive_lock(root, 'registry'):
        return _read_unlocked(root)


def append_event(root, event):
    """Append a full node snapshot. Status is declared, never qualification proof."""
    event = _validate(event)
    root = Path(root)
    with archive_lock(root, 'registry'):
        history = _read_unlocked(root)
        if event.get('event_id') is not None:
            for prior in history:
                if prior['event'].get('event_id') == event['event_id']:
                    if prior['event'] != event:
                        raise ValueError('Conflicting event_id reuse')
                    return prior
        _lineage(event, {e['event']['node_id']:e['event'] for e in history})
        envelope = {'schema_version':SCHEMA, 'sequence':len(history)+1,
                    'previous_sha256':history[-1]['sha256'] if history else None,
                    'recorded_at':now(), 'event':event, 'qualified':False}
        envelope['sha256'] = _digest(envelope)
        directory = root / 'events'
        directory.mkdir(exist_ok=True)
        fsync_directory(root)
        destination = directory / f'{len(history)+1:012d}.json'
        descriptor, temporary = tempfile.mkstemp(prefix='.pending-', dir=directory)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(_bytes(envelope) + b'\n'); stream.flush(); os.fsync(stream.fileno())
            # Hard-link publication is atomic and fails if destination exists.
            # Unlike replace(), it can never overwrite a historical event.
            os.link(temporary, destination)
            fsync_directory(directory)
        finally:
            os.unlink(temporary)
        return envelope


def current_frontier(root):
    """Latest snapshots with actionable statuses; all declarations remain unqualified."""
    latest = {}
    for envelope in read_events(root):
        latest[envelope['event']['node_id']] = envelope
    return [latest[key] for key in sorted(latest)
            if latest[key]['event']['status'] not in ('REJECTED','PROMOTED','CONFIRMED')]
