"""Local HTTP gateway and sandboxed secretary demo (standard library only)."""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .policy import Profile, choose
from .runtime_identity import binding_matches, runtime_identity

ROOT = Path(__file__).resolve().parents[1]


def parse_calls(text):
    """Read a single generated tool call, without inventing missing arguments."""
    matches = re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.S)
    if not matches:
        matches = re.findall(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
    if not matches and text.strip().startswith('{'):
        matches = [text.strip()]
    calls = []
    for candidate in matches:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        name, arguments = value.get('name'), value.get('arguments')
        if isinstance(name, str) and isinstance(arguments, dict):
            calls.append({'id': 'call_' + uuid.uuid4().hex[:12], 'type': 'function',
                          'function': {'name': name, 'arguments': json.dumps(arguments)}})
    return calls


class TuningJob:
    def __init__(self, target):
        self.exit_code = None
        self.error = None
        self.completed = 0
        self.total = 0
        self.result = None
        def run():
            try:
                self.result = target(self)
                self.exit_code = 0
            except Exception as exc:
                self.error = str(exc)
                self.exit_code = 1
        self.thread = threading.Thread(target=run, daemon=True)

    def poll(self):
        return self.exit_code

    def progress(self, done, total):
        self.completed, self.total = done, total



class Engine:
    def __init__(self, config):
        self.config = config
        self.lock = threading.RLock()
        self.runtime = None
        self.runtime_binding = None
        self.loaded = {}
        self.history = []
        self.profiles = [Profile(**p) for p in config.get('profiles', [])]
        self.tuning_process = None
        self.tuning_dir = None
        self.applied = None
        self.hash_cache = {}
        state = Path(config.get('data_dir', 'local/demo'))/'last-tuning.json'
        if state.is_file():
            prior = json.loads(state.read_text(encoding='utf-8'))
            if prior.get('model_id') in config['models'] and Path(prior.get('recommendation_file', '')).is_file():
                config['recommendation_file'] = prior['recommendation_file']
                config['default'] = prior['model_id']

    def start_tune(self, body=None):
        from .tuning import Variant, SearchSpace, run_tuning, plan_cells
        body = body or {}
        with self.lock:
            if self.tuning_process and self.tuning_process.poll() is None:
                raise ValueError('A device sweep is already running')
            settings = self.config.get('tuner')
            if not settings:
                raise ValueError('No local benchmark executable configured')
            model_id = body.get('model_id', self.config['default'])
            if model_id not in self.config['models']:
                raise ValueError('Unknown model')
            spec = self.config['models'][model_id]
            variant = Variant.from_dict(dict(id=model_id, path=spec['path'],
                architecture=spec.get('architecture', 'unverified'), quantization=spec.get('quantization', 'unverified'),
                plugin=spec.get('plugin', 'llama_cpp'), kind=spec.get('kind', 'llm'),
                compiled_contexts=spec.get('compiled_contexts'), tokenizer_path=spec.get('tokenizer_path'),
                mmproj_path=spec.get('mmproj_path')))
            search = dict(devices=['cpu', 'npu'], threads=[0, 10], contexts=[4096],
                          prompt_tokens=512, gen_tokens=128, repeats=3, warmup=0)
            if variant.plugin == 'qairt':
                from .native import _qairt_bundle_input
                _, compiled_context = _qairt_bundle_input(spec['path'])
                if tuple(variant.compiled_contexts or ()) != (compiled_context,):
                    raise ValueError('Register the QAIRT artifact compiled context before tuning')
                if not settings.get('prompt_file'):
                    raise ValueError('QAIRT tuning requires a configured text prompt_file')
                search.update(devices=['npu'], threads=[0], contexts=[compiled_context])
            search.update(body.get('search_space', {}))
            space = SearchSpace.from_dict(search)
            cells = plan_cells([variant], space)
            objective = body.get('objective', 'fast')
            if objective not in {'fast', 'efficient', 'balanced', 'decode', 'prefill'}:
                raise ValueError('Unknown objective')
            self._check_resident_runtime()
            for model in self.loaded.values():
                model.close()
            self.loaded.clear()
            self.applied = None
            # Release model allocations, but retain the initialized bridge.
            # On the installed Windows SDK, deinit followed by reinit in one
            # process aborts in ggml's exception-handler assertion. Child
            # benchmark processes own separate runtimes; this bridge is idle.
            self.tuning_dir = Path(self.config.get('results_dir', 'local/tuning')) / ('run-' + uuid.uuid4().hex[:10])
            self.tuning_dir.parent.mkdir(parents=True, exist_ok=True)
            def execute(job):
                record = run_tuning(settings['exe'], [variant], space, str(self.tuning_dir),
                    objective=objective, progress=job.progress, timeout_s=min(300, settings.get('timeout_s', 120)),
                    budget_s=min(1800, settings.get('budget_s', 600)),
                    prompt_file=settings.get('prompt_file'))
                if record.get('recommendation_path'):
                    with self.lock:
                        self.config['recommendation_file'] = record['recommendation_path']
                        self.config['default'] = model_id
                        state = Path(self.config.get('data_dir', 'local/demo'))/'last-tuning.json'
                        state.parent.mkdir(parents=True, exist_ok=True)
                        state.write_text(json.dumps({'model_id':model_id, 'recommendation_file':record['recommendation_path']}), encoding='utf-8')
                return record
            self.tuning_process = TuningJob(execute)
            self.tuning_process.total = len(cells)
            self.tuning_process.thread.start()
            return {'running': True, 'completed': 0, 'total': len(cells), 'objective': objective}

    def modes(self):
        path = Path(self.config.get('recommendation_file', ROOT/'benchmarks/results/recommended.json'))
        record = json.loads(path.read_text(encoding='utf-8-sig'))
        modes = dict(record.get('modes', {}))
        # Balanced chooses an existing measured profile; it invents no new point.
        if modes and 'balanced' not in modes:
            candidates = [v for v in modes.values() if v.get('metrics', {}).get('decode_tps') and v.get('metrics', {}).get('tokens_per_joule')]
            if candidates:
                max_speed = max(v['metrics']['decode_tps'] for v in candidates)
                max_eff = max(v['metrics']['tokens_per_joule'] for v in candidates)
                selected = max(candidates, key=lambda v: 2/(max_speed/v['metrics']['decode_tps']+max_eff/v['metrics']['tokens_per_joule']))
                modes['balanced'] = dict(selected, selection_rule='equal-weight harmonic mean of normalized decode speed and full-trial tokens/J')
        return {**record, 'modes': modes}

    def apply(self, mode, model_id=None):
        if mode == 'turbo':
            mode = 'fast'
        if mode not in {'fast', 'efficient', 'balanced', 'baseline'}:
            raise ValueError('Unknown mode')
        with self.lock:
            if self.tuning_process and self.tuning_process.poll() is None:
                raise ValueError('Inference paused while tuner is running')
            model_id = model_id or self.config['default']
            if model_id not in self.config['models']:
                raise ValueError('Unknown model')
            base = self.config['models'][model_id]
            if mode == 'baseline':
                if base.get('plugin') == 'qairt':
                    from .native import _qairt_bundle_input
                    _, context = _qairt_bundle_input(base['path'])
                    cfg = {'device': 'npu', 'threads': 0, 'context': context}
                    source = 'QAIRT compiled artifact defaults; separate from the official GGUF reference'
                else:
                    cfg = {'device': 'auto', 'threads': 0, 'context': 4096}
                    source = 'GenieX default automatic placement'
                evidence = {'source': source, 'quality_calibrated': False}
            else:
                record = self.modes()
                if mode not in record['modes']:
                    raise ValueError('Mode has no eligible measured profile')
                if record.get('schema_version') != 'turbo.recommended.v2':
                    raise ValueError('Recommendation requires fresh tuner v2 measurements')
                if record.get('plugin') != base.get('plugin', 'llama_cpp'):
                    raise ValueError('Recommendation belongs to a different runtime plugin')
                path = Path(base['path'])
                paths = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
                stamp = tuple((str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns,
                               p.stat().st_ctime_ns) for p in paths)
                if stamp not in self.hash_cache:
                    from .tuning import _sha256
                    self.hash_cache[stamp] = _sha256(path)
                if self.hash_cache[stamp] != record['model_sha256']:
                    raise ValueError('Recommendation belongs to different model weights; tune this model first')
                current = self._current_runtime_binding()
                self._check_resident_runtime(current)
                if not binding_matches(record.get('runtime_binding'), current):
                    raise ValueError('Runtime identity differs from measurements; rerun the tuner')
                cfg = {k: record['modes'][mode][k] for k in ('device', 'threads', 'context')}
                evidence = {'source': record['scope']['evidence'], 'scope': record['scope'], 'metrics': record['modes'][mode]['metrics']}
                if mode == 'efficient':
                    metrics = evidence['metrics']
                    efficiency = metrics.get('tokens_per_joule')
                    if (type(efficiency) not in (int, float) or not math.isfinite(efficiency)
                            or efficiency <= 0 or not metrics.get('energy_channel')
                            or metrics.get('energy_scope') != 'full_process_trial'):
                        raise ValueError('Efficient mode requires measured tokens/J with channel and scope')
            applied = {'model': model_id, 'mode': mode, 'config': cfg, 'evidence': evidence}
            if self.applied != applied:
                for loaded in self.loaded.values():
                    loaded.close()
                self.loaded.clear()
            self.applied = applied
            return applied

    def _current_runtime_binding(self):
        return runtime_identity((self.config.get('tuner') or {}).get('exe'),
                                self.config.get('sdk_dir'), use_cache=True)

    def _check_resident_runtime(self, current=None):
        if self.runtime_binding is not None:
            current = current or self._current_runtime_binding()
            if not binding_matches(self.runtime_binding, current):
                raise ValueError('Native SDK changed while loaded; restart the service before tuning or inference')

    def load(self, model_id):
        self._check_resident_runtime()
        if model_id not in self.loaded:
            from .native import NativeRuntime, NativeModel
            if self.runtime is None:
                binding = self._current_runtime_binding() if self.config.get('tuner') else None
                self.runtime = NativeRuntime(self.config['sdk_dir'])
                self.runtime_binding = binding
            spec = self.config['models'][model_id]
            settings = self.applied['config'] if self.applied and self.applied['model'] == model_id else spec
            self.loaded[model_id] = NativeModel(self.runtime, spec['path'],
                device=settings.get('device', 'cpu'), threads=settings.get('threads', 0),
                context=settings.get('context', 4096), spec_type=settings.get('spec_type', 'none'),
                draft_tokens=settings.get('draft_tokens', 8), threads_batch=settings.get('threads_batch', 0),
                ubatch=settings.get('ubatch', 0), plugin=spec.get('plugin', 'llama_cpp'))
        return self.loaded[model_id]

    def select(self, messages, mode, requested=None):
        requested = None if requested == 'turbo' else requested
        applied = self.apply(mode, requested)
        return applied['model'], {'reason': 'measured configuration applied' if mode != 'baseline' else 'stock auto baseline', **applied}

    def completion(self, body, mode='turbo', callback=None):
        messages = body.get('messages')
        if not isinstance(messages, list) or not messages:
            raise ValueError('messages must be a nonempty list')
        if any(not isinstance(m, dict) or not isinstance(m.get('content', ''), (str, type(None))) for m in messages):
            raise ValueError('This adapter supports text messages only')
        with self.lock:
            if self.tuning_process and self.tuning_process.poll() is None:
                raise ValueError('Inference paused while the isolated device sweep is running')
            start = time.perf_counter()
            mode = body.get('mode', mode)
            model_id, decision = self.select(messages, mode, body.get('model'))
            model = self.load(model_id)
            max_tokens = int(body.get('max_tokens', 256))
            if max_tokens < 1 or max_tokens > 2048:
                raise ValueError('max_tokens must be between 1 and 2048')
            result = model.chat(messages, tools=body.get('tools'), max_tokens=max_tokens,
                                temperature=float(body.get('temperature', 0)),
                                reset=not bool(body.get('cache_prompt', False)), on_token=callback)
            result['elapsed_s'] = time.perf_counter() - start
            result['model'], result['route'], result['mode'] = model_id, decision, mode
            result['tool_calls'] = parse_calls(result.get('text', ''))
            result['applied'] = self.applied
            return result

    def secretary(self, prompt=None, mode='fast', task_id=None):
        from .secretary import TOOLS, create_fixture, execute_tool, load_tasks, grade_task
        task = next((t for t in load_tasks() if t['id'] == task_id), None) if task_id else None
        if task_id and task is None:
            raise ValueError('Unknown task_id')
        if task:
            if prompt and prompt != task['prompt']:
                raise ValueError('Prompt differs from selected evaluation task')
            prompt = task['prompt']
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
            raise ValueError('Enter a request between 1 and 8000 characters')
        with self.lock:
            start = time.perf_counter()
            run_id = uuid.uuid4().hex[:12]
            workspace = Path(self.config.get('data_dir', 'local/demo')) / run_id
            inventory = create_fixture(workspace)
            messages = [
                {'role': 'system', 'content': 'You are a local file secretary. Emit the required tool calls only, at most four, and preserve exact paths and constraints. Both source and destination are full workspace-relative filenames. Preserve the basename when moving into a folder. Copy source paths exactly from the inventory, including parent folders. Use clarify when essential information is missing. Never invent file contents. Available files:\n' + '\n'.join(f['path'] for f in inventory)},
                {'role': 'user', 'content': prompt},
            ]
            result = self.completion({'messages': messages, 'tools': TOOLS, 'max_tokens': 256}, mode)
            result.update(run_id=run_id, prompt=prompt, result=[], errors=[])
            normalized = []
            if not 1 <= len(result['tool_calls']) <= 4:
                result['errors'].append('Expected one to four tool calls; no action executed')
            else:
                for c in result['tool_calls']:
                    call = c['function']
                    args = json.loads(call['arguments'])
                    normalized.append({'name': call['name'], 'arguments': args})
                    outcome = execute_tool(workspace, call['name'], args)
                    result['result'].append(outcome)
                    if not outcome['ok']:
                        result['errors'].append(outcome['error'])
                        break
            result['verification'] = grade_task(task, normalized, result['result'], workspace) if task else {'passed': None, 'reason': 'No gold label for an arbitrary request'}
            result['passed'] = result['verification']['passed']
            result['elapsed_s'] = time.perf_counter() - start
            result['task_timing_scope'] = 'fixture creation, profile validation, model load if cold, inference, tool execution and verification'
            result['workspace'] = str(workspace)
            self.history.append(result)
            self.history = self.history[-30:]
            return result

    def status(self):
        rows = []
        results_dir = Path(self.config.get('results_dir', 'benchmarks/results'))
        if results_dir.exists():
            for path in sorted(results_dir.rglob('*.json')):
                try:
                    r = json.loads(path.read_text(encoding='utf-8-sig'))
                    if 'agg' not in r:
                        continue
                    rows.append({'id': r.get('cell_id', path.stem), 'device': r.get('device'),
                        'decode_tps': r['agg']['decode_tps']['median'],
                        'prefill_tps': r['agg']['prefill_tps']['median'],
                        'ttft_ms': r['agg']['ttft_ms']['median'], 'runs': len(r.get('runs', [])),
                        'config': r.get('params', {}), 'model': Path(r.get('model_path', '')).name,
                        'device_id': r.get('device_id'),
                        'dispatch': 'resolved ' + str(r.get('device_id') or r.get('device')) + '; execution trace pending',
                        'memory_mb': r.get('telemetry', {}).get('peak_working_set_mb'),
                        'power_w': r.get('telemetry', {}).get('average_power_w'),
                        'tokens_per_joule': r.get('telemetry', {}).get('tokens_per_joule'),
                        'complete_length': bool(r.get('runs')) and all(x.get('gen_tokens') == r.get('params', {}).get('n_gen') for x in r.get('runs', []))})
                except (OSError, ValueError, KeyError):
                    continue
        tuning = {'running': False, 'completed': 0, 'total': 0, 'error': None}
        if self.tuning_process:
            job = self.tuning_process
            tuning.update(running=job.poll() is None, completed=job.completed,
                          total=job.total, error=job.error, record=job.result)
            if job.result is None and self.tuning_dir:
                try:
                    tuning['record'] = json.loads((self.tuning_dir/'record.json').read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    pass
        try:
            recommendation = self.modes()
        except (OSError, ValueError):
            recommendation = None
        return {'runtime_available': bool(self.config.get('sdk_dir')) and Path(self.config['sdk_dir']).is_dir(),
                'models': [{'id': k, 'available': Path(v['path']).is_file(),
                            'device': v.get('device', 'cpu'), 'threads': v.get('threads', 0)}
                           for k, v in self.config['models'].items()],
                'profiles': self.config.get('profiles', []), 'history': self.history,
                'results': rows, 'recommendation': recommendation, 'applied': self.applied, 'tuning': tuning, 'version': '0.2.0'}


def handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, payload, status=200):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/api/modes':
                return self.send_json(engine.modes())
            if self.path == '/api/status':
                return self.send_json(engine.status())
            if self.path == '/api/tasks':
                from .secretary import load_tasks
                tasks = load_tasks()
                if isinstance(tasks, dict):
                    tasks = tasks.get('tasks', [])
                return self.send_json([{'id': t['id'], 'prompt': t.get('prompt', t.get('request', ''))} for t in tasks])
            if self.path == '/v1/models':
                return self.send_json({'object': 'list', 'data': [{'id': x, 'object': 'model'} for x in ['turbo', *engine.config['models']]]})
            target = (ROOT / 'web' / ('index.html' if self.path == '/' else self.path.lstrip('/'))).resolve()
            if not target.is_relative_to((ROOT/'web').resolve()) or not target.is_file():
                return self.send_json({'error': 'Not found'}, 404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            # Loopback-only server; also reject cross-origin browser mutations.
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + self.headers.get('Host', '')}:
                return self.send_json({'error': 'Cross-origin request rejected'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 1_000_000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Request must be an object')
                if self.path == '/api/apply':
                    return self.send_json(engine.apply(body.get('mode', 'fast'), body.get('model_id')))
                if self.path == '/api/tune':
                    return self.send_json(engine.start_tune(body), 202)
                if self.path == '/api/run':
                    if body.get('mode', 'fast') not in {'baseline', 'turbo', 'fast', 'efficient', 'balanced'}:
                        raise ValueError('Invalid mode')
                    return self.send_json(engine.secretary(body.get('prompt'), body.get('mode', 'fast'), body.get('task_id')))
                if self.path == '/api/compare':
                    # Separate fixtures, identical prompt. This is a demonstration;
                    # repeated randomized/paired measurements use the CLI suite.
                    with engine.lock:
                        results = {mode: engine.secretary(body.get('prompt'), mode, body.get('task_id')) for mode in ('fast', 'efficient')}
                    return self.send_json(results)
                if self.path != '/v1/chat/completions':
                    return self.send_json({'error': 'Not found'}, 404)
                if body.get('stream') and body.get('tools'):
                    raise ValueError('Streaming tools are not supported by this adapter; use stream=false')
                ident = 'chatcmpl-' + uuid.uuid4().hex
                if body.get('stream'):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.close_connection = True
                    def event(payload):
                        self.wfile.write(('data: ' + json.dumps(payload) + '\n\n').encode())
                        self.wfile.flush()
                    def token(text):
                        event({'id': ident, 'object': 'chat.completion.chunk',
                               'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': None}]})
                        return True
                    try:
                        result = engine.completion(body, callback=token)
                        profile = result.get('profile', {})
                        usage = {'prompt_tokens': profile.get('prompt_tokens'), 'completion_tokens': profile.get('generated_tokens')}
                        event({'id': ident, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], 'usage': usage, 'turbo': result})
                        self.wfile.write(b'data: [DONE]\n\n')
                    except Exception as exc:
                        event({'error': str(exc)})
                    return
                result = engine.completion(body)
                profile = result.get('profile', {})
                message = {'role': 'assistant', 'content': result['text']}
                if result['tool_calls']:
                    message = {'role': 'assistant', 'content': None, 'tool_calls': result['tool_calls']}
                return self.send_json({'id': ident, 'object': 'chat.completion', 'model': result['model'],
                    'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if result['tool_calls'] else 'stop'}],
                    'usage': {'prompt_tokens': profile.get('prompt_tokens'), 'completion_tokens': profile.get('generated_tokens')},
                    'turbo': result})
            except (ValueError, KeyError, TypeError) as exc:
                self.send_json({'error': str(exc)}, 400)
            except Exception as exc:
                self.send_json({'error': str(exc)}, 503)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='local/config.json')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Engine(config)))
    print(f'Local Turbo listening on http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
