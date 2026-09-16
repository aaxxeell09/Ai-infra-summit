"""Hardware queue tests: ordering, the single claim, recovery and grouping."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import hardware_queue as hq

FAMILY = {'attempted': 0, 'survived_s2': 0}


def candidate(name, **overrides):
    base = {'candidate_id': name, 'family': 'output_budget', 'variable': 'max_tokens',
            'stage': 'S2', 'config': {'max_tokens': 64}}
    base.update(overrides)
    return base


def test_priority_is_bounded_and_a_float():
    for stage in ('S1', 'S2', 'S3', 'S4', 'S5'):
        for phase in ('explore', 'focus', 'confirm_only', 'closing'):
            score = hq.priority(candidate('c', stage=stage), family_stats=FAMILY, phase=phase)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0


def test_priority_honours_the_phase_stage_policy():
    explore = hq.priority(candidate('c', stage='S1'), family_stats=FAMILY, phase='explore')
    closing = hq.priority(candidate('c', stage='S1'), family_stats=FAMILY, phase='closing')
    assert explore > 0.0
    assert closing == 0.0, 'the closing window may only run a confirmation'
    assert hq.priority(candidate('c', stage='S5'), family_stats=FAMILY, phase='closing') > 0.0


def test_an_undeclared_stage_cannot_be_scheduled():
    unstaged = candidate('c')
    unstaged.pop('stage')
    assert hq.priority(unstaged, family_stats=FAMILY, phase='explore') == 0.0


def test_an_unknown_hardware_cost_is_the_declared_default_not_free():
    unknown = hq.priority(candidate('unknown'), family_stats=FAMILY, phase='explore')
    declared = hq.priority(candidate('declared', estimated_seconds=hq.DEFAULT_HARDWARE_SECONDS),
                           family_stats=FAMILY, phase='explore')
    cheap = hq.priority(candidate('cheap', estimated_seconds=1.0),
                        family_stats=FAMILY, phase='explore')
    assert unknown == declared
    assert unknown < cheap, 'an unknown cost must not outrank a genuinely cheap job'


def test_a_restart_adds_the_reload_cost_and_an_unknown_reload_is_the_default():
    hot = candidate('hot', variable='max_tokens')
    cold = candidate('cold', variable='threads', config={'threads': 8})
    assert hq.requires_restart(hot) is False
    assert hq.requires_restart(cold) is True

    hot_score = hq.priority(hot, family_stats=FAMILY, phase='explore')
    cold_score = hq.priority(cold, family_stats=FAMILY, phase='explore')
    assert cold_score < hot_score

    defaulted = hq.priority(cold, family_stats=FAMILY, phase='explore', reload_cost_s=None)
    explicit = hq.priority(cold, family_stats=FAMILY, phase='explore',
                           reload_cost_s=hq.DEFAULT_RELOAD_SECONDS)
    assert defaulted == explicit


def test_an_unrecognised_variable_is_assumed_to_need_a_restart():
    assert hq.requires_restart({'variable': 'no_such_knob'}) is True
    assert hq.requires_restart({}) is True
    assert hq.requires_restart('not a candidate') is True
    assert hq.requires_restart({'variable': 'max_tokens', 'requires_restart': True}) is True


def test_an_unexplored_family_outranks_a_well_mapped_one():
    fresh = hq.priority(candidate('c'), family_stats={'attempted': 0, 'survived_s2': 0},
                        phase='explore')
    mapped = hq.priority(candidate('c'), family_stats={'attempted': 8, 'survived_s2': 4},
                         phase='explore')
    assert fresh > mapped


def test_risk_and_impact_move_the_score_in_the_expected_direction():
    plain = hq.priority(candidate('c'), family_stats=FAMILY, phase='explore')
    risky = hq.priority(candidate('c', implementation_risk=1.0), family_stats=FAMILY,
                        phase='explore')
    valuable = hq.priority(candidate('c', impact=1.0), family_stats=FAMILY, phase='explore')
    assert risky < plain < valuable


def test_priority_refuses_a_non_object_candidate():
    with pytest.raises(ValueError):
        hq.priority('c', family_stats=FAMILY, phase='explore')


def test_queue_pops_highest_priority_first():
    queue = hq.HardwareQueue()
    queue.push(candidate('low'), 0.1)
    queue.push(candidate('high'), 0.9)
    queue.push(candidate('mid'), 0.5)
    assert len(queue) == 3
    assert queue.peek()['candidate_id'] == 'high'
    assert [queue.pop()['candidate_id'] for _ in range(3)] == ['high', 'mid', 'low']
    assert len(queue) == 0
    assert queue.pop() is None
    assert queue.peek() is None


def test_equal_priorities_are_first_in_first_out():
    queue = hq.HardwareQueue()
    for name in ('a', 'b', 'c', 'd'):
        queue.push(candidate(name), 0.5)
    queue.push(candidate('winner'), 0.6)
    assert [c['candidate_id'] for c in queue.drain()] == ['winner', 'a', 'b', 'c', 'd']
    assert len(queue) == 0


def test_push_refuses_a_non_numeric_priority():
    queue = hq.HardwareQueue()
    for bad in (None, 'high', True):
        with pytest.raises(ValueError):
            queue.push(candidate('c'), bad)


def test_only_one_candidate_can_be_claimed_at_a_time():
    queue = hq.HardwareQueue()
    first, second = candidate('first'), candidate('second')
    assert queue.active is None
    queue.claim(first)
    assert queue.active is first
    with pytest.raises(RuntimeError):
        queue.claim(second)
    assert queue.active is first


def test_release_frees_the_slot_for_the_next_claim():
    queue = hq.HardwareQueue()
    first, second = candidate('first'), candidate('second')
    queue.claim(first)
    assert queue.release(first) is first
    assert queue.active is None
    queue.claim(second)
    assert queue.active is second


def test_release_refuses_an_empty_or_mismatched_claim():
    queue = hq.HardwareQueue()
    with pytest.raises(RuntimeError):
        queue.release(candidate('nobody'))
    queue.claim(candidate('first'))
    with pytest.raises(RuntimeError):
        queue.release(candidate('other'))
    assert queue.active['candidate_id'] == 'first'


def test_snapshot_restore_preserves_pop_order_and_the_claim():
    queue = hq.HardwareQueue()
    queue.push(candidate('a'), 0.5)
    queue.push(candidate('b'), 0.9)
    queue.push(candidate('c'), 0.5)
    queue.claim(candidate('running'))
    snapshot = queue.snapshot()
    assert [e['candidate']['candidate_id'] for e in snapshot['entries']] == ['b', 'a', 'c']

    recovered = hq.HardwareQueue()
    assert recovered.restore(snapshot) is recovered
    assert len(recovered) == 3
    assert recovered.active['candidate_id'] == 'running'
    assert [c['candidate_id'] for c in recovered.drain()] == ['b', 'a', 'c']


def test_a_restored_queue_keeps_issuing_fresh_sequence_numbers():
    queue = hq.HardwareQueue()
    queue.push(candidate('a'), 0.5)
    queue.push(candidate('b'), 0.5)
    recovered = hq.HardwareQueue().restore(queue.snapshot())
    recovered.push(candidate('late'), 0.5)
    assert [c['candidate_id'] for c in recovered.drain()] == ['a', 'b', 'late']


def test_restore_refuses_a_foreign_or_malformed_snapshot():
    queue = hq.HardwareQueue()
    with pytest.raises(ValueError):
        queue.restore({'schema_version': 'other', 'entries': []})
    with pytest.raises(ValueError):
        queue.restore({'schema_version': hq.SCHEMA})
    with pytest.raises(ValueError):
        queue.restore({'schema_version': hq.SCHEMA, 'entries': [{'priority': 1.0}]})
    with pytest.raises(ValueError):
        queue.restore(['not', 'an', 'object'])


def test_grouping_clusters_candidates_that_share_a_restart_state():
    eight = candidate('t8', variable='threads', config={'threads': 8})
    eight_again = candidate('t8b', variable='threads', config={'threads': 8})
    four = candidate('t4', variable='threads', config={'threads': 4})
    groups = hq.group_by_runtime_state([eight, four, eight_again])
    assert [[c['candidate_id'] for c in group] for group in groups] == [['t8', 't8b'], ['t4']]


def test_grouping_separates_restart_free_candidates_from_restart_ones():
    hot_a = candidate('hot_a', variable='max_tokens', config={'max_tokens': 64})
    hot_b = candidate('hot_b', variable='max_tokens', config={'max_tokens': 128})
    cold = candidate('cold', variable='context', config={'context': 2048})
    groups = hq.group_by_runtime_state([hot_a, cold, hot_b])
    assert [[c['candidate_id'] for c in group] for group in groups] == [['hot_a', 'hot_b'], ['cold']]


def test_grouping_separates_values_that_only_compare_equal_by_coincidence():
    zero = candidate('zero', variable='threads', config={'threads': 0})
    off = candidate('off', variable='threads', config={'threads': False})
    assert zero['config']['threads'] == off['config']['threads']
    groups = hq.group_by_runtime_state([zero, off])
    assert len(groups) == 2, '0 and False are the same value but not the same runtime state'


def test_grouping_preserves_every_candidate_exactly_once():
    candidates = [candidate('a', variable='threads', config={'threads': 2}),
                  candidate('b', variable='threads', config={'threads': 2}),
                  candidate('c', variable='ubatch', config={'ubatch': 128}),
                  candidate('d')]
    groups = hq.group_by_runtime_state(candidates)
    flattened = [c for group in groups for c in group]
    assert len(flattened) == len(candidates)
    assert {c['candidate_id'] for c in flattened} == {'a', 'b', 'c', 'd'}


def test_grouping_an_empty_backlog_is_empty():
    assert hq.group_by_runtime_state([]) == []


def test_restart_keys_come_from_the_search_space_registry():
    keys = hq.restart_keys()
    assert 'threads' in keys and 'context' in keys
    assert 'max_tokens' not in keys
