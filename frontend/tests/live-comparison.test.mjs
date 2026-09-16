import test from 'node:test';
import assert from 'node:assert/strict';
import { createLiveComparisonProvider } from '../public/live-comparison.mjs';
import { createComparisonRequest, comparisonLanes, routingSelections, routingRoute, ROUTING_POLICY } from '../public/comparison.mjs';
import { normalizeSnapshot } from '../public/data.mjs';
import { readFileSync } from 'node:fs';

function snapshot() {
  const root = new URL('../../benchmarks/results/screen-01/', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('sweep.json', root)));
  const reports = Object.fromEntries(manifest.cells.map(cell => [cell.id, JSON.parse(readFileSync(new URL(cell.id + '.json', root)))]));
  return normalizeSnapshot({ schema_version: 'local-turbo.recorded.v1', mode: 'recorded', manifest, reports });
}

const H = id => id.repeat(32).slice(0, 64);
const provenance = (device, backend) => ({ backend_id: backend, requested_device: device, resolved_device: device.toUpperCase(), dispatch_verified: false });
function ackSpeed(cfg) {
  return { cell_id: cfg.cell_id, model: cfg.model, model_sha256: cfg.model_sha256, runtime_sha256: cfg.runtime_sha256,
    plugin: cfg.plugin, device: cfg.requested_device, backend_id: { cpu: 'llama_cpp_cpu', gpu: 'llama_cpp_gpu', npu: 'llama_cpp_htp' }[cfg.requested_device],
    threads: cfg.params.n_threads, context: cfg.params.n_ctx, sdk_sha256: H('ab'), quantization: 'Q4_0',
    native_provenance: provenance(cfg.requested_device, { cpu: 'llama_cpp_cpu', gpu: 'llama_cpp_gpu', npu: 'llama_cpp_htp' }[cfg.requested_device]) };
}
function laneDone(cfg, text = 'Actual answer') {
  return { status: 'completed', answer: text, configuration_applied: true, effective_configuration: ackSpeed(cfg),
    ttft_ms: 20, total_time_s: 2, inference_time_s: 1.5, output_tokens: 5, native_decode_tps: 50, native_prefill_tps: 900, quality: 'not_evaluated' };
}
function routeEventAck(route, modelSha) {
  return { route_id: route.id, cell_id: route.id, model: route.model, model_id: route.model_id, model_sha256: modelSha, runtime_sha256: H('cd'),
    sdk_sha256: H('ab'), plugin: route.plugin, device: route.device, backend_id: route.backend_id,
    threads: route.threads, context: route.context, quantization: route.quantization,
    native_provenance: provenance(route.device, route.backend_id) };
}
const ROUTE = { id: 'qwen06-qairt', label: 'Qwen3 0.6B · Qualcomm QAIRT / NPU', model_id: 'qwen06-qairt', model: 'qwen06-qairt.bundle',
  plugin: 'qairt', device: 'npu', backend_id: 'qairt_npu', threads: 0, context: 4096, quantization: null, available: true };
const capabilities = () => ({ available: true, supported_cell_ids: ['cpu-t0', 'gpu', 'npu'],
  routing: { available: true, policy: 'public-demo-v1', routes: [ROUTE, { ...ROUTE, id: 'qwen06-gpu', device: 'gpu', backend_id: 'llama_cpp_gpu', plugin: 'llama_cpp', quantization: 'Q4_0' }], selections: ['auto', 'qwen06-qairt', 'qwen06-gpu'] } });
const routingRequest = (selection = 'auto') => {
  const request = createComparisonRequest(snapshot(), null, 'decode', 'routing', 'quick', 'req-1', { routingSelection: selection });
  return structuredClone(request);
};
const speedRequest = cell => structuredClone(createComparisonRequest(snapshot(), snapshot().rows.find(row => row.id === cell), 'decode', 'speed', 'quick', 'req-1'));

function memory() { const m = new Map(); return { getItem: k => m.get(k), setItem: (k, v) => m.set(k, v), removeItem: k => m.delete(k) }; }
const reply = value => ({ ok: true, json: async () => value });

function routingScenario({ selection = 'auto', laneAck, routeAck = routeEventAck(ROUTE, H('ef')), finalRouting, events, state = 'completed', laneStatus } = {}) {
  const request = routingRequest(selection);
  const route = { request_id: 'req-1', type: 'route', lane: 'turbo', routing: { selection, policy: ROUTING_POLICY, selected_route_id: ROUTE.id,
    reason: 'Short explanation: use the small model, preferring the registered Qualcomm QAIRT bundle.', quality: 'not_calibrated',
    candidates: [], effective_configuration: structuredClone(routeAck) } };
  const turbo = { status: laneStatus || 'completed', answer: 'Turbo answer', configuration_applied: true,
    effective_configuration: laneAck || structuredClone(routeAck), ttft_ms: 30, total_time_s: 3, output_tokens: 6, native_decode_tps: 40, quality: 'not_evaluated' };
  const result = { schema_version: 'local-turbo.comparison-result.v1', request_id: 'req-1', mode: 'live', comparison: 'routing',
    execution: 'sequential', lanes: { default: laneDone(request.baseline), turbo }, winner: null, speedup: null,
    routing: finalRouting === undefined ? structuredClone({ ...route.routing, effective_configuration: { ...structuredClone(routeAck), native_provenance: provenance('npu', 'qairt_npu') } }) : finalRouting };
  const snapshotResponse = { request_id: 'req-1', state, events: events || [route,
    { request_id: 'req-1', type: 'start', lane: 'default', effective_configuration: ackSpeed(request.baseline) },
    { request_id: 'req-1', type: 'complete', lane: 'default', result: laneDone(request.baseline) },
    { request_id: 'req-1', type: 'start', lane: 'turbo', effective_configuration: structuredClone(routeAck) },
    { request_id: 'req-1', type: 'complete', lane: 'turbo', result: turbo }], result, error: null };
  return { request, snapshotResponse };
}

function provider(scenarioResponse, { calls = [], storage = memory() } = {}) {
  return createLiveComparisonProvider({ storage, interval: 0, fetcher: async (url, options) => {
    calls.push({ url, method: options?.method });
    if (String(url).endsWith('/capabilities')) return reply(capabilities());
    if (String(url).endsWith('/cancel')) return reply({});
    if (options?.method) return reply({ request_id: 'req-1', state: 'running', events: [], result: null });
    return reply(scenarioResponse);
  } });
}

test('speed gpu passes exact ack validation including native provenance', async () => {
  const request = speedRequest('gpu');
  const done = laneDone(request.selected);
  const response = { request_id: 'req-1', state: 'completed', events: [
    { request_id: 'req-1', type: 'start', lane: 'default', effective_configuration: ackSpeed(request.baseline) },
    { request_id: 'req-1', type: 'complete', lane: 'default', result: laneDone(request.baseline) },
    { request_id: 'req-1', type: 'start', lane: 'turbo', effective_configuration: ackSpeed(request.selected) },
    { request_id: 'req-1', type: 'complete', lane: 'turbo', result: done }],
    result: { schema_version: 'local-turbo.comparison-result.v1', request_id: 'req-1', mode: 'live', comparison: 'speed',
      execution: 'sequential', lanes: { default: laneDone(request.baseline), turbo: done }, winner: null, speedup: null, routing: null } };
  const calls = [];
  const p = provider(response, { calls });
  const r = await p.execute(request);
  assert.equal(r.lanes.turbo.answer, 'Actual answer');
  assert.equal(r.lanes.turbo.native_prefill_tps, 900);
  assert.equal(p.pendingRequest(), null);
  assert.deepEqual(calls.filter(call => call.method === 'POST').map(call => call.url), ['/api/live-comparisons']);
});

test('speed gpu rejects a wrong applied configuration and keeps reconciliation state', async () => {
  const request = speedRequest('gpu');
  const response = { request_id: 'req-1', state: 'completed', events: [], result: { schema_version: 'local-turbo.comparison-result.v1',
    request_id: 'req-1', mode: 'live', comparison: 'speed', execution: 'sequential',
    lanes: { default: laneDone(request.baseline), turbo: { ...laneDone(request.selected), effective_configuration: { ...ackSpeed(request.selected), threads: 6 } } },
    winner: null, speedup: null, routing: null } };
  const p = provider(response);
  await assert.rejects(p.execute(request), /acknowledge/);
  assert.equal(p.pendingRequest().request_id, 'req-1');
});

test('speed npu with a mismatched backend id fails validation, no silent fallback', async () => {
  const request = speedRequest('npu');
  const bad = { ...ackSpeed(request.selected), backend_id: 'llama_cpp_cpu' };
  const response = { request_id: 'req-1', state: 'completed', events: [], result: { schema_version: 'local-turbo.comparison-result.v1',
    request_id: 'req-1', mode: 'live', comparison: 'speed', execution: 'sequential',
    lanes: { default: laneDone(request.baseline), turbo: { status: 'completed', answer: 'x', configuration_applied: true, effective_configuration: bad } },
    winner: null, speedup: null, routing: null } };
  await assert.rejects(provider(response).execute(request), /acknowledge/);
});

test('routing auto accepts a route event and lane ack that carry full provenance', async () => {
  const { request, snapshotResponse } = routingScenario();
  const r = await provider(snapshotResponse).execute(request);
  assert.equal(r.routing.selected_route_id, 'qwen06-qairt');
  assert.equal(r.lanes.turbo.effective_configuration.native_provenance.dispatch_verified, false);
  assert.equal(r.lanes.default.effective_configuration.cell_id, 'cpu-t0');
});

test('routing auto rejects a selected route outside the cached advertised capabilities', async () => {
  const { request, snapshotResponse } = routingScenario();
  snapshotResponse.events[0].routing.selected_route_id = 'qwen08-quantum';
  await assert.rejects(provider(snapshotResponse).execute(request), /advertised capabilities/);
});

test('routing manual selection mismatch fails even when the server picks another route', async () => {
  const { request, snapshotResponse } = routingScenario({ selection: 'qwen06-gpu' });
  await assert.rejects(provider(snapshotResponse).execute(request), /different route than requested/);
});

test('routing manual accepted when the device picks exactly the requested route', async () => {
  const { request, snapshotResponse } = routingScenario({ selection: 'qwen06-qairt' });
  snapshotResponse.events[0].routing.selection = 'qwen06-qairt';
  const r = await provider(snapshotResponse).execute(request);
  assert.equal(r.routing.selected_route_id, 'qwen06-qairt');
});

test('route event configuration mismatch with the executed lane is rejected', async () => {
  const { request, snapshotResponse } = routingScenario();
  snapshotResponse.events[0].routing.effective_configuration.backend_id = 'llama_cpp_cpu';
  await assert.rejects(provider(snapshotResponse).execute(request), /acknowledge/);
});

test('missing native provenance fails a completed lane', async () => {
  const { request, snapshotResponse } = routingScenario();
  delete snapshotResponse.events[0].routing.effective_configuration.native_provenance;
  snapshotResponse.result.lanes.turbo.effective_configuration = { ...snapshotResponse.result.lanes.turbo.effective_configuration, native_provenance: undefined };
  await assert.rejects(provider(snapshotResponse).execute(request), /provenance/);
});

test('final routing decision must match the route event', async () => {
  const { request, snapshotResponse } = routingScenario();
  snapshotResponse.result.routing.selected_route_id = 'qwen06-gpu';
  await assert.rejects(provider(snapshotResponse).execute(request), /differs from the route event/);
});

test('missing final route, SDK drift and contradictory native identity are rejected', async () => {
  for (const corrupt of [
    s => { s.result.routing = null; },
    s => { s.result.lanes.turbo.effective_configuration.sdk_sha256 = H('12'); },
    s => { s.result.lanes.turbo.effective_configuration.native_provenance.backend_id = 'llama_cpp_cpu'; },
  ]) {
    const { request, snapshotResponse } = routingScenario(); corrupt(snapshotResponse);
    await assert.rejects(provider(snapshotResponse).execute(request), /acknowledge|provenance|differs/);
  }
});

test('routing lane failure preserves the default lane evidence and surfaces the error', async () => {
  const { request, snapshotResponse } = routingScenario({ laneStatus: 'failed' });
  snapshotResponse.state = 'failed';
  snapshotResponse.error = 'Native load failed';
  snapshotResponse.result.lanes.turbo = { status: 'failed', answer: '' };
  const r = await provider(snapshotResponse).execute(request);
  assert.equal(r.status, 'failed');
  assert.equal(r.lanes.default.answer, 'Actual answer');
});

test('unavailable route selection is blocked before any device call', async () => {
  const request = routingRequest('qwen06-htp');
  let deviceCalls = 0;
  const p = createLiveComparisonProvider({ storage: memory(), fetcher: async url => {
    if (String(url).endsWith('/capabilities')) return reply(capabilities());
    deviceCalls++; return reply({});
  } });
  await assert.rejects(p.execute(request), /advertised route/);
  assert.equal(deviceCalls, 0);
});

test('routing request carries the policy object and manual options are labelled', () => {
  const request = routingRequest();
  assert.deepEqual(request.routing, { selection: 'auto', policy: ROUTING_POLICY, allow_uncalibrated: true });
  assert.equal(request.selected, null);
  assert.equal(routingSelections(capabilities()).includes('qwen06-qairt'), true);
  assert.equal(routingRoute(capabilities(), 'qwen06-qairt').label.includes('QAIRT'), true);
  const lanes = comparisonLanes(request, { route: routingRoute(capabilities(), 'qwen06-qairt') });
  assert.match(lanes.turbo.model, /QAIRT/);
  const autoLanes = comparisonLanes(request, { route: null });
  assert.match(autoLanes.turbo.model, /Task policy/);
});

test('speed request unchanged and cancel/reconcile flow intact', async () => {
  const request = speedRequest('gpu');
  assert.equal(request.selected.requested_device, 'gpu');
  assert.equal(request.routing, null);
  let cancelled = false, polls = 0;
  const controller = new AbortController();
  const response = { request_id: 'req-1', state: 'cancelled', events: [],
    result: { schema_version: 'local-turbo.comparison-result.v1', request_id: 'req-1', mode: 'live', comparison: 'speed',
      execution: 'sequential', lanes: {}, winner: null, speedup: null, routing: null } };
  const p = createLiveComparisonProvider({ storage: memory(), interval: 0, fetcher: async (url, options) => {
    if (String(url).endsWith('/cancel')) { cancelled = true; return reply({}); }
    if (options?.method) { controller.abort(); return reply({}); }
    polls++;
    return reply(polls === 1 ? { request_id: 'req-1', state: 'running', events: [], result: null } : response);
  } });
  const r = await p.execute(request, { signal: controller.signal });
  assert.ok(cancelled);
  assert.equal(r.status, 'cancelled');
  assert.equal(p.pendingRequest(), null);
});
