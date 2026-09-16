"""Inspect existing development outputs or export a Lane C candidate; no inference."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.clarify_diagnostic import report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-only', action='store_true', required=True)
    parser.add_argument('--result', type=Path, action='append', default=[])
    parser.add_argument('--export-candidate', choices=['prompt', 'schema', 'ambiguity-shadow'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report(args.result, args.export_candidate)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(str(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
