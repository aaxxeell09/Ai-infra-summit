import { exportConfiguration } from './data.mjs';

export const PROMPTS = [
  { id: 'quick', label: 'Quick explanation', prompt: 'In two sentences, explain why local AI can work without an internet connection.',
    answer: 'Local AI runs the model on your own device, using model files already stored there. Once the software and model are installed, it can process your request without sending it to an online service.',
    route: 'Small model candidate', reason: 'A short explanation with no multi-step calculation.' },
  { id: 'reasoning', label: 'Reasoning challenge', prompt: 'A demo starts at 14:00. Setup takes 25 minutes, testing takes 20 minutes, and we need a 10-minute buffer. Testing must follow setup. What is the latest time we can start? Show the schedule.',
    answer: 'Start at 13:05.\n\n13:05–13:30 · Setup (25 minutes)\n13:30–13:50 · Testing (20 minutes)\n13:50–14:00 · Buffer (10 minutes)\n\nThe three stages take 55 minutes, so starting at 13:05 leaves everything ready for 14:00.',
    route: 'Reasoning model candidate', reason: 'A multi-step question with timing constraints to check.' },
];

export function createComparisonRequest(snapshot, row, metric, mode, promptId, requestId) {
  const scenario = PROMPTS.find(item => item.id === promptId);
  if (!scenario || !['speed', 'routing'].includes(mode) || !requestId) throw new Error('Choose a comparison and prompt first.');
  const baseline = snapshot.rows.find(item => item.id === 'cpu-t0');
  if (!baseline) throw new Error('The recorded default configuration is unavailable.');
  return { schema_version: 'local-turbo.comparison-request.v1', request_id: requestId,
    comparison: mode, prompt_id: promptId, prompt: scenario.prompt, execution: 'sequential',
    baseline: exportConfiguration(snapshot, baseline, metric),
    selected: mode === 'speed' ? exportConfiguration(snapshot, row, metric) : null,
    routing: mode === 'routing' ? { status: 'pending_calibration', objective: 'latency', quality_requirement: null } : null };
}

export function comparisonLanes(request) {
  const scenario = PROMPTS.find(item => item.id === request.prompt_id);
  return {
    default: { title: 'Default setup', model: request.baseline.model.replace(/\.gguf$/, ''),
      configuration: request.comparison === 'speed' ? 'CPU · automatic threads' : 'Fixed model for every prompt',
      reason: request.comparison === 'speed' ? 'The recorded default settings.' : 'The same model handles both example prompts.' },
    turbo: { title: 'Local Turbo', model: request.comparison === 'speed' ? request.selected.model.replace(/\.gguf$/, '') : scenario.route,
      configuration: request.comparison === 'speed' ? `${request.selected.requested_device.toUpperCase()} · ${request.selected.requested_device === 'cpu' ? request.selected.params.n_threads ? request.selected.params.n_threads + ' threads' : 'automatic threads' : 'selected runtime settings'}` : 'Illustrative route · model not selected yet',
      reason: request.comparison === 'speed' ? 'Your configuration from the Compare screen.' : scenario.reason },
  };
}

const measured = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
const percentChange = (before, after) => before > 0 && after !== null ? (after / before - 1) * 100 : null;

// The preview answer is scripted, but the surrounding performance evidence is
// taken directly from the recorded benchmark rows. Energy remains diagnostic:
// it is one full-process screening interval, not a confirmed efficiency claim.
export function comparisonEvidence(snapshot, selected) {
  const baseline = snapshot?.rows?.find(row => row.id === 'cpu-t0');
  if (!baseline || !selected || baseline.status !== 'completed' || selected.status !== 'completed' ||
      baseline.signature !== selected.signature) {
    throw new Error('Comparable recorded evidence is unavailable.');
  }
  const lane = row => ({
    decode_tps: measured(row.metrics?.decode),
    energy_j: measured(row.telemetry?.energy_j),
  });
  const defaultLane = lane(baseline);
  const turboLane = lane(selected);
  return {
    default: defaultLane,
    turbo: turboLane,
    speed_gain_pct: percentChange(defaultLane.decode_tps, turboLane.decode_tps),
    energy_change_pct: percentChange(defaultLane.energy_j, turboLane.energy_j),
    answer_check: 'scripted_match',
    accuracy_pct: null,
    energy_status: defaultLane.energy_j !== null && turboLane.energy_j !== null ? 'diagnostic' : 'unavailable',
    energy_channel: 'SYS',
    energy_scope: 'full process screening interval including initialization and warmup',
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
