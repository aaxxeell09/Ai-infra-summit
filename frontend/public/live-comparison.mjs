// Real native answers only. Unknown execution is retained for reconciliation.
export function createLiveComparisonProvider({fetcher = fetch, interval = 200, storage = globalThis.sessionStorage, maxWaitMs = 140000} = {}) {
  const key = 'local-turbo.pending-live-comparison';
  let pending = null;
  try { pending = JSON.parse(storage?.getItem(key) || 'null'); } catch { /* no saved public request */ }
  const save = value => { pending = value; if (value) storage?.setItem(key, JSON.stringify(value)); else storage?.removeItem(key); };
  async function json(path, options = {}) {
    const response = await fetcher(path, { ...options, signal: AbortSignal.timeout(10000), headers: {'Content-Type':'application/json'} });
    const value = await response.json();
    if (!response.ok) { const error = new Error(value.error || `Device request failed (${response.status})`); error.httpStatus = response.status; throw error; }
    return value;
  }
  function checkLane(lane, expected) {
    if (!lane || !['completed','failed','cancelled','running'].includes(lane.status) || typeof lane.answer !== 'string') throw new Error('Invalid native lane result');
    if (lane.status !== 'completed') return;
    const ack = lane.effective_configuration;
    if (!lane.configuration_applied || !ack || ack.cell_id !== expected.cell_id || ack.model_sha256 !== expected.model_sha256 || ack.runtime_sha256 !== expected.runtime_sha256 || ack.device !== expected.requested_device || ack.threads !== expected.params.n_threads || ack.context !== expected.params.n_ctx) throw new Error('Device did not acknowledge the selected configuration');
    for (const name of ['ttft_ms','total_time_s','output_tokens','native_decode_tps']) if (lane[name] !== null && (!Number.isFinite(lane[name]) || lane[name] < 0)) throw new Error('Invalid device measurement');
  }
  return {
    mode: 'live',
    pendingRequest: () => pending,
    capabilities: () => json('/api/live-comparisons/capabilities'),
    async execute(request, {signal, onEvent = () => {}} = {}) {
      if (request.comparison !== 'speed' || request.selected?.requested_device !== 'cpu') throw new Error('Live demo supports the recorded CPU settings. Choose CPU on Compare; routing is not calibrated.');
      if (pending && pending.request_id !== request.request_id) throw new Error('Reconcile the previous device job before starting another.');
      const resume = !!pending;
      signal?.throwIfAborted();
      save(request);
      let cursor = 0, cancelSent = false;
      const started = Date.now();
      try {
        if (!resume) {
          try { await json('/api/live-comparisons', {method:'POST', body:JSON.stringify(request)}); }
          catch (error) { if (error.httpStatus === 400 || error.httpStatus === 403) save(null); throw error; }
        }
        while (Date.now() - started < maxWaitMs) {
          if (signal?.aborted && !cancelSent) {
            await json(`/api/live-comparisons/${request.request_id}/cancel`, {method:'POST',body:'{}'});
            cancelSent = true;
          }
          const status = await json(`/api/live-comparisons/${request.request_id}`);
          if (status.request_id !== request.request_id || !Array.isArray(status.events)) throw new Error('Mismatched device job response');
          if (status.events.length < cursor) throw new Error('Device event history was replaced');
          for (; cursor < status.events.length; cursor++) {
            const event = status.events[cursor];
            if (event.request_id !== request.request_id || !['default','turbo'].includes(event.lane) || !['start','text','complete'].includes(event.type)) throw new Error('Mismatched device event');
            if (event.type === 'complete') checkLane(event.result, request[event.lane === 'default' ? 'baseline' : 'selected']);
            onEvent(event);
          }
          if (status.state !== 'running') {
            if (!['completed','failed','cancelled'].includes(status.state)) throw new Error('Unknown device execution state');
            const result = status.result;
            if (!result || result.request_id !== request.request_id || result.mode !== 'live' || result.schema_version !== 'local-turbo.comparison-result.v1') throw new Error('Missing or mismatched native result');
            for (const [name,lane] of Object.entries(result.lanes)) checkLane(lane, request[name === 'default' ? 'baseline' : 'selected']);
            if (status.state === 'completed' && ['default','turbo'].some(name => result.lanes[name]?.status !== 'completed')) throw new Error('Incomplete pair cannot be marked complete');
            save(null);
            return {...result, status:status.state, error:status.error};
          }
          await new Promise(resolve => setTimeout(resolve, interval));
        }
        await json(`/api/live-comparisons/${request.request_id}/cancel`, {method:'POST',body:'{}'});
        throw new Error('Device deadline reached. Cancellation requested; check job status before retrying.');
      } catch (error) {
        error.reconciliationRequired = !!pending;
        throw error;
      }
    }
  };
}
