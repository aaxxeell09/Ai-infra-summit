"""Offline development-only repetition plans. Never launch an experiment or model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .experiments import digest, read_json

SCHEMA = 'local-turbo.campaign-plan.v1'


def config_snapshot(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Config file missing: ' + str(path))
    raw = path.read_bytes()
    value = read_json(path)
    if not isinstance(value, dict) or not value:
        raise ValueError('Config must be a nonempty JSON object')
    return dict(path=str(path), byte_sha256=hashlib.sha256(raw).hexdigest(),
                semantic_sha256=digest(value), value=value)


def differences(left, right, prefix=''):
    """Exact changed JSON fields; arrays are one configuration field."""
    if isinstance(left, dict) and isinstance(right, dict):
        changed = []
        for key in sorted(set(left) | set(right)):
            path = prefix + '.' + key if prefix else key
            if key not in left or key not in right:
                changed.append(path)
            else:
                changed.extend(differences(left[key], right[key], path))
        return changed
    return [] if type(left) is type(right) and left == right else [prefix]


def plan(control_name, control_config, candidates, repetitions=3):
    """Rotate treatment positions across equal-sized blocks, >=3 trials each.

    Each candidate is {name, config, variable, hypothesis}. Exactly one JSON
    field may differ from the control. Cross-model/backend bundles needing
    several changed fields require a separately designed experiment, not a
    misleading single-variable label.
    """
    if type(repetitions) is not int or not 3 <= repetitions <= 1000:
        raise ValueError('repetitions must be an integer between 3 and 1000')
    if not isinstance(control_name, str) or not control_name.strip():
        raise ValueError('Control name required')
    if not candidates:
        raise ValueError('At least one candidate treatment is required')
    control = config_snapshot(control_config)
    treatments = [dict(name=control_name, role='control', config=control,
                       variable=None, hypothesis='Reference condition; no optimization claim')]
    names = {control_name}
    for candidate in candidates:
        name = candidate.get('name')
        hypothesis = candidate.get('hypothesis')
        variable = candidate.get('variable')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('Treatment names must be nonempty and unique')
        if not isinstance(hypothesis, str) or not hypothesis.strip():
            raise ValueError('Each candidate requires an explicit hypothesis')
        if not isinstance(variable, str) or not variable.strip():
            raise ValueError('Each candidate requires its single changed variable')
        snapshot = config_snapshot(candidate['config'])
        changed = differences(control['value'], snapshot['value'])
        if changed != [variable]:
            raise ValueError(f'{name}: expected only {variable!r} to change, found {changed}')
        names.add(name)
        treatments.append(dict(name=name, role='candidate', config=snapshot,
                               variable=variable, hypothesis=hypothesis))
    runs = []
    count = len(treatments)
    for block in range(repetitions):
        rotation = block % count
        ordered = treatments[rotation:] + treatments[:rotation]
        for position, treatment in enumerate(ordered, 1):
            runs.append(dict(run_order=len(runs) + 1, block_index=block + 1,
                             position_in_block=position, repetition=block + 1,
                             treatment=treatment['name'], control=control_name,
                             dataset='dev', config_path=treatment['config']['path'],
                             config_byte_sha256=treatment['config']['byte_sha256'],
                             variable=treatment['variable'], hypothesis=treatment['hypothesis']))
    result = dict(schema_version=SCHEMA, dataset='dev', control=control_name,
                  repetitions=repetitions, treatments=treatments, runs=runs,
                  methodology='One trial per treatment per block, cyclic position rotation. Counts are equal; position counts differ by at most one when the block count is not a multiple of treatment count.',
                  execution='OFFLINE_PLAN_ONLY: no processes, models or hardware launched',
                  qualification='No quality thresholds or winner implied. Failed attempts must remain visible; do not silently replace them with successful repetitions.')
    result['plan_sha256'] = digest(result)
    return result


def verify_plan(value):
    """Fail closed on altered plans, changed config bytes or changed schedule."""
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA or value.get('dataset') != 'dev':
        raise ValueError('Unsupported or non-development plan')
    unsigned = {key: item for key, item in value.items() if key != 'plan_sha256'}
    if value.get('plan_sha256') != digest(unsigned):
        raise ValueError('Campaign plan checksum mismatch')
    treatments = value.get('treatments')
    if not isinstance(treatments, list) or len(treatments) < 2:
        raise ValueError('Campaign treatments missing')
    controls = [t for t in treatments if t.get('role') == 'control']
    if len(controls) != 1 or controls[0]['name'] != value.get('control'):
        raise ValueError('Campaign control is inconsistent')
    for treatment in treatments:
        saved = treatment['config']
        current = config_snapshot(saved['path'])
        if current != saved:
            raise ValueError('Config drift detected: ' + treatment['name'])
    candidates = [dict(name=t['name'], config=t['config']['path'], variable=t['variable'], hypothesis=t['hypothesis'])
                  for t in treatments if t['role'] == 'candidate']
    rebuilt = plan(value['control'], controls[0]['config']['path'], candidates, value['repetitions'])
    if rebuilt != value:
        raise ValueError('Campaign schedule or metadata differs from deterministic plan')
    return dict(status='VERIFIED', trials=len(value['runs']), dataset='dev',
                execution='OFFLINE_PLAN_ONLY', plan_sha256=value['plan_sha256'])


def write_plan(path, value):
    path = Path(path).resolve()
    verify_plan(value)
    if any(path == Path(t['config']['path']) for t in value['treatments']):
        raise ValueError('Plan cannot overwrite an input config')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return path
