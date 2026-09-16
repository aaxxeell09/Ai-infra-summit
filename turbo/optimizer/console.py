"""Single-line session logging an operator can still read six hours later.

A bounded autotune session emits thousands of events overnight. A multi-line,
prose-shaped log buries the three lines that mattered, and a log that prints a
zero where nothing was measured invents evidence that the session never had.
Every event here is exactly one line, the columns land in the same place so one
family or one candidate can be followed down the page by eye, and any value the
caller did not supply prints as the literal 'unknown' rather than as 0, as an
empty column, or as a confident guess.

Timestamps are UTC, matching turbo/optimizer/state.py, so a log line and a state
record describe the same instant without a timezone argument between them.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = 'local-turbo.autotune-console.v1'

#: What a missing value renders as. Never 0, never a blank column.
UNKNOWN = 'unknown'

KIND_WIDTH = 5
SUBJECT_WIDTH = 10
#: Counts are right justified so the digits of consecutive lines stack up.
COUNT_WIDTH = 3

#: Stage label mapping, kind column.
#:   S0 static generation and admission (no hardware)
#:   S1 load and single smoke case
#:   S2 small screening subset
#:   S3 larger screening subset
#:   S4 the full 35 case development split, logged as DEV35 because "S4" alone
#:      does not tell a reader at 03:00 how many cases backed the number
#:   S5 repeat confirmation of a surviving candidate
STAGE_LABELS = {'S0': 'S0', 'S1': 'S1', 'S2': 'S2', 'S3': 'S3', 'S4': 'DEV35', 'S5': 'CONFIRM'}

#: Colour is a reading aid on a terminal, never part of the record. Capture the
#: stream instead of the terminal and you get these same lines with no escapes.
ANSI = {'GUARD': '\x1b[2m', 'PROMO': '\x1b[32m', 'CONTROL': '\x1b[36m',
        'WARN': '\x1b[33m', 'ERROR': '\x1b[31m'}
RESET = '\x1b[0m'


def _text(value):
    return UNKNOWN if value is None else str(value)


def _count(value, width):
    """Right justified count, or 'unknown'. The value is printed as supplied."""
    return UNKNOWN if value is None else str(value).rjust(width)


def _is_tty(stream):
    """A stream that cannot answer is treated as not a terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _colour_enabled(stream, colour):
    if colour is False:
        return False
    return _is_tty(stream)


class Console:
    """Aligned, one-event-per-line logger.

    ``colour=None`` means auto: colour appears only on a terminal. ``True``
    requests colour but is still refused on a non-tty, because a redirected log
    or a captured test output must contain no escape sequences. ``False``
    disables it everywhere.

    ``clock`` returns epoch seconds and exists so a test can freeze time; the
    console never reads the clock for anything but the timestamp column.
    """

    def __init__(self, stream=sys.stdout, *, clock=time.time, colour=None):
        self.stream = stream
        self.clock = clock
        self.colour = _colour_enabled(stream, colour)

    def timestamp(self):
        return datetime.fromtimestamp(float(self.clock()), timezone.utc).strftime('[%H:%M:%S]')

    def _emit(self, body, kind=None):
        line = (self.timestamp() + ' ' + body).rstrip()
        painted = line
        if self.colour and ANSI.get(kind):
            painted = ANSI[kind] + line + RESET
        self.stream.write(painted + '\n')
        flush = getattr(self.stream, 'flush', None)
        if flush is not None:
            flush()
        return line

    def line(self, text):
        """Anything that does not fit the grid, timestamped and nothing else."""
        return self._emit(_text(text))

    def event(self, kind, subject, detail):
        """One gridded line: kind column, subject column, free-form detail."""
        body = (_text(kind).ljust(KIND_WIDTH) + ' ' + _text(subject).ljust(SUBJECT_WIDTH)
                + ' ' + _text(detail))
        return self._emit(body, _text(kind))

    def generated(self, family, count):
        return self.event('GEN', family, _count(count, COUNT_WIDTH) + ' candidates')

    def guard(self, family, accepted, rejected):
        # Only the accepted count is padded: it is the number a reader scans down
        # the page, and padding the second one too would push 'rejected' around.
        return self.event('GUARD', family, _count(accepted, COUNT_WIDTH) + ' accepted / '
                          + _count(rejected, 0) + ' rejected')

    def stage(self, stage, candidate_id, detail):
        """Log a stage outcome. An unmapped stage name is printed verbatim."""
        return self.event(STAGE_LABELS.get(stage, _text(stage)), candidate_id, detail)

    def promotion(self, candidate_id, detail):
        return self.event('PROMO', candidate_id, detail)

    def control(self, old, new):
        """Control changes are rare and deliberately break the column grid."""
        return self._emit('CONTROL ' + _text(old) + ' -> ' + _text(new), 'CONTROL')

    def warn(self, message):
        return self._emit('WARN'.ljust(KIND_WIDTH) + ' ' + _text(message), 'WARN')

    def error(self, message):
        return self._emit('ERROR'.ljust(KIND_WIDTH) + ' ' + _text(message), 'ERROR')
