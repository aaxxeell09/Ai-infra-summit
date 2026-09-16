import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { normalizeConfirmed, exportConfirmedProfile, createConfirmedProvider } from '../public/confirmed.mjs';
import { createConfirmedComparisonRequest, comparisonLanes } from '../public/comparison.mjs';

const results = new URL('../../benchmarks/results/', import.meta.url);
function fixture() {
  const bytes = readFileSync(new URL('recommended.json', results));
  const recommendation = JSON.parse(bytes);
  const manifest = readFileSync(new URL(recommendation.scope.evidence, results));
  return { schema_version: 'local-turbo.confirmed.v1', mode: 'recorded',
    source: 'benchmarks/results/recommended.json', energy_channel: 'SYS',
    dispatch_evidence: 'dispatch/npu-ops.txt',
    recommendation_sha256: createHash('sha256').update(bytes).digest('hex'),
    manifest_sha256: createHash('sha256').update(manifest).digest('hex'),
    recommendation };
}

test('published confirmed profiles show the speed and energy trade-off without mixing scopes', () => {
  const record = normalizeConfirmed(fixture());
  assert.ok(record.decodeRatio > 2.6 && record.decodeRatio < 2.8);
  assert.ok(record.energyRatio > 1.5 && record.energyRatio < 1.6);
  assert.equal(record.scope.power_state, 'battery');
  assert.equal(record.scope.quality_calibrated, false);
  assert.equal(record.energyChannel, 'SYS');
  assert.equal(record.fast.metrics.output_tokens, record.efficient.metrics.output_tokens);
});

test('confirmed data refuses changed workload, missing full output, and invented quality', () => {
  for (const mutate of [
    p => { p.recommendation.scope.prompt_tokens = 128; },
    p => { p.recommendation.modes.fast.metrics.output_tokens = 1600; },
    p => { p.recommendation.scope.quality_calibrated = true; },
    p => { p.energy_channel = 'NPU'; },
  ]) {
    const payload = fixture(); mutate(payload);
    assert.throws(() => normalizeConfirmed(payload));
  }
});

test('profile exports retain source hashes and do not claim application or task quality', () => {
  const record = normalizeConfirmed(fixture());
  const exported = exportConfirmedProfile(record, 'efficient');
  assert.equal(exported.configuration.device, 'npu');
  assert.equal(exported.source_sha256, record.recommendationHash);
  assert.equal(exported.confirmation_manifest_sha256, record.manifestHash);
  assert.equal(exported.quality_calibrated, false);
  assert.equal(exported.applied_to_device, false);
  assert.throws(() => exportConfirmedProfile(record, 'qairt'));
});

test('preview labels use confirmed auto NPU and fast CPU while retaining a simulated execution', () => {
  const record = normalizeConfirmed(fixture());
  const snapshot = { model: 'Qwen3-0.6B-Q4_0.gguf', modelHash: record.modelHash };
  const request = createConfirmedComparisonRequest(snapshot, record, 'speed', 'quick', 'preview-1');
  assert.equal(request.baseline.requested_device, 'auto');
  assert.equal(request.baseline.resolved_device, 'HTP0');
  assert.equal(request.selected.params.n_threads, 10);
  assert.match(comparisonLanes(request).default.configuration, /Auto → NPU/);
  assert.equal(request.baseline.model_sha256, request.selected.model_sha256);
  assert.throws(() => createConfirmedComparisonRequest({ ...snapshot, modelHash: 'wrong' }, record, 'speed', 'quick', 'preview-1'));
});

test('failed confirmation fetch never falls back to screening measurements', async () => {
  const provider = createConfirmedProvider(async () => ({ ok: false, status: 503 }));
  await assert.rejects(provider.load(), /503/);
});
