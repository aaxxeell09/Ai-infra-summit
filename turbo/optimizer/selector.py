"""The one place a candidate is allowed to become the control.

Stage evidence accumulates in many places: screening subsets, the full 35 case
development run, a repeat confirmation. Turning that pile into "this is now the
control" is a single decision, and it is kept here so it can be read, tested and
audited in one file instead of being reconstructed from an orchestration loop.

The statistical rule itself lives in turbo/optimizer/successive_halving.py. This
module only applies the rule's verdict to session state, records why, and hands
back enough to undo it. It fails closed in both directions: an unavailable rule
module is an error rather than an implicit promote, and a 'promote' verdict is
refused when the gates this module can see are not explicitly satisfied.
"""
from __future__ import annotations

import importlib

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import state as session_state

SCHEMA = 'local-turbo.autotune-selector.v1'

UNKNOWN = 'unknown'

PROMOTE = 'promote'
REJECT = 'reject'
ROLLED_BACK = 'rolled_back'

#: Promotion without a tracker experiment id. Kept as a constant because the
#: report and the console both have to say the same thing about it.
UNTRACKED_PROMOTION = ('Promotion carries no tracker experiment id: this is an orchestration '
                       'decision only and cannot be cited as measured evidence')


class Selection(dict):
    """A decision plus everything needed to explain or reverse it.

    Keys always present: decision, candidate_id, reasons, net_cases, confirmed,
    rolled_back, experiment_id, experiment_id_status, previous_control.
    A value that was not measured is None, never 0.
    """

    def __init__(self, *, decision, candidate_id=None, reasons=(), net_cases=None,
                 confirmed=False, rolled_back=False, experiment_id=None,
                 experiment_id_status=UNKNOWN, previous_control=None, control=None):
        super().__init__(decision=decision, candidate_id=candidate_id, reasons=list(reasons),
                         net_cases=net_cases, confirmed=bool(confirmed),
                         rolled_back=bool(rolled_back), experiment_id=experiment_id,
                         experiment_id_status=experiment_id_status,
                         previous_control=previous_control, control=control)


def _rules():
    """Import the halving rules late, with an error a reader can act on."""
    try:
        # importlib consults sys.modules first, so a test that substitutes the
        # rules module sees its substitute. A plain "from package import module"
        # would read the package attribute instead and silently use the real
        # rules, which is exactly the failure a stub is meant to prevent.
        successive_halving = importlib.import_module('turbo.optimizer.successive_halving')
    except ImportError as exc:
        raise ImportError('turbo.optimizer.successive_halving is unavailable, so no promotion rule '
                          'exists and nothing may be promoted: ' + str(exc)) from exc
    if not hasattr(successive_halving, 'promotion_decision'):
        raise ImportError('turbo.optimizer.successive_halving defines no promotion_decision; '
                          'the selector refuses to invent one')
    return successive_halving


def _net_cases(verdict, dev35_deltas):
    """Net development cases gained, from the rule if it says, else from the deltas.

    The rule module reports it as 'net'; 'net_cases' is accepted too so the two
    spellings cannot silently become two different numbers.
    """
    if isinstance(verdict, dict):
        for key in ('net_cases', 'net'):
            if verdict.get(key) is not None:
                return verdict[key]
    if dev35_deltas is None:
        return None
    values = list(dev35_deltas)
    if not values or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in values):
        return None
    return sum(values)


def _verdict(raw):
    """Normalise whatever the rule returned into (decision, reasons, dict)."""
    if isinstance(raw, dict):
        decision = raw.get('decision')
        reasons = list(raw.get('reasons') or ())
    elif isinstance(raw, str):
        decision, reasons, raw = raw, [], {}
    else:
        raise TypeError('successive_halving.promotion_decision returned '
                        + type(raw).__name__ + ', expected a decision string or a dict')
    if not isinstance(decision, str) or not decision:
        raise ValueError('successive_halving.promotion_decision returned no decision')
    return decision, reasons, raw


def consider(state, candidate, *, dev35_deltas, confirmation_deltas, latency_gate_ok,
             deterministic_output, experiment_id=None):
    """Apply the halving rule to one candidate and act on its verdict.

    ``state`` is a session record from turbo/optimizer/state.py (a plain dict, so
    the module functions are applied to it, not methods on it).

    On 'promote' the candidate becomes the session control through state.promote
    and the previous control is returned under ``previous_control`` so the caller
    can hand it to rollback() if confirmation later fails.

    ``experiment_id`` is the tracker id of the archive that produced this
    evidence. When it is None the selection records experiment_id_status
    'unknown' and carries UNTRACKED_PROMOTION as a reason: a promotion without a
    tracked experiment is an orchestration decision only and cannot be cited as
    measured evidence, in a report, a claim or a comparison.

    Nothing here reads energy. Energy is not commissioned, so it may not rank or
    select a candidate at all.
    """
    rules = _rules()
    decision, reasons, raw = _verdict(rules.promotion_decision(
        dev35_deltas=dev35_deltas, confirmation_deltas=confirmation_deltas,
        latency_gate_ok=latency_gate_ok, deterministic_output=deterministic_output))
    candidate_id = candidate.get('candidate_id') or candidate.get('name')
    net_cases = _net_cases(raw, dev35_deltas)
    confirmed = bool(raw.get('confirmed')) if 'confirmed' in raw else bool(
        decision == PROMOTE and confirmation_deltas)

    # A gate whose result is unknown is not a passed gate. Refusing here can only
    # ever block a promotion, never create one, so disagreeing with the rule
    # module is safe in this direction.
    #
    # Determinism is deliberately NOT such a gate. Establishing that output is
    # deterministic only relaxes how many repeats a promotion needs; it is not
    # itself a promotion requirement. Treating it as one would make every
    # promotion impossible for a stochastic runtime, which is the normal case
    # here, and the repetition requirement in the rule module already handles
    # the non-deterministic branch by demanding a confirming repeat.
    if decision == PROMOTE and latency_gate_ok is not True:
        decision = REJECT
        reasons.append('Latency gate is not an explicit pass: ' + repr(latency_gate_ok))

    if decision != PROMOTE:
        return Selection(decision=decision, candidate_id=candidate_id, reasons=reasons,
                         net_cases=net_cases, confirmed=confirmed,
                         experiment_id=experiment_id,
                         experiment_id_status='recorded' if experiment_id else UNKNOWN)

    if not experiment_id:
        reasons.append(UNTRACKED_PROMOTION)
    previous = session_state.promote(state, candidate, experiment_id=experiment_id)
    return Selection(decision=PROMOTE, candidate_id=candidate_id, reasons=reasons,
                     net_cases=net_cases, confirmed=confirmed, experiment_id=experiment_id,
                     experiment_id_status='recorded' if experiment_id else UNKNOWN,
                     previous_control=previous, control=dict(state['current_control']))


def rollback(state, reason):
    """Restore the previous control and say why, in the same shape as consider."""
    restored = session_state.rollback(state)
    return Selection(decision=ROLLED_BACK, candidate_id=restored.get('name'),
                     reasons=[reason], rolled_back=True,
                     experiment_id=restored.get('experiment_id'),
                     experiment_id_status='recorded' if restored.get('experiment_id') else UNKNOWN,
                     control=dict(state['current_control']))
