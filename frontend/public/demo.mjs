// Deliberately deterministic browser-only fixtures, never claimed as inference.
export const SCENARIOS = [
  { id: 'move', label: 'Move the final file', prompt: 'Move budget-final.csv to Presentation. Keep budget-draft.csv here.',
    action: { tool: 'move_file', source: 'budget-final.csv', destination: 'Presentation/budget-final.csv' } },
  { id: 'clarify', label: 'An ambiguous request', prompt: 'Move the budget to Presentation.',
    clarification: 'Which file: budget-final.csv or budget-draft.csv?' },
];
export const initialFiles = () => [
  { name: 'budget-final.csv', folder: 'Workspace', size: '12 KB', kind: 'csv' },
  { name: 'budget-draft.csv', folder: 'Workspace', size: '10 KB', kind: 'csv' },
  { name: 'meeting-notes.md', folder: 'Workspace', size: '3 KB', kind: 'md' },
];
export function simulateScenario(id) {
  const scenario = SCENARIOS.find(item => item.id === id);
  if (!scenario) throw new Error('Unknown demo scenario');
  const files = initialFiles();
  if (scenario.action) files.find(file => file.name === scenario.action.source).folder = 'Presentation';
  return { mode: 'simulated', files, action: scenario.action ?? null,
    clarification: scenario.clarification ?? null, task_time_s: null, model_correctness: null };
}

// View-facing contract. The live bridge is intentionally injected: no invented
// API endpoints, automatic device configuration, or silent preview fallback.
export function createTaskRequest(snapshot, row, objective, scenarioId, requestId) {
  const scenario = SCENARIOS.find(item => item.id === scenarioId);
  if (!row || !scenario || !requestId) throw new Error('Select a configuration and task first.');
  return {
    schema_version: 'local-turbo.task-request.v1', request_id: requestId,
    scenario_id: scenario.id, prompt: scenario.prompt, fixture_id: 'budget-files.v1',
    configuration: {
      cell_id: row.id, model: snapshot.model, model_sha256: snapshot.modelHash,
      runtime_sha256: snapshot.runtimeHash, plugin: row.plugin,
      requested_device: row.requestedDevice, params: structuredClone(row.params), objective,
    },
  };
}

const sameConfiguration = (actual, expected) => actual &&
  ['cell_id', 'model_sha256', 'runtime_sha256', 'plugin', 'requested_device'].every(key => actual[key] === expected[key]) &&
  Object.keys(expected.params).every(key => actual.params?.[key] === expected.params[key]);
const validInventory = files => Array.isArray(files) && files.every(file =>
  typeof file.name === 'string' && file.name.length > 0 && ['Workspace', 'Presentation'].includes(file.folder) &&
  typeof file.kind === 'string' && typeof file.size === 'string') &&
  new Set(files.map(file => `${file.folder}/${file.name}`)).size === files.length;
const duration = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
const canonicalFiles = files => files.map(file => [file.folder, file.name, file.kind, file.size])
  .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
const sameFiles = (a, b) => JSON.stringify(canonicalFiles(a)) === JSON.stringify(canonicalFiles(b));
const sameFixture = files => JSON.stringify(files.map(file => [file.folder, file.name]).sort()) ===
  JSON.stringify(initialFiles().map(file => [file.folder, file.name]).sort());

export function validateAppliedSession(session, request) {
  if (!session?.session_id || !session.snapshot_id || session.fixture_id !== request.fixture_id ||
      session.configuration_applied !== true || !sameConfiguration(session.effective_configuration, request.configuration) ||
      !validInventory(session.files) || !sameFixture(session.files)) {
    throw new Error('The device did not confirm the selected configuration and demo workspace. No task was started.');
  }
  return session;
}

export function normalizeTaskResult(payload, request, session) {
  if (payload?.schema_version !== 'local-turbo.task-result.v1' || payload.mode !== 'live' ||
      payload.request_id !== request.request_id || payload.session_id !== session.session_id ||
      payload.before_snapshot_id !== session.snapshot_id || !payload.after_snapshot_id ||
      !sameConfiguration(payload.effective_configuration, request.configuration) ||
      !['completed', 'clarification', 'failed'].includes(payload.status) || !validInventory(payload.files) ||
      typeof payload.model_output !== 'string' ||
      typeof payload.message !== 'string' || !payload.message.trim()) {
    throw new Error('The device returned an incomplete or mismatched result. Check the device before retrying.');
  }
  const quality = payload.quality;
  if (!quality || !['passed', 'failed', 'not_evaluated'].includes(quality.status) ||
      (quality.status !== 'not_evaluated' && (!Array.isArray(quality.checks) || !quality.checks.length ||
       !quality.checks.every(check => typeof check.name === 'string' && typeof check.passed === 'boolean') ||
       (quality.status === 'passed') !== quality.checks.every(check => check.passed)))) {
    throw new Error('The device returned a quality verdict without consistent checks.');
  }
  if (payload.status === 'clarification' && (typeof payload.clarification !== 'string' || !payload.clarification.trim() || payload.action || !sameFiles(payload.files, session.files))) {
    throw new Error('The device reported clarification alongside file changes. Inspect the run evidence.');
  }
  if (quality.status === 'passed') {
    const required = ['intent', 'action', 'file_postconditions'];
    if (!required.every(name => quality.checks.some(check => check.name === name && check.passed))) {
      throw new Error('Task success requires intent, action and file postcondition checks.');
    }
    if (request.scenario_id === 'move') {
      const expected = session.files.map(file => ({ ...file, folder: file.name === 'budget-final.csv' ? 'Presentation' : file.folder }));
      if (payload.status !== 'completed' || !sameFiles(payload.files, expected)) {
        throw new Error('The returned workspace does not match the claimed successful task.');
      }
    } else if (request.scenario_id === 'clarify' && payload.status !== 'clarification') {
      throw new Error('The ambiguous task requires clarification without moving files.');
    }
  }
  const scopedTiming = typeof payload.timing_source === 'string' && payload.timing_source.trim() &&
    typeof payload.timing_scope === 'string' && payload.timing_scope.trim();
  return { ...payload, task_time_s: scopedTiming ? duration(payload.task_time_s) : null,
    ttft_ms: scopedTiming ? duration(payload.ttft_ms) : null,
    quality: { status: quality.status, checks: quality.checks ?? [] },
    configuration_applied: true };
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted();
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export function createPreviewTaskProvider({ delay = 1200 } = {}) {
  return { mode: 'simulated', async execute(request, { signal } = {}) {
    await wait(delay, signal);
    const result = simulateScenario(request.scenario_id);
    return { ...result, request_id: request.request_id,
      configuration: request.configuration, configuration_applied: false,
      status: result.clarification ? 'clarification' : 'completed',
      message: result.clarification || 'budget-final.csv moved to Presentation. The draft stayed in Workspace.',
      ttft_ms: null, quality: { status: 'not_evaluated', checks: [] } };
  } };
}

// bridge.prepare must apply/verify the exact configuration and reset a disposable
// fixture. bridge.run owns inference, protected execution, grading and timings.
export function createLiveTaskProvider(bridge) {
  if (typeof bridge?.prepare !== 'function' || typeof bridge?.run !== 'function') throw new Error('A device task bridge is required.');
  return { mode: 'live', async execute(request, { signal, onPrepared = () => {} } = {}) {
    signal?.throwIfAborted();
    const session = validateAppliedSession(await bridge.prepare(request, { signal }), request);
    signal?.throwIfAborted();
    onPrepared(session);
    const result = await bridge.run({ ...request, session_id: session.session_id, snapshot_id: session.snapshot_id }, { signal });
    signal?.throwIfAborted();
    return normalizeTaskResult(result, request, session);
  } };
}
