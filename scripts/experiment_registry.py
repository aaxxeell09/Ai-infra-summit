#!/usr/bin/env python3
"""Local append-only planning registry. Does not execute or qualify experiments."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from turbo.experiment_registry import append_event, current_frontier, read_events
from turbo.json_io import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'local/experiment-registry')
    commands = parser.add_subparsers(dest='command', required=True)
    append = commands.add_parser('append')
    append.add_argument('--event', type=Path, required=True)
    commands.add_parser('frontier')
    commands.add_parser('history')
    args = parser.parse_args(argv)
    try:
        if args.command == 'append':
            result = append_event(args.root, read_json(args.event, require_object=True))
        elif args.command == 'frontier':
            result = current_frontier(args.root)
        else:
            result = read_events(args.root)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
