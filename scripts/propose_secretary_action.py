"""Print an opt-in diagnostic action proposal without execution or inference."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.experiments import read_json
from turbo.secretary_proposal import propose


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--inventory', required=True, type=Path, help='Local JSON array of relative filenames')
    parser.add_argument('--enable-candidate', action='store_true', help='Explicit diagnostic opt-in; never executes the proposal')
    args = parser.parse_args(argv)
    try:
        result = propose(args.prompt, read_json(args.inventory), enabled=args.enable_candidate)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
