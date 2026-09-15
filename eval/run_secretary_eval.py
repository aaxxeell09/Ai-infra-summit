"""Evaluate ToolWire first-action intent. No file action is ever executed."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scoring import load_dataset, score, summarize, compare, digest
from turbo.action_codec import ActionCodec

PROTOCOL = 'toolwire-first-action-v1'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def execute(cases, codec, complete):
    rows = []
    for case in cases:
        started = time.perf_counter()
        error, output = None, {}
        try:
            output = complete([
                {'role': 'system', 'content': codec.instructions()},
                {'role': 'user', 'content': case['prompt']}])
            if not isinstance(output, dict) or not isinstance(output.get('text'), str):
                raise ValueError('Completion must contain text')
        except Exception as exc:
            # Preserve error type without leaking host paths or secrets.
            error = type(exc).__name__
            output = {}
        row = score(case, output.get('text'), codec)
        row.update(latency_ms=round((time.perf_counter()-started)*1000, 3),
                   expected_tool=case['expected']['tool'], case_sha256=digest(case), execution_error=error,
                   output_text=output.get('text'), profile=output.get('profile'),
                   timings=output.get('timings'), selected_device=output.get('device'),
                   selected_route=None, routing_accuracy=None)
        if error:
            row['task_success'] = False
        rows.append(row)
    return rows


def markdown(report):
    lines = ['# Secretary correctness benchmark', '',
             'Scope: ToolWire first-action intent only; no tool execution or complete Secretary workflow.', '',
             'Status: ' + report['status'], 'Application commit: ' + report['git_commit'],
             'Candidate: ' + report['candidate_name'], '']
    if report['status'] != 'measured':
        return '\n'.join(lines + ['Metrics: **not measured**.', '', *report.get('blockers', [])]) + '\n'
    m = report['metrics']
    lines += [f"Task success: {m['task_success']}/{m['total_prompts']} ({m['task_accuracy']:.2f}%)",
              f"Tool / action / arguments: {m['tool_accuracy']:.2f}% / {m['action_accuracy']:.2f}% / {m['argument_accuracy']:.2f}%",
              f"Latency mean / median / p95 (ms): {m['avg_latency_ms']:.3f} / {m['median_latency_ms']:.3f} / {m['p95_latency_ms']}",
              '', 'Quality gate: ' + report['comparison']['status'], '', '## Categories', '']
    for name, c in m['categories'].items():
        lines.append(f"- {name}: {c['task_success']}/{c['total']}; failures: {', '.join(c['failures']) or 'none'}")
    lines += ['', '## Gate details', '', '```json', json.dumps(report['comparison'], indent=2), '```']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', choices=['development', 'heldout', 'all'], default='development')
    p.add_argument('--candidate-name', required=True)
    p.add_argument('--config', type=Path, help='Private JSON: sdk_dir, model_path, device, threads, context, max_tokens')
    p.add_argument('--baseline', type=Path, default=ROOT/'eval/results/baseline.json')
    p.add_argument('--freeze-baseline', action='store_true')
    p.add_argument('--output-dir', type=Path, default=ROOT/'local/secretary-eval')
    p.add_argument('--policy', type=Path, default=ROOT/'eval/quality_policy.json')
    p.add_argument('--validate-only', action='store_true')
    args = p.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.candidate_name):
        p.error('candidate-name must be a safe filename label')
    paths = [ROOT/'eval/datasets'/name for split, name in
             [('development', 'secretary_dev.json'), ('heldout', 'secretary_heldout.json')]
             if args.dataset in {split, 'all'}]
    cases = load_dataset(paths)
    files = json.loads((ROOT/'eval/fixtures/files.json').read_text())
    codec = ActionCodec.from_files(files)
    if args.validate_only:
        print(json.dumps({'cases': len(cases), 'dataset_sha256': digest(cases), 'fixture_sha256': codec.digest}))
        return 0
    if args.freeze_baseline and args.dataset != 'all':
        p.error('A frozen reference requires all 50 cases')
    if not args.config:
        p.error('--config is required for measured execution; no model fallback or mock baseline')
    config = json.loads(args.config.read_text())
    allowed = {'sdk_dir', 'model_path', 'device', 'threads', 'context', 'threads_batch', 'ubatch',
               'spec_type', 'draft_tokens', 'plugin', 'max_tokens', 'grammar', 'hardware_note'}
    if set(config) - allowed:
        p.error('Unknown configuration keys: ' + ', '.join(sorted(set(config)-allowed)))
    policy = json.loads(args.policy.read_text())
    for key in ['max_accuracy_drop_points', 'max_category_drop_points']:
        if not isinstance(policy[key], (int, float)) or not math.isfinite(policy[key]) or policy[key] < 0:
            p.error('Quality thresholds must be finite and nonnegative')
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / ('baseline.json' if args.freeze_baseline else 'candidate_'+args.candidate_name+'.json')
    if destination.exists() or destination.with_suffix('.md').exists():
        p.error('Output already exists; choose a new name/directory. Baselines are never overwritten.')
    commit = git('rev-parse', 'HEAD')
    status = git('status', '--porcelain')
    metadata = {'schema_version': 1, 'protocol_version': PROTOCOL, 'scope': 'first_action_intent',
                'type': 'baseline' if args.freeze_baseline else 'candidate', 'status': 'measured',
                'candidate_name': args.candidate_name, 'git_commit': commit,
                'branch': git('branch', '--show-current'), 'dirty': bool(status),
                'application_sources_sha256': {name: file_hash(ROOT/name) for name in
                   ['turbo/action_codec.py', 'turbo/native.py', 'turbo/policy.py']},
                'timestamp': datetime.now(timezone.utc).isoformat(), 'dataset_sha256': digest(cases),
                'fixture_sha256': codec.digest, 'environment': {'system': platform.system(),
                  'machine': platform.machine(), 'python': platform.python_version(),
                  'hardware_note': config.get('hardware_note', 'not recorded')},
                'config': {k:v for k,v in config.items() if k not in {'sdk_dir','model_path'}},
                'evaluator_sha256': {name: file_hash(ROOT/name) for name in ['eval/scoring.py', 'eval/run_secretary_eval.py']},
                'generation_protocol': {'max_tokens':config.get('max_tokens',128), 'temperature':0, 'reset':True},
                'model_sha256': file_hash(config['model_path']) if Path(config['model_path']).is_file() else None,
                'run_command': 'python eval/run_secretary_eval.py --dataset '+args.dataset+' --candidate-name '+args.candidate_name+' --config PRIVATE_CONFIG.json',
                'warmup': 'one untimed first-development prompt; reset context each case; temperature 0',
                'secretary_module_present': (ROOT/'turbo/secretary.py').exists()}
    # SDK import/load occurs only for measured execution, never scoring tests.
    from turbo.native import NativeRuntime, NativeModel, PINNED_VERSION
    metadata['runtime_version'] = PINNED_VERSION
    source_hashes = {**metadata['application_sources_sha256'], **metadata['evaluator_sha256']}
    if metadata['secretary_module_present']:
        source_hashes['turbo/secretary.py'] = file_hash(ROOT/'turbo/secretary.py')
    metadata['source_hashes'] = source_hashes
    runtime = NativeRuntime(config['sdk_dir'])
    try:
        kwargs = {k:config[k] for k in ['device','threads','context','threads_batch','ubatch','spec_type','draft_tokens','plugin'] if k in config}
        with NativeModel(runtime, config['model_path'], **kwargs) as model:
            def complete(messages):
                return model.chat(messages, max_tokens=config.get('max_tokens', 128), temperature=0,
                                  reset=True, grammar=codec.grammar() if config.get('grammar', False) else None)
            warmup = load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
            complete([{'role':'system','content':codec.instructions()}, {'role':'user','content':warmup['prompt']}])
            rows = execute(cases, codec, complete)
    finally:
        runtime.close()
    if (git('rev-parse','HEAD') != commit or git('status','--porcelain') != status
            or any(file_hash(ROOT/name) != value for name,value in source_hashes.items())):
        raise RuntimeError('Source tree changed during run; no baseline published')
    metadata['results'], metadata['metrics'] = rows, summarize(rows)
    metadata['comparison'] = ({'status':'REFERENCE', 'reasons':[]} if args.freeze_baseline else compare(metadata, baseline, policy))
    if args.freeze_baseline and any(r['execution_error'] for r in rows):
        metadata['status'] = 'invalid_baseline'
        metadata['comparison'] = {'status':'NOT_EVALUATED','reasons':['Execution errors; repair environment and rerun']}
    with destination.open('x', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, allow_nan=False)
    destination.with_suffix('.md').write_text(markdown(metadata), encoding='utf-8')
    print(markdown(metadata))
    print('Saved:', destination)
    return 0 if metadata['comparison']['status'] in {'PASS','REFERENCE'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
