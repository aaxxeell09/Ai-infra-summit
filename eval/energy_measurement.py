"""Optional lifecycle coordination for the existing Secretary runner and PDH meter."""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import platform
from datetime import datetime, timezone

from turbo.telemetry import EnergySession, ProcessMemory, power_snapshot

SCHEMA = 'secretary-energy-v1'
BOUNDARY = 'warm_task_v1'
WARMUP_PROMPTS = (
    'List the files available in this workspace.',
    'Show the available workspace file inventory.',
    'Please list all available files in the workspace.',
)


def validate_protocol(protocol):
    # The session owns counter/idle configuration validation. No meter opened here.
    EnergySession.validate_protocol(protocol)
    for field in ('hardware_note', 'display_network_conditions', 'counter_resolution_evidence', 'power_mode'):
        if not isinstance(protocol.get(field), str) or not protocol[field].strip():
            raise ValueError('Energy protocol requires recorded ' + field)
    if protocol.get('power_source') not in ('ac', 'battery'):
        raise ValueError('Energy protocol requires one fixed power_source: ac or battery')
    if protocol.get('background_contamination') is not False:
        raise ValueError('Record background_contamination=false only after checking the environment')
    return protocol


def sdk_fingerprints(sdk_dir):
    root = Path(sdk_dir)
    binaries = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll','.so','.dylib'))
    if not binaries:
        raise ValueError('No SDK binaries available to fingerprint')
    result = {}
    for path in binaries:
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
        result[path.relative_to(root).as_posix()] = h.hexdigest()
    return result


def measured_run(config, metadata, cases, codec, execute, fixture_root, protocol, run_order,
                 native_runtime, native_model):
    """No backend-specific timing boundaries or settings. Called only with --energy-protocol."""
    from eval.scoring import digest
    validate_protocol(protocol)
    if platform.system() != 'Windows':
        raise ValueError('Energy measurements require Windows PDH on the target; no host substitution')
    runtime_hashes = sdk_fingerprints(config['sdk_dir'])  # outside load/task energy
    with ExitStack() as stack:
        session = EnergySession(protocol)
        stack.callback(session.close)
        memory = ProcessMemory(os.getpid())
        stack.callback(memory.close)
        before = power_snapshot()
        platform_idle = session.measure_idle('platform')
        with session.measure('cold_load') as cold:
            runtime = native_runtime(config['sdk_dir'])
            stack.callback(runtime.close)
            kwargs = {k:config[k] for k in ('device','threads','context','threads_batch','ubatch',
                      'n_batch','spec_type','draft_tokens','plugin','backend','stop_after_tool_call') if k in config}
            model = stack.enter_context(native_model(runtime, config['model_path'],
                                      generation_observer=session, **kwargs))
        metadata['inference_backend'] = {**model.provenance(), 'model_path_or_id':metadata['model_label']}
        from eval.secretary_adapter import TOOLS
        def complete(messages):
            return model.chat(messages, tools=TOOLS, max_tokens=config.get('max_tokens',128), temperature=0, reset=True)
        warmups = []
        for index in range(protocol['warmup_count']):
            with session.measure('warmup') as warm:
                complete([{'role':'system','content':codec.instructions()},
                          {'role':'user','content':WARMUP_PROMPTS[index % len(WARMUP_PROMPTS)]}])
            warmups.append(warm)
        runtime_idle = session.measure_idle('runtime')
        ready_power = power_snapshot()
        rows = execute(cases, codec, complete, fixture_root, measurement=session)
        after = power_snapshot()
        memory_result = memory.sample()
        invalid = []
        for field in ('ac_line_status', 'active_scheme_guid', 'battery_saver'):
            values = [p.get(field) for p in (before,ready_power,after)]
            if any(v is None or v in ('unknown','unavailable') for v in values):
                invalid.append('Power condition unavailable: '+field)
            elif values[0] != values[1] or values[0] != values[2]:
                invalid.append('Power condition changed: '+field)
        if before.get('ac_line_status') != protocol['power_source']:
            invalid.append('Observed power source differs from protocol')
        if not runtime_idle['stable']: invalid.append('Warm-runtime idle is unstable or unavailable')
        if not platform_idle['stable']: invalid.append('Platform idle is unstable or unavailable')
        if any(r['energy']['gross_energy_j'] is None for r in rows):
            invalid.append('Incomplete or unresolved warm-task energy; no partial-suite efficiency')
        if sdk_fingerprints(config['sdk_dir']) != runtime_hashes:
            invalid.append('Runtime binaries changed during measurement')
        signature = {
            'boundary':BOUNDARY, 'channel':protocol['channel'],
            'warmup_count':protocol['warmup_count'], 'warmup_prompts_sha256':digest(WARMUP_PROMPTS),
            'idle_window_s':protocol['idle_window_s'], 'idle_repeats':protocol['idle_repeats'],
            'counter_resolution_s':protocol['counter_resolution_s'],
            'protocol_sha256':digest(protocol),
            'instrumentation_sha256':metadata['energy_instrumentation_sha256'],
            'runtime_files_sha256':runtime_hashes,
            'power_condition':{'ac_line_status':before.get('ac_line_status'),
                               'active_scheme_guid':before.get('active_scheme_guid'),
                               'power_mode':protocol['power_mode'],
                               'battery_saver':before.get('battery_saver')},
            'machine':{'system':platform.system(),'machine':platform.machine(),
                       'hardware_note':protocol['hardware_note']},
        }
        metadata['energy_measurement'] = {
            'schema_version':SCHEMA, 'signature':signature, 'protocol':protocol,
            'valid':not invalid, 'invalid_reasons':invalid,
            'run_order':run_order, 'timestamp':datetime.now(timezone.utc).isoformat(),
            'power_before':before, 'power_ready':ready_power, 'power_after':after,
            'idle_platform':platform_idle, 'idle_runtime':runtime_idle, 'cold_load':cold,
            'warmups':warmups, 'process_memory':memory_result,
            'memory_scope':'process peak working set includes load, warmup and audit',
            'thermal_telemetry':None, 'background_contamination':protocol['background_contamination'],
            'npu_only_energy':None,
        }
        metadata['warmup'] = str(protocol['warmup_count'])+' non-evaluation requests, reset each call; energy reported separately'
        return rows
