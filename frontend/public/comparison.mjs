import { exportConfiguration } from './data.mjs';

export const PROMPTS = [
  { id: 'quick', label: 'Quick explanation', prompt: 'In two sentences, explain why local AI can work without an internet connection.',
    answer: 'Local AI runs the model on your own device, using model files already stored there. Once the software and model are installed, it can process your request without sending it to an online service.',
    reason: 'A short explanation with no multi-step calculation.' },
  { id: 'reasoning', label: 'Reasoning challenge', prompt: 'A demo starts at 14:00. Setup takes 25 minutes, testing takes 20 minutes, and we need a 10-minute buffer. Testing must follow setup. What is the latest time we can start? Show the schedule.',
    answer: 'Start at 13:05.\n\n13:05–13:30 · Setup (25 minutes)\n13:30–13:50 · Testing (20 minutes)\n13:50–14:00 · Buffer (10 minutes)\n\nThe three stages take 55 minutes, so starting at 13:05 leaves everything ready for 14:00.',
    reason: 'A multi-step question with timing constraints to check.' },
];

export const ROUTING_POLICY = 'public-demo-v1';

export function routingSelections(capabilities) {
  const ids = capabilities?.routing?.selections;
  return Array.isArray(ids) && ids.includes('auto') ? ids : ['auto'];
}

export function routingRoute(capabilities, selection) {
  if (selection === 'auto') return null;
  const row = capabilities?.routing?.routes?.find(item => item.id === selection);
  if (!row) return { id: selection, label: selection, unavailable: true, reason: 'This route is not in the gateway capabilities.' };
  return { ...row, unavailable: row.available !== true };
}

export function createComparisonRequest(snapshot, row, metric, mode, promptId, requestId, { routingSelection = 'auto' } = {}) {
  const scenario = PROMPTS.find(item => item.id === promptId);
  if (!scenario || !['speed', 'routing'].includes(mode) || !requestId) throw new Error('Choose a comparison and prompt first.');
  const baseline = snapshot.rows.find(item => item.id === 'cpu-t0');
  if (!baseline) throw new Error('The recorded default configuration is unavailable.');
  return { schema_version: 'local-turbo.comparison-request.v1', request_id: requestId,
    comparison: mode, prompt_id: promptId, prompt: scenario.prompt, execution: 'sequential',
    baseline: exportConfiguration(snapshot, baseline, metric),
    selected: mode === 'speed' ? exportConfiguration(snapshot, row, metric) : null,
    routing: mode === 'routing' ? { selection: routingSelection, policy: ROUTING_POLICY, allow_uncalibrated: true } : null };
}

function speedConfiguration(config) {
  const device = config.requested_device.toUpperCase();
  const threads = config.requested_device === 'cpu'
    ? (config.params.n_threads ? config.params.n_threads + ' threads' : 'automatic threads')
    : 'selected runtime settings';
  return device + ' · ' + threads;
}

function routeConfiguration(route) {
  const device = String(route?.device || 'route').toUpperCase();
  const threads = Number.isInteger(route?.threads) && route.threads > 0 ? route.threads + ' threads' : 'runtime default threads';
  return device + ' · ' + threads;
}

export function comparisonLanes(request, { route = null } = {}) {
  const scenario = PROMPTS.find(item => item.id === request.prompt_id);
  if (request.comparison !== 'routing') {
    return {
      default: { title: 'Default setup', model: request.baseline.model.replace(/\.gguf$/, ''),
        configuration: 'CPU · automatic threads', reason: 'The recorded default settings.' },
      turbo: { title: 'Local Turbo', model: request.selected.model.replace(/\.gguf$/, ''),
        configuration: speedConfiguration(request.selected), reason: 'Your configuration from the Compare screen.' },
    };
  }
  return {
    default: { title: 'Default setup', model: request.baseline.model.replace(/\.gguf$/, ''),
      configuration: 'Fixed model for every prompt', reason: 'The same model handles both example prompts.' },
    turbo: { title: 'Local Turbo',
      model: route && !route.unavailable ? route.label : 'Task policy · experimental',
      configuration: route && !route.unavailable ? routeConfiguration(route) : 'Route resolved on the device',
      reason: scenario.reason },
  };
}

function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted();
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

// Animation deliberately uses the same pace for both lanes. It is not a race,
// tokenizer, measured throughput or model output. Replace at the provider boundary.
export function createPreviewComparisonProvider({ delay = 65 } = {}) {
  return { mode: 'simulated', async execute(request, { signal, onEvent = () => {} } = {}) {
    const scenario = PROMPTS.find(item => item.id === request.prompt_id);
    if (!scenario || scenario.prompt !== request.prompt) throw new Error('This preview requires one of the example prompts.');
    const lanes = {};
    for (const lane of ['default', 'turbo']) {
      signal?.throwIfAborted(); onEvent({ type: 'start', lane });
      const chunks = scenario.answer.match(/[\s\S]{1,14}/g) || [];
      let answer = '';
      for (const chunk of chunks) {
        await pause(delay, signal); answer += chunk;
        onEvent({ type: 'text', lane, answer });
      }
      lanes[lane] = { status: 'completed', answer, ttft_ms: null, total_time_s: null,
        output_tokens: null, quality: 'not_evaluated', configuration_applied: false };
      onEvent({ type: 'complete', lane, result: lanes[lane] });
    }
    return { schema_version: 'local-turbo.comparison-result.v1', request_id: request.request_id,
      mode: 'simulated', comparison: request.comparison, execution: 'sequential', lanes,
      routing: request.routing, speedup: null, winner: null };
  } };
}
