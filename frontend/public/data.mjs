// This module is the boundary between backend evidence and presentation.
const finite = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const positive = value => finite(value) !== null && value > 0 ? value : null;
export const METRICS = {
  decode: { label: 'Answer writing speed', tab: 'Write the answer', unit: 'tok/s', key: 'decode_tps', direction: 'max', hint: 'Higher is faster',
    description: 'How quickly the model writes its answer once it has started responding.',
    units: 'Tokens per second. A token is a small piece of text, not necessarily a whole word.', best: 'writing the answer' },
  prefill: { label: 'Prompt reading speed', tab: 'Read the prompt', unit: 'tok/s', key: 'prefill_tps', direction: 'max', hint: 'Higher is faster',
    description: 'How quickly the model processes your request and supplied text before answering.',
    units: 'Tokens per second. A token is a small piece of text, not necessarily a whole word.', best: 'processing the prompt' },
  ttft: { label: 'Wait before the answer starts', tab: 'Start responding', unit: 'ms', key: 'ttft_ms', direction: 'min', hint: 'Lower is faster',
    description: 'How long you wait before the model produces the first piece of its answer.',
    units: 'Milliseconds of waiting. 1,000 ms = 1 second. This is not the time to finish the answer.', best: 'starting the answer' },
};
const arg = (command, key) => {
  const at = command?.indexOf(key) ?? -1;
  return at >= 0 ? command[at + 1] : null;
};

export function normalizeSnapshot(payload) {
  if (payload?.schema_version !== 'local-turbo.recorded.v1' || payload.mode !== 'recorded' ||
      payload.manifest?.schema_version !== 'turbo.sweep.v1' || !Array.isArray(payload.manifest.cells)) {
    throw new Error('Unsupported benchmark response. No sample data was substituted.');
  }
  const { manifest, reports = {} } = payload;
  if (![manifest.model_sha256, manifest.runtime_sha256].every(value => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value)) || !manifest.timing_source) {
    throw new Error('Recorded model/runtime provenance is missing. Results cannot be compared.');
  }
  const rows = manifest.cells.map(cell => {
    const report = reports[cell.id];
    const params = report?.params;
    const requestedDevice = arg(cell.command, '--device');
    const threads = params?.n_threads ?? (arg(cell.command, '-t') === null ? null : Number(arg(cell.command, '-t')));
    const device = report?.device ?? requestedDevice ?? 'unknown';
    const validCounts = params && ['repetitions', 'n_prompt', 'n_gen', 'n_ctx'].every(key => Number.isInteger(params[key]) && params[key] > 0) &&
      Number.isInteger(params.warmup) && params.warmup >= 0 && Number.isInteger(params.n_threads) && params.n_threads >= 0;
    const commandMatches = params && [['-p','n_prompt'],['-n','n_gen'],['-c','n_ctx'],['-t','n_threads'],['-r','repetitions'],['--warmup','warmup'],['--temperature','temperature'],['--seed','seed']]
      .every(([flag, key]) => arg(cell.command, flag) !== null && Number(arg(cell.command, flag)) === params[key]) &&
      requestedDevice === report.device && arg(cell.command, '--plugin') === report.plugin && arg(cell.command, '-m') === report.model_path;
    const complete = cell.status === 'completed' && cell.exit_code === 0 && report?.schema_version === '4' && validCounts && commandMatches &&
      report.cell_id === cell.id && cell.complete_length_runs === params.repetitions && Array.isArray(report.runs) && report.runs.length === params.repetitions &&
      report.runs.every(run => run.gen_tokens === params.n_gen && run.prompt_tokens === params.n_prompt && run.stop_reason === 'length');
    const label = device === 'cpu' ? (threads === 0 ? 'CPU · default' : `CPU · ${threads ?? '?'} threads`) : device.toUpperCase();
    const signature = params ? JSON.stringify([
      manifest.model_sha256, manifest.runtime_sha256, manifest.timing_source, report.plugin,
      params.n_prompt, params.n_gen, params.n_ctx, params.temperature, params.seed, params.warmup, params.repetitions,
    ]) : null;
    return {
      id: cell.id, label, device, requestedDevice, resolvedDevice: report?.device_id ?? null, threads,
      status: complete ? 'completed' : (cell.status === 'completed' ? 'incomplete' : cell.status || 'unavailable'),
      reason: complete ? null : cell.error || (report && !commandMatches ? 'Result configuration does not match its recorded command.' : 'Missing, failed, or incomplete recorded trial.'),
      signature, params: params ?? null, plugin: report?.plugin ?? null,
      metrics: {
        decode: complete ? positive(report.agg?.decode_tps?.median) : null,
        prefill: complete ? positive(report.agg?.prefill_tps?.median) : null,
        ttft: complete ? positive(report.agg?.ttft_ms?.median) : null,
      },
      memory_mb: finite(report?.telemetry?.peak_working_set_mb),
      telemetry: report?.telemetry ?? null,
      dispatch: ['npu', 'hybrid'].includes(device) ? 'Operation-level dispatch verification pending' : 'Native runtime report',
      raw: report ?? cell,
    };
  });
  return { mode: 'recorded', source: payload.source, device: payload.device, runtime: payload.runtime,
    model: manifest.model_name, modelHash: manifest.model_sha256, runtimeHash: manifest.runtime_sha256, manifestHash: payload.manifest_sha256 ?? null,
    recordedAt: manifest.started_at, phase: manifest.phase, timingSource: manifest.timing_source,
    rows, manifest, raw: payload };
}

export function rankRows(snapshot, metric = 'decode') {
  const definition = METRICS[metric];
  if (!definition) throw new Error('Unknown metric');
  const baseline = snapshot.rows.find(row => row.id === 'cpu-t0' && row.status === 'completed') ??
    snapshot.rows.find(row => row.status === 'completed');
  const eligible = row => row.status === 'completed' && row.signature === baseline?.signature && row.metrics[metric] !== null;
  const rows = [...snapshot.rows].sort((a, b) => {
    if (eligible(a) !== eligible(b)) return eligible(a) ? -1 : 1;
    if (!eligible(a)) return a.label.localeCompare(b.label);
    const delta = a.metrics[metric] - b.metrics[metric];
    return (definition.direction === 'max' ? -delta : delta) || a.label.localeCompare(b.label);
  });
  const best = rows.find(eligible);
  const leaders = best ? rows.filter(row => eligible(row) && row.metrics[metric] === best.metrics[metric]).map(row => row.id) : [];
  return { rows, leaders, baseline, eligible };
}

export function exportConfiguration(snapshot, row, metric) {
  if (!rankRows(snapshot, metric).eligible(row)) throw new Error('This trial is not eligible for configuration export.');
  return {
    schema_version: 'local-turbo.recommendation.v1', status: 'provisional',
    objective: METRICS[metric].key, source_mode: snapshot.mode, source: snapshot.source,
    cell_id: row.id, recorded_at: snapshot.recordedAt, source_sha256: snapshot.manifestHash,
    model: snapshot.model, model_sha256: snapshot.modelHash, runtime_sha256: snapshot.runtimeHash,
    runtime: snapshot.runtime, plugin: row.plugin, requested_device: row.requestedDevice,
    resolved_device: row.resolvedDevice, params: row.params, measured: row.metrics,
    measurement_source: snapshot.timingSource, dispatch_evidence: row.dispatch,
    quality_validated: false, confirmed_speedup: false, applied_to_device: false,
  };
}

export function createRecordedProvider(fetcher = fetch) {
  return {
    mode: 'recorded',
    async load({ signal } = {}) {
      const response = await fetcher('/api/recorded', { signal });
      if (!response.ok) throw new Error(`Recorded results unavailable (${response.status}).`);
      return normalizeSnapshot(await response.json());
    },
  };
}
