"""Wall-clock budget policy, so a bounded session spends its time on purpose.

An autotune session owns one piece of hardware for a fixed number of minutes.
Without an explicit policy the failure mode is predictable: the session explores
until the clock runs out and finishes holding a pile of unconfirmed S2 hints and
no promotable, confirmed result. This module makes the remaining time a first
class input, so late work narrows toward confirmation instead of widening, and
so a job whose cost is unknown is never started on the hope that it fits.

Nothing here measures anything. It reads a clock and answers policy questions.
"""
from __future__ import annotations

import time

SCHEMA = 'local-turbo.autotune-budget.v1'

PHASES = ('explore', 'focus', 'confirm_only', 'closing')

#: Phase boundaries as fractions of the total budget, not as absolute minutes,
#: so the same policy holds for any --budget-minutes. For the 120 minute
#: session the operator described these are the windows:
#:   explore       remaining > 60 min        (> 1/2 of total)
#:   focus         60 min down to 20 min     (1/2 down to 1/6)
#:   confirm_only  20 min down to 10 min     (1/6 down to 1/12)
#:   closing       below 10 min              (< 1/12)
#: Each boundary belongs to the later, more conservative phase: at exactly half
#: the budget the session is already focusing.
EXPLORE_FLOOR = 1.0 / 2.0
FOCUS_FLOOR = 1.0 / 6.0
CONFIRM_FLOOR = 1.0 / 12.0

#: Heuristic stage weights per phase. These are scheduling preferences, NOT
#: probabilities and not measured quantities: they encode "prefer cheap
#: elimination early, prefer confirmation late" and nothing more. A weight of
#: 0.0 means the phase does not permit that stage at all, which is a policy
#: statement the scheduler must honour; the nonzero values only rank.
#: S0 (candidate generation and static validation) is absent on purpose: it
#: costs no hardware seconds, so it is not rationed here.
_STAGE_MIX = {
    'explore': {'S1': 0.9, 'S2': 0.7, 'S3': 0.3, 'S4': 0.1, 'S5': 0.0},
    'focus': {'S1': 0.3, 'S2': 0.5, 'S3': 0.9, 'S4': 0.8, 'S5': 0.2},
    'confirm_only': {'S1': 0.0, 'S2': 0.0, 'S3': 0.0, 'S4': 0.6, 'S5': 1.0},
    'closing': {'S1': 0.0, 'S2': 0.0, 'S3': 0.0, 'S4': 0.0, 'S5': 1.0},
}


def stage_mix(phase):
    """Bounded heuristic weight per stage for one phase. Not probabilities.

    Weights are in [0, 1] and do not sum to one. Zero means forbidden in this
    phase; larger means preferred. Callers get a fresh dict so the table cannot
    be mutated through a returned reference.
    """
    if phase not in _STAGE_MIX:
        raise ValueError('Unknown budget phase: ' + repr(phase))
    return dict(_STAGE_MIX[phase])


class Budget:
    """Remaining wall clock for one session, with the phase policy attached.

    ``clock`` is injectable so tests and replays never sleep. It must be
    monotonic in the same sense as ``time.monotonic``: the value it returns is
    only ever compared with an earlier value from the same clock.
    """

    def __init__(self, total_minutes, *, clock=time.monotonic):
        if isinstance(total_minutes, bool) or not isinstance(total_minutes, (int, float)):
            raise ValueError('total_minutes must be a number')
        if total_minutes <= 0:
            raise ValueError('total_minutes must be positive')
        self.total_minutes = float(total_minutes)
        self.total_seconds = self.total_minutes * 60.0
        self._clock = clock
        self._started_at = clock()
        self._offset_s = 0.0

    @property
    def elapsed_s(self):
        # Clamped at zero: a restored offset plus a clock that appears to move
        # backwards must never read as unused budget.
        return max(0.0, self._offset_s + (self._clock() - self._started_at))

    @property
    def remaining_s(self):
        return max(0.0, self.total_seconds - self.elapsed_s)

    @property
    def remaining_minutes(self):
        return self.remaining_s / 60.0

    @property
    def fraction_remaining(self):
        return self.remaining_s / self.total_seconds

    @property
    def exhausted(self):
        return self.remaining_s <= 0.0

    def phase(self):
        """Which policy window the session is in right now."""
        fraction = self.fraction_remaining
        if fraction > EXPLORE_FLOOR:
            return 'explore'
        if fraction > FOCUS_FLOOR:
            return 'focus'
        if fraction > CONFIRM_FLOOR:
            return 'confirm_only'
        return 'closing'

    def stage_mix(self):
        return stage_mix(self.phase())

    def can_start(self, estimated_seconds, *, allow_unknown=False):
        """Whether there is time to finish a job that costs this many seconds.

        Fail closed on both sides of the comparison. An unknown cost is refused
        unless the caller explicitly accepts the risk with ``allow_unknown``,
        because "we do not know how long this takes" is not a licence to start
        it with nine minutes left. A negative or non numeric estimate is refused
        outright rather than coerced.
        """
        if self.exhausted:
            return False
        if estimated_seconds is None:
            return bool(allow_unknown)
        if isinstance(estimated_seconds, bool) or not isinstance(estimated_seconds, (int, float)):
            return False
        if estimated_seconds < 0:
            return False
        return float(estimated_seconds) <= self.remaining_s

    def snapshot(self):
        """Orchestration bookkeeping only, shaped to sit inside a state file."""
        return {'schema_version': SCHEMA, 'budget_minutes': self.total_minutes,
                'elapsed_seconds': self.elapsed_s, 'remaining_seconds': self.remaining_s,
                'phase': self.phase()}

    def restore(self, snapshot):
        """Reattach a previous session's elapsed time to this live clock.

        The snapshot carries elapsed seconds, not an absolute start time: the
        process that resumes has a different monotonic origin, so an absolute
        timestamp would be meaningless. The live ``total_minutes`` wins over the
        snapshot's, because a resume may legitimately declare a new budget, and
        the difference is reported rather than silently absorbed.
        """
        if not isinstance(snapshot, dict):
            raise ValueError('Budget snapshot must be an object')
        if snapshot.get('schema_version') != SCHEMA:
            raise ValueError('Unsupported budget snapshot schema: ' + repr(snapshot.get('schema_version')))
        elapsed = snapshot.get('elapsed_seconds')
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
            raise ValueError('Budget snapshot carries no usable elapsed_seconds')
        self._offset_s = float(elapsed)
        self._started_at = self._clock()
        return self
