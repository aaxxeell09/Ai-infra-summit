"""Deterministic action scoring against the actual Secretary tool schema."""
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

TOOLS = {'read_file': 'r', 'list_files': 'l', 'search_files': 's',
         'move_file': 'm', 'clarify': 'q'}
from eval.secretary_adapter import SCHEMAS
ARGS = {name:set(schema['required']) for name,schema in SCHEMAS.items()}
ARGS['clarify'] = set()


def load_dataset(paths):
    cases = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('Dataset must be an array')
        cases.extend(data)
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id'].strip():
            raise ValueError('Invalid case')
        if case['id'] in ids:
            raise ValueError('Duplicate case ID')
        ids.add(case['id'])
        if (case.get('split') not in {'development', 'heldout'} or not isinstance(case.get('prompt'),str)
                or not case['prompt'].strip() or not isinstance(case.get('category'),str) or not case['category'].strip()):
            raise ValueError('Missing case metadata')
        exp = case.get('expected')
        if not isinstance(exp,dict) or not isinstance(exp.get('arguments'),dict):
            raise ValueError('Missing golden expectation')
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
        if not isinstance(text,str) or len(text) > 65536:
            raise ValueError('Missing or oversized output')
        def unique_keys(pairs):
            result = {}
            for k,v in pairs:
                if k in result: raise ValueError('Duplicate output field')
                result[k] = v
            return result
        parts = re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>',text,re.S) or re.findall(r'```(?:json)?\s*(.*?)\s*```',text,re.S) or [text]
        for part in parts: json.loads(part, object_pairs_hook=unique_keys)
        actual, arguments = codec.decode(text, snapshot_digest=codec.digest)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        error = type(exc).__name__
    tool_ok = actual == expected['tool']
    arguments_ok = actual is not None and all(
        k in arguments and normalize(arguments[k], k) == normalize(v, k)
        for k, v in expected['arguments'].items())
    clarification = actual == 'clarify'
    no_action_ok = actual is not None and clarification == expected['clarification_required']
    failures = []
    if error:
        failures.append('PARSE_ERROR' if error == 'JSONDecodeError' else 'INVALID_OUTPUT')
    elif expected['clarification_required'] and not clarification:
        failures.append('FAILED_TO_CLARIFY')
    elif not expected['clarification_required'] and clarification:
        failures.append('UNNECESSARY_CLARIFICATION')
    elif not tool_ok:
        failures.append('WRONG_ACTION')
    elif not arguments_ok:
        for key,value in expected['arguments'].items():
            if key not in arguments or normalize(arguments[key],key) != normalize(value,key):
                failures.append({'source':'WRONG_SOURCE','destination':'WRONG_DESTINATION','path':'WRONG_SOURCE' if actual=='move_file' else 'WRONG_ARGUMENT'}.get(key,'WRONG_ARGUMENT'))
    return {'id': case['id'], 'difficulty':case.get('difficulty','unclassified'),
            'prompt':case['prompt'], 'expected':expected, 'failure_reasons':failures, 'category': case['category'], 'split': case['split'],
            'tool': actual, 'action': actual, 'arguments': arguments,
            'clarification': clarification, 'should_act': actual is not None and not clarification,
            'clarification_correct':no_action_ok, 'invalid_output': error is not None,
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
    task_latencies=[r.get('task_latency_ms',r['latency_ms']) for r in rows]
    out['avg_task_latency_ms']=statistics.mean(task_latencies)
    out['median_task_latency_ms']=statistics.median(task_latencies)
    latency = sorted(r['latency_ms'] for r in rows)
    out.update(avg_latency_ms=statistics.mean(latency), median_latency_ms=statistics.median(latency),
               p95_latency_ms=latency[math.ceil(.95*n)-1] if n >= 20 else None,
               latency_samples=n, errors=sum(bool(r.get('execution_error')) for r in rows))
    out['categories'] = {c: {'total': len(group), 'task_success': sum(r['task_success'] for r in group),
                           'task_accuracy': 100*sum(r['task_success'] for r in group)/len(group),
                           'failures': [r['id'] for r in group if not r['task_success']]}
                         for c in sorted({r['category'] for r in rows})
                         for group in [[r for r in rows if r['category'] == c]]}
    out['failed_tasks'] = n - out['task_success']
    out['invalid_output_rate'] = sum(bool(r.get('invalid_output',r.get('parse_error'))) for r in rows)/n
    out['parse_failure_rate'] = sum('PARSE_ERROR' in r.get('failure_reasons',[]) for r in rows)/n
    clarify_rows = [r for r in rows if r.get('expected_tool',r.get('expected',{}).get('tool')) == 'clarify']
    out['clarification_prompts'] = len(clarify_rows)
    out['clarification_accuracy'] = (100*sum(r['no_action_correct'] for r in clarify_rows)/len(clarify_rows)) if clarify_rows else None
    out['difficulties'] = {level:{'total':len(group),'task_success':sum(r['task_success'] for r in group),
                                 'task_accuracy':100*sum(r['task_success'] for r in group)/len(group)}
                           for level in sorted({r.get('difficulty','unclassified') for r in rows})
                           for group in [[r for r in rows if r.get('difficulty','unclassified')==level]]}
    out['actions'] = {tool:{'total':len(group),'task_success':sum(r['task_success'] for r in group),
                           'task_accuracy':100*sum(r['task_success'] for r in group)/len(group)}
                      for tool in sorted({r.get('expected_tool',r.get('expected',{}).get('tool','unknown')) for r in rows})
                      for group in [[r for r in rows if r.get('expected_tool',r.get('expected',{}).get('tool','unknown'))==tool]]}
    return out


def compare(candidate, baseline, policy):
    reasons = []
    if not baseline or baseline.get('status') != 'measured':
        return {'status': 'NOT_EVALUATED', 'reasons': ['Measured baseline unavailable']}
    approval = baseline.get('baseline_approval') or {}
    if (baseline.get('type') != 'baseline' or baseline.get('dirty') is not False
            or not isinstance(approval,dict) or approval.get('status') != 'confirmed'
            or approval.get('confirmed_by') != 'Henry'
            or not baseline.get('git_commit') or approval.get('application_commit') != baseline.get('git_commit')
            or not baseline.get('config_sha256') or approval.get('config_sha256') != baseline.get('config_sha256')):
        return {'status':'NOT_EVALUATED','reasons':['Reference is not an approved clean official baseline']}
    for report in [candidate,baseline]:
        for key in ('benchmark_version','protocol_version','fixture_sha256','action_schema_sha256','evaluator_sha256','generation_protocol','dataset_sha256','git_commit','config_sha256','model_sha256'):
            if not report.get(key):
                return {'status':'NOT_COMPARABLE','reasons':['Missing provenance: '+key]}
    for key in ('fixture_sha256', 'protocol_version', 'evaluator_sha256', 'generation_protocol', 'benchmark_version', 'action_schema_sha256', 'system_prompt_sha256'):
        if candidate.get(key) != baseline.get(key):
            reasons.append('Incompatible ' + key)
    if reasons:
        return {'status': 'NOT_COMPARABLE', 'reasons': reasons}
    for key in ('max_accuracy_drop_points', 'max_category_drop_points'):
        value = policy[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid quality policy')
    if candidate.get('status') != 'measured':
        return {'status':'NOT_EVALUATED','reasons':['Candidate is not a measured run']}
    before_rows = {r['id']: r for r in baseline['results']}
    selected = candidate['results']
    if len(selected) == len(before_rows) and candidate.get('dataset_sha256') != baseline.get('dataset_sha256'):
        return {'status':'NOT_COMPARABLE', 'reasons':['Dataset digest differs for a full comparison']}
    if any(r['id'] not in before_rows or r.get('case_sha256') != before_rows[r['id']].get('case_sha256') for r in selected):
        return {'status':'NOT_COMPARABLE', 'reasons':['Case IDs or expectations differ from baseline']}
    if candidate.get('dataset_sha256') != baseline.get('dataset_sha256') and not all(r.get('case_sha256') for r in selected):
        return {'status':'NOT_COMPARABLE', 'reasons':['Missing per-case provenance for subset comparison']}
    if not selected or len({r['id'] for r in selected}) != len(selected):
        return {'status':'NOT_COMPARABLE','reasons':['Empty or duplicate candidate cases']}
    a = summarize(selected)
    b = summarize([before_rows[r['id']] for r in selected])
    delta = a['task_accuracy'] - b['task_accuracy']
    if delta < -policy['max_accuracy_drop_points']:
        reasons.append('Overall accuracy drop exceeds policy')
    max_invalid = policy.get('max_invalid_action_rate', 0.02)
    max_invalid_increase = policy.get('max_invalid_action_increase_points', 2)
    max_clarify_drop = policy.get('max_clarification_drop_points', 0)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v < 0 for v in [max_invalid,max_invalid_increase,max_clarify_drop]) or max_invalid > 1:
        raise ValueError('Invalid invalid-output/clarification policy')
    if a['invalid_output_rate'] > max_invalid:
        reasons.append('Invalid output rate exceeds absolute limit')
    if (a['invalid_output_rate']-b['invalid_output_rate'])*100 > max_invalid_increase:
        reasons.append('Invalid output rate increase exceeds policy')
    if b['clarification_accuracy'] is not None and a['clarification_accuracy'] < b['clarification_accuracy']-max_clarify_drop:
        reasons.append('Clarification accuracy drop exceeds policy')
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
            'baseline_metrics':b, 'candidate_metrics':a,
            'invalid_output_delta_points':100*(a['invalid_output_rate']-b['invalid_output_rate']),
            'compared_prompts': len(selected), 'policy': policy}
