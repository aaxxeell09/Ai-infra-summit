"""Create or verify a development-only offline repeated experiment plan; never run hardware."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.campaign_plan import plan, verify_plan, write_plan
from turbo.experiments import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path, help='Verify an existing plan and every config byte hash; no execution')
    parser.add_argument('--control-name', default='control')
    parser.add_argument('--control-config', type=Path)
    parser.add_argument('--candidate', nargs=4, action='append', default=[], metavar=('NAME', 'CONFIG', 'VARIABLE', 'HYPOTHESIS'))
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if args.output or args.control_config or args.candidate:
                parser.error('--verify cannot be combined with plan creation inputs')
            print(json.dumps(verify_plan(read_json(args.verify)), indent=2))
            return 0
        if not args.control_config or not args.output:
            parser.error('--control-config and --output are required to create a plan')
        candidates = [dict(name=n, config=c, variable=v, hypothesis=h) for n, c, v, h in args.candidate]
        result = plan(args.control_name, args.control_config, candidates, args.repetitions)
        path = write_plan(args.output, result)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(f'Saved offline plan ({len(result["runs"])} development trials): {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
