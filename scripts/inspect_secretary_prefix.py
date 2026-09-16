"""Measure static Secretary prompt bytes; token counts require the actual tokenizer."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.secretary_adapter import SecretaryAdapter
from turbo.secretary import TOOLS


def inspect_prefix(files):
    adapter = SecretaryAdapter(files)
    full = adapter.instructions()
    inventory = '\n'.join(adapter.files)
    # Instructions end in the inventory; preserve exact existing bytes.
    system = full[:-len(inventory)] if inventory else full
    schema = json.dumps(TOOLS, ensure_ascii=False, separators=(',', ':'))
    def describe(text):
        raw = text.encode('utf-8')
        return {'characters': len(text), 'utf8_bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'tokens': None}
    return {'evidence': 'STATIC_CODE_EVIDENCE', 'system_without_inventory': describe(system),
            'inventory': describe(inventory), 'system_with_inventory': describe(full),
            'tool_schema_canonical_json': describe(schema), 'inventory_entries': len(adapter.files),
            'token_count_status': 'UNKNOWN: actual backend tokenizer and chat template required',
            'schema_serialization': 'Diagnostic canonical JSON; not claimed native chat serialization',
            'user_tokens': None, 'heldout_inspected': False,
            'cache_support': 'UNKNOWN: reset=False exists but safe prefix reuse is not established',
            'frozen_runner_reset_per_case': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to(ROOT/'eval') or output.is_relative_to(ROOT/'benchmarks/results'):
        parser.error('Use a new local diagnostic output outside frozen evidence')
    data = inspect_prefix(json.loads((ROOT/'eval/fixtures/files.json').read_text(encoding='utf-8')))
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except OSError as exc:
        parser.error(str(exc))
    print('Saved static prompt evidence:', output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
