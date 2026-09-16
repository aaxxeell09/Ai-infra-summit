"""Stage promotion rules, written to lose arguments with an optimistic search.

Successive halving is cheap because most candidates die on thin evidence. That
is exactly what makes it dangerous here: 35 development cases are few enough
that a lucky one case swing looks like a win, and a loop that promotes on such
a swing will tune itself onto the development split and carry nothing to the
heldout set. So every rule in this module is one sided. Early stages may only
eliminate; only the full development run plus an agreeing repeat can promote,
and the reasons list always records which evidence was used, so a promotion can
be argued with after the fact.

Thresholds here are elimination heuristics for an internal search loop. They are
not owner approved quality or latency thresholds and they never establish an
overall winner (see AGENTS.md); every one of them is an explicit argument with a
documented default, and the value actually used is recorded in the reasons.
"""
from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = 'local-turbo.autotune-halving.v1'

#: Mirrors turbo.optimizer.state.STAGES. S0 is candidate generation and static
#: validation (no hardware), S1 a load smoke test, S2 a small elimination
#: subset, S3 a larger development subset, S4 the full 35 development cases,
#: S5 the confirmation repeat.
STAGE_ORDER = ('S0', 'S1', 'S2', 'S3', 'S4', 'S5')

#: The only outcomes an early stage may produce. 'promote' is deliberately
#: absent: it is not a value any of these functions can return.
ELIMINATION_OUTCOMES = ('survive', 'drop')

#: Stages whose evidence may support a promotion. S2 is absent by construction.
PROMOTION_EVIDENCE_STAGES = ('S4', 'S5')

#: Net development case improvement a candidate must show before promotion is
#: even considered. Two, not one: a single case swing on 35 cases is within the
#: noise this loop can generate by chance across many candidates.
PROMOTION_MIN_NET = 2

#: Invalid structured output is the one axis with no tolerance by default: the
#: frozen quality policy already caps invalid actions, and a candidate that
#: produces more malformed actions than the control has no upside worth buying.
DEFAULT_INVALID_RATE_TOLERANCE = 0.0

#: Latency elimination multiples, loosest at the cheapest stage. A candidate
#: that is 25% slower than the control on a smoke subset is not worth a larger
#: subset; by S3/S4 the bar tightens because the sample is better.
S2_LATENCY_MULTIPLE = 1.25
S3_LATENCY_MULTIPLE = 1.15
S4_LATENCY_MULTIPLE = 1.15

#: S2 correctness floor, as a fraction of the control's correct count. S2 runs
#: too few cases to resolve a one or two case regression, so it only catches a
#: collapse: half or fewer of the cases the control got right.
S2_CORRECTNESS_FLOOR_FRACTION = 0.5

#: Net case floors for the larger subsets. S3 only eliminates net regressions
#: (its subset is still small); S4 already demands the promotion floor, so a
#: candidate that cannot promote never buys a confirmation repeat.
S3_MIN_NET = 0
S4_MIN_NET = PROMOTION_MIN_NET


def next_stage(stage):
    """The stage that follows, or None at the end of the ladder."""
    if stage not in STAGE_ORDER:
        raise ValueError('Unknown stage: ' + repr(stage))
    index = STAGE_ORDER.index(stage) + 1
    return STAGE_ORDER[index] if index < len(STAGE_ORDER) else None


def _number(value):
    """A usable float, or None. Booleans are not numbers here."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return float(value)


def _count_outcomes(rows):
    improved = regressed = 0
    for row in rows:
        if isinstance(row, dict):
            outcome = row.get('outcome')
            if outcome in ('fixed', 'improved', 'win'):
                improved += 1
            elif outcome in ('regressed', 'broken', 'loss'):
                regressed += 1
            continue
        value = _number(row)
        if value is None:
            continue
        if value > 0:
            improved += 1
        elif value < 0:
            regressed += 1
    return improved, regressed


def normalize_deltas(value):
    """Reduce whatever ``statistics.case_deltas`` produced to counts.

    The statistics module is a sibling deliverable, so this accepts the shapes
    a case level delta can reasonably take rather than hard coding one: a
    mapping carrying ``net``/``improved``/``regressed`` (counts or collections),
    a mapping carrying a ``cases`` list of per case records, or a bare sequence
    of per case records or signed numbers. Anything it cannot read stays
    unknown, and unknown is never treated as zero.

    Returns ``{'improved', 'regressed', 'net', 'stage', 'known'}``. ``stage``
    is the provenance tag the caller attached, if any.
    """
    result = {'improved': None, 'regressed': None, 'net': None, 'stage': None, 'known': False}
    if value is None:
        return result
    if isinstance(value, dict):
        result['stage'] = value.get('stage')
        cases = value.get('cases')
        improved = value.get('improved', value.get('fixed'))
        regressed = value.get('regressed')
        if isinstance(improved, (list, tuple, set)):
            improved = len(improved)
        if isinstance(regressed, (list, tuple, set)):
            regressed = len(regressed)
        improved = _number(improved)
        regressed = _number(regressed)
        if (improved is None or regressed is None) and isinstance(cases, (list, tuple)):
            improved, regressed = (float(n) for n in _count_outcomes(cases))
        net = _number(value.get('net', value.get('net_cases')))
        if net is None and improved is not None and regressed is not None:
            net = improved - regressed
        result['improved'] = None if improved is None else int(improved)
        result['regressed'] = None if regressed is None else int(regressed)
        result['net'] = None if net is None else int(net)
        result['known'] = net is not None
        return result
    if isinstance(value, (list, tuple)):
        improved, regressed = _count_outcomes(value)
        result.update(improved=improved, regressed=regressed, net=improved - regressed, known=True)
        return result
    return result


def case_deltas_from_rows(control_rows, candidate_rows):
    """Delegate to the statistics module, imported at call time.

    Late import on purpose: this module must stay importable (and testable)
    while ``turbo.optimizer.statistics`` is being written alongside it, and a
    caller that never passes raw rows never needs it.
    """
    statistics = importlib.import_module('turbo.optimizer.statistics')
    return statistics.case_deltas(control_rows, candidate_rows)


def _resolve_deltas(deltas, observation):
    if deltas is None and isinstance(observation, dict):
        deltas = observation.get('case_deltas')
        if deltas is None and observation.get('control_rows') is not None:
            deltas = case_deltas_from_rows(observation['control_rows'], observation.get('rows'))
    return normalize_deltas(deltas)


def evaluate_s1(observation):
    """Did this configuration load and run at all? Nothing more is claimed.

    S1 is a liveness check, NOT a correctness claim: surviving it says the
    runner accepted the config and the model came up, and says nothing about
    whether a single action was right. A missing startup time is recorded as
    unknown rather than treated as a failure, because the load already
    succeeded; a missing load flag is a drop, since absence of evidence that it
    loaded is not evidence that it did.
    """
    reasons = []
    if not isinstance(observation, dict):
        return 'drop', ['S1 observation is not an object']

    loaded = observation.get('loaded')
    if loaded is not True:
        reasons.append('did not load' if loaded is False else 'load status unknown')

    error = observation.get('runtime_error')
    if error:
        reasons.append('runtime error: ' + str(error))

    exit_code = observation.get('exit_code')
    if exit_code is None:
        # In process runs report no exit code at all; the load flag carries the
        # positive evidence in that case, so this alone does not eliminate.
        reasons.append('exit code unknown')
    elif _number(exit_code) not in (0.0,):
        reasons.append('runner refused the configuration with exit code ' + str(exit_code))

    startup = _number(observation.get('startup_seconds'))
    if startup is None:
        reasons.append('startup_seconds unknown')

    dropped = any(r for r in reasons if r not in ('exit code unknown', 'startup_seconds unknown'))
    return ('drop' if dropped else 'survive'), reasons


def _invalid_rate_reasons(observation, control, tolerance, label):
    reasons = []
    observed = _number(observation.get('invalid_rate'))
    baseline = _number(control.get('invalid_rate'))
    if observed is None:
        reasons.append(label + ': invalid rate unknown, cannot clear the gate')
    elif baseline is None:
        reasons.append(label + ': control invalid rate unknown, no baseline to compare against')
    elif observed > baseline + tolerance:
        reasons.append(label + ': invalid rate ' + repr(observed) + ' above control '
                       + repr(baseline) + ' (tolerance ' + repr(tolerance) + ')')
    return reasons


def _latency(record):
    """The task-latency median under either spelling, explicit name first.

    ``median_task_latency_ms`` is the name that says which boundary it belongs
    to; ``median_latency_ms`` is the shorter name the simulator and early call
    sites used. Reading both here keeps one definition of the quantity instead
    of two, which is the substitution the tracking audit ruled out.
    """
    for key in ('median_task_latency_ms', 'median_latency_ms'):
        value = _number((record or {}).get(key))
        if value is not None:
            return value
    return None


def _latency_reasons(observation, control, multiple, label):
    reasons = []
    observed = _latency(observation)
    baseline = _latency(control)
    if observed is None:
        reasons.append(label + ': median latency unknown, cannot clear the gate')
    elif baseline is None:
        reasons.append(label + ': control median latency unknown, no baseline to compare against')
    elif observed > baseline * multiple:
        reasons.append(label + ': median latency ' + repr(observed) + ' ms exceeds '
                       + repr(multiple) + 'x control ' + repr(baseline) + ' ms')
    return reasons


def evaluate_s2(observation, *, control, invalid_rate_tolerance=DEFAULT_INVALID_RATE_TOLERANCE,
                latency_multiple=S2_LATENCY_MULTIPLE):
    """Elimination only. S2 can remove a candidate, it can never rank one.

    The subset S2 runs is chosen to be cheap, which makes it far too small to
    say that one configuration is better than another. So this returns only
    'survive' or 'drop': 'promote' is not a value it can produce, and a caller
    that wants a promotion has to go and get S4 and S5 evidence. 'survive' means
    nothing worse than "no gross harm was observed", not "this is an
    improvement".

    Drops on: any invalid structured output above the control's rate (plus an
    explicit tolerance, zero by default), a correctness collapse (fewer correct
    cases than S2_CORRECTNESS_FLOOR_FRACTION of the control's correct count,
    rounded up), or a median latency above a declared multiple of the control's.
    A gate with no evidence on either side cannot be cleared, so it drops too.
    """
    if not isinstance(observation, dict) or not isinstance(control, dict):
        return 'drop', ['S2 observation and control must both be objects']

    blocking = _invalid_rate_reasons(observation, control, invalid_rate_tolerance, 'S2')
    blocking.extend(_latency_reasons(observation, control, latency_multiple, 'S2'))
    notes = []

    correct = _number(observation.get('correct'))
    baseline_correct = _number(control.get('correct'))
    if correct is None:
        blocking.append('S2: correct count unknown, cannot clear the gate')
    elif baseline_correct is None:
        blocking.append('S2: control correct count unknown, no baseline to compare against')
    elif baseline_correct <= 0:
        notes.append('S2: control has no correct cases, correctness cannot eliminate here')
    else:
        floor = math.ceil(baseline_correct * S2_CORRECTNESS_FLOOR_FRACTION)
        if correct < floor:
            blocking.append('S2: correctness collapse, ' + str(int(correct)) + ' correct below floor '
                            + str(int(floor)) + ' derived from control ' + str(int(baseline_correct)))

    # Two literals, one of which is 'survive': there is no expression in this
    # function that can yield 'promote'.
    return ('drop' if blocking else 'survive'), blocking + notes


def _evaluate_subset(stage, observation, control, deltas, invalid_rate_tolerance,
                     latency_multiple, min_net):
    if not isinstance(observation, dict) or not isinstance(control, dict):
        return 'drop', [stage + ' observation and control must both be objects']

    blocking = _invalid_rate_reasons(observation, control, invalid_rate_tolerance, stage)
    blocking.extend(_latency_reasons(observation, control, latency_multiple, stage))
    notes = []

    summary = _resolve_deltas(deltas, observation)
    if not summary['known']:
        blocking.append(stage + ': case level deltas unknown, cannot clear the gate')
    else:
        notes.append(stage + ': net ' + str(summary['net']) + ' cases (improved '
                     + str(summary['improved']) + ', regressed ' + str(summary['regressed']) + ')')
        if summary['net'] < min_net:
            blocking.append(stage + ': net ' + str(summary['net']) + ' below floor ' + str(min_net))

    return ('drop' if blocking else 'survive'), blocking + notes


def evaluate_s3(observation, *, control, deltas=None,
                invalid_rate_tolerance=DEFAULT_INVALID_RATE_TOLERANCE,
                latency_multiple=S3_LATENCY_MULTIPLE, min_net=S3_MIN_NET):
    """Larger development subset. Still elimination only, never a promotion.

    ``deltas`` is whatever ``turbo.optimizer.statistics.case_deltas`` returned;
    when omitted it is read from ``observation['case_deltas']``, or computed
    from ``observation['control_rows']`` and ``observation['rows']``.
    """
    return _evaluate_subset('S3', observation, control, deltas, invalid_rate_tolerance,
                            latency_multiple, min_net)


def evaluate_s4(observation, *, control, deltas=None,
                invalid_rate_tolerance=DEFAULT_INVALID_RATE_TOLERANCE,
                latency_multiple=S4_LATENCY_MULTIPLE, min_net=S4_MIN_NET):
    """Full 35 case development run. Elimination only; promotion lives below.

    The net floor here is already the promotion floor, so a candidate that could
    never promote does not get to spend hardware on a confirmation repeat.
    """
    return _evaluate_subset('S4', observation, control, deltas, invalid_rate_tolerance,
                            latency_multiple, min_net)


def promotion_decision(dev35_deltas, confirmation_deltas, *, latency_gate_ok, deterministic_output,
                       min_net=PROMOTION_MIN_NET):
    """The only function in this module that can say 'promote'.

    All three of these must hold:
      1. a net improvement of at least ``min_net`` development cases,
      2. the latency gate not materially violated, passed in as a fact,
      3. a repeat that agrees in direction with the development run.

    Requirement 3 may be met by a single run when ``deterministic_output`` is
    exactly True. That argument is a fact the caller established empirically
    (identical outputs across repeats of the same configuration), not an
    assumption this function is entitled to make, so it is never inferred here
    and the branch that was taken is always written into ``reasons``.

    'reject' means the evidence argues against promotion; 'hold' means the
    evidence so far is consistent with promotion but incomplete, so more
    measurement could still change the answer.

    S2 evidence cannot reach a promotion. ``evaluate_s2`` has no 'promote' in
    its result vocabulary at all, and if the deltas passed here carry a stage
    tag it must be one of PROMOTION_EVIDENCE_STAGES, so a caller cannot route
    an S2 summary into this function either.
    """
    reasons = []
    dev = normalize_deltas(dev35_deltas)
    confirm = normalize_deltas(confirmation_deltas)
    net = dev['net']

    for label, summary in (('development', dev), ('confirmation', confirm)):
        stage = summary['stage']
        if stage is not None and stage not in PROMOTION_EVIDENCE_STAGES:
            reasons.append('Evidence from stage ' + str(stage) + ' cannot support a promotion ('
                           + label + ' deltas)')
            return {'decision': 'reject', 'reasons': reasons, 'net': net, 'confirmed': False}

    if not dev['known']:
        reasons.append('Development case deltas unknown; unknown is not a promotion')
        return {'decision': 'reject', 'reasons': reasons, 'net': None, 'confirmed': False}
    reasons.append('development net ' + str(net) + ' cases (improved ' + str(dev['improved'])
                   + ', regressed ' + str(dev['regressed']) + ')')

    if latency_gate_ok is not True:
        reasons.append('Latency gate not satisfied' if latency_gate_ok is False
                       else 'Latency gate status unknown; unknown is not a pass')
        return {'decision': 'reject', 'reasons': reasons, 'net': net, 'confirmed': False}
    reasons.append('latency gate satisfied')

    if net < min_net:
        reasons.append('Net improvement ' + str(net) + ' below the promotion floor of ' + str(min_net))
        return {'decision': 'reject', 'reasons': reasons, 'net': net, 'confirmed': False}

    if deterministic_output is True:
        reasons.append('determinism branch: deterministic_output established empirically, '
                       'a single run satisfies the repetition requirement')
        if confirm['known'] and confirm['net'] < 1:
            reasons.append('Confirmation run disagrees in direction (net ' + str(confirm['net'])
                           + '), determinism claim contradicted by measurement')
            return {'decision': 'reject', 'reasons': reasons, 'net': net, 'confirmed': False}
        return {'decision': 'promote', 'reasons': reasons, 'net': net, 'confirmed': True}

    reasons.append('determinism branch: output determinism not established, '
                   'an agreeing confirmation repeat is required')
    if not confirm['known']:
        reasons.append('Confirmation repeat missing; holding until it is measured')
        return {'decision': 'hold', 'reasons': reasons, 'net': net, 'confirmed': False}
    if confirm['net'] < 1:
        reasons.append('Confirmation repeat disagrees in direction (net ' + str(confirm['net']) + ')')
        return {'decision': 'reject', 'reasons': reasons, 'net': net, 'confirmed': False}
    reasons.append('confirmation repeat agrees in direction (net ' + str(confirm['net']) + ')')
    return {'decision': 'promote', 'reasons': reasons, 'net': net, 'confirmed': True}
