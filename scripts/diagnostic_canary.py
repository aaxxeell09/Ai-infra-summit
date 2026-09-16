"""Run a fixed subset of DEVELOPMENT cases as a labelled elimination signal.

The frozen runner exposes development, heldout and all, with no supported way to
ask for eight cases, and widening it for a convenience would change a contract
that every historical result depends on. So the cheap stages live here instead,
outside the frozen runner and loudly labelled.

This is not a second evaluator. It imports the frozen runner's own ``execute``
and the frozen scoring path unchanged, and only chooses fewer cases, so a canary
and a tracked run cannot disagree about what a correct answer is. What it
produces is still not a measurement: every record says DIAGNOSTIC_CANARY,
``qualified: false`` and ``promotion_evidence: false``, and no archive is
written. A candidate is eliminated here or it goes on to a tracked run; it is
never promoted from this.

Heldout is unreachable: only the development dataset file is ever loaded.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turbo.optimizer import probe

DEVELOPMENT = ROOT / 'eval/datasets/secretary_dev.json'


def load_development_cases():
    """Only ever the development file. There is no parameter to change that."""
    from eval.scoring import load_dataset
    return load_dataset([DEVELOPMENT])


def run_canary(config, *, size, seed_label, max_seconds=None):
    """Execute the chosen subset and return the labelled record plus raw rows."""
    from eval.run_secretary_eval import execute, PROTOCOL
    from eval.secretary_adapter import SecretaryAdapter, TOOLS
    from eval.validate_dataset import validate
    from turbo.native import NativeModel, NativeRuntime

    validate()
    cases = load_development_cases()
    identities = [case.get('id') or case.get('case_id') or str(index)
                  for index, case in enumerate(cases)]
    chosen = probe.fixed_subset(identities, size, seed_label=seed_label)
    selected = [case for case, identity in zip(cases, identities) if identity in set(chosen)]

    files = json.loads((ROOT / 'eval/fixtures/files.json').read_text(encoding='utf-8'))
    codec = SecretaryAdapter.from_files(files)
    runtime = NativeRuntime(config['sdk_dir'])
    started = time.perf_counter()
    try:
        kwargs = {k: config[k] for k in ('device', 'threads', 'context', 'threads_batch', 'ubatch',
                                         'n_batch', 'spec_type', 'draft_tokens', 'plugin',
                                         'backend', 'stop_after_tool_call') if k in config}
        with NativeModel(runtime, config['model_path'], **kwargs) as model:
            def complete(messages):
                return model.chat(messages, tools=TOOLS, max_tokens=config.get('max_tokens', 128),
                                  temperature=0, reset=True)
            warmup = cases[0]
            complete([{'role': 'system', 'content': codec.instructions()},
                      {'role': 'user', 'content': warmup['prompt']}])
            rows = execute(selected, codec, complete, ROOT / 'eval/fixtures/secretary_workspace')
    finally:
        runtime.close()
    elapsed = round(time.perf_counter() - started, 3)

    latencies = [row.get('warm_task_latency_ms') for row in rows]
    boundary = 'warm_task_v1: excludes fixture preparation, load and final filesystem audit'
    if any(value is None for value in latencies):
        latencies = [row.get('latency_ms') for row in rows]
        boundary = 'inference_latency_ms: generation only, not a task boundary'
    median = statistics.median(latencies) if latencies and all(
        isinstance(v, (int, float)) for v in latencies) else None

    record = probe.canary_result(
        subset=chosen, attempted=len(rows),
        correct=sum(1 for row in rows if row['task_success']),
        invalid=sum(1 for row in rows if row.get('invalid_output') is True),
        median_latency_ms=median)
    record.update(
        protocol_version=PROTOCOL,
        latency_boundary=boundary,
        median_task_latency_ms=median,
        invalid_rate=(sum(1 for row in rows if row.get('invalid_output') is True) / len(rows)
                      if rows else None),
        hardware_seconds=elapsed,
        seed_label=seed_label,
        rows=[{'case_id': row.get('case_sha256') or row.get('id'),
               'case_sha256':row.get('case_sha256'),
               'task_success': bool(row['task_success']),
               'invalid_output': row.get('invalid_output'),
               'expected_tool': row.get('expected_tool'),
               'failure_reasons': list(row.get('failure_reasons') or [])}
              for row in rows])
    if any(entry['case_id'] is None for entry in record['rows']):
        raise ValueError('A canary row carries no case identity; refusing to emit it')
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--size', type=int, required=True,
                   help='How many development cases to run; never all of them')
    p.add_argument('--seed-label', required=True,
                   help='Fixed before the session so the subset cannot adapt to results')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)

    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    reasons = probe.config_acceptable(config, config.get('backend'))
    if reasons:
        p.error('; '.join(reasons))
    if not config.get('sdk_dir') or not config.get('model_path'):
        p.error('sdk_dir and model_path must be configured for a canary')
    try:
        record = run_canary(config, size=args.size, seed_label=args.seed_label)
    except (ValueError, OSError, RuntimeError) as exc:
        p.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({k: v for k, v in record.items() if k != 'rows'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
