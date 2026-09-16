const finite = value => typeof value === 'number' && Number.isFinite(value);

function validateCandidate(candidate) {
  return candidate && typeof candidate.label === 'string' && typeof candidate.runtime === 'string' &&
    Number.isInteger(candidate.correct) && Number.isInteger(candidate.total) && candidate.total > 0 &&
    candidate.correct >= 0 && candidate.correct <= candidate.total && finite(candidate.accuracy_pct) &&
    candidate.accuracy_pct >= 0 && candidate.accuracy_pct <= 100 && finite(candidate.median_inference_ms) &&
    candidate.median_inference_ms > 0 && finite(candidate.average_inference_ms) && candidate.average_inference_ms > 0 &&
    finite(candidate.invalid_rate) && candidate.invalid_rate >= 0 &&
    candidate.invalid_rate <= 1 && typeof candidate.quality_status === 'string';
}

export function normalizeLatestResults(payload) {
  if (payload?.schema_version !== 'local-turbo.latest-results.v1' || !payload.qairt ||
      !validateCandidate(payload.qairt.control) || !validateCandidate(payload.qairt.optimized) ||
      !Array.isArray(payload.candidates) || payload.candidates.length !== 3 ||
      !payload.candidates.every(validateCandidate) || payload.quality_gate_passed !== false) {
    throw new Error('Latest device evidence is incomplete. The recorded comparison remains available.');
  }
  const { control, optimized } = payload.qairt;
  if (control.total !== optimized.total || control.runtime !== optimized.runtime ||
      payload.candidates[0].label !== 'Qwen3 0.6B') {
    throw new Error('QAIRT results do not describe one comparable full benchmark.');
  }
  return {
    ...payload,
    qairt: {
      ...payload.qairt,
      accuracyGainPoints: optimized.accuracy_pct - control.accuracy_pct,
      latencyReductionPct: (1 - optimized.average_inference_ms / control.average_inference_ms) * 100,
      invalidReductionPoints: (control.invalid_rate - optimized.invalid_rate) * 100,
    },
  };
}

export function createLatestResultsProvider(fetcher = fetch) {
  return {
    async load({ signal } = {}) {
      const response = await fetcher('/api/latest-results', { signal });
      if (!response.ok) throw new Error(`Latest device evidence unavailable (${response.status}).`);
      return normalizeLatestResults(await response.json());
    },
  };
}
