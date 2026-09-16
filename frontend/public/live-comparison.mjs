// Real native answers only. Unknown execution is retained for reconciliation.
const ROUTING_POLICY = 'public-demo-v1';
const BACKENDS = { cpu: 'llama_cpp_cpu', gpu: 'llama_cpp_gpu', npu: 'llama_cpp_htp' };
const isHash = value => typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);
const finiteNonNegative = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;

function expectedFor(request, lane) {
  const cfg = lane === 'default' ? request.baseline : request.comparison === 'speed' ? request.selected : null;
  if (!cfg) return null;
  return { cell_id: cfg.cell_id, model: cfg.model, model_sha256: cfg.model_sha256, runtime_sha256: cfg.runtime_sha256,
    plugin: cfg.plugin, device: cfg.requested_device, backend_id: BACKENDS[cfg.requested_device],
    threads: cfg.params.n_threads, context: cfg.params.n_ctx };
}

function matchesExpected(ack, expected) {
  return !!expected && ack.cell_id === expected.cell_id && ack.model === expected.model
    && ack.model_sha256 === expected.model_sha256 && ack.runtime_sha256 === expected.runtime_sha256
    && ack.plugin === expected.plugin && ack.device === expected.device
    && ack.backend_id === expected.backend_id && ack.threads === expected.threads && ack.context === expected.context
    && (!expected.sdk_sha256 || ack.sdk_sha256 === expected.sdk_sha256);
}

// The default lane is always an exact speed acknowledgement; routing checks apply to turbo only.
function checkLane(lane, expected, context = {}) {
  if (!lane || !['completed', 'failed', 'cancelled', 'running'].includes(lane.status) || typeof lane.answer !== 'string') throw new Error('Invalid native lane result');
  if (lane.status !== 'completed') return;
  if (context.routing) {
    const routeEvent = context.routeEvent;
    if (!routeEvent || routeEvent.lane !== 'turbo' || routeEvent.routing?.policy !== ROUTING_POLICY) throw new Error('Routing acknowledgement is missing its route event');
    if (routeEvent.routing.selection !== context.routing.selection) throw new Error('Route event selection differs from the request');
    const selected = routeEvent.routing.selected_route_id;
    if (context.routing.selection === 'auto') {
      if (!context.routes?.some(row => row.id === selected)) throw new Error('Automatic route is not one of the advertised capabilities');
    } else if (selected !== context.routing.selection) throw new Error('Device selected a different route than requested');
    const eventCfg = routeEvent.routing.effective_configuration;
    if (!eventCfg) throw new Error('Route event is missing its effective configuration');
    expected = eventCfg;
    if (lane.effective_configuration?.route_id !== selected) throw new Error('Executed lane does not carry the selected route ID');
  }
  const ack = lane.effective_configuration;
  if (!lane.configuration_applied || !ack || !matchesExpected(ack, expected)) throw new Error('Device did not acknowledge the selected configuration');
  if (context.routing) {
    const eventCfg = context.routeEvent.routing.effective_configuration;
    if (!eventCfg || eventCfg.model_sha256 !== ack.model_sha256 || eventCfg.runtime_sha256 !== ack.runtime_sha256
      || eventCfg.plugin !== ack.plugin || eventCfg.device !== ack.device || eventCfg.backend_id !== ack.backend_id
      || eventCfg.threads !== ack.threads || eventCfg.context !== ack.context) throw new Error('Route event configuration differs from the executed lane');
  }
  const native = ack.native_provenance;
  if (!native || typeof native !== 'object') throw new Error('Native dispatch provenance is missing');
  if (native.backend_id !== ack.backend_id || native.requested_device !== ack.device) throw new Error('Native provenance disagrees with the applied backend');
  if (typeof native.dispatch_verified !== 'boolean') throw new Error('Native dispatch verification status is missing');
  if (context.routing && (!isHash(ack.model_sha256) || !isHash(ack.runtime_sha256) || !isHash(ack.sdk_sha256))) throw new Error('Routed lane is missing full artifact provenance');
  for (const name of ['ttft_ms', 'total_time_s', 'inference_time_s', 'output_tokens', 'native_decode_tps', 'native_prefill_tps']) {
    if (lane[name] !== null && lane[name] !== undefined && !finiteNonNegative(lane[name])) throw new Error('Invalid device measurement');
  }
}

export function createLiveComparisonProvider({ fetcher = fetch, interval = 200, storage = globalThis.sessionStorage, maxWaitMs = 140000 } = {}) {
  const key = 'local-turbo.pending-live-comparison';
  let pending = null;
  let cachedCapabilities = null;
  try { pending = JSON.parse(storage?.getItem(key) || 'null'); } catch { /* no saved public request */ }
  const save = value => { pending = value; if (value) storage?.setItem(key, JSON.stringify(value)); else storage?.removeItem(key); };
  async function json(path, options = {}) {
    const response = await fetcher(path, { ...options, signal: AbortSignal.timeout(10000), headers: { 'Content-Type': 'application/json' } });
    const value = await response.json();
    if (!response.ok) { const error = new Error(value.error || `Device request failed (${response.status})`); error.httpStatus = response.status; throw error; }
    return value;
  }
  return {
    mode: 'live',
    pendingRequest: () => pending,
    // Capabilities are fetched once per provider and reused; the gateway owns availability truth.
    async capabilities() { cachedCapabilities = await json('/api/live-comparisons/capabilities'); return cachedCapabilities; },
    async execute(request, { signal, onEvent = () => {} } = {}) {
      const routing = request.comparison === 'routing'
        ? (request.routing && request.routing.policy === ROUTING_POLICY && (request.routing.selection === 'auto' || typeof request.routing.selection === 'string')
          ? request.routing : null)
        : null;
      if (request.comparison === 'routing' && !routing) throw new Error('Routing requires the experimental public-demo-v1 policy and a selection');
      if (request.comparison === 'speed' && !(request.selected && ['cpu', 'gpu', 'npu'].includes(request.selected.requested_device))) {
        throw new Error('Choose a supported CPU, GPU or NPU configuration on Compare for the live demo.');
      }
      let routes = null;
      if (routing) {
        const caps = cachedCapabilities || await this.capabilities().catch(error => { throw new Error('Routing capabilities are unavailable: ' + error.message); });
        routes = Array.isArray(caps?.routing?.routes) ? caps.routing.routes : null;
        if (!routes) throw new Error('Routing capabilities do not advertise routes');
        if (routing.selection !== 'auto' && !routes.some(row => row.id === routing.selection)) throw new Error('Choose an advertised route or the automatic task policy.');
      }
      if (pending && pending.request_id !== request.request_id) throw new Error('Reconcile the previous device job before starting another.');
      const resume = !!pending;
      signal?.throwIfAborted();
      save(request);
      let cursor = 0, cancelSent = false, routeEvent = null;
      const started = Date.now();
      try {
        if (!resume) {
          try { await json('/api/live-comparisons', { method: 'POST', body: JSON.stringify(request) }); }
          catch (error) { if (error.httpStatus === 400 || error.httpStatus === 403) save(null); throw error; }
        }
        while (Date.now() - started < maxWaitMs) {
          if (signal?.aborted && !cancelSent) {
            await json(`/api/live-comparisons/${request.request_id}/cancel`, { method: 'POST', body: '{}' });
            cancelSent = true;
          }
          const status = await json(`/api/live-comparisons/${request.request_id}`);
          if (status.request_id !== request.request_id || !Array.isArray(status.events)) throw new Error('Mismatched device job response');
          if (status.events.length < cursor) throw new Error('Device event history was replaced');
          for (; cursor < status.events.length; cursor++) {
            const event = status.events[cursor];
            if (event.request_id !== request.request_id || !['default', 'turbo'].includes(event.lane) || !['start', 'text', 'complete', 'route'].includes(event.type)) throw new Error('Mismatched device event');
            if (event.type === 'route') {
              if (event.lane !== 'turbo' || routeEvent) throw new Error('Unexpected duplicate or misplaced route event');
              routeEvent = event; onEvent(event); continue;
            }
            if (event.type === 'start') {
              const expected = expectedFor(request, event.lane);
              if (expected && (!event.effective_configuration || !matchesExpected(event.effective_configuration, expected))) throw new Error('Device start configuration differs from the requested selection');
            }
            if (event.type === 'complete') checkLane(event.result, expectedFor(request, event.lane), event.lane === 'turbo' ? { routing, routeEvent, routes } : {});
            onEvent(event);
          }
          if (status.state !== 'running') {
            if (!['completed', 'failed', 'cancelled'].includes(status.state)) throw new Error('Unknown device execution state');
            const result = status.result;
            if (!result || result.request_id !== request.request_id || result.mode !== 'live' || result.schema_version !== 'local-turbo.comparison-result.v1') throw new Error('Missing or mismatched native result');
            for (const [name, lane] of Object.entries(result.lanes)) {
              checkLane(lane, expectedFor(request, name), name === 'turbo' ? { routing, routeEvent, routes } : {});
            }
            if (routing && routeEvent && status.state === 'completed') {
              if (!result.routing || result.routing.policy !== ROUTING_POLICY || result.routing.selection !== routing.selection
                || result.routing.selected_route_id !== routeEvent.routing.selected_route_id
                || !matchesExpected(result.routing.effective_configuration || {}, routeEvent.routing.effective_configuration)) throw new Error('Final routing decision differs from the route event');
            }
            if (status.state === 'completed' && ['default', 'turbo'].some(name => result.lanes[name]?.status !== 'completed')) throw new Error('Incomplete pair cannot be marked complete');
            save(null);
            return { ...result, status: status.state, error: status.error };
          }
          await new Promise(resolve => setTimeout(resolve, interval));
        }
        await json(`/api/live-comparisons/${request.request_id}/cancel`, { method: 'POST', body: '{}' });
        throw new Error('Device deadline reached. Cancellation requested; check job status before retrying.');
      } catch (error) {
        error.reconciliationRequired = !!pending;
        throw error;
      }
    },
  };
}
