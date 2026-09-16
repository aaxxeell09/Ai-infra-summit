"""Read-only development diagnostics. Never imported by the qualified runner."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from eval.scoring import digest, score
from eval.secretary_adapter import SecretaryAdapter, TOOLS
from turbo.json_io import read_json
from turbo.service import parse_calls

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT / 'eval/datasets/secretary_dev.json'
SCHEMA = 'local-turbo.clarify-diagnostic.v1'
PROMPT_SUFFIX = '''\nDiagnostic first-action contract: emit exactly one tool call. If a required
argument is absent, a file reference matches several inventory paths, the
requested operation is unsupported, a destination exists where overwrite is
forbidden, or constraints conflict, call clarify with
one nonempty question about the unresolved requirement. Do not guess a path,
destination or search query. Clarification is a tool call, not prose. Use
{"name":"clarify","arguments":{"question":"Which information is missing?"}}
as a syntax example only; ask a question relevant to the actual request.
If the first action is fully specified and supported, perform that action
instead of asking an unnecessary question. Stop after the first complete call.'''
CLARIFY_DESCRIPTION = ('Ask one nonempty question when required information is missing, '
    'a file reference is ambiguous, the operation is unsupported, or constraints '
    'cannot all be satisfied (including a forbidden overwrite). Do not act first or guess missing arguments. '
    'Use only when the first requested action cannot be determined safely.')


def development():
    cases = read_json(DEVELOPMENT)
    if not isinstance(cases, list) or any(c.get('split') != 'development' for c in cases):
        raise ValueError('Development-only cases required')
    return cases


def codec_and_files():
    files = read_json(ROOT / 'eval/fixtures/files.json')
    return SecretaryAdapter.from_files(files), files


def ambiguity_shadow(prompt, files):
    """Abstaining detector: only an entire 'Read BASENAME.' request is recognized.

    No golden labels, case IDs, prompt lookup table or filesystem actions.
    Anything involving qualifiers, paths, multiple clauses or unique names abstains.
    """
    match = re.fullmatch(r'\s*(?:read|open)\s+([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\.?\s*',
                         prompt, re.IGNORECASE)
    if not match:
        return {'decision': 'abstain', 'matches': []}
    basename = match.group(1)
    matches = sorted({p for p in files if p.rsplit('/', 1)[-1] == basename})
    if len(matches) < 2:
        return {'decision': 'abstain', 'matches': matches}
    return {'decision': 'would_clarify', 'matches': matches,
            'reason': 'bare basename has multiple exact inventory matches'}


def candidate(kind, codec):
    result = {'protocol': SCHEMA, 'lane': 'C', 'qualified': False,
              'promotion_evidence': False, 'kind': kind, 'executes_actions': False}
    if kind == 'prompt':
        result['system_prompt'] = codec.instructions() + PROMPT_SUFFIX
    elif kind == 'schema':
        tools = deepcopy(TOOLS)
        next(t['function'] for t in tools if t['function']['name'] == 'clarify')['description'] = CLARIFY_DESCRIPTION
        result['tools'] = tools
    elif kind == 'ambiguity-shadow':
        result['mechanism'] = 'Entire bare-basename read/open request with multiple exact inventory matches; otherwise abstain'
    else:
        raise ValueError('Unknown diagnostic candidate')
    result['candidate_sha256'] = digest(result)
    return result


def classify(case, raw, codec, profile=None):
    """Additional labels only; the original frozen parser/score is never repaired."""
    frozen = score(case, raw, codec)
    labels = []
    calls = parse_calls(raw) if isinstance(raw, str) else []
    if not isinstance(raw, str):
        labels.append('raw_output_unavailable')
    else:
        if len(calls) > 1:
            labels.append('multiple_actions')
        if raw.count('<tool_call>') != raw.count('</tool_call>'):
            labels.append('unbalanced_tool_call_tags')
        if frozen['parse_error']:
            labels.append('malformed_or_noncontract_output')
            if not calls and not any(token in raw for token in ('{', '<tool_call>', '```')):
                labels.append('plain_prose_instead_of_tool_call')
        for call in calls:
            function = call['function']
            if function['name'] == 'clarify':
                question = json.loads(function['arguments']).get('question')
                if not isinstance(question, str) or not question.strip():
                    labels.append('missing_or_empty_question')
        if calls and case['expected']['tool'] == 'clarify' and calls[0]['function']['name'] != 'clarify':
            labels.append('wrong_first_tool')
            if any(call['function']['name'] == 'clarify' for call in calls[1:]):
                labels.append('clarification_after_action')
    if 'FAILED_TO_CLARIFY' in frozen['failure_reasons']:
        labels.append('semantic_decision_failure')
    if 'UNNECESSARY_CLARIFICATION' in frozen['failure_reasons']:
        labels.append('unnecessary_clarification')
    stop = (profile or {}).get('stop_reason')
    if stop == 'length':
        labels.append('reported_length_stop')
    return {'labels': sorted(set(labels)), 'frozen_failure_reasons': frozen['failure_reasons'],
            'frozen_parse_error': frozen['parse_error'], 'frozen_action_only_success': frozen['task_success'],
            'first_parsed_tool': calls[0]['function']['name'] if calls else None,
            'parsed_call_count': len(calls), 'stop_reason': stop,
            'raw_utf8_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest() if isinstance(raw, str) else None}


def analyze_result(path, cases, codec):
    path = Path(path)
    data = read_json(path, require_object=True)
    rows = data.get('results', data.get('rows'))
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected nonempty result rows')
    index = {c['id']: c for c in cases}
    hashes = {digest(c): c for c in cases}
    bound = []
    seen = set()
    # Validate every identity before processing any outputs. Mixed/full results
    # are rejected rather than filtered down into a tuning input.
    for row in rows:
        identity = row.get('id', row.get('case_id'))
        case = index.get(identity) or hashes.get(identity)
        if case is None or row.get('split', 'development') != 'development':
            raise ValueError('Only development identities accepted; mixed results rejected')
        if case['id'] in seen:
            raise ValueError('Duplicate case identity')
        seen.add(case['id'])
        if row.get('case_sha256') not in (None, digest(case)):
            raise ValueError('Case hash mismatch')
        if row.get('prompt', case['prompt']) != case['prompt'] or row.get('expected', case['expected']) != case['expected']:
            raise ValueError('Case content mismatch')
        bound.append((case, row))
    analyzed = []
    for case, row in bound:
        raw = row.get('output_text', row.get('raw_output'))
        item = {'case_id': case['id'], 'case_sha256': digest(case),
                'expected_tool': case['expected']['tool'],
                'archived_failure_reasons': row.get('failure_reasons'),
                'archived_task_success': row.get('task_success'),
                'raw_output': raw,
                'analysis': classify(case, raw, codec, row.get('profile')) if raw is not None else None}
        analyzed.append(item)
    clarify = [r for r in analyzed if r['expected_tool'] == 'clarify']
    return {'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'input_path': str(path),
            'evaluator_sha256': data.get('evaluator_sha256'), 'dataset_sha256': data.get('dataset_sha256'),
            'config': {k: data.get('config', {}).get(k) for k in ('max_tokens', 'stop_after_tool_call')},
            'source_commit': data.get('git_commit'), 'rows': analyzed,
            'clarify_rows': len(clarify),
            'clarify_raw_available': sum(r['analysis'] is not None for r in clarify),
            'clarify_label_counts': dict(Counter(label for r in clarify if r['analysis']
                                                for label in r['analysis']['labels']))}


def report(paths=(), export_candidate=None):
    cases = development()
    codec, files = codec_and_files()
    shadow = [{'case_id': c['id'], 'expected_tool': c['expected']['tool'],
               **ambiguity_shadow(c['prompt'], files)} for c in cases]
    return {'schema_version': SCHEMA, 'lane': 'C', 'qualified': False,
            'promotion_evidence': False, 'inference_performed': False,
            'source': 'read_only_archived_outputs_and_development_static_analysis',
            'development_sha256': hashlib.sha256(DEVELOPMENT.read_bytes()).hexdigest(),
            'clarify_cases': [{k: c[k] for k in ('id', 'prompt', 'expected', 'rationale')}
                              for c in cases if c['expected']['tool'] == 'clarify'],
            'shadow_decisions': shadow,
            'results': [analyze_result(path, cases, codec) for path in paths],
            'candidate': candidate(export_candidate, codec) if export_candidate else None}
