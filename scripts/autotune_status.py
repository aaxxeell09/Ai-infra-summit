"""Read-only view of a TurboLab session. Never writes, never schedules.

It exists so an operator can look at a running session without touching it. A
status command that could modify state would be one more way for a session to
change while nobody is watching, so this one opens the file, prints, and exits.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turbo.optimizer import report, state as state_module

NOT_MEASURED = 'not measured'


def _rounded(value, places=2):
    """Round for display only. None stays None so it prints as not measured."""
    return None if value is None else round(value, places)


def _value(value, suffix=''):
    return NOT_MEASURED if value is None else (str(value) + suffix)


def rows(state):
    timing = state.get('timing', {})
    counters = state.get('counters', {})
    busy, idle = timing.get('hardware_busy_s'), timing.get('hardware_idle_s')
    budget_minutes = state.get('budget_minutes')
    elapsed = state.get('elapsed_seconds')
    remaining = (budget_minutes - elapsed / 60.0
                 if budget_minutes is not None and elapsed is not None else None)
    control = state.get('current_control') or {}
    llm_counters = state.get('llm') or {}
    queued = len(state.get('queue_snapshot', {}).get('entries', [])
                 if isinstance(state.get('queue_snapshot'), dict) else [])
    return [
        ('SESSION', state.get('session_id', 'unknown')),
        ('BACKEND', state.get('backend', 'unknown')),
        ('SPLIT', state.get('split', 'unknown')),
        ('TIME LEFT', _value(None if remaining is None else round(remaining, 1), ' min')),
        ('CURRENT CONTROL', str(control.get('name', 'unknown'))),
        ('CONTROL EXPERIMENT', str(control.get('experiment_id') or 'unknown')),
        ('HARDWARE BUSY', _value(None if busy is None else round(busy, 1), ' s')),
        ('HARDWARE IDLE', _value(None if idle is None else round(idle, 1), ' s')),
        ('HARDWARE UTILISATION', _value(_rounded(report.utilisation(busy, idle)), ' %')),
        ('QUEUE LENGTH', str(queued)),
        ('GENERATED', str(counters.get('generated', 0))),
        ('STATIC REJECTED', str(counters.get('static_rejected', 0))),
        ('S1', str(counters.get('S1', 0))),
        ('S2', str(counters.get('S2', 0))),
        ('S3', str(counters.get('S3', 0))),
        ('DEV35', str(counters.get('S4', 0))),
        ('CONFIRMATIONS', str(counters.get('S5', 0))),
        ('PROMOTIONS', str(counters.get('promotions', 0))),
        ('LLM PROPOSER CALLS', str(llm_counters.get('LLM_PROPOSER_CALLS', 0))),
        ('LLM CRITIC CALLS', str(llm_counters.get('LLM_CRITIC_CALLS', 0))),
        ('LLM HYPOTHESES', str(llm_counters.get('LLM_HYPOTHESES', 0))),
        ('LLM ADMISSIBLE', str(llm_counters.get('LLM_ADMISSIBLE_HYPOTHESES', 0))),
        ('LLM REJECTED', str(llm_counters.get('LLM_REJECTED_HYPOTHESES', 0))),
        ('LLM API WAIT', _value(llm_counters.get('LLM_API_WAIT_SECONDS'), ' s')),
        ('ENERGY COMMISSIONED', 'yes' if state.get('energy_commissioned') else 'no'),
        ('FINISHED', str(state.get('finished_at') or 'no')),
    ]


def render(state):
    width = max(len(label) for label, _ in rows(state))
    return '\n'.join(label.ljust(width) + '  ' + value for label, value in rows(state))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('session', nargs='?', type=Path,
                   default=state_module.DEFAULT_HOME / 'session.json')
    p.add_argument('--json', action='store_true', help='Emit the rows as JSON')
    args = p.parse_args(argv)
    if not args.session.exists():
        p.error('No session at ' + str(args.session))
    try:
        state = state_module.load(args.session)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
        return 2
    if args.json:
        print(json.dumps(dict(rows(state)), indent=2))
    else:
        print(render(state))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
