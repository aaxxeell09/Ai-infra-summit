"""Stage promotion tests, centred on what must never happen.

The interesting assertions here are negative: S2 cannot promote, one net case
cannot promote, an unrepeated result cannot promote, and a summary tagged with
an early stage cannot be routed into the promotion rule.
"""
from __future__ import annotations

import itertools
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import state, successive_halving as halving

CONTROL = {'invalid_rate': 0.02, 'correct': 20, 'median_latency_ms': 1000.0}


def s2_observation(**overrides):
    base = {'invalid_rate': 0.02, 'correct': 20, 'median_latency_ms': 1000.0}
    base.update(overrides)
    return base


def deltas(improved, regressed, stage=None):
    value = {'improved': improved, 'regressed': regressed, 'net': improved - regressed}
    if stage is not None:
        value['stage'] = stage
    return value


def test_stage_order_matches_the_state_module():
    assert halving.STAGE_ORDER == state.STAGES


def test_next_stage_walks_the_ladder_and_stops():
    assert halving.next_stage('S0') == 'S1'
    assert halving.next_stage('S3') == 'S4'
    assert halving.next_stage('S5') is None
    with pytest.raises(ValueError):
        halving.next_stage('S6')


def test_s1_drops_a_configuration_that_did_not_load():
    outcome, reasons = halving.evaluate_s1({'loaded': False, 'startup_seconds': 3.0,
                                            'runtime_error': None, 'exit_code': 0})
    assert outcome == 'drop'
    assert any('did not load' in r for r in reasons)


def test_s1_drops_on_a_runtime_error_or_a_refusing_exit_code():
    outcome, reasons = halving.evaluate_s1({'loaded': True, 'startup_seconds': 3.0,
                                            'runtime_error': 'Unknown configuration keys',
                                            'exit_code': 0})
    assert outcome == 'drop'
    assert any('Unknown configuration keys' in r for r in reasons)

    outcome, reasons = halving.evaluate_s1({'loaded': True, 'startup_seconds': 3.0,
                                            'runtime_error': None, 'exit_code': 2})
    assert outcome == 'drop'
    assert any('exit code 2' in r for r in reasons)


def test_s1_drops_when_the_load_flag_is_missing():
    outcome, reasons = halving.evaluate_s1({'startup_seconds': 3.0})
    assert outcome == 'drop'
    assert any('load status unknown' in r for r in reasons)


def test_s1_records_an_unknown_startup_time_without_dropping():
    outcome, reasons = halving.evaluate_s1({'loaded': True, 'startup_seconds': None,
                                            'runtime_error': None, 'exit_code': 0})
    assert outcome == 'survive'
    assert 'startup_seconds unknown' in reasons


def test_s1_survives_an_in_process_run_with_no_exit_code():
    outcome, reasons = halving.evaluate_s1({'loaded': True, 'startup_seconds': 2.5,
                                            'runtime_error': None, 'exit_code': None})
    assert outcome == 'survive'
    assert 'exit code unknown' in reasons


def test_s2_never_returns_promote_for_any_observation():
    grid = itertools.product([0.0, 0.02, 0.5, None], [0, 5, 20, 35, None],
                             [10.0, 1000.0, 9000.0, None])
    seen = set()
    for invalid, correct, latency in grid:
        outcome, _ = halving.evaluate_s2(
            {'invalid_rate': invalid, 'correct': correct, 'median_latency_ms': latency},
            control=CONTROL)
        seen.add(outcome)
    assert seen <= set(halving.ELIMINATION_OUTCOMES)
    assert 'promote' not in seen
    assert 'promote' not in halving.ELIMINATION_OUTCOMES


def test_s2_survives_a_candidate_that_shows_no_gross_harm():
    outcome, reasons = halving.evaluate_s2(s2_observation(correct=19, median_latency_ms=1100.0),
                                           control=CONTROL)
    assert outcome == 'survive'
    assert reasons == []


def test_s2_drops_on_invalid_output_above_the_control():
    outcome, reasons = halving.evaluate_s2(s2_observation(invalid_rate=0.03), control=CONTROL)
    assert outcome == 'drop'
    assert any('invalid rate' in r for r in reasons)


def test_s2_drops_on_a_correctness_collapse_against_the_derived_floor():
    # Floor is ceil(20 * 0.5) = 10, so 10 survives and 9 collapses.
    assert halving.evaluate_s2(s2_observation(correct=10), control=CONTROL)[0] == 'survive'
    outcome, reasons = halving.evaluate_s2(s2_observation(correct=9), control=CONTROL)
    assert outcome == 'drop'
    assert any('correctness collapse' in r for r in reasons)


def test_s2_drops_on_latency_above_the_declared_multiple():
    assert halving.S2_LATENCY_MULTIPLE == 1.25
    assert halving.evaluate_s2(s2_observation(median_latency_ms=1250.0), control=CONTROL)[0] == 'survive'
    outcome, reasons = halving.evaluate_s2(s2_observation(median_latency_ms=1251.0), control=CONTROL)
    assert outcome == 'drop'
    assert any('median latency' in r for r in reasons)


def test_s2_drops_when_a_gate_has_no_evidence_on_either_side():
    outcome, reasons = halving.evaluate_s2(s2_observation(correct=None), control=CONTROL)
    assert outcome == 'drop'
    assert any('correct count unknown' in r for r in reasons)

    outcome, reasons = halving.evaluate_s2(s2_observation(),
                                           control={'invalid_rate': 0.02, 'correct': 20,
                                                    'median_latency_ms': None})
    assert outcome == 'drop'
    assert any('control median latency unknown' in r for r in reasons)


def test_s2_says_so_when_the_control_has_no_correct_cases_to_collapse_from():
    outcome, reasons = halving.evaluate_s2(s2_observation(correct=0),
                                           control={'invalid_rate': 0.02, 'correct': 0,
                                                    'median_latency_ms': 1000.0})
    assert outcome == 'survive'
    assert any('cannot eliminate here' in r for r in reasons)


def test_s3_eliminates_only_a_net_regression():
    observation = s2_observation()
    assert halving.S3_MIN_NET == 0
    assert halving.evaluate_s3(observation, control=CONTROL, deltas=deltas(2, 2))[0] == 'survive'
    outcome, reasons = halving.evaluate_s3(observation, control=CONTROL, deltas=deltas(1, 3))
    assert outcome == 'drop'
    assert any('below floor 0' in r for r in reasons)


def test_s4_already_demands_the_promotion_floor():
    observation = s2_observation()
    assert halving.S4_MIN_NET == halving.PROMOTION_MIN_NET == 2
    outcome, reasons = halving.evaluate_s4(observation, control=CONTROL, deltas=deltas(3, 2))
    assert outcome == 'drop'
    assert any('below floor 2' in r for r in reasons)
    assert halving.evaluate_s4(observation, control=CONTROL, deltas=deltas(4, 2))[0] == 'survive'


def test_s3_and_s4_also_apply_the_invalid_and_latency_gates():
    good = deltas(5, 0)
    assert halving.evaluate_s4(s2_observation(invalid_rate=0.05), control=CONTROL,
                               deltas=good)[0] == 'drop'
    assert halving.evaluate_s4(s2_observation(median_latency_ms=1200.0), control=CONTROL,
                               deltas=good)[0] == 'drop'


def test_subset_stages_drop_when_case_deltas_are_unknown():
    outcome, reasons = halving.evaluate_s3(s2_observation(), control=CONTROL, deltas=None)
    assert outcome == 'drop'
    assert any('case level deltas unknown' in r for r in reasons)


def test_deltas_are_read_from_the_observation_when_not_passed():
    observation = s2_observation(case_deltas=deltas(4, 1))
    assert halving.evaluate_s4(observation, control=CONTROL)[0] == 'survive'


def test_normalize_deltas_reads_the_shapes_case_deltas_can_return():
    from_counts = halving.normalize_deltas({'improved': 3, 'regressed': 1})
    assert (from_counts['net'], from_counts['known']) == (2, True)

    from_lists = halving.normalize_deltas({'improved': ['a', 'b'], 'regressed': ['c']})
    assert from_lists['net'] == 1

    from_cases = halving.normalize_deltas({'cases': [{'outcome': 'fixed'}, {'outcome': 'fixed'},
                                                     {'outcome': 'regressed'},
                                                     {'outcome': 'unchanged'}]})
    assert (from_cases['improved'], from_cases['regressed'], from_cases['net']) == (2, 1, 1)

    from_sequence = halving.normalize_deltas([1, 1, -1, 0])
    assert from_sequence['net'] == 1

    unknown = halving.normalize_deltas(None)
    assert unknown['known'] is False and unknown['net'] is None


def test_raw_rows_reach_the_statistics_module_lazily(monkeypatch):
    calls = {}

    def case_deltas(control_rows, candidate_rows):
        calls['args'] = (control_rows, candidate_rows)
        return {'improved': 4, 'regressed': 0}

    stub = types.ModuleType('turbo.optimizer.statistics')
    stub.case_deltas = case_deltas
    monkeypatch.setitem(sys.modules, 'turbo.optimizer.statistics', stub)

    observation = s2_observation(control_rows=['before'], rows=['after'])
    assert halving.evaluate_s4(observation, control=CONTROL)[0] == 'survive'
    assert calls['args'] == (['before'], ['after'])


def test_promotion_refuses_a_single_net_case():
    result = halving.promotion_decision(deltas(3, 2), deltas(3, 2), latency_gate_ok=True,
                                        deterministic_output=True)
    assert result['decision'] == 'reject'
    assert result['net'] == 1
    assert result['confirmed'] is False
    assert any('below the promotion floor of 2' in r for r in result['reasons'])


def test_promotion_holds_when_the_confirmation_repeat_is_missing():
    result = halving.promotion_decision(deltas(4, 1), None, latency_gate_ok=True,
                                        deterministic_output=False)
    assert result['decision'] == 'hold'
    assert result['confirmed'] is False
    assert any('Confirmation repeat missing' in r for r in result['reasons'])


def test_promotion_rejects_a_repeat_that_disagrees_in_direction():
    result = halving.promotion_decision(deltas(4, 1), deltas(0, 2), latency_gate_ok=True,
                                        deterministic_output=False)
    assert result['decision'] == 'reject'
    assert any('disagrees in direction' in r for r in result['reasons'])


def test_promotion_records_the_repeated_run_determinism_branch():
    result = halving.promotion_decision(deltas(4, 1), deltas(3, 1), latency_gate_ok=True,
                                        deterministic_output=False)
    assert result['decision'] == 'promote'
    assert result['confirmed'] is True
    branch = [r for r in result['reasons'] if r.startswith('determinism branch:')]
    assert len(branch) == 1
    assert 'agreeing confirmation repeat is required' in branch[0]


def test_promotion_records_the_single_run_determinism_branch():
    result = halving.promotion_decision(deltas(4, 1), None, latency_gate_ok=True,
                                        deterministic_output=True)
    assert result['decision'] == 'promote'
    assert result['confirmed'] is True
    branch = [r for r in result['reasons'] if r.startswith('determinism branch:')]
    assert len(branch) == 1
    assert 'established empirically' in branch[0]


def test_a_truthy_non_true_determinism_claim_does_not_take_the_single_run_branch():
    result = halving.promotion_decision(deltas(4, 1), None, latency_gate_ok=True,
                                        deterministic_output='probably')
    assert result['decision'] == 'hold'
    assert any('not established' in r for r in result['reasons'])


def test_promotion_rejects_a_failed_or_unknown_latency_gate():
    failed = halving.promotion_decision(deltas(5, 0), deltas(5, 0), latency_gate_ok=False,
                                        deterministic_output=True)
    assert failed['decision'] == 'reject'
    assert any('Latency gate not satisfied' in r for r in failed['reasons'])

    unknown = halving.promotion_decision(deltas(5, 0), deltas(5, 0), latency_gate_ok=None,
                                         deterministic_output=True)
    assert unknown['decision'] == 'reject'
    assert any('unknown is not a pass' in r for r in unknown['reasons'])


def test_promotion_rejects_unknown_development_deltas():
    result = halving.promotion_decision(None, deltas(5, 0), latency_gate_ok=True,
                                        deterministic_output=True)
    assert result['decision'] == 'reject'
    assert result['net'] is None


def test_s2_evidence_can_never_reach_a_promotion():
    # Both halves of the guarantee: the S2 evaluator has no promote in its
    # vocabulary, and an S2 tagged summary is refused by the promotion rule.
    assert 'promote' not in halving.ELIMINATION_OUTCOMES
    assert 'S2' not in halving.PROMOTION_EVIDENCE_STAGES

    result = halving.promotion_decision(deltas(9, 0, stage='S2'), deltas(9, 0, stage='S5'),
                                        latency_gate_ok=True, deterministic_output=True)
    assert result['decision'] == 'reject'
    assert any('stage S2 cannot support a promotion' in r for r in result['reasons'])

    smuggled = halving.promotion_decision(deltas(9, 0, stage='S4'), deltas(9, 0, stage='S2'),
                                          latency_gate_ok=True, deterministic_output=False)
    assert smuggled['decision'] == 'reject'


def test_stage_tagged_promotion_evidence_is_accepted():
    result = halving.promotion_decision(deltas(4, 0, stage='S4'), deltas(3, 0, stage='S5'),
                                        latency_gate_ok=True, deterministic_output=False)
    assert result['decision'] == 'promote'
