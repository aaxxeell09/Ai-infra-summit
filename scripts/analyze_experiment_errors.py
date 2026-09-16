"""Write local development-only failure evidence from one verified archive."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.experiment_analysis import error_analysis, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True,
                        help='New local .md or .json report; raw output is not printed')
    args = parser.parse_args(argv)
    try:
        result = error_analysis(args.archive)
        path = write_report(args.output, result, [args.archive])
    except (ValueError, OSError, AttributeError, TypeError, KeyError, OverflowError) as exc:
        parser.error(str(exc))
    print('Saved development-only failure diagnostics:', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
