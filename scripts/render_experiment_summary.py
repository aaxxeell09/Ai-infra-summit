"""Render verified experiment KPIs and descriptive comparisons; never choose a winner."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.experiments import DEFAULT_ARCHIVES, archives
from turbo.experiment_analysis import summary, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='*', type=Path)
    parser.add_argument('--root', type=Path, default=DEFAULT_ARCHIVES)
    parser.add_argument('--output', type=Path, required=True, help='New local .json or .md file outside archives')
    args = parser.parse_args(argv)
    sources = args.archives or archives(args.root)
    if not sources:
        parser.error('No experiment archives found')
    try:
        report = summary(sources)
        path = write_report(args.output, report, sources)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print('Saved verified experiment report:', path)
    return 2 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
