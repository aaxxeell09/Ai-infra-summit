"""Descriptive statistics for autotune, with no inferential claim available.

An optimization loop that repeats a treatment until one run looks better is a
machine for manufacturing false positives, and the usual way that gets written
up is a p-value nobody chose a test for. So this module offers counts, spreads
and unanimity across repeats, and nothing that could be read as significance:
significance_statement exists only to raise, so the absence of a test is loud at
the call site instead of silently absent from the report.

Case-level comparison here pairs strictly by case identity. Two result arrays in
the same order are not two arrays of the same cases, and pairing them by index
would invent agreements and disagreements that were never measured.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import stats

SCHEMA = 'local-turbo.autotune-statistics.v1'


def describe(values):
    """n, mean, median, stddev, cv, minimum, maximum. Empty gives None, not zero.

    This wraps turbo.experiments.stats rather than recomputing: that function
    already returns None for every field it cannot characterise, which is the
    fail-closed behaviour wanted here. Only the key names are adapted (min/max
    spelled out, p95 dropped because an autotune sample is far too small for a
    tail quantile to mean anything). Its refusal rule is inherited too: a value
    that is negative or not finite makes every field None, so an unmeasurable
    sample never reads as a measured one.
    """
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError('describe expects a list of numbers')
    summary = stats(list(values))
    return {'n': summary['n'], 'mean': summary['mean'], 'median': summary['median'],
            'stddev': summary['stddev'], 'cv': summary['cv'],
            'minimum': summary['min'], 'maximum': summary['max']}


def case_identity(row):
    """Stable identity of one evaluator row, or None when it carries none.

    case_id wins when present because a caller that supplies it has already
    chosen the identity; otherwise the frozen evaluator's case_sha256 is it.
    """
    if not isinstance(row, dict):
        raise ValueError('Result rows must be objects')
    identity = row.get('case_id')
    if identity is None:
        identity = row.get('case_sha256')
    if identity is None or (isinstance(identity, str) and not identity.strip()):
        return None
    return identity


def _index(rows, side):
    indexed, unidentified = {}, []
    for row in rows:
        identity = case_identity(row)
        if identity is None:
            unidentified.append({'side': side, 'case': None,
                                 'reason': 'Row carries neither case_id nor case_sha256'})
            continue
        if identity in indexed:
            # Two rows claiming one case make every count below ambiguous, and
            # picking either one would hide that the input is malformed.
            raise ValueError('Duplicate case identity in ' + side + ' rows: ' + repr(identity))
        indexed[identity] = row
    return indexed, unidentified


def case_deltas(control_rows, candidate_rows):
    """Per-case correctness movement between a control run and a candidate run.

    Counts only cases present on both sides with a boolean task_success. Anything
    else lands in ``unpaired`` with a reason and is excluded, because a case that
    was not measured twice cannot have moved.
    """
    for rows, side in ((control_rows, 'control'), (candidate_rows, 'candidate')):
        if isinstance(rows, (str, bytes)) or not isinstance(rows, (list, tuple)):
            raise ValueError(side + ' rows must be a list of result objects')
    control, unpaired = _index(control_rows, 'control')
    candidate, unidentified = _index(candidate_rows, 'candidate')
    unpaired = unpaired + unidentified

    for identity in sorted(set(control) - set(candidate), key=repr):
        unpaired.append({'side': 'control', 'case': identity,
                         'reason': 'No candidate row with this case identity'})
    for identity in sorted(set(candidate) - set(control), key=repr):
        unpaired.append({'side': 'candidate', 'case': identity,
                         'reason': 'No control row with this case identity'})

    improved, regressed = [], []
    unchanged_correct = unchanged_incorrect = 0
    for identity in sorted(set(control) & set(candidate), key=repr):
        before = control[identity].get('task_success')
        after = candidate[identity].get('task_success')
        if before is not True and before is not False or after is not True and after is not False:
            unpaired.append({'side': 'both', 'case': identity,
                             'reason': 'task_success is not a boolean on at least one side'})
            continue
        if after and not before:
            improved.append(identity)
        elif before and not after:
            regressed.append(identity)
        elif before:
            unchanged_correct += 1
        else:
            unchanged_incorrect += 1
    return {'improved': len(improved), 'regressed': len(regressed),
            'unchanged_correct': unchanged_correct, 'unchanged_incorrect': unchanged_incorrect,
            'net': len(improved) - len(regressed),
            'improved_cases': improved, 'regressed_cases': regressed,
            'unpaired': unpaired}


def agreement(observations):
    """Whether repeated runs of one treatment produced the same correct count.

    Identical counts across repeats say the pipeline was deterministic for this
    sample, nothing more: they do not say the treatment is good, and a spread of
    zero over two repeats is weak evidence of determinism, so the raw n stays in
    the result for the reader to weigh.
    """
    if isinstance(observations, (str, bytes)) or not isinstance(observations, (list, tuple)):
        raise ValueError('agreement expects a list of per-repeat correct counts')
    values = list(observations)
    for value in values:
        if type(value) is not int or value < 0:
            raise ValueError('Each observation must be a non-negative integer correct count')
    distinct = sorted(set(values))
    return {'n_repeats': len(values), 'distinct_values': distinct,
            # No repeats means nothing agreed; unknown determinism is not identity.
            'identical': bool(values) and len(distinct) == 1,
            'spread': (max(values) - min(values)) if values else None,
            'describe': describe(values)}


def stable_wins(repeat_deltas):
    """Cases that moved the same way in every repeat, and those that did not.

    Unanimity is the bar because a case that flips between repeats is measuring
    run-to-run variance, and counting it as a win is how a search convinces
    itself that noise is progress.
    """
    if isinstance(repeat_deltas, (str, bytes)) or not isinstance(repeat_deltas, (list, tuple)):
        raise ValueError('stable_wins expects a list of case_deltas results')
    repeats = list(repeat_deltas)
    for entry in repeats:
        if not isinstance(entry, dict) or not isinstance(entry.get('improved_cases'), (list, tuple)) \
                or not isinstance(entry.get('regressed_cases'), (list, tuple)):
            raise ValueError('Each repeat must be a case_deltas result with improved and regressed cases')
    wins, losses, unstable = [], [], []
    every = []
    for entry in repeats:
        for identity in list(entry['improved_cases']) + list(entry['regressed_cases']):
            if identity not in every:
                every.append(identity)
    for identity in sorted(every, key=repr):
        improved = sum(1 for entry in repeats if identity in entry['improved_cases'])
        regressed = sum(1 for entry in repeats if identity in entry['regressed_cases'])
        if repeats and improved == len(repeats) and regressed == 0:
            wins.append(identity)
        elif repeats and regressed == len(repeats) and improved == 0:
            losses.append(identity)
        else:
            unstable.append(identity)
    return {'n_repeats': len(repeats), 'stable_wins': wins, 'stable_losses': losses,
            'unstable': unstable}


def significance_statement(*args, **kwargs):
    """Always raises. There is no significance claim available from this module.

    Kept as a real function with a real name so that a caller reaching for one
    gets an explicit refusal at the point of use, rather than finding some
    adjacent descriptive number and reporting it as if a test had been run.
    """
    raise NotImplementedError(
        'No significance test has been run and none is available here: this module is descriptive '
        'only. A significance claim requires an explicitly chosen test (with its assumptions, its '
        'unit of analysis and its multiple-comparison correction stated) plus an owner decision to '
        'run it. Report counts, per-case movement and repeat agreement instead.')
