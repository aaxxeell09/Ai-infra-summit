const SOURCE = 'drafts/hexagon-invoice.md';
const DESTINATION = 'invoices/2026/hexagon-invoice.md';

const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const hash = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

export function normalizeInvoiceStatus(payload) {
  if (payload?.schema_version !== 'local-turbo.invoice-demo-status.v1' ||
      typeof payload.available !== 'boolean' || typeof payload.running !== 'boolean' ||
      payload.task_id !== 't13' || typeof payload.device !== 'string' || typeof payload.model !== 'string' ||
      (payload.reason !== null && payload.reason !== undefined && typeof payload.reason !== 'string')) {
    throw new Error('The live demo status is incomplete.');
  }
  return payload;
}

export function normalizeInvoiceResult(payload) {
  const move = payload?.file_move;
  const exact = payload?.exact_call;
  const timing = payload?.timing;
  const config = payload?.configuration;
  if (payload?.schema_version !== 'local-turbo.invoice-demo-result.v1' || payload.mode !== 'live' ||
      payload.task_id !== 't13' || typeof payload.run_id !== 'string' || !payload.run_id ||
      typeof payload.model !== 'string' || !payload.model || payload.quality_qualified !== false ||
      !config || typeof config.runtime !== 'string' || !['cpu', 'gpu', 'npu', 'hybrid'].includes(config.device) ||
      (config.threads !== null && !Number.isInteger(config.threads)) ||
      (config.context !== null && !Number.isInteger(config.context)) ||
      !move || typeof move.verified !== 'boolean' || move.source !== SOURCE || move.destination !== DESTINATION ||
      (move.sha256 !== null && !hash(move.sha256)) || (move.reason !== null && typeof move.reason !== 'string') ||
      !exact || ['passed', 'calls_match', 'final_state_match', 'execution_ok'].some(key => typeof exact[key] !== 'boolean') ||
      !timing || (timing.loop_seconds !== null && !finite(timing.loop_seconds)) ||
      (timing.process_seconds !== null && !finite(timing.process_seconds)) ||
      (timing.loop_scope !== null && typeof timing.loop_scope !== 'string') ||
      (timing.process_scope !== null && typeof timing.process_scope !== 'string')) {
    throw new Error('The Latitude returned an incomplete or unverifiable demo result.');
  }
  if (move.verified && (!move.sha256 || !exact.final_state_match || !exact.execution_ok)) {
    throw new Error('The Latitude reported a verified move without matching filesystem evidence.');
  }
  return payload;
}

async function responseJson(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error || `The live demo request failed (${response.status}).`);
  return payload;
}

export function createInvoiceDemoProvider(fetchImpl = fetch) {
  return {
    mode: 'live',
    async status({ signal } = {}) {
      return normalizeInvoiceStatus(await responseJson(await fetchImpl('/api/demo/status', { signal })));
    },
    async execute({ signal } = {}) {
      const response = await fetchImpl('/api/demo/invoice', {
        method: 'POST', headers: { Accept: 'application/json', 'X-Local-Turbo-Action': 'invoice-demo-v1' }, signal,
      });
      return normalizeInvoiceResult(await responseJson(response));
    },
  };
}

export const INVOICE_TASK = {
  id: 't13',
  prompt: 'Find the Hexagon invoice draft and move it into invoices/2026, preserving its filename.',
  source: SOURCE,
  destination: DESTINATION,
};
