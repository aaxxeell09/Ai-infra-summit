"""Record and classify offline research; export ideas, never hardware jobs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.research_inbox import STATUSES, add_finding, classify_finding, export_ready_ideas, list_findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('add')
    add.add_argument('--file', type=Path, required=True)
    commands.add_parser('list')
    classify = commands.add_parser('classify')
    classify.add_argument('finding_id')
    classify.add_argument('status', choices=sorted(STATUSES))
    classify.add_argument('--reason', required=True)
    export = commands.add_parser('export-ready')
    export.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'add':
            result = add_finding(args.inbox, json.loads(args.file.read_text(encoding='utf-8')))
        elif args.command == 'list':
            result = list_findings(args.inbox)
        elif args.command == 'classify':
            result = classify_finding(args.inbox, args.finding_id, args.status, args.reason)
        else:
            result = export_ready_ideas(args.inbox, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
