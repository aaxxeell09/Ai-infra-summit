"""Structural consistency checks for imported reports; never alter scoring."""
import math
import re
import statistics
from pathlib import Path

from eval.scoring import digest
from eval.energy_measurement import validate_protocol, WARMUP_PROMPTS

BACKENDS = {'llama_cpp_cpu': ('llama_cpp', 'cpu'),
            'llama_cpp_htp': ('llama_cpp', 'npu'), 'qairt_npu': ('qairt', 'npu')}


def classify_backend_identity(report, expected_backend=None):
    """Classify consistency of reported evidence; requested devices prove no dispatch.

    verified_consistent requires an explicit dispatch_verified=true assertion and
    matching resolved-device evidence. It is not independent hardware verification.
    """
    errors = []
    def result(status, backend=None):
        return {'classification': status, 'backend_id': backend, 'reasons': errors,
                'verification_basis': 'reported dispatch flag and resolved device' if status == 'verified_consistent' else None}
    if not isinstance(report, dict):
        errors.append('Invalid report object')
        return result('contradiction')
    identity = report.get('inference_backend')
    config = report.get('config')
    cases = report.get('results')
    if identity is None: identity = {}
    if config is None: config = {}
    if cases is None: cases = []
    if not isinstance(identity, dict) or not isinstance(config, dict) or not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
        errors.append('Invalid backend identity/config/results object')
        return result('contradiction')
    records = [('report', report), ('identity', identity), ('config', config)] + [('case ' + str(i), c) for i, c in enumerate(cases)]
    def device_class(value):
        if not isinstance(value, str): return None
        lowered = value.lower()
        return 'cpu' if lowered == 'cpu' else 'npu' if lowered == 'npu' or lowered.startswith('htp') else 'gpu' if lowered.startswith(('gpu', 'cuda', 'vulkan')) else None
    backend = identity.get('backend_id')
    if backend is not None and not isinstance(backend, str):
        errors.append('Invalid backend_id type')
        return result('contradiction')
    if not backend:
        plugin = config.get('plugin')
        selected = [device_class(c.get('selected_device')) for c in cases]
        if selected and all(v == selected[0] and v is not None for v in selected):
            backend = {('llama_cpp', 'cpu'): 'llama_cpp_cpu', ('llama_cpp', 'npu'): 'llama_cpp_htp', ('qairt', 'npu'): 'qairt_npu'}.get((plugin, selected[0])) if isinstance(plugin, str) else None
    if backend is not None and backend not in BACKENDS:
        errors.append('Unknown backend identity')
        return result('unknown')
    # Expected slot is only a consistency constraint, never identity evidence.
    target = backend or expected_backend
    if target not in BACKENDS:
        return result('unknown')
    if backend and expected_backend and backend != expected_backend:
        errors.append('Backend identity does not match slot')
    plugin, device = BACKENDS[target]
    for label, record in records:
        for key in ('backend_id', 'backend', 'plugin', 'runtime', 'device', 'requested_device', 'resolved_device', 'selected_device', 'model_artifact_type'):
            value = record.get(key)
            if value is None: continue
            if not isinstance(value, str):
                errors.append(label + ': invalid ' + key + ' type')
                continue
            if key in ('backend_id', 'backend') and value not in (target, 'geniex'):
                errors.append(label + ': contradictory ' + key)
            elif key in ('plugin', 'runtime') and value != plugin:
                errors.append(label + ': contradictory ' + key)
            elif key in ('device', 'requested_device', 'resolved_device', 'selected_device'):
                actual = device_class(value)
                if actual and actual != device:
                    errors.append(label + ': contradictory ' + key)
            elif key == 'model_artifact_type' and value.upper() != ('QAIRT' if plugin == 'qairt' else 'GGUF'):
                errors.append(label + ': contradictory model_artifact_type')
        if record.get('dispatch_verified') is not None and type(record['dispatch_verified']) is not bool:
            errors.append(label + ': invalid dispatch_verified type')
    for field in ('model_sha256', 'config_sha256', 'runtime_sha256', 'geniex_version', 'qairt_version'):
        values = []
        for label, record in records:
            value = record.get(field)
            if value is None: continue
            if not isinstance(value, str) or not value:
                errors.append(label + ': invalid ' + field + ' type')
            else: values.append(value)
        if len(set(values)) > 1:
            errors.append('Contradictory ' + field + ' across report/config/case evidence')
    dispatch_flags = [record['dispatch_verified'] for _, record in records if type(record.get('dispatch_verified')) is bool]
    if True in dispatch_flags and False in dispatch_flags:
        errors.append('Contradictory dispatch_verified flags across report/case evidence')
    if errors: return result('contradiction', backend)
    if not backend: return result('unknown')
    resolved = device_class(identity.get('resolved_device'))
    if identity.get('dispatch_verified') is True and resolved == device:
        return result('verified_consistent', backend)
    return result('consistent_but_dispatch_unverified', backend)


def backend_identity_errors(report, expected_backend=None):
    classification = classify_backend_identity(report, expected_backend)
    errors = classification['reasons'][:]
    if classification['classification'] == 'unknown' and not errors:
        errors.append('Unknown backend identity')
    return errors


def _finite(value, positive=False):
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def _observation_valid(sample, scope):
    if not isinstance(sample, dict) or sample.get('scope') != scope or sample.get('channel') != 'SYS':
        return False
    before, after = sample.get('raw_before'), sample.get('raw_after')
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    try:
        first, last = before['channels_pwh']['SYS'], after['channels_pwh']['SYS']
        start, end = before['monotonic_s'], after['monotonic_s']
        duration, energy = sample['duration_s'], sample['gross_energy_j']
        return (not before.get('error') and not after.get('error')
                and all(_finite(v) for v in (first, last, start, end, duration, energy))
                and last > first and end > start and duration > 0 and energy > 0
                and math.isclose(duration, end-start, rel_tol=1e-7, abs_tol=1e-9)
                and math.isclose(energy, (last-first)*3.6e-9, rel_tol=1e-7, abs_tol=1e-9))
    except (KeyError, TypeError):
        return False


def energy_evidence_errors(report):
    """Revalidate retained commissioning evidence, not just producer's valid flag."""
    errors = []
    if not isinstance(report, dict):
        return ['Invalid report object']
    energy = report.get('energy_measurement')
    if not isinstance(energy, dict):
        return ['Energy evidence object missing']
    protocol, signature = energy.get('protocol'), energy.get('signature')
    if not isinstance(signature, dict):
        return ['Energy signature object missing']
    try:
        validate_protocol(protocol)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return ['Invalid retained energy protocol: ' + str(exc)]
    if signature.get('protocol_sha256') != digest(protocol):
        errors.append('Energy protocol hash does not match retained protocol')
    for key in ('channel', 'warmup_count', 'idle_window_s', 'idle_repeats', 'counter_resolution_s'):
        if signature.get(key) != protocol[key]:
            errors.append('Energy signature contradicts protocol: ' + key)
    if signature.get('warmup_prompts_sha256') != digest(WARMUP_PROMPTS):
        errors.append('Warmup prompt provenance missing or incompatible')
    for key in ('runtime_files_sha256', 'instrumentation_sha256'):
        values = signature.get(key)
        if not isinstance(values, dict) or not values or any(not isinstance(k, str) or not k or not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{64}', v) is None for k, v in values.items()):
            errors.append('Invalid energy fingerprint mapping: ' + key)
    if report.get('energy_instrumentation_sha256') is not None and signature.get('instrumentation_sha256') != report['energy_instrumentation_sha256']:
        errors.append('Instrumentation signature contradicts report provenance')
    machine = signature.get('machine')
    if not isinstance(machine, dict) or machine.get('hardware_note') != protocol['hardware_note']:
        errors.append('Machine signature contradicts protocol')
    power = signature.get('power_condition')
    if not isinstance(power, dict):
        errors.append('Invalid power condition')
    else:
        if power.get('power_mode') != protocol['power_mode'] or power.get('ac_line_status') != protocol['power_source']:
            errors.append('Power signature contradicts protocol')
        for key in ('power_before', 'power_ready', 'power_after'):
            record = energy.get(key)
            if not isinstance(record, dict) or any(record.get(k) != power.get(k) for k in ('ac_line_status', 'active_scheme_guid', 'battery_saver')):
                errors.append('Missing or contradictory power observation: ' + key)
    if energy.get('background_contamination') is not False:
        errors.append('Background contamination observation missing or invalid')
    for kind in ('platform', 'runtime'):
        idle = energy.get('idle_' + kind)
        samples = idle.get('samples') if isinstance(idle, dict) else None
        if not isinstance(samples, list) or len(samples) != protocol['idle_repeats'] or any(not _observation_valid(s, kind + '_idle') for s in samples):
            errors.append('Missing or invalid ' + kind + ' idle observations')
            continue
        powers = [s['gross_energy_j']/s['duration_s'] for s in samples]
        if any(not _finite(power, True) for power in powers):
            errors.append('Nonfinite ' + kind + ' idle power')
            continue
        mean = statistics.mean(powers)
        cv = statistics.pstdev(powers)/mean
        if (idle.get('stable') is not True or cv > protocol['idle_max_cv']
                or any(s['duration_s'] < protocol['idle_window_s'] for s in samples)
                or not _finite(idle.get('mean_power_w'), True) or not math.isclose(idle['mean_power_w'], mean, rel_tol=1e-7)
                or not _finite(idle.get('cv')) or not math.isclose(idle['cv'], cv, rel_tol=1e-7, abs_tol=1e-9)):
            errors.append('Unstable or inconsistent ' + kind + ' idle evidence')
    warmups = energy.get('warmups')
    if not isinstance(warmups, list) or len(warmups) != protocol['warmup_count'] or any(not _observation_valid(w, 'warmup') for w in warmups):
        errors.append('Missing or invalid warmup observations')
    return errors


def write_report_pair(output, markdown_text, json_text, inputs=()):
    """Reserve both destinations exclusively before writing; never replace evidence."""
    output = Path(output)
    if output.suffix != '.md':
        raise ValueError('Output must end in .md')
    paths = (output, output.with_suffix('.json'))
    sources = {Path(p).resolve() for p in inputs if p is not None}
    if any(p.resolve() in sources for p in paths):
        raise ValueError('Output collides with an input file')
    if any(p.exists() or p.is_symlink() for p in paths):
        raise ValueError('Refusing to overwrite existing report')
    output.parent.mkdir(parents=True, exist_ok=True)
    created, handles = [], []
    try:
        for path in paths:
            handles.append(path.open('x', encoding='utf-8'))
            created.append(path)
        for handle, text in zip(handles, (markdown_text, json_text)):
            handle.write(text)
        for handle in handles:
            handle.close()
    except BaseException:
        for handle in handles:
            handle.close()
        for path in created:
            path.unlink()
        raise
