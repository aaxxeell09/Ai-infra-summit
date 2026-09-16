"""Budget policy tests. The clock is injected, so nothing here sleeps."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer.budget import (CONFIRM_FLOOR, EXPLORE_FLOOR, FOCUS_FLOOR, PHASES, Budget,
                                    stage_mix)


class FakeClock:
    """Monotonic only because the test advances it; never wall clock."""

    def __init__(self, start=1000.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)
        return self.now


def budget(total_minutes=120, start=1000.0):
    clock = FakeClock(start)
    return Budget(total_minutes, clock=clock), clock


def test_fresh_budget_is_exploring():
    session, _ = budget()
    assert session.phase() == 'explore'
    assert session.remaining_minutes == 120.0
    assert session.elapsed_s == 0.0
    assert session.exhausted is False


def test_phase_boundaries_at_exact_fractions_of_120():
    session, clock = budget()
    clock.advance(59 * 60)
    assert session.remaining_minutes == 61.0
    assert session.phase() == 'explore'

    clock.advance(60)
    assert session.remaining_minutes == 60.0
    assert session.phase() == 'focus', 'the boundary belongs to the later phase'

    clock.advance(39 * 60 + 59)
    assert session.phase() == 'focus'
    clock.advance(1)
    assert session.remaining_minutes == 20.0
    assert session.phase() == 'confirm_only'

    clock.advance(9 * 60 + 59)
    assert session.phase() == 'confirm_only'
    clock.advance(1)
    assert session.remaining_minutes == 10.0
    assert session.phase() == 'closing'


def test_phase_boundaries_scale_to_a_non_120_budget():
    session, clock = budget(30)
    assert session.phase() == 'explore'
    clock.advance(15 * 60)
    assert session.remaining_minutes == 15.0
    assert session.phase() == 'focus'
    clock.advance(10 * 60)
    assert session.remaining_minutes == 5.0
    assert session.phase() == 'confirm_only'
    clock.advance(2 * 60 + 30)
    assert session.remaining_minutes == 2.5
    assert session.phase() == 'closing'


def test_boundary_fractions_are_the_documented_ones():
    assert (EXPLORE_FLOOR, FOCUS_FLOOR, CONFIRM_FLOOR) == (0.5, 1 / 6, 1 / 12)
    session, clock = budget(7.5)
    clock.advance(7.5 * 60 * (1 - EXPLORE_FLOOR))
    assert session.phase() == 'focus'


def test_exhaustion_clamps_and_never_reports_negative_remaining():
    session, clock = budget(10)
    clock.advance(10 * 60 + 500)
    assert session.remaining_s == 0.0
    assert session.remaining_minutes == 0.0
    assert session.exhausted is True
    assert session.phase() == 'closing'
    assert session.elapsed_s == 1100.0


def test_a_clock_that_moves_backwards_does_not_create_budget():
    session, clock = budget(10)
    clock.advance(-500)
    assert session.elapsed_s == 0.0
    assert session.remaining_minutes == 10.0


def test_can_start_refuses_an_unknown_cost():
    session, _ = budget()
    assert session.can_start(None) is False
    assert session.can_start(None, allow_unknown=True) is True


def test_can_start_refuses_work_that_would_overrun():
    session, clock = budget(10)
    clock.advance(9 * 60)
    assert session.remaining_s == 60.0
    assert session.can_start(60) is True
    assert session.can_start(60.5) is False
    assert session.can_start(0) is True


def test_can_start_refuses_nonsense_estimates_and_an_exhausted_budget():
    session, clock = budget(10)
    assert session.can_start(-1) is False
    assert session.can_start('120') is False
    assert session.can_start(True) is False
    clock.advance(10 * 60)
    assert session.can_start(1) is False
    assert session.can_start(None, allow_unknown=True) is False


def test_snapshot_restore_round_trip_across_a_fake_clock():
    session, clock = budget()
    clock.advance(70 * 60)
    snapshot = session.snapshot()
    assert snapshot['phase'] == 'focus'
    assert snapshot['elapsed_seconds'] == 4200.0
    assert snapshot['budget_minutes'] == 120.0

    resumed_clock = FakeClock(5.0)
    resumed = Budget(120, clock=resumed_clock)
    assert resumed.phase() == 'explore'
    assert resumed.restore(snapshot) is resumed
    assert resumed.elapsed_s == 4200.0
    assert resumed.remaining_minutes == 50.0
    assert resumed.phase() == 'focus'

    resumed_clock.advance(31 * 60)
    assert resumed.remaining_minutes == 19.0
    assert resumed.phase() == 'confirm_only'


def test_restore_refuses_a_foreign_or_broken_snapshot():
    session, _ = budget()
    with pytest.raises(ValueError):
        session.restore({'schema_version': 'something-else', 'elapsed_seconds': 1.0})
    with pytest.raises(ValueError):
        session.restore({'schema_version': session.snapshot()['schema_version']})
    with pytest.raises(ValueError):
        session.restore({'schema_version': session.snapshot()['schema_version'],
                         'elapsed_seconds': -1.0})
    with pytest.raises(ValueError):
        session.restore('not an object')


def test_restore_keeps_the_live_budget_when_a_resume_declares_a_new_one():
    session, clock = budget(120)
    clock.advance(60 * 60)
    snapshot = session.snapshot()
    shorter = Budget(80, clock=FakeClock())
    shorter.restore(snapshot)
    assert shorter.total_minutes == 80.0
    assert shorter.remaining_minutes == 20.0


def test_construction_refuses_a_nonpositive_or_non_numeric_budget():
    for bad in (0, -5, None, 'ten', True):
        with pytest.raises(ValueError):
            Budget(bad)


def test_stage_mix_weights_are_bounded_heuristics():
    for phase in PHASES:
        mix = stage_mix(phase)
        assert set(mix) == {'S1', 'S2', 'S3', 'S4', 'S5'}
        assert all(0.0 <= weight <= 1.0 for weight in mix.values())


def test_stage_mix_follows_the_phase_policy():
    explore = stage_mix('explore')
    assert min(explore['S1'], explore['S2']) > max(explore['S3'], explore['S4'], explore['S5'])

    focus = stage_mix('focus')
    assert min(focus['S3'], focus['S4']) > max(focus['S1'], focus['S2'], focus['S5'])

    confirm = stage_mix('confirm_only')
    assert confirm['S1'] == confirm['S2'] == confirm['S3'] == 0.0
    assert confirm['S4'] > 0.0 and confirm['S5'] > 0.0

    closing = stage_mix('closing')
    assert [name for name, weight in closing.items() if weight > 0.0] == ['S5']


def test_stage_mix_table_cannot_be_mutated_through_a_returned_reference():
    stage_mix('closing')['S1'] = 1.0
    assert stage_mix('closing')['S1'] == 0.0


def test_stage_mix_refuses_an_unknown_phase():
    with pytest.raises(ValueError):
        stage_mix('cruising')


def test_budget_exposes_the_mix_for_its_own_phase():
    session, clock = budget(120)
    clock.advance(115 * 60)
    assert session.phase() == 'closing'
    assert session.stage_mix() == stage_mix('closing')
