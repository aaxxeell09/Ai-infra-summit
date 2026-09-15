import test from 'node:test';
import assert from 'node:assert/strict';
import { createTaskRequest, createPreviewTaskProvider, createLiveTaskProvider, initialFiles, simulateScenario } from '../public/demo.mjs';

function fixture(scenario = 'move') {
  const request = createTaskRequest({ model: 'test-model', modelHash: 'a'.repeat(64), runtimeHash: 'b'.repeat(64) }, {
    id: 'cpu-t10', plugin: 'llamacpp', requestedDevice: 'cpu', params: { n_threads: 10, n_ctx: 4096, n_gen: 128 },
  }, 'decode_tps', scenario, 'request-1');
  const session = { session_id: 'session-1', snapshot_id: 'before-1', fixture_id: request.fixture_id,
    configuration_applied: true, effective_configuration: structuredClone(request.configuration), files: initialFiles() };
  const example = simulateScenario(scenario);
  const result = { schema_version: 'local-turbo.task-result.v1', mode: 'live', request_id: request.request_id,
    session_id: session.session_id, before_snapshot_id: session.snapshot_id, after_snapshot_id: 'after-1',
    effective_configuration: structuredClone(request.configuration), files: example.files,
    status: example.clarification ? 'clarification' : 'completed', message: example.clarification || 'File moved.',
    action: example.action, clarification: example.clarification, model_output: 'Test model output',
    task_time_s: 1.2, ttft_ms: 60, timing_source: 'backend monotonic clock', timing_scope: 'Full task after model preparation; TTFT from inference request to first token.',
    quality: { status: 'passed', checks: ['intent', 'action', 'file_postconditions'].map(name => ({ name, passed: true })) } };
  return { request, session, result };
}

test('preview carries the exact selection without claiming execution or measured speed', async () => {
  const { request } = fixture();
  const result = await createPreviewTaskProvider({ delay: 0 }).execute(request);
  assert.equal(result.configuration.params.n_threads, 10);
  assert.equal(result.request_id, request.request_id);
  assert.equal(result.configuration_applied, false);
  assert.equal(result.mode, 'simulated');
  assert.equal(result.task_time_s, null);
  assert.equal(result.quality.status, 'not_evaluated');
});

test('live task requires application acknowledgement before calling inference', async () => {
  for (const change of [s => s.configuration_applied = false, s => s.effective_configuration.params.n_threads = 2,
    s => s.effective_configuration.model_sha256 = 'different', s => s.snapshot_id = null]) {
    const { request, session } = fixture(); change(session); let ran = false;
    const provider = createLiveTaskProvider({ prepare: async () => session, run: async () => { ran = true; } });
    await assert.rejects(provider.execute(request), /did not confirm/);
    assert.equal(ran, false);
  }
});

test('live provider preserves authoritative results and announces application first', async () => {
  const { request, session, result } = fixture(); const events = [];
  const provider = createLiveTaskProvider({ prepare: async () => { events.push('prepare'); return session; }, run: async input => {
    events.push('run'); assert.equal(input.snapshot_id, session.snapshot_id); return result;
  } });
  const actual = await provider.execute(request, { onPrepared: () => events.push('applied') });
  assert.deepEqual(events, ['prepare', 'applied', 'run']);
  assert.deepEqual(actual.files, result.files); assert.equal(actual.task_time_s, 1.2);
  assert.equal(actual.quality.status, 'passed'); assert.equal(actual.configuration_applied, true);
});

test('stale responses and wrong configurations cannot become a successful task', async () => {
  for (const change of [r => r.request_id = 'previous-run', r => r.before_snapshot_id = 'wrong-workspace',
    r => r.effective_configuration.params.n_ctx = 2048, r => r.mode = 'simulated']) {
    const { request, session, result } = fixture(); change(result);
    await assert.rejects(createLiveTaskProvider({ prepare: async () => session, run: async () => result }).execute(request), /mismatched/);
  }
});

test('success requires semantic checks and matching file postconditions', async () => {
  for (const change of [r => r.quality.checks = [], r => r.quality.checks[0].passed = false,
    r => r.quality.checks[0].name = 'valid_json', r => r.files = initialFiles()]) {
    const { request, session, result } = fixture(); change(result);
    await assert.rejects(createLiveTaskProvider({ prepare: async () => session, run: async () => result }).execute(request));
  }
});

test('clarification leaves files untouched; contradictory changes are rejected', async () => {
  const { request, session, result } = fixture('clarify');
  const provider = createLiveTaskProvider({ prepare: async () => session, run: async () => result });
  assert.equal((await provider.execute(request)).status, 'clarification');
  result.files = simulateScenario('move').files;
  await assert.rejects(provider.execute(request), /clarification alongside file changes/);
});

test('unscoped timings are unavailable and failed task checks stay failed', async () => {
  const { request, session, result } = fixture(); delete result.timing_source;
  result.quality = { status: 'failed', checks: [{ name: 'intent', passed: false }] };
  const actual = await createLiveTaskProvider({ prepare: async () => session, run: async () => result }).execute(request);
  assert.equal(actual.task_time_s, null); assert.equal(actual.ttft_ms, null);
  assert.equal(actual.quality.status, 'failed');
});

test('device failure never falls back to simulation and abort stops the next stage', async () => {
  const { request, session } = fixture(); let ran = false;
  await assert.rejects(createLiveTaskProvider({ prepare: async () => { throw new Error('Device offline'); }, run: async () => {} }).execute(request), /Device offline/);
  const controller = new AbortController();
  const provider = createLiveTaskProvider({ prepare: async () => { controller.abort(); return session; }, run: async () => { ran = true; } });
  await assert.rejects(provider.execute(request, { signal: controller.signal }), { name: 'AbortError' });
  assert.equal(ran, false);
});

test('real file sizes and reordered object keys do not invalidate correct postconditions', async () => {
  const { request, session, result } = fixture();
  session.files[0].size = '37 B';
  result.files = session.files.map(file => ({ size: file.size, kind: file.kind, name: file.name,
    folder: file.name === 'budget-final.csv' ? 'Presentation' : file.folder }));
  const actual = await createLiveTaskProvider({ prepare: async () => session, run: async () => result }).execute(request);
  assert.equal(actual.quality.status, 'passed');
  assert.equal(actual.files.find(file => file.name === 'budget-final.csv').size, '37 B');
});

test('ambiguous scenario cannot claim success after a move or an empty question', async () => {
  for (const change of [r => { r.status = 'completed'; r.files = simulateScenario('move').files; }, r => r.clarification = '   ']) {
    const { request, session, result } = fixture('clarify'); change(result);
    await assert.rejects(createLiveTaskProvider({ prepare: async () => session, run: async () => result }).execute(request), /clarif/);
  }
});

test('empty or wrong prepared fixture cannot start inference', async () => {
  const { request, session } = fixture(); session.files = []; let ran = false;
  await assert.rejects(createLiveTaskProvider({ prepare: async () => session, run: async () => { ran = true; } }).execute(request), /did not confirm/);
  assert.equal(ran, false);
});
