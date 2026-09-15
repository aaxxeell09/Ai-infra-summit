import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { normalizeSnapshot, rankRows, exportConfiguration, createRecordedProvider } from '../public/data.mjs';
import { initialFiles, simulateScenario } from '../public/demo.mjs';

function fixture() {
  const root = new URL('../../benchmarks/results/screen-01/', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('sweep.json', root)));
  const reports = Object.fromEntries(manifest.cells.map(cell => [cell.id, JSON.parse(readFileSync(new URL(`${cell.id}.json`, root)))]));
  return { schema_version: 'local-turbo.recorded.v1', mode: 'recorded', source: 'benchmarks/results/screen-01', manifest, reports };
}

test('real recorded cells rank correctly for throughput and time to first response', () => {
  const data = normalizeSnapshot(fixture());
  assert.equal(data.rows.length, 10);
  assert.ok(data.rows.every(row => row.status === 'completed'));
  assert.deepEqual(rankRows(data, 'decode').leaders, ['cpu-t10']);
  assert.deepEqual(rankRows(data, 'ttft').leaders, ['cpu-t2']);
  assert.deepEqual(rankRows(data, 'prefill').leaders, ['cpu-t2']);
  assert.equal(data.rows.find(row => row.id === 'cpu-t10').metrics.decode, 97.90581);
});

test('failed cells stay visible and cannot rank or export', () => {
  const payload = fixture(); const cell = payload.manifest.cells.find(row => row.id === 'cpu-t10');
  cell.status = 'timeout'; cell.exit_code = 1;
  const data = normalizeSnapshot(payload); const row = data.rows.find(row => row.id === cell.id);
  assert.equal(row.metrics.decode, null);
  assert.equal(row.status, 'timeout');
  assert.equal(rankRows(data).rows.length, 10);
  assert.ok(!rankRows(data).leaders.includes(cell.id));
  assert.throws(() => exportConfiguration(data, row, 'decode'));
});

test('missing metrics are unavailable, never zero or a winning latency', () => {
  const payload = fixture(); payload.reports['cpu-t2'].agg.ttft_ms.median = null;
  const data = normalizeSnapshot(payload);
  assert.equal(data.rows.find(row => row.id === 'cpu-t2').metrics.ttft, null);
  assert.ok(!rankRows(data, 'ttft').leaders.includes('cpu-t2'));
});

test('different workloads are excluded rather than compared as a tuning gain', () => {
  const payload = fixture(); const cell = payload.manifest.cells.find(row => row.id === 'cpu-t10');
  const report = payload.reports[cell.id]; report.params.n_ctx = 8192;
  cell.command[cell.command.indexOf('-c') + 1] = '8192';
  const data = normalizeSnapshot(payload); const row = data.rows.find(row => row.id === cell.id);
  assert.equal(row.status, 'completed');
  assert.equal(rankRows(data).eligible(row), false);
  assert.throws(() => exportConfiguration(data, row, 'decode'));
});

test('ties retain every leader', () => {
  const payload = fixture(); payload.reports['cpu-t12'].agg.decode_tps.median = payload.reports['cpu-t10'].agg.decode_tps.median;
  assert.deepEqual(rankRows(normalizeSnapshot(payload)).leaders.sort(), ['cpu-t10', 'cpu-t12']);
});

test('empty trials are not evidence', () => {
  const payload = fixture();
  for (const report of Object.values(payload.reports)) { report.params.repetitions = 0; report.runs = []; }
  assert.deepEqual(rankRows(normalizeSnapshot(payload)).leaders, []);
});

test('missing model or runtime hashes fails closed', () => {
  for (const key of ['model_sha256', 'runtime_sha256']) {
    const payload = fixture(); delete payload.manifest[key];
    assert.throws(() => normalizeSnapshot(payload), /provenance/);
  }
});

test('contradictory command and report parameters are excluded', () => {
  const payload = fixture(); payload.reports['cpu-t10'].params.n_threads = 2;
  const data = normalizeSnapshot(payload); const row = data.rows.find(row => row.id === 'cpu-t10');
  assert.equal(row.status, 'incomplete');
  assert.match(row.reason, /does not match/);
  assert.equal(rankRows(data).eligible(row), false);
});

test('export retains evidence and explicitly disclaims application, confirmation, and quality', () => {
  const data = normalizeSnapshot(fixture()); const row = data.rows.find(row => row.id === 'cpu-t10');
  const exported = exportConfiguration(data, row, 'decode');
  assert.equal(exported.params.n_threads, 10);
  assert.equal(exported.model_sha256, data.modelHash);
  assert.equal(exported.runtime_sha256, data.runtimeHash);
  assert.equal(exported.applied_to_device, false);
  assert.equal(exported.quality_validated, false);
  assert.equal(exported.confirmed_speedup, false);
  assert.equal(exported.status, 'provisional');
});

test('unknown response schemas and failed fetches do not fall back to fixtures', async () => {
  assert.throws(() => normalizeSnapshot({ schema_version: 'bench.v1' }), /Unsupported/);
  const provider = createRecordedProvider(async () => ({ ok: false, status: 503 }));
  await assert.rejects(provider.load(), /503/);
});

test('simulated move preserves the draft and independent fixture state', () => {
  const before = initialFiles(); const after = simulateScenario('move');
  assert.equal(after.files.find(file => file.name === 'budget-final.csv').folder, 'Presentation');
  assert.equal(after.files.find(file => file.name === 'budget-draft.csv').folder, 'Workspace');
  assert.ok(before.every(file => file.folder === 'Workspace'));
  assert.equal(after.task_time_s, null); assert.equal(after.model_correctness, null);
  assert.equal(after.mode, 'simulated');
});

test('ambiguous request produces clarification without moving a file', () => {
  const result = simulateScenario('clarify');
  assert.ok(result.clarification); assert.equal(result.action, null);
  assert.deepEqual(result.files, initialFiles());
  assert.throws(() => simulateScenario('arbitrary-shell-command'));
});
