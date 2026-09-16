"""Evaluate one real Secretary action and its execution in an isolated fixture."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scoring import load_dataset, score, summarize, compare, digest
from eval.secretary_adapter import SecretaryAdapter as ActionCodec, TOOLS, execute_in_fixture, PreparedFixture
from eval.validate_dataset import validate, BENCHMARK_VERSION

PROTOCOL = 'secretary-single-action-v2'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def execute(cases, codec, complete, fixture_root=None, measurement=None):
    rows = []
    for case in cases:
        # Golden execution and disposable roots are benchmark setup, not task energy.
        prepared = PreparedFixture(fixture_root, case['expected']) if measurement else nullcontext(None)
        with prepared as fixture:
            interval = measurement.measure('warm_task') if measurement else nullcontext(None)
            if measurement: measurement.last_inference = None
            with interval as energy:
                started = time.perf_counter()
                error, output = None, {}
                try:
                    output = complete([
                        {'role': 'system', 'content': codec.instructions()},
                        {'role': 'user', 'content': case['prompt']}])
                    if not isinstance(output, dict) or not isinstance(output.get('text'), str):
                        raise ValueError('Completion must contain text')
                except Exception as exc:
                    error = type(exc).__name__
                    output = {}
                inference_ms=round((time.perf_counter()-started)*1000,3)
                row = score(case, output.get('text'), codec)
                row.update(latency_ms=inference_ms,
                           expected_tool=case['expected']['tool'], case_sha256=digest(case), execution_error=error,
                           output_text=output.get('text'), profile=output.get('profile'),
                           timings=output.get('timings'), selected_device=output.get('device'),
                           selected_route=None, routing_accuracy=None,
                           backend_id=output.get('backend_id'), runtime=output.get('runtime'),
                           requested_device=output.get('requested_device'), resolved_device=output.get('resolved_device'),
                   generation_control=output.get('generation_control'))
                if error:
                    row['task_success'] = False
                    row['failure_reasons'] = ['TIMEOUT' if error in {'TimeoutError','TimeoutExpired'} else 'MODEL_ERROR']
                checked = None
                if fixture_root is not None and not row['parse_error'] and not error:
                    if fixture:
                        fixture.run_actual(row['tool'],row['arguments'])
                    else:
                        checked=execute_in_fixture(row['tool'],row['arguments'],case['expected'],fixture_root)
                warm_ms=round((time.perf_counter()-started)*1000,3)
            # Filesystem comparison is an audit, after the requested tool has finished.
            if fixture and fixture.outcome is not None: checked = fixture.check()
            if checked is not None:
                row.update(checked)
                row['task_success'] = row['task_success'] and checked['execution_ok'] and checked['final_state_match']
                if not checked['execution_ok']: row['failure_reasons'].append('EXECUTION_ERROR')
                if not checked['final_state_match']: row['failure_reasons'].append('WRONG_FINAL_STATE')
            row['task_latency_ms']=round((time.perf_counter()-started)*1000,3)
            if measurement:
                inference_energy = measurement.last_inference
                if inference_energy is not None:
                    tokens = (output.get('profile') or {}).get('generated_tokens')
                    joules = inference_energy.get('gross_energy_j')
                    inference_energy['tokens_per_joule'] = (tokens/joules if type(tokens) is int
                        and tokens >= 0 and isinstance(joules,(int,float)) and joules > 0 else None)
                row.update(energy=energy, warm_task_latency_ms=warm_ms,
                           inference_energy=inference_energy)
            rows.append(row)
    return rows


def markdown(report):
    lines = ['# Secretary correctness audit', '',
             'Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.', '',
             'Benchmark: ' + report.get('benchmark_version','unversioned'),
             'Status: ' + report['status'], 'Application commit: ' + report['git_commit'],
             'Candidate: ' + report['candidate_name'], 'Model: '+report.get('model_label','unavailable'),
             '', 'Configuration:', '```json', json.dumps(report.get('config'),indent=2), '```']
    if report['status'] != 'measured':
        return '\n'.join(lines + ['Metrics: **not an accepted measurement**.', '', *report.get('blockers', []),
                                  json.dumps(report.get('comparison',{}),indent=2)])+'\n'
    m = report['metrics']
    lines += [f"Task success: {m['task_success']}/{m['total_prompts']} ({m['task_accuracy']:.2f}%)",
              f"Failed tasks: {m['failed_tasks']}",
              f"Tool / action / arguments: {m['tool_accuracy']:.2f}% / {m['action_accuracy']:.2f}% / {m['argument_accuracy']:.2f}%",
              f"Clarification accuracy (expected-clarify cases): {m['clarification_accuracy']}",
              f"Invalid output rate: {m['invalid_output_rate']:.2%}",
              f"Latency mean / median / p95 (ms): {m['avg_latency_ms']:.3f} / {m['median_latency_ms']:.3f} / {m['p95_latency_ms']}",
              '', 'Quality gate: '+report['comparison']['status']]
    for heading,key in [('Categories','categories'),('Difficulty','difficulties'),('Expected action','actions')]:
        lines += ['', '## '+heading, '']
        for name,c in m[key].items(): lines.append(f"- {name}: {c['task_success']}/{c['total']} ({c['task_accuracy']:.2f}%)")
    lines += ['', '## Failed tests', '']
    failed = [r for r in report['results'] if not r['task_success']]
    if not failed: lines.append('None.')
    for row in failed:
        lines += ['### '+row['id'], '', 'Prompt: '+row['prompt'], '',
                  'Failure: '+', '.join(row['failure_reasons']), '', 'Expected vs actual:',
                  '```json', json.dumps({'expected':row['expected'],
                   'actual':{'tool':row['tool'],'arguments':row['arguments']},
                   'raw_output':row['output_text'],'error':row['execution_error']},indent=2,ensure_ascii=False), '```']
    if report.get('energy_measurement'):
        lines += ['', '## Energy measurement', '', '```json',
                  json.dumps(report['energy_measurement'],indent=2), '```']
    lines += ['', '## Comparison', '', '```json',json.dumps(report['comparison'],indent=2),'```']
    return '\n'.join(lines)+'\n'


def run_uninstrumented(config, metadata, cases, codec, NativeRuntime, NativeModel):
    runtime = NativeRuntime(config['sdk_dir'])
    try:
        kwargs = {k:config[k] for k in ['device','threads','context','threads_batch','ubatch','n_batch','spec_type','draft_tokens','plugin','backend','stop_after_tool_call'] if k in config}
        with NativeModel(runtime, config['model_path'], **kwargs) as model:
            metadata['inference_backend'] = {**model.provenance(), 'model_path_or_id': metadata['model_label']}
            def complete(messages):
                return model.chat(messages, tools=TOOLS, max_tokens=config.get('max_tokens',128), temperature=0,reset=True)
            warmup = load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
            complete([{'role':'system','content':codec.instructions()}, {'role':'user','content':warmup['prompt']}])
            rows = execute(cases,codec,complete,ROOT/'eval/fixtures/secretary_workspace')
    finally:
        runtime.close()
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', choices=['dev', 'development', 'heldout', 'all'], default='development')
    p.add_argument('--candidate-name', required=True)
    p.add_argument('--config', type=Path, help='Private JSON: sdk_dir, model_path, device, threads, context, max_tokens')
    p.add_argument('--baseline', type=Path, default=ROOT/'eval/results/baseline.json')
    p.add_argument('--freeze-baseline', action='store_true')
    p.add_argument('--output-dir', type=Path, default=ROOT/'local/secretary-eval')
    p.add_argument('--policy', type=Path, default=ROOT/'eval/quality_policy.json')
    p.add_argument('--validate-only', action='store_true')
    p.add_argument('--energy-protocol', type=Path, help='Opt-in observed power/counter/idle protocol JSON')
    p.add_argument('--run-order', type=int, help='Position in the recorded sequential backend block')
    p.add_argument('--baseline-approval', type=Path, help='Henry-confirmed baseline manifest; required to freeze official baseline')
    args = p.parse_args(argv)
    if args.dataset == 'dev': args.dataset = 'development'
    golden = validate()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.candidate_name):
        p.error('candidate-name must be a safe filename label')
    paths = [ROOT/'eval/datasets'/name for split, name in
             [('development', 'secretary_dev.json'), ('heldout', 'secretary_heldout.json')]
             if args.dataset in {split, 'all'}]
    cases = load_dataset(paths)
    files = json.loads((ROOT/'eval/fixtures/files.json').read_text())
    codec = ActionCodec.from_files(files)
    if args.validate_only:
        print(json.dumps({'cases': len(cases), 'dataset_sha256': digest(cases), 'fixture_sha256': golden['fixture_sha256'], 'benchmark_version':BENCHMARK_VERSION}))
        return 0
    if args.freeze_baseline and args.dataset != 'all':
        p.error('A frozen reference requires all 50 cases')
    if not args.config:
        p.error('--config is required for measured execution; no model fallback or mock baseline')
    config = json.loads(args.config.read_text())
    allowed = {'sdk_dir', 'model_path', 'device', 'threads', 'context', 'threads_batch', 'ubatch', 'n_batch',
               'spec_type', 'draft_tokens', 'plugin', 'backend', 'stop_after_tool_call', 'max_tokens', 'grammar', 'hardware_note'}
    if set(config) - allowed:
        p.error('Unknown configuration keys: ' + ', '.join(sorted(set(config)-allowed)))
    if config.get('grammar'):
        p.error('ToolWire grammar is not valid for the production Secretary tool contract')
    from turbo.native import backend_options
    try:
        backend_options(config.get('backend'), config.get('plugin'), config.get('device'), config.get('model_path'))
    except ValueError as exc:
        p.error(str(exc))
    energy_protocol = None
    if args.energy_protocol:
        from eval.energy_measurement import validate_protocol
        try:
            energy_protocol = validate_protocol(json.loads(args.energy_protocol.read_text(encoding='utf-8-sig')))
        except ValueError as exc:
            p.error(str(exc))
        if args.run_order is None or args.run_order < 1:
            p.error('--run-order must be a positive integer for energy measurements')
    policy = json.loads(args.policy.read_text())
    for key in ['max_accuracy_drop_points', 'max_category_drop_points']:
        if not isinstance(policy[key], (int, float)) or not math.isfinite(policy[key]) or policy[key] < 0:
            p.error('Quality thresholds must be finite and nonnegative')
    if args.freeze_baseline:
        if git('status','--porcelain'):
            p.error('Official baseline requires a clean committed worktree')
        if not args.baseline_approval:
            p.error('--baseline-approval is required; Henry must explicitly confirm the original configuration')
        approval = json.loads(args.baseline_approval.read_text())
        if (approval.get('status') != 'confirmed' or approval.get('confirmed_by') != 'Henry'
                or approval.get('config_sha256') != digest(config)
                or approval.get('application_commit') != git('rev-parse','HEAD')):
            p.error('Baseline approval must confirm Henry, this config hash and the current application commit')
    else:
        approval = None
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / ('baseline.json' if args.freeze_baseline else 'candidate_'+args.candidate_name+'.json')
    if destination.exists() or destination.with_suffix('.md').exists() or (args.freeze_baseline and (args.output_dir/'baseline_manifest.json').exists()):
        p.error('Output already exists; choose a new name/directory. Baselines are never overwritten.')
    commit = git('rev-parse', 'HEAD')
    status = git('status', '--porcelain')
    metadata = {'schema_version': 2, 'benchmark_version':BENCHMARK_VERSION, 'protocol_version': PROTOCOL, 'scope': 'single_action_with_fixture_execution',
                'type': 'baseline' if args.freeze_baseline else 'candidate', 'status': 'measured',
                'candidate_name': args.candidate_name, 'git_commit': commit,
                'branch': git('branch', '--show-current'), 'dirty': bool(status),
                'application_sources_sha256': {name: file_hash(ROOT/name) for name in
                   ['turbo/secretary.py','turbo/service.py','turbo/native.py','turbo/policy.py','turbo/tuning.py']},
                'timestamp': datetime.now(timezone.utc).isoformat(), 'dataset_sha256': digest(cases),
                'fixture_sha256': golden['fixture_sha256'], 'inventory_sha256':codec.digest,
                'action_schema_sha256':golden['action_schema_sha256'], 'system_prompt_sha256':golden['system_prompt_sha256'], 'baseline_approval':approval,
                'config_sha256':digest(config), 'environment': {'system': platform.system(),
                  'machine': platform.machine(), 'python': platform.python_version(),
                  'hardware_note': config.get('hardware_note', 'not recorded')},
                'config': {k:v for k,v in config.items() if k not in {'sdk_dir','model_path'}},
                'evaluator_sha256': {name: file_hash(ROOT/name) for name in ['eval/scoring.py', 'eval/run_secretary_eval.py', 'eval/validate_dataset.py','eval/secretary_adapter.py']},
                'generation_protocol': {'max_tokens':config.get('max_tokens',128), 'temperature':0, 'reset':True},
                'model_label':Path(config['model_path']).name,
                'model_sha256': file_hash(config['model_path']) if Path(config['model_path']).is_file() else None,
                'run_command': ('python eval/run_secretary_eval.py --dataset '+args.dataset+' --candidate-name '+args.candidate_name+' --config PRIVATE_CONFIG.json'
                    + (' --freeze-baseline --baseline-approval PRIVATE_APPROVAL.json' if args.freeze_baseline else ' --baseline BASELINE.json')
                    + ' --output-dir OUTPUT_DIRECTORY'),
                'warmup': 'one untimed first-development prompt; reset context each case; temperature 0',
                'secretary_module_present': (ROOT/'turbo/secretary.py').exists()}
    # SDK import/load occurs only for measured execution, never scoring tests.
    from turbo.native import NativeRuntime, NativeModel, PINNED_VERSION
    metadata['runtime_version'] = PINNED_VERSION
    if Path(config['model_path']).is_dir():
        from turbo.tuning import _sha256
        metadata['model_sha256'] = _sha256(config['model_path'])
        metadata['model_hash_method'] = 'turbo.tuning._sha256 directory manifest'

    source_hashes = {**metadata['application_sources_sha256'], **metadata['evaluator_sha256']}
    if metadata['secretary_module_present']:
        source_hashes['turbo/secretary.py'] = file_hash(ROOT/'turbo/secretary.py')
    for pth in [ROOT/'eval/benchmark_manifest.json', ROOT/'eval/fixtures/files.json', *paths]:
        source_hashes[pth.relative_to(ROOT).as_posix()] = file_hash(pth)
    metadata['source_hashes'] = source_hashes
    if energy_protocol:
        instrumented = ['turbo/telemetry.py','eval/energy_measurement.py','eval/run_secretary_eval.py',
                        'eval/secretary_adapter.py','turbo/native.py','eval/decision_table.py']
        metadata['energy_instrumentation_sha256'] = {name:file_hash(ROOT/name) for name in instrumented}
        source_hashes.update(metadata['energy_instrumentation_sha256'])
        metadata['run_command'] += ' --energy-protocol PRIVATE_ENERGY_PROTOCOL.json --run-order '+str(args.run_order)
        from eval.energy_measurement import measured_run
        rows = measured_run(config, metadata, cases, codec, execute, ROOT/'eval/fixtures/secretary_workspace',
                            energy_protocol, args.run_order, NativeRuntime, NativeModel)
    else:
        rows = run_uninstrumented(config, metadata, cases, codec, NativeRuntime, NativeModel)
    if (git('rev-parse','HEAD') != commit or git('status','--porcelain') != status
            or any(file_hash(ROOT/name) != value for name,value in source_hashes.items())
            or validate() != golden):
        raise RuntimeError('Source tree changed during run; no baseline published')
    metadata['results'], metadata['metrics'] = rows, summarize(rows)
    if energy_protocol:
        from eval.decision_table import energy_summary
        metadata['energy_measurement']['summary'] = {**energy_summary(rows),
            'tasks':len(rows), 'correct_tasks':metadata['metrics']['task_success'],
            'accuracy_pct':metadata['metrics']['task_accuracy'],
            'invalid_output_count':sum(r['invalid_output'] for r in rows),
            'clarification_accuracy_pct':metadata['metrics']['clarification_accuracy'],
            'critical_move_failures':sum(not r['task_success'] for r in rows if r['expected_tool']=='move_file')}
    metadata['comparison'] = ({'status':'REFERENCE', 'reasons':[]} if args.freeze_baseline else compare(metadata, baseline, policy))
    if args.freeze_baseline and any(r['execution_error'] for r in rows):
        metadata['status'] = 'invalid_baseline'
        metadata['comparison'] = {'status':'NOT_EVALUATED','reasons':['Execution errors; repair environment and rerun']}
    if args.freeze_baseline and energy_protocol and not metadata['energy_measurement']['valid']:
        metadata['status'] = 'invalid_baseline'
        metadata['comparison'] = {'status':'NOT_EVALUATED','reasons':['Energy reference has invalid or incomplete telemetry']}
    if args.freeze_baseline and metadata['model_sha256'] is None:
        metadata['status'] = 'invalid_baseline'
        metadata['comparison'] = {'status':'NOT_EVALUATED','reasons':['Model identity unverified: use a hashed model file or implement bundle manifest hashing']}
    with destination.open('x', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, allow_nan=False)
    with destination.with_suffix('.md').open('x',encoding='utf-8') as f:
        f.write(markdown(metadata))
    if args.freeze_baseline:
        manifest_path = args.output_dir/'baseline_manifest.json'
        with manifest_path.open('x',encoding='utf-8') as f:
            json.dump({k:v for k,v in metadata.items() if k not in {'results','metrics'}},f,indent=2,allow_nan=False)
    print(markdown(metadata))
    print('Saved:', destination)
    return 0 if metadata['comparison']['status'] in {'PASS','REFERENCE'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
