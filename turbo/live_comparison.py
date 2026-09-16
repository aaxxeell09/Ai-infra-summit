"""Opt-in, sequential native answer demos using the frontend's recorded settings.

This is a presentation adapter, not an evaluation runner. It never changes the
frozen Secretary workload and never promotes a winner from one answer pair.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import subprocess
import threading
import time
from pathlib import Path

PROMPTS = {
    'quick': 'In two sentences, explain why local AI can work without an internet connection.',
    'reasoning': 'A demo starts at 14:00. Setup takes 25 minutes, testing takes 20 minutes, and we need a 10-minute buffer. Testing must follow setup. What is the latest time we can start? Show the schedule.',
}
CPU_CELLS = tuple(f'cpu-t{n}' for n in (0, 2, 4, 6, 8, 10, 12))
LIVE_CELLS = (*CPU_CELLS, 'gpu', 'npu')
BACKENDS = {'cpu': 'llama_cpp_cpu', 'gpu': 'llama_cpp_gpu', 'npu': 'llama_cpp_htp'}
ROOT = Path(__file__).resolve().parents[1]


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _metric(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _manifest_hashes(path):
    # Git's Windows checkout can expand LF to CRLF. Accept those two exact byte
    # representations only; do not normalize content, whitespace or JSON values.
    raw = Path(path).read_bytes()
    return {hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}


class LiveComparisons:
    def __init__(self, engine, *, root=ROOT, model_factory=None):
        self.engine = engine
        self.root = Path(root)
        self.model_factory = model_factory
        self.guard = threading.RLock()
        self.jobs = {}
        self.active = None
        self.enabled = engine.config.get('live_comparison_enabled') is True
        self.source = self.root / 'benchmarks/results/screen-01'
        self.manifest = json.loads((self.source / 'sweep.json').read_text())

    def capabilities(self):
        from .demo_routing import POLICY, catalog
        routes = catalog(self.engine.config)
        return {'available': self.enabled, 'supported_cell_ids': list(LIVE_CELLS) if self.enabled else [],
                'model_sha256': self.manifest['model_sha256'], 'comparison': 'speed',
                'backends': list(BACKENDS.values()), 'quality': 'not_evaluated',
                'routing': {'available': self.enabled and any(row['available'] for row in routes),
                            'policy': POLICY, 'routes': routes, 'selections': ['auto', *[row['id'] for row in routes]],
                            'scope': 'Experimental public-prompt task policy; not a calibrated speed/quality ranking'},
                'scope': 'Opt-in native answer demonstration; one pair is not a confirmed speedup.'}

    def _validate(self, request):
        if not self.enabled:
            raise ValueError('Live answer comparison is not enabled on this gateway')
        if (request.get('schema_version') != 'local-turbo.comparison-request.v1'
                or request.get('comparison') not in ('speed', 'routing') or request.get('execution') != 'sequential'):
            raise ValueError('Only sequential public-demo comparisons are supported')
        ident = request.get('request_id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', ident):
            raise ValueError('Invalid request ID')
        if request.get('prompt_id') not in PROMPTS or request.get('prompt') != PROMPTS[request['prompt_id']]:
            raise ValueError('Choose one of the two fixed public presentation prompts')
        routing = request.get('comparison') == 'routing'
        if routing:
            from .demo_routing import POLICY, ROUTES
            options = request.get('routing')
            if (not isinstance(options, dict) or options.get('policy') != POLICY
                    or options.get('allow_uncalibrated') is not True
                    or options.get('selection') not in ('auto', *[row[0] for row in ROUTES])
                    or request.get('selected') is not None):
                raise ValueError('Routing requires an explicit experimental policy and a supported selection')
        for lane, key in [('default', 'baseline'), ('turbo', 'selected')]:
            if routing and lane == 'turbo':
                continue
            cfg = request.get(key)
            if not isinstance(cfg, dict) or cfg.get('cell_id') not in LIVE_CELLS:
                raise ValueError(f'{lane}: select a supported CPU, GPU or HTP configuration on Compare')
            if lane == 'default' and cfg['cell_id'] != 'cpu-t0':
                raise ValueError('Default lane must use the recorded CPU automatic-thread configuration')
            report = json.loads((self.source / (cfg['cell_id'] + '.json')).read_text())
            expected = {'model': self.manifest['model_name'], 'model_sha256': self.manifest['model_sha256'],
                        'runtime_sha256': self.manifest['runtime_sha256'], 'plugin': 'llama_cpp',
                        'requested_device': report['device']}
            if any(cfg.get(k) != v for k, v in expected.items()):
                raise ValueError(f'{lane}: model, runtime, backend or source identity differs from the recorded selection')
            if cfg.get('source_sha256') not in _manifest_hashes(self.source / 'sweep.json'):
                raise ValueError(f'{lane}: recorded source hash differs, including after Git CRLF normalization')
            if cfg.get('params') != report['params']:
                raise ValueError(f'{lane}: requested parameters differ from the recorded selection')
        return ident

    def start(self, request):
        ident = self._validate(request)
        with self.guard:
            if ident in self.jobs:
                if self.jobs[ident]['request'] != request:
                    raise ValueError('Request ID already belongs to different inputs')
                return self.snapshot(ident)
            if self.active is not None:
                raise ValueError('Another live comparison is active; reconcile its status before retrying')
            if len(self.jobs) >= 100:
                raise ValueError('Presentation session limit reached; restart the gateway after checking saved results')
            output = Path(self.engine.config.get('data_dir', 'local/demo')) / 'live-comparisons' / ident
            output.mkdir(parents=True, exist_ok=False)
            job = {'request_id': ident, 'request': copy.deepcopy(request), 'state': 'running', 'events': [],
                   'cancel_requested': False, 'result': None, 'error': None, '_output': output}
            (output / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
            self.jobs[ident] = job
            self.active = ident
            worker = threading.Thread(target=self._run, args=(ident,), daemon=True)
            worker.start()
            return self.snapshot(ident)

    def snapshot(self, ident):
        with self.guard:
            if ident not in self.jobs:
                raise KeyError('Unknown live comparison')
            return copy.deepcopy({k: v for k, v in self.jobs[ident].items() if not k.startswith('_') and k != 'request'})

    def cancel(self, ident):
        with self.guard:
            if ident not in self.jobs:
                raise KeyError('Unknown live comparison')
            if self.jobs[ident]['state'] == 'running':
                self.jobs[ident]['cancel_requested'] = True
            return self.snapshot(ident)

    def _event(self, job, event):
        with self.guard:
            job['events'].append({'request_id': job['request_id'], **event})

    def _identity(self):
        from .runtime_identity import runtime_identity
        specs = self.engine.config['models']
        candidates = [(key, value) for key, value in specs.items()
                      if Path(value['path']).name == self.manifest['model_name'] and value.get('plugin', 'llama_cpp') == 'llama_cpp']
        if len(candidates) != 1:
            raise ValueError('Configure exactly one matching recorded GGUF model for the live answer demo')
        model_id, spec = candidates[0]
        model_hash = _hash(spec['path'])
        exe = (self.engine.config.get('tuner') or {}).get('exe')
        if model_hash != self.manifest['model_sha256'] or not exe or _hash(exe) != self.manifest['runtime_sha256']:
            raise ValueError('Installed model or benchmark executable does not match the recorded selection')
        binding = runtime_identity(exe, self.engine.config['sdk_dir'], use_cache=False)
        self.engine._check_resident_runtime(binding)
        return model_id, spec, binding

    def _run(self, ident):
        job = self.jobs[ident]
        request = job['request']
        start = time.perf_counter()
        deadline = start + 110
        acquired = False
        lanes = {}
        final_state, final_error = 'failed', None
        result = {'schema_version': 'local-turbo.comparison-result.v1', 'request_id': ident,
                  'mode': 'live', 'comparison': request['comparison'], 'execution': 'sequential', 'lanes': lanes,
                  'winner': None, 'speedup': None, 'quality': 'not_evaluated', 'routing': None,
                  'prompt_sha256': hashlib.sha256(request['prompt'].encode()).hexdigest(),
                  'generation': {'max_tokens': 128, 'temperature_requested': 0, 'seed': -1,
                                 'seed_scope': 'SDK default, not a deterministic seeded trial',
                                 'greedy_zero': False, 'fresh_model_each_lane': True, 'fresh_kv': True, 'warmup': 0},
                  'scope': 'Public answer demonstration. Different answer lengths can affect latency. No confirmed tuning or quality win.'}
        try:
            acquired = self.engine.lock.acquire(blocking=False)
            if not acquired:
                raise ValueError('Gateway is busy with another inference; wait for it to finish')
            if self.engine.tuning_process and self.engine.tuning_process.poll() is None:
                raise ValueError('Tuning is active; do not overlap this presentation with measurements')
            model_id, spec, binding = self._identity()
            result['runtime_binding'] = binding
            result['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
            result['working_tree_clean'] = not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=self.root, text=True).strip()
            if not result['working_tree_clean']:
                raise ValueError('Live presentation requires a clean committed checkout')
            from .native import NativeModel, NativeRuntime
            for loaded in self.engine.loaded.values():
                loaded.close()
            self.engine.loaded.clear()
            if self.engine.runtime is None:
                self.engine.runtime = NativeRuntime(self.engine.config['sdk_dir'])
                self.engine.runtime_binding = binding
            route, decision = None, None
            if request['comparison'] == 'routing':
                from .demo_routing import choose_route
                from .tuning import _sha256
                route, decision = choose_route(self.engine.config, request, self.engine.runtime)
                route_spec = self.engine.config['models'][route['model_id']]
                route['model_sha256'] = _sha256(route_spec['path'], deadline=time.monotonic() + max(0, deadline-time.perf_counter()))
                pins = {'qwen06': self.manifest['model_sha256'],
                        'qwen4b': 'e0ba675d86ab277c61701c6793659b2ae801d95e3be791464c321e6fbf613be2'}
                if route['model_id'] in pins and route['model_sha256'] != pins[route['model_id']]:
                    raise ValueError('Selected model weights differ from the pinned demo artifact')
                result['routing'] = decision
            for lane, key in [('default', 'baseline'), ('turbo', 'selected')]:
                if job['cancel_requested'] or time.perf_counter() >= deadline:
                    raise InterruptedError('Comparison cancelled or deadline reached')
                selected_route = route if lane == 'turbo' else None
                lane_spec, lane_model_id = spec, model_id
                if selected_route:
                    lane_model_id = route['model_id']
                    lane_spec = self.engine.config['models'][lane_model_id]
                    cfg = dict(cell_id=route['id'], model=route['model'], model_sha256=route['model_sha256'],
                               runtime_sha256=self.manifest['runtime_sha256'], plugin=route['plugin'],
                               requested_device=route['device'], params={'n_threads': route['threads'], 'n_ctx': route['context']})
                else:
                    cfg = request[key]
                params = cfg['params']
                backend = route['backend_id'] if selected_route else BACKENDS[cfg['requested_device']]
                ack = {'cell_id': cfg['cell_id'], 'model': cfg['model'], 'model_id': lane_model_id,
                       'model_sha256': cfg['model_sha256'], 'runtime_sha256': cfg['runtime_sha256'],
                       'runtime_hash_scope': 'benchmark executable; current SDK/plugin hashes are in runtime_binding',
                       'sdk_sha256': binding['sha256'], 'plugin': cfg['plugin'], 'device': cfg['requested_device'],
                       'backend_id': backend, 'threads': params['n_threads'], 'context': params['n_ctx'],
                       'thread_scope': 'Value passed to the SDK; zero requests automatic selection, resolved worker count unavailable',
                       'quantization': route['quantization'] if selected_route else 'Q4_0', 'source_sha256': cfg.get('source_sha256'),
                       'source_hash_validation': 'Exact JSON bytes or Git CRLF-to-LF conversion only'}
                if selected_route:
                    ack.update(route_id=route['id'], source_sha256=None, source_hash_validation=None,
                               quantization_scope=route.get('quantization_scope', 'Pinned Q4_0 GGUF'),
                               model_hash_scope='Full bundle via tuning._sha256 (host path separators)' if cfg['plugin'] == 'qairt' else 'Exact GGUF bytes')
                    decision['effective_configuration'] = copy.deepcopy(ack)
                    self._event(job, {'type': 'route', 'lane': lane, 'routing': copy.deepcopy(decision)})
                lane_result = {'status': 'running', 'answer': '', 'configuration_applied': False,
                               'effective_configuration': None, 'ttft_ms': None, 'total_time_s': None,
                               'inference_time_s': None, 'native_decode_tps': None, 'output_tokens': None,
                               'finish_reason': None, 'quality': 'not_evaluated', 'retries': 0, 'fallbacks': [],
                               'timing_scope': 'Lane model creation, template/generation and model destruction; excludes pair identity checks and prior-model unload',
                               'ttft_scope': 'Native generation TTFT, excluding model loading',
                               'memory': None, 'energy': None}
                lanes[lane] = lane_result
                self._event(job, {'type': 'start', 'lane': lane, 'effective_configuration': ack})
                lane_start = time.perf_counter()
                model = None
                try:
                    model = (self.model_factory or NativeModel)(self.engine.runtime, lane_spec['path'], device=cfg['requested_device'],
                            threads=params['n_threads'], context=params['n_ctx'], plugin=cfg['plugin'], backend=backend)
                    provenance = model.provenance()
                    from .demo_routing import resolved_matches
                    if provenance['backend_id'] != backend or not resolved_matches(backend, provenance.get('resolved_device')):
                        raise ValueError('Native backend acknowledgement differs from requested backend')
                    provenance['model_path_or_id'] = cfg['model']
                    ack['native_provenance'] = provenance
                    if selected_route:
                        decision['effective_configuration'] = copy.deepcopy(ack)
                    lane_result.update(configuration_applied=True, effective_configuration=ack)
                    def token(piece):
                        if job['cancel_requested'] or time.perf_counter() >= deadline:
                            return False
                        lane_result['answer'] += piece
                        self._event(job, {'type': 'text', 'lane': lane, 'answer': lane_result['answer']})
                        return True
                    if job['cancel_requested'] or time.perf_counter() >= deadline:
                        raise InterruptedError('Comparison cancelled during model loading')
                    native = model.chat([{'role': 'user', 'content': request['prompt']}], max_tokens=128,
                                        temperature=0, reset=True, on_token=token)
                    # Native text is authoritative, including a truncated/cancelled answer.
                    lane_result['answer'] = native['text']
                    if native.get('backend_id') not in (None, backend):
                        raise ValueError('Generation reported a different backend')
                    profile = native.get('profile', {})
                    lane_result.update(native_profile=profile, sampling=native.get('sampling'),
                        ttft_ms=_metric(profile.get('ttft')) / 1000 if _metric(profile.get('ttft')) is not None else None,
                        output_tokens=_metric(profile.get('generated_tokens')), native_decode_tps=_metric(profile.get('decoding_speed')),
                        native_prefill_tps=_metric(profile.get('prefill_speed')),
                        inference_time_s=_metric(native.get('timings', {}).get('total')), finish_reason=profile.get('stop_reason'))
                    if job['cancel_requested'] or time.perf_counter() >= deadline:
                        raise InterruptedError('Comparison cancelled or deadline reached')
                    lane_result['status'] = 'completed'
                except InterruptedError:
                    lane_result['status'] = 'cancelled'
                    raise
                except Exception as exc:
                    lane_result.update(status='failed', error=str(exc))
                    raise
                finally:
                    if model is not None:
                        model.close()
                    lane_result['total_time_s'] = time.perf_counter() - lane_start
                    self._event(job, {'type': 'complete', 'lane': lane, 'result': copy.deepcopy(lane_result)})
            final_state = 'completed'
        except InterruptedError as exc:
            final_state, final_error = 'cancelled', str(exc)
        except Exception as exc:
            final_state, final_error = 'failed', str(exc)
        finally:
            if acquired:
                # Qualcomm plugins can retain DSP sessions beyond model.close().
                # Tear down the SDK between jobs before the next backend opens.
                if self.model_factory is None and self.engine.runtime is not None:
                    try:
                        self.engine.runtime.close()
                        self.engine.runtime = None
                        self.engine.runtime_binding = None
                    except Exception as exc:
                        final_state = 'failed'
                        final_error = f'{final_error + "; " if final_error else ""}SDK cleanup failed: {exc}'
                self.engine.lock.release()
            result['total_time_s'] = time.perf_counter() - start
            result['timing_scope'] = 'Pair identity checks, prior-model unload, both lane load/generate/unload cycles and final SDK cleanup; excludes HTTP/browser transport'
            with self.guard:
                job.update(state=final_state, error=final_error, result=result)
                self.active = None
                try:
                    (job['_output'] / 'result.json').write_text(json.dumps(self.snapshot(ident), indent=2), encoding='utf-8')
                except OSError as exc:
                    job.update(state='failed', error=f'Result persistence failed: {exc}')
