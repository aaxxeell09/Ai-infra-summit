"""One bounded inference through the existing NativeModel; no Secretary changes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.native import NativeRuntime, NativeModel, backend_options
from turbo.tuning import _sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--prompt', default='Reply with the single word hello.')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    try:
        backend_options(config.get('backend'), config.get('plugin'), config.get('device'), config.get('model_path'))
        if not config.get('sdk_dir') or not config.get('model_path'):
            raise ValueError('sdk_dir and model_path must be configured')
    except ValueError as exc:
        parser.error(str(exc))
    # Same existing artifact fingerprint as the tuner; no model download here.
    model_hash = _sha256(config['model_path'])
    runtime = NativeRuntime(config['sdk_dir'])
    try:
        kwargs = {k: config[k] for k in ('backend', 'plugin', 'device', 'context', 'threads',
                  'threads_batch', 'n_batch', 'ubatch', 'spec_type', 'draft_tokens') if k in config}
        with NativeModel(runtime, config['model_path'], **kwargs) as model:
            result = model.chat([{'role': 'user', 'content': args.prompt}], max_tokens=16,
                                temperature=0, reset=True)
            result['model_sha256'] = model_hash
            print(json.dumps(result, indent=2))
    finally:
        runtime.close()


if __name__ == '__main__':
    main()
