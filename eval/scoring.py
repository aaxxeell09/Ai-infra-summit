"""Deterministic first-action scoring against the real ActionCodec contract."""
import hashlib
import json
import math
import statistics
from pathlib import Path

TOOLS = {'read_file': 'r', 'list_files': 'l', 'search_files': 's',
         'move_file': 'm', 'clarify': 'q'}
ARGS = {'read_file': {'path'}, 'list_files': {'path'}, 'search_files': {'query'},
        'move_file': {'source', 'destination'}, 'clarify': set()}


def load_dataset(paths):
    cases = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('Dataset must be an array')
        cases.extend(data)
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str):
            raise ValueError('Invalid case')
        if case['id'] in ids:
            raise ValueError('Duplicate case ID')
        ids.add(case['id'])
        if case.get('split') not in {'development', 'heldout'} or not case.get('prompt') or not case.get('category'):
            raise ValueError('Missing case metadata')
        exp = case['expected']
        if exp.get('tool') not in TOOLS or type(exp.get('clarification_required')) is not bool:
            raise ValueError('Invalid expected tool/clarification')
        if exp['clarification_required'] != (exp['tool'] == 'clarify'):
            raise ValueError('Inconsistent clarification')
        if set(exp.get('arguments', {})) != ARGS[exp['tool']]:
            raise ValueError('Expected arguments do not match the real schema')
        if any(not isinstance(v, str) or not v.strip() for v in exp['arguments'].values()):
            raise ValueError('Invalid argument value')
    if not cases:
        raise ValueError('Empty dataset')
    return cases


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(value, key):
    # Preserve case and interior spaces in paths and search queries.
    # Only normalize Windows separators and a harmless explicit current directory.
    if key in {'path', 'source', 'destination'}:
        value = value.replace('\\', '/')
        while value.startswith('./'):
            value = value[2:]
    return value


def score(case, text, codec):
    expected = case['expected']
    actual, arguments, error = None, {}, None
    try:
        actual, arguments = codec.decode(text, snapshot_digest=codec.digest)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        error = type(exc).__name__
    tool_ok = actual == expected['tool']
    arguments_ok = actual is not None and all(
        k in arguments and normalize(arguments[k], k) == normalize(v, k)
        for k, v in expected['arguments'].items())
    clarification = actual == 'clarify'
    no_action_ok = actual is not None and clarification == expected['clarification_required']
    return {'id': case['id'], 'category': case['category'], 'split': case['split'],
            'tool': actual, 'action': TOOLS.get(actual), 'arguments': arguments,
            'clarification': clarification,
            'unnecessary_tool_call': actual is not None and not clarification and expected['clarification_required'],
            'tool_correct': tool_ok, 'action_correct': tool_ok,
            'arguments_correct': arguments_ok, 'no_action_correct': no_action_ok,
            'task_success': tool_ok and arguments_ok and no_action_ok,
            'parse_error': error}


def summarize(rows):
    if not rows:
        raise ValueError('Cannot summarize empty evaluation')
    n = len(rows)
    out = {'total_prompts': n, 'task_success': sum(r['task_success'] for r in rows)}
    for key, field in [('task_accuracy', 'task_success'), ('tool_accuracy', 'tool_correct'),
                       ('action_accuracy', 'action_correct'), ('argument_accuracy', 'arguments_correct'),
                       ('clarification_no_action_accuracy', 'no_action_correct')]:
        out[key] = 100 * sum(bool(r[field]) for r in rows) / n
    applicable = [r for r in rows if r.get('expected_tool') != 'clarify']
    out['argument_applicable_prompts'] = len(applicable)
    out['argument_accuracy_applicable'] = (100 * sum(r['arguments_correct'] for r in applicable) / len(applicable)) if applicable else None
    latency = sorted(r['latency_ms'] for r in rows)
    out.update(avg_latency_ms=statistics.mean(latency), median_latency_ms=statistics.median(latency),
               p95_latency_ms=latency[math.ceil(.95*n)-1] if n >= 20 else None,
               latency_samples=n, errors=sum(bool(r.get('execution_error')) for r in rows))
    out['categories'] = {c: {'total': len(group), 'task_success': sum(r['task_success'] for r in group),
                           'task_accuracy': 100*sum(r['task_success'] for r in group)/len(group),
                           'failures': [r['id'] for r in group if not r['task_success']]}
                         for c in sorted({r['category'] for r in rows})
                         for group in [[r for r in rows if r['category'] == c]]}
    return out


def compare(candidate, baseline, policy):
    reasons = []
    if not baseline or baseline.get('status') != 'measured':
        return {'status': 'NOT_EVALUATED', 'reasons': ['Measured baseline unavailable']}
    for key in ('fixture_sha256', 'protocol_version', 'evaluator_sha256', 'generation_protocol'):
        if candidate.get(key) != baseline.get(key):
            reasons.append('Incompatible ' + key)
    if reasons:
        return {'status': 'NOT_COMPARABLE', 'reasons': reasons}
    for key in ('max_accuracy_drop_points', 'max_category_drop_points'):
        value = policy[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid quality policy')
    before_rows = {r['id']: r for r in baseline['results']}
    selected = candidate['results']
    if len(selected) == len(before_rows) and candidate.get('dataset_sha256') != baseline.get('dataset_sha256'):
        return {'status':'NOT_COMPARABLE', 'reasons':['Dataset digest differs for a full comparison']}
    if any(r['id'] not in before_rows or r.get('case_sha256') != before_rows[r['id']].get('case_sha256') for r in selected):
        return {'status':'NOT_COMPARABLE', 'reasons':['Case IDs or expectations differ from baseline']}
    if candidate.get('dataset_sha256') != baseline.get('dataset_sha256') and not all(r.get('case_sha256') for r in selected):
        return {'status':'NOT_COMPARABLE', 'reasons':['Missing per-case provenance for subset comparison']}
    a = candidate['metrics']
    b = summarize([before_rows[r['id']] for r in selected])
    delta = a['task_accuracy'] - b['task_accuracy']
    if delta < -policy['max_accuracy_drop_points']:
        reasons.append('Overall accuracy drop exceeds policy')
    regressions = []
    for category, old in b['categories'].items():
        new = a['categories'][category]
        drop = old['task_accuracy'] - new['task_accuracy']
        if drop > 0:
            regressions.append({'category': category, 'drop_points': drop, 'failures': new['failures']})
        if drop > policy['max_category_drop_points']:
            reasons.append(category + ': category accuracy drop exceeds policy')
    before = {r['id']: r for r in baseline['results']}
    for row in candidate['results']:
        if (row['category'] in policy['critical_categories'] or row.get('expected_tool') in policy.get('critical_tools', [])) and before[row['id']]['task_success'] and not row['task_success']:
            reasons.append(row['id'] + ': critical task regressed')
    return {'status': 'FAIL' if reasons else 'PASS', 'reasons': reasons,
            'accuracy_delta_points': delta, 'category_regressions': regressions,
            'median_latency_change_pct': ((a['median_latency_ms']/b['median_latency_ms']-1)*100 if b['median_latency_ms'] else None),
            'compared_prompts': len(selected), 'policy': policy}
