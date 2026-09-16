"""Explicit public-demo task policy, separate from quality-calibrated routing.

This policy selects a configured artifact/backend; it does not invent speed or
quality profiles. A successful resolver is a prerequisite, not utilization proof.
"""
import json
from pathlib import Path

POLICY = 'public-demo-v1'
ROUTES = (
    ('qwen06-qairt', 'Qwen3 0.6B · Qualcomm QAIRT / NPU', 'qwen06-qairt', 'qairt', 'npu', 'qairt_npu', 0),
    ('qwen06-htp', 'Qwen3 0.6B · Hexagon HTP', 'qwen06', 'llama_cpp', 'npu', 'llama_cpp_htp', 0),
    ('qwen06-gpu', 'Qwen3 0.6B · Adreno GPU', 'qwen06', 'llama_cpp', 'gpu', 'llama_cpp_gpu', 0),
    ('qwen06-cpu', 'Qwen3 0.6B · CPU, 10 threads', 'qwen06', 'llama_cpp', 'cpu', 'llama_cpp_cpu', 10),
    ('qwen4b-cpu', 'Qwen3 4B · CPU, 10 threads', 'qwen4b', 'llama_cpp', 'cpu', 'llama_cpp_cpu', 10),
)


def catalog(config):
    from .native import _qairt_bundle_input
    rows = []
    for ident, label, model_id, plugin, device, backend, threads in ROUTES:
        spec = config.get('models', {}).get(model_id, {})
        path = Path(spec.get('path', ''))
        row = dict(id=ident, label=label, model_id=model_id, model=path.name,
                   plugin=plugin, device=device, backend_id=backend, threads=threads,
                   context=4096, quantization='Q4_0' if plugin == 'llama_cpp' else None,
                   available=False, reason='Model is not registered',
                   availability_scope='Configured files only; native resolution and loading are checked during execution')
        if spec:
            try:
                if spec.get('plugin', 'llama_cpp') != plugin:
                    raise ValueError('Registered plugin differs from route')
                if plugin == 'qairt':
                    _, row['context'] = _qairt_bundle_input(str(path))
                    if not (path / 'geniex.json').is_file():
                        raise ValueError('Missing QAIRT geniex.json')
                    manifest = json.loads((path / 'geniex.json').read_text(encoding='utf-8'))
                    declared = manifest.get('ModelFile', {})
                    if isinstance(declared, dict) and len(declared) == 1:
                        row['quantization'] = next(iter(declared))
                        row['quantization_scope'] = 'Declared by installed geniex.json; not independently measured'
                elif not path.is_file() or path.suffix.lower() != '.gguf':
                    raise ValueError('Registered GGUF file is unavailable')
                expected = {'qwen06': 'Qwen3-0.6B-Q4_0.gguf', 'qwen4b': 'Qwen3-4B-Instruct-2507-Q4_0.gguf'}
                if model_id in expected and path.name != expected[model_id]:
                    raise ValueError('Registered model does not match this demo task policy')
                row.update(available=True, reason='Configured; execution not yet verified for this run')
            except (OSError, ValueError) as exc:
                row['reason'] = str(exc)
        rows.append(row)
    return rows


def resolved_matches(backend, resolved):
    name = (resolved or '').upper()
    return {'llama_cpp_cpu': name in ('', 'CPU'),
            'llama_cpp_gpu': name.startswith('GPU'),
            'llama_cpp_htp': name.startswith('HTP'),
            'qairt_npu': name == 'NPU' or name.startswith('HTP')}.get(backend, False)


def choose_route(config, request, runtime):
    """Availability fallback is recorded; inference failures never trigger retry."""
    selection = request['routing']['selection']
    rows = catalog(config)
    if selection == 'auto':
        ids = (['qwen06-qairt', 'qwen06-htp', 'qwen06-gpu', 'qwen06-cpu']
               if request['prompt_id'] == 'quick' else ['qwen4b-cpu'])
        reason = ('Short explanation: use the small model, preferring the registered Qualcomm QAIRT bundle.'
                  if request['prompt_id'] == 'quick' else
                  'Multi-step schedule: request the 4B model on the established CPU path. This is a task heuristic, not a measured quality advantage.')
    else:
        ids, reason = [selection], 'Explicit route selected in the demo.'
    by_id = {row['id']: row for row in rows}
    selected = None
    for ident in ids:
        row = by_id[ident]
        if not row['available']:
            continue
        try:
            device, layers, warning = runtime.resolve_device(row['plugin'], row['device'])
            if not resolved_matches(row['backend_id'], device):
                raise ValueError('Native resolver does not match requested backend')
            row.update(resolved_device=device, n_gpu_layers=layers, resolver_warning=warning,
                       reason='Files registered and native alias resolved; load still required')
            selected = row
            break
        except (ValueError, RuntimeError) as exc:
            row.update(available=False, reason=str(exc))
    if selected is None:
        raise ValueError('No available route satisfies this task policy: ' + '; '.join(f"{i}: {by_id[i]['reason']}" for i in ids))
    decision = dict(selection=selection, policy=POLICY, selected_route_id=selected['id'],
                    reason=reason, quality='not_calibrated', candidates=rows,
                    preference_order=ids, calibrated=False, fastest_claim=False,
                    fallback_scope='Availability checks only; execution failure is surfaced without retry',
                    artifact_scope='QAIRT uses a separate compiled artifact; not the same GGUF quantization')
    return selected, decision
