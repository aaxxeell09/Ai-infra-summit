"""Lane C five-repeat sampler diagnostic; fail closed without native readback."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL_OUTPUT_ROOT = ROOT / 'local'
sys.path.insert(0, str(ROOT))
from turbo.json_io import read_json
from turbo.qairt_sampler_diagnostic import blocked_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--temperature', type=float, required=True)
    parser.add_argument('--top-p', type=float, required=True)
    parser.add_argument('--top-k', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--repeats', type=int, choices=[5], default=5)
    parser.add_argument('--prompt', default='Say hello in one short word.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.suffix != '.json' or not args.output.resolve().is_relative_to(LOCAL_OUTPUT_ROOT.resolve()):
            raise ValueError('Diagnostic output must be a new .json file under ignored local/')
        if args.output.resolve() == args.config.resolve():
            raise ValueError('Output collides with the input config')
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('Refusing to overwrite existing diagnostic evidence')
        requested = {'temperature':args.temperature,'top_p':args.top_p,'top_k':args.top_k,'seed':args.seed}
        result = blocked_report(read_json(args.config, require_object=True), requested, args.prompt)
        result['config_sha256'] = hashlib.sha256(args.config.read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError, OverflowError) as exc:
        parser.error(str(exc))
    print('BLOCKED_EFFECTIVE_READBACK_UNAVAILABLE; no inference attempted. Saved:', args.output)
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
