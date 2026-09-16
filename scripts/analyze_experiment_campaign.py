"""Summarize all archived attempts and compatible repetitions without selecting a winner."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.experiments import DEFAULT_ARCHIVES, archives
from turbo.experiment_analysis import campaign, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='*', type=Path)
    parser.add_argument('--root', type=Path, default=DEFAULT_ARCHIVES)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    sources = args.archives or archives(args.root)
    if not sources:
        parser.error('No experiment archives found')
    try:
        report = campaign(sources)
        path = write_report(args.output, report, sources)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print('Saved campaign report:', path)
    return 2 if report['integrity_failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
