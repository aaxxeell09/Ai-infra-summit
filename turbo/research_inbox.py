"""Offline append-only research triage. Findings are never executable jobs."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from datetime import datetime, timezone

from turbo.experiments import archive_lock, fsync_directory, read_json

STATUSES = frozenset({
    'NEW_EXPERIMENT', 'SUPPORTS_EXISTING_EXPERIMENT', 'ALREADY_TESTED',
    'NOT_AVAILABLE', 'LOW_PRIORITY', 'REQUIRES_PROTOCOL_OR_CODE_CHANGE',
})
INITIAL_REASON = 'Unclassified; explicit triage required before planner'
FIELDS = frozenset({'finding_id', 'title', 'technique', 'mechanism', 'source',
                   'stack_compatibility', 'expected_impact', 'confidence', 'implementation_cost'})


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text')
    return value.strip()


def _finding(value):
    if not isinstance(value, dict) or not FIELDS <= value.keys():
        raise ValueError('Finding requires: ' + ', '.join(sorted(FIELDS)))
    if value.keys() - FIELDS - {'hardware_cost_estimate'}:
        raise ValueError('Unknown finding fields')
    result = {key: _text(item, key) for key, item in value.items() if key != 'hardware_cost_estimate'}
    estimate = value.get('hardware_cost_estimate')
    result['hardware_cost_estimate'] = None if estimate is None else _text(estimate, 'hardware_cost_estimate')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', result['finding_id']):
        raise ValueError('finding_id must be a portable slug')
    for key in ('expected_impact', 'confidence'):
        if result[key] not in {'HIGH', 'MED', 'LOW'}:
            raise ValueError(f'{key} must be HIGH, MED or LOW')
    return result


def _normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split()).rstrip('.!?')


def _fingerprint(finding):
    # Conservative near-duplicate identity: trailing prose punctuation, case and whitespace only.
    # Preserve numeric signs and operators. Do not conflate different mechanisms or stacks based on vague similarity.
    material = [_normalized(finding[key]) for key in ('technique', 'mechanism', 'stack_compatibility')]
    return hashlib.sha256(json.dumps(material).encode()).hexdigest()


def _exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()
    fd, temporary = tempfile.mkstemp(prefix='.research-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic publication; refuses existing destination.
        fsync_directory(path.parent)
    finally:
        os.unlink(temporary)


def _load(root):
    rows = {}
    paths = sorted((Path(root) / 'events').glob('*.json'))
    for sequence, path in enumerate(paths, 1):
        if path.name != f'{sequence:08d}.json' or path.is_symlink():
            raise ValueError('Invalid inbox journal sequence')
        event = read_json(path)
        if not isinstance(event, dict) or event.get('schema') != 'research-inbox-event-v1':
            raise ValueError('Unsupported inbox journal schema')
        if event.get('kind') == 'finding':
            row = _finding(event['finding'])
            identity = row['finding_id']
            if identity in rows:
                raise ValueError('Duplicate finding identity in journal')
            rows[identity] = dict(row, status='LOW_PRIORITY', classification_reason=INITIAL_REASON)
        elif event.get('kind') == 'classification':
            identity = event['finding_id']
            if identity not in rows or event['status'] not in STATUSES:
                raise ValueError('Invalid classification event')
            rows[identity].update(status=event['status'], classification_reason=_text(event['reason'], 'reason'))
        else:
            raise ValueError('Invalid inbox event kind')
    return rows, len(paths)


def _append(root, sequence, **event):
    _exclusive_json(Path(root) / 'events' / f'{sequence + 1:08d}.json', dict(
        schema='research-inbox-event-v1', at=datetime.now(timezone.utc).isoformat(), **event))


def add_finding(root, finding):
    finding = _finding(finding)
    with archive_lock(root, 'research-inbox'):
        rows, count = _load(root)
        for existing in rows.values():
            if existing['finding_id'] == finding['finding_id']:
                original = {key: existing[key] for key in existing if key not in {'status', 'classification_reason'}}
                if original != finding:
                    raise ValueError('finding_id already exists with different contents')
                return {'created': False, 'finding': existing}
        for existing in rows.values():
            if _fingerprint(existing) == _fingerprint(finding):
                return {'created': False, 'finding': existing}
        _append(root, count, kind='finding', finding=finding)
        return {'created': True, 'finding': dict(finding, status='LOW_PRIORITY', classification_reason=INITIAL_REASON)}


def list_findings(root):
    with archive_lock(root, 'research-inbox'):
        return list(_load(root)[0].values())


def classify_finding(root, finding_id, status, reason):
    if status not in STATUSES:
        raise ValueError('Unknown classification status')
    reason = _text(reason, 'reason')
    with archive_lock(root, 'research-inbox'):
        rows, count = _load(root)
        if finding_id not in rows:
            raise ValueError('Unknown finding_id')
        row = rows[finding_id]
        if row['status'] != status or row['classification_reason'] != reason:
            _append(root, count, kind='classification', finding_id=finding_id, status=status, reason=reason)
        return dict(row, status=status, classification_reason=reason)


def export_ready_ideas(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError('Export must be outside the inbox journal')
    rows = list_findings(root)
    result = {'schema': 'research-ideas-v1', 'status': 'READY', 'executable': False,
              'scope': 'development_planning_only',
              'ideas': [row for row in rows if row['status'] == 'NEW_EXPERIMENT']}
    _exclusive_json(output, result)
    return result
