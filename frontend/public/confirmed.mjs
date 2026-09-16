const positive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);

export function normalizeConfirmed(payload) {
  const record = payload?.recommendation;
  const scope = record?.scope;
  const fast = record?.modes?.fast;
  const efficient = record?.modes?.efficient;
  if (payload?.schema_version !== 'local-turbo.confirmed.v1' || payload.mode !== 'recorded' ||
      record?.schema_version !== 'turbo.recommended.v1' || !hash(record.model_sha256) ||
      !hash(payload.recommendation_sha256) || !hash(payload.manifest_sha256) ||
      scope?.evidence !== 'confirm-auto-01/sweep.json' || scope.power_state !== 'battery' ||
      scope.prompt_tokens !== 512 || scope.generated_tokens !== 128 || scope.context !== 4096 ||
      scope.cold_kv !== true || scope.quality_calibrated !== false ||
      scope.energy_interval !== 'full trial including load, prefill and decode' ||
      payload.energy_channel !== 'SYS' || payload.dispatch_evidence !== 'dispatch/npu-ops.txt') {
    throw new Error('Confirmed result provenance is incomplete or unsupported.');
  }
  for (const [profile, device, threads] of [[fast, 'cpu', 10], [efficient, 'npu', 0]]) {
    const m = profile?.metrics;
    if (profile?.device !== device || profile.threads !== threads || profile.context !== scope.context ||
        !m || !['decode_tps', 'prefill_tps', 'median_ttft_ms', 'median_peak_mib',
          'tokens_per_joule', 'energy_j'].every(key => positive(m[key])) ||
        m.output_tokens !== 3200 || m.battery_only !== true) {
      throw new Error('Confirmed performance profiles are missing or incomparable.');
    }
  }
  return {
    source: payload.source, modelHash: record.model_sha256, runtime: record.runtime,
    device: record.device, scope, fast, efficient,
    decodeRatio: fast.metrics.decode_tps / efficient.metrics.decode_tps,
    energyRatio: efficient.metrics.tokens_per_joule / fast.metrics.tokens_per_joule,
    dispatchEvidence: payload.dispatch_evidence, energyChannel: payload.energy_channel,
    recommendationHash: payload.recommendation_sha256, manifestHash: payload.manifest_sha256,
    raw: payload,
  };
}

export function exportConfirmedProfile(confirmed, mode) {
  const profile = confirmed?.[mode];
  if (!['fast', 'efficient'].includes(mode) || !profile) throw new Error('Unknown confirmed profile.');
  return {
    schema_version: 'local-turbo.performance-profile.v1', status: 'measured',
    objective: mode === 'fast' ? 'native_decode_throughput' : 'full_trial_energy_efficiency',
    source: confirmed.source, source_sha256: confirmed.recommendationHash,
    confirmation_manifest_sha256: confirmed.manifestHash,
    model_sha256: confirmed.modelHash, runtime: confirmed.runtime,
    workload: confirmed.scope, configuration: profile, energy_channel: confirmed.energyChannel,
    quality_calibrated: false, applied_to_device: false,
  };
}

export function createConfirmedProvider(fetcher = fetch) {
  return { async load({ signal } = {}) {
    const response = await fetcher('/api/confirmed', { signal });
    if (!response.ok) throw new Error(`Confirmed results unavailable (${response.status}).`);
    return normalizeConfirmed(await response.json());
  } };
}
