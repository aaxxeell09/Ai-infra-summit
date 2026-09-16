"""Why a candidate won or lost, case by case, before any model is consulted.

A net score tells you a treatment moved two cases. It does not tell you that it
fixed three clarify cases and broke one move_file case, which is the difference
between a promotion and a regression nobody noticed until the heldout run. So
the arithmetic lives here, in plain Python, and it is the only source of numbers
in this module.

The optional narration at the bottom hands an already-computed analysis to a
model and asks for labels. The model never produces a metric.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import taxonomy
from turbo.optimizer.llm import (RESERVED_KEYS, LLMProtocolError, call_json, require,
                                 require_keys, require_text, response_meta)

SCHEMA = 'local-turbo.autotune-analysis.v1'

FIXED = 'fixed'
BROKEN = 'broken'
UNCHANGED_PASS = 'unchanged_pass'
UNCHANGED_FAIL = 'unchanged_fail'

CLUSTER_KEYS = ('label', 'cases', 'likely_mechanism')
ADVICE_KEYS = ('family', 'direction', 'why')
DIRECTIONS = ('more', 'less')

SYSTEM_PROMPT = (
    'You are labelling an already-computed case-level analysis of one configuration experiment. '
    'Every number in the payload was computed by a deterministic analyzer. You must not produce, '
    'restate as new, estimate or contradict any number: name the clusters and say what runtime '
    'mechanism would explain them.\n'
    'Only use case identifiers that appear in the payload.\n'
    'Answer with a single JSON object and nothing else, no prose and no code fence:\n'
    '{"clusters":[{"label":str,"cases":[str],"likely_mechanism":str}],'
    '"budget_advice":{"family":str,"direction":"more"|"less","why":str}}'
)


def case_id(row):
    """The case identity, accepting every spelling the repository uses.

    turbo.optimizer.statistics reads case_id or case_sha256, the frozen
    evaluator rows carry id, so both are honoured here and the rows handed to
    that module are normalised onto case_id before it sees them.
    """
    for key in ('case_id', 'id', 'case', 'case_sha256'):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError('Evaluator row carries no case identifier')


def expected_tool(row):
    value = row.get('expected_tool')
    if not isinstance(value, str) or not value:
        value = ((row.get('expected') or {}) if isinstance(row.get('expected'), dict) else {}).get('tool')
    return value if isinstance(value, str) and value else 'unknown'


def _by_case(rows, where):
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(where + ' must contain evaluator row objects')
        key = case_id(row)
        if key in indexed:
            raise ValueError(where + ' contains case ' + key + ' twice; a duplicate row makes the '
                             'pairing ambiguous rather than merely noisy')
        if type(row.get('task_success')) is not bool:
            raise ValueError(where + ' case ' + key + ' has no boolean task_success')
        indexed[key] = row
    return indexed


def _fallback_deltas(control_index, candidate_index):
    """The counts case_deltas would have produced, from a plain inner join.

    Temporary: turbo.optimizer.statistics owns this arithmetic and the variance
    handling around it. This exists only so the analyzer still works in an
    environment where that module cannot be imported, and it deliberately
    mirrors the same result keys so nothing downstream has to branch.
    """
    improved, regressed = [], []
    unchanged_correct = unchanged_incorrect = 0
    for key in sorted(set(control_index) & set(candidate_index)):
        verdict = classify(control_index[key], candidate_index[key])
        if verdict == FIXED:
            improved.append(key)
        elif verdict == BROKEN:
            regressed.append(key)
        elif verdict == UNCHANGED_PASS:
            unchanged_correct += 1
        else:
            unchanged_incorrect += 1
    return {'improved': len(improved), 'regressed': len(regressed),
            'unchanged_correct': unchanged_correct, 'unchanged_incorrect': unchanged_incorrect,
            'net': len(improved) - len(regressed), 'improved_cases': improved,
            'regressed_cases': regressed, 'unpaired': []}


DELTA_KEYS = ('improved', 'regressed', 'unchanged_correct', 'unchanged_incorrect', 'net',
              'improved_cases', 'regressed_cases')


def _deltas(control_index, candidate_index):
    """Ask turbo.optimizer.statistics for the movement, or degrade to our own.

    The rows are re-keyed onto case_id first so both sides pair on exactly the
    same identities: a silent identity mismatch would make that module report
    everything as unpaired while this one still had records, which is the one
    disagreement that would be invisible in the output.
    """
    normalized = ([dict(row, case_id=key) for key, row in sorted(control_index.items())],
                  [dict(row, case_id=key) for key, row in sorted(candidate_index.items())])
    try:
        from turbo.optimizer.statistics import case_deltas
    except ImportError:
        return _fallback_deltas(control_index, candidate_index), 'analyzer.fallback_pairing'
    deltas = case_deltas(*normalized)
    if not isinstance(deltas, dict) or any(key not in deltas for key in DELTA_KEYS):
        raise ValueError('turbo.optimizer.statistics.case_deltas returned an unexpected shape')
    return deltas, 'turbo.optimizer.statistics.case_deltas'


def classify(control_row, candidate_row):
    before, after = control_row['task_success'], candidate_row['task_success']
    if before and after:
        return UNCHANGED_PASS
    if before and not after:
        return BROKEN
    if after and not before:
        return FIXED
    return UNCHANGED_FAIL


def analyze_cases(control_rows, candidate_rows):
    """Case-level truth about one comparison. No model is involved.

    Pairs cases by identifier, classifies each pair as fixed, broken or
    unchanged, groups the regressions by expected tool and by failure reason,
    and reports unpaired cases explicitly instead of quietly dropping them: a
    case that only one side ran is missing evidence, not a zero.
    """
    control_index = _by_case(list(control_rows), 'control_rows')
    candidate_index = _by_case(list(candidate_rows), 'candidate_rows')
    deltas, source = _deltas(control_index, candidate_index)

    excluded = {entry.get('case') for entry in deltas.get('unpaired') or []
                if entry.get('side') == 'both'}
    records = []
    for key in sorted((set(control_index) & set(candidate_index)) - excluded):
        control_row, candidate_row = control_index[key], candidate_index[key]
        records.append({'case_id': key, 'change': classify(control_row, candidate_row),
                        'expected_tool': expected_tool(candidate_row),
                        'control_taxonomy': taxonomy(control_row),
                        'candidate_taxonomy': taxonomy(candidate_row),
                        'control_tool': control_row.get('tool'),
                        'candidate_tool': candidate_row.get('tool')})

    # The counts below are the delta module's, not ours. If its verdicts and
    # ours ever diverge the analysis is not trustworthy under either, so this
    # stops rather than picking a winner.
    for verdict, field in ((FIXED, 'improved_cases'), (BROKEN, 'regressed_cases')):
        mine = {r['case_id'] for r in records if r['change'] == verdict}
        theirs = set(deltas[field])
        if mine != theirs:
            raise ValueError('Case movement disagreement on ' + verdict + ': '
                             + repr(sorted(mine ^ theirs)))

    regressions = [r for r in records if r['change'] == BROKEN]
    fixes = [r for r in records if r['change'] == FIXED]

    analysis = {
        'schema_version': SCHEMA,
        'pairing_source': source,
        'totals': {'paired': len(records), 'fixed': deltas['improved'], 'broken': deltas['regressed'],
                   'unchanged_pass': deltas['unchanged_correct'],
                   'unchanged_fail': deltas['unchanged_incorrect'],
                   'net_cases': deltas['net']},
        'cases': records,
        'regressions_by_expected_tool': _group(regressions, 'expected_tool'),
        'fixes_by_expected_tool': _group(fixes, 'expected_tool'),
        'regressions_by_reason': _group_by_reason(regressions, 'candidate_taxonomy'),
        'fixes_by_reason': _group_by_reason(fixes, 'control_taxonomy'),
        'unpaired': {'control_only': sorted(set(control_index) - set(candidate_index)),
                     'candidate_only': sorted(set(candidate_index) - set(control_index)),
                     'excluded_from_pairing': sorted(excluded, key=repr)},
    }
    analysis['clusters'] = _clusters(regressions, fixes)
    return analysis


def _group(records, field):
    grouped = {}
    for record in records:
        grouped.setdefault(record[field], []).append(record['case_id'])
    return {key: sorted(values) for key, values in sorted(grouped.items())}


def _group_by_reason(records, field):
    grouped = {}
    for record in records:
        for label in record[field] or ['unclassified_incorrect']:
            grouped.setdefault(label, []).append(record['case_id'])
    return {key: sorted(values) for key, values in sorted(grouped.items())}


def _clusters(regressions, fixes):
    """Group each side by expected tool and dominant failure label.

    The dominant label is the candidate's taxonomy for a regression and the
    control's for a fix, because in each case that is the failure the treatment
    is responsible for.
    """
    clusters = []
    for kind, records, field in (('regression', regressions, 'candidate_taxonomy'),
                                 ('fix', fixes, 'control_taxonomy')):
        buckets = {}
        for record in records:
            labels = record[field] or ['unclassified_incorrect']
            buckets.setdefault((record['expected_tool'], labels[0]), []).append(record['case_id'])
        for (tool, label), cases in sorted(buckets.items()):
            clusters.append({'kind': kind, 'expected_tool': tool, 'reason': label,
                             'label': kind + ': ' + tool + ' / ' + label,
                             'cases': sorted(cases), 'size': len(cases)})
    clusters.sort(key=lambda c: (-c['size'], c['label']))
    return clusters


def dominant_failures(analysis, limit=5):
    """The heaviest regression reasons, for a digest or a report line."""
    counter = Counter({label: len(cases) for label, cases in analysis['regressions_by_reason'].items()})
    return [{'reason': label, 'cases': count} for label, count in counter.most_common(limit)]


def narration_payload(analysis):
    """What the narrator is allowed to see: counts, ids, tools, labels."""
    return {'schema_version': SCHEMA, 'totals': analysis['totals'],
            'pairing_source': analysis['pairing_source'],
            'clusters': analysis['clusters'],
            'regressions_by_expected_tool': analysis['regressions_by_expected_tool'],
            'regressions_by_reason': analysis['regressions_by_reason'],
            'fixes_by_expected_tool': analysis['fixes_by_expected_tool'],
            'fixes_by_reason': analysis['fixes_by_reason'],
            'unpaired': analysis['unpaired']}


def known_cases(analysis):
    return {record['case_id'] for record in analysis.get('cases', [])}


def validate(response, analysis):
    """Strict schema check, plus: a named case must exist in the analysis."""
    # call_json stamps timing and cache facts onto what it returns, so the
    # schema is checked against the model's own keys only.
    body = {k: v for k, v in require(response, dict, 'narration response').items()
            if k not in RESERVED_KEYS}
    require_keys(body, ('clusters', 'budget_advice'), 'narration response')
    raw = require(body['clusters'], list, 'clusters')
    known = known_cases(analysis)
    clusters = []
    for index, item in enumerate(raw):
        where = 'clusters[' + str(index) + ']'
        require_keys(item, CLUSTER_KEYS, where)
        require_text(item['label'], where + '.label')
        require_text(item['likely_mechanism'], where + '.likely_mechanism')
        cases = require(item['cases'], list, where + '.cases')
        for position, value in enumerate(cases):
            require(value, str, where + '.cases[' + str(position) + ']')
            if value not in known:
                raise LLMProtocolError(where + '.cases names ' + repr(value)
                                       + ', which is not a case in this analysis')
        clusters.append(dict(item))

    advice = body['budget_advice']
    require_keys(advice, ADVICE_KEYS, 'budget_advice')
    require_text(advice['family'], 'budget_advice.family')
    require_text(advice['why'], 'budget_advice.why')
    if advice['direction'] not in DIRECTIONS:
        raise LLMProtocolError('budget_advice.direction must be more or less, got '
                               + repr(advice['direction']))
    return {'clusters': clusters, 'budget_advice': dict(advice)}


def explain(client, analysis, *, cache=None, timeout_s=60, retries=1):
    """Optional narration of an analysis that has already been computed.

    The model receives counts, case identifiers, expected tools and failure
    labels, and returns labels and a budget direction. Every number in the
    result still comes from analyze_cases: the model never produces a metric,
    and a narration that names a case the analysis does not contain is rejected
    as a protocol error rather than kept as colour.
    """
    import json
    payload = narration_payload(analysis)
    user = ('Computed analysis:\n'
            + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + '\n\nReturn the declared JSON object.')
    response = call_json(client, SYSTEM_PROMPT, user, cache=cache, timeout_s=timeout_s, retries=retries)
    narration = validate(response, analysis)
    narration['schema_version'] = SCHEMA
    narration['totals'] = analysis['totals']
    narration['source'] = {'client': getattr(client, 'name', None),
                           'model': getattr(client, 'model', None), **response_meta(response)}
    return narration
