import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLatestResults } from '../public/latest.mjs';

const candidate = overrides => ({
  label: 'Qwen3 0.6B', size: '0.6B', runtime: 'QAIRT', correct: 20, total: 50,
  accuracy_pct: 40, average_inference_ms: 810.76248, median_inference_ms: 524.575,
  invalid_rate: 0.34, quality_status: 'NOT_COMPARABLE', ...overrides,
});

const payload = () => ({
  schema_version: 'local-turbo.latest-results.v1',
  device: 'Dell Latitude 7455',
  qairt: {
    model: 'qwen3-06-qairt-x-elite', runtime: 'qairt', requested_device: 'npu', resolved_device: 'NPU', dispatch_verified: false,
    control: candidate({ label: 'Standard generation' }),
    optimized: candidate({ label: 'Stop after tool call', correct: 29, accuracy_pct: 58, average_inference_ms: 518.68592, median_inference_ms: 496.1615, invalid_rate: 0.08 }),
  },
  candidates: [
    candidate({ correct: 29, accuracy_pct: 58, average_inference_ms: 518.68592, median_inference_ms: 496.1615, invalid_rate: 0.08 }),
    candidate({ label: 'Qwen3 4B', size: '4B', runtime: 'llama.cpp · CPU', correct: 37, accuracy_pct: 74, average_inference_ms: 5940.103, median_inference_ms: 3430.061, invalid_rate: 0.04 }),
    candidate({ label: 'Qwen3 8B', size: '8B', runtime: 'llama.cpp · CPU', correct: 38, accuracy_pct: 76, average_inference_ms: 19896.854, median_inference_ms: 12808.861, invalid_rate: 0.04, quality_status: 'NOT_QUALIFIED' }),
  ],
  quality_gate_passed: false,
  sources: {},
});

test('derives the bounded QAIRT improvement from comparable full runs', () => {
  const result = normalizeLatestResults(payload());
  assert.equal(result.qairt.accuracyGainPoints, 18);
  assert.ok(Math.abs(result.qairt.latencyReductionPct - 36.02) < 0.02);
  assert.equal(result.qairt.invalidReductionPoints, 26);
});

test('rejects a candidate count that could hide or add model results', () => {
  const input = payload();
  input.candidates.pop();
  assert.throws(() => normalizeLatestResults(input), /incomplete/);
});

test('rejects QAIRT runs with mismatched task counts', () => {
  const input = payload();
  input.qairt.optimized.total = 35;
  assert.throws(() => normalizeLatestResults(input), /comparable full benchmark/);
});
