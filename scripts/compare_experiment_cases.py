"""Write local development-only fixed/regressed action diagnostics from verified archives."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.experiment_analysis import case_comparison, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New local report; raw output is never printed to stdout')
    args = parser.parse_args(argv)
    try:
        report = case_comparison(args.left, args.right)
        path = write_report(args.output, report, [args.left, args.right])
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print('Saved development-only case diagnostics:', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
