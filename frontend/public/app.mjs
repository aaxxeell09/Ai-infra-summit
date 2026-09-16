import { createRecordedProvider, METRICS, rankRows, exportConfiguration } from './data.mjs';
import { createLatestResultsProvider } from './latest.mjs';
import { createLiveComparisonProvider } from './live-comparison.mjs';
import { PROMPTS, createComparisonRequest, comparisonLanes, createPreviewComparisonProvider, routingSelections, routingRoute } from './comparison.mjs';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const number = (value, digits = 2) => value === null || value === undefined ? 'Unavailable' : value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const arrow = '<span aria-hidden="true">↗</span>';
const provider = createRecordedProvider();
const latestProvider = createLatestResultsProvider();
let taskProvider = createPreviewComparisonProvider();
let liveCapabilities = null;
let liveSetupError = null;
const state = { snapshot: null, latest: null, latestError: null, page: 'device', metric: 'decode', metricHelp: false, selected: null, scenario: 'quick', comparison: 'speed', routingSelection: 'auto', turboDispatched: undefined, demo: 'idle', lanes: {}, result: null, error: null, reveal: false };
let demoGeneration = 0;
let taskAbort;
let toastTimer;
let clockTick;
let laneClocks = {};

// Browser animation clocks stay separate from authoritative device measurements.
function clockText(key) {
  const clock = laneClocks[key];
  if (!clock) return '—';
  return `${((clock.elapsed ?? (performance.now() - clock.started)) / 1000).toFixed(1)} s`;
}
function updateClocks() {
  for (const key of ['default', 'turbo']) {
    const output = document.querySelector(`[data-clock="${key}"]`);
    if (output) output.textContent = clockText(key);
  }
}

function notify(message) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').classList.add('visible');
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 3500);
}

function currentRow() {
  const ranked = rankRows(state.snapshot, state.metric);
  return state.snapshot.rows.find(row => row.id === state.selected) ?? ranked.rows.find(ranked.eligible);
}

function latestEvidence() {
  if (!state.latest) return state.latestError ? `<p class="latest-unavailable">Latest model study unavailable. The configuration comparison above is unchanged.</p>` : '';
  const q = state.latest.qairt;
  const stateBlock = (name, result, tuned = false) => `<article class="behavior-state ${tuned ? 'tuned' : ''}"><span class="behavior-name">${name}</span><div class="behavior-metrics"><div><span>Task success</span><strong>${number(result.accuracy_pct, 0)}<small>%</small></strong></div><div><span>Mean inference</span><strong>${number(result.average_inference_ms, 0)}<small>ms</small></strong></div></div></article>`;
  return `<section class="behavior-study" aria-labelledby="latest-evidence-title">
    <header class="behavior-head"><div><span class="eyebrow">NPU OUTPUT CONTROL</span><h2 id="latest-evidence-title">One complete action. Then stop.</h2></div><p>No trailing text or extra tool calls.</p></header>
    <div class="behavior-flow">
      ${stateBlock('Without stop rule', q.control)}
      <div class="behavior-transition"><span class="transition-line"></span><div><small>LOCALTURBO RULE</small><strong>Stop after first valid action</strong></div><span class="transition-arrow" aria-hidden="true">→</span></div>
      ${stateBlock('With stop rule', q.optimized, true)}
    </div>
    <footer class="behavior-foot"><span>Qwen3 0.6B · QAIRT · NPU</span><span><i></i>Experimental · quality gate not passed</span></footer>
  </section>`;
}

function deviceScreen() {
  const s = state.snapshot;
  const cpus = s.rows.filter(row => row.device === 'cpu').length;
  return `<section class="screen device-screen">
    <div class="device-copy"><div class="eyebrow"><span class="tiny-line"></span> LOCAL INFERENCE TUNING</div>
      <h1><span>Tune your model.</span> <em>For this machine.</em></h1>
      <p class="lead">Compare the measurements. Choose how it runs.</p>
      <button class="button primary large" data-action="explore">Compare configurations ${arrow}</button>
    </div>
    <div class="machine-stage">
      <div class="stage-label"><span class="mono">TARGET MACHINE</span><span class="chip-status">Windows ARM64</span></div>
      <div class="chip-scene" aria-hidden="true">
        <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="orbit orbit-three"></div>
        <div class="trace trace-a"></div><div class="trace trace-b"></div><div class="trace trace-c"></div><div class="trace trace-d"></div>
        <div class="chip"><div class="chip-edge"><span class="chip-small">SNAPDRAGON</span><span class="chip-x">X<span>ELITE</span></span><span class="chip-small chip-bottom">${esc(s.device.chipset)}</span></div></div>
        <span class="compute-node node-cpu">CPU<span>${cpus} settings</span></span><span class="compute-node node-gpu">GPU<span>Adreno X1-85</span></span><span class="compute-node node-npu">NPU<span>Hexagon</span></span>
      </div>
      <div class="machine-identity"><div><h2>${esc(s.device.name)}</h2><p>${esc(s.device.processor)} · ${esc(s.device.chipset)}</p></div><div class="memory-tag"><strong>${s.device.ram_gb}</strong><span>GB RAM</span></div></div>
      <div class="model-line"><span class="model-glyph" aria-hidden="true">◇</span><div><span class="quiet">MODEL UNDER TEST</span><strong>${esc(s.model.replace(/\.gguf$/, ''))}</strong></div><span class="runtime">${esc(s.runtime)}</span></div>
    </div>
  </section>`;
}

function calibrationScreen() {
  const s = state.snapshot;
  const { rows, leaders, eligible, baseline } = rankRows(s, state.metric);
  const metric = METRICS[state.metric];
  const chosen = currentRow();
  const max = Math.max(1, ...rows.filter(eligible).map(row => row.metrics[state.metric]));
  const chartRows = rows.map((row, index) => {
    const valid = eligible(row); const winner = leaders.includes(row.id); const selected = chosen?.id === row.id;
    const value = row.metrics[state.metric];
    const annotation = winner ? (leaders.length > 1 ? 'Tied here' : 'Best here') : row.id === 'cpu-t0' ? 'Default' : '';
    return `<button class="result-row ${winner ? 'winner' : ''} ${selected ? 'selected' : ''} ${!valid ? 'invalid' : ''}" data-select="${esc(row.id)}" aria-pressed="${selected}" aria-label="${esc(row.label)}, ${valid ? `${number(value)} ${metric.unit}` : esc(row.reason || 'Not comparable')}" style="--delay:${Math.min(index * 55, 500)}ms">
      <span class="row-label">${esc(row.label)}${annotation ? `<span class="row-annotation">${annotation}</span>` : ''}</span>
      <span class="bar-track"><span class="bar" style="--bar:${valid ? value / max * 100 : 0}%"></span></span>
      <span class="row-value">${valid ? number(value) : '—'}</span><span class="row-chevron" aria-hidden="true">↗</span>
    </button>`;
  }).join('');
  const isEligible = chosen && eligible(chosen);
  const isLeader = chosen && leaders.includes(chosen.id);
  const secondaryMetric = state.metric === 'ttft' ? ['Answer writing speed', chosen?.metrics.decode, 'tok/s'] : ['Wait before answer', chosen?.metrics.ttft, 'ms'];
  return `<section class="screen calibration-screen ${state.reveal ? 'reveal' : ''}">
    <div class="section-heading"><div><div class="eyebrow">SAME MODEL. SAME WORKLOAD.</div><h1>Choose how it runs.</h1></div><span class="record-label">${esc(s.model.replace(/\.gguf$/, ''))}</span></div>
    <div class="calibration-layout"><div class="chart-panel">
      <div class="chart-toolbar"><div class="metric-tabs" role="group" aria-label="Measurement to compare" aria-describedby="metric-explanation">${['prefill', 'ttft', 'decode'].map(key => `<button data-metric="${key}" aria-pressed="${state.metric === key}" class="${state.metric === key ? 'active' : ''}">${METRICS[key].tab}</button>`).join('')}</div><span class="chart-unit">${metric.unit} · ${metric.hint}</span></div>
      <div class="metric-explanation" id="metric-explanation"><p>${metric.description}</p><button class="metric-help-button" data-action="metric-help" aria-label="About ${metric.unit === 'tok/s' ? 'tokens per second' : 'milliseconds'}" aria-expanded="${state.metricHelp}" aria-controls="metric-unit-help"><span aria-hidden="true">ⓘ</span></button><span id="metric-unit-help" ${state.metricHelp ? '' : 'hidden'}>${metric.units}</span></div>
      <div class="chart" aria-label="${esc(metric.label)} comparison">${chartRows}</div>
      <div class="chart-foot"><span>${baseline?.params ? `Median of ${baseline.params.repetitions} repetitions · ${baseline.params.n_prompt} input / ${baseline.params.n_gen} output tokens` : 'No comparable workload available'}</span></div>
    </div><aside class="selection-panel">
      <div class="selection-top"><span class="eyebrow">SELECTED CONFIGURATION</span><span class="selection-status">${isLeader ? 'Current leader' : 'Measured'}</span></div>
      <h2>${chosen ? esc(chosen.label.replace(' · ', '<|>').split('<|>')[0]) : 'No result'}<span>${chosen?.device === 'cpu' ? esc(chosen.threads === 0 ? 'Automatic threads' : `${chosen.threads} threads`) : 'Recorded configuration'}</span></h2>
      <p class="selection-caption">${isEligible ? (isLeader ? `${leaders.length > 1 ? 'Tied for fastest' : 'Fastest'} ${{ decode: 'answer generation', prefill: 'prompt processing', ttft: 'first response' }[state.metric]} in this run.` : 'Selected for the answer comparison. Other settings may be faster.') : esc(chosen?.reason || 'No comparable result available.')}</p>
      <p class="ranking-scope">No overall winner yet.</p>
      <div class="selection-metrics"><div><span>${secondaryMetric[0]}</span><strong>${number(secondaryMetric[1])}<small>${secondaryMetric[1] == null ? '' : secondaryMetric[2]}</small></strong></div><div><span>Peak process memory</span><strong>${chosen?.memory_mb == null ? 'Unavailable' : number(chosen.memory_mb / 1024, 2)}<small>${chosen?.memory_mb == null ? '' : 'GiB'}</small></strong></div></div>
      <div class="evidence-note"><span class="note-dot"></span><p>Preliminary measurements.<br>Repeat comparison and task checks pending.${chosen && ['npu', 'hybrid'].includes(chosen.device) ? '<br>NPU execution is not yet verified.' : ''}</p></div>
      <button class="button primary" data-action="try" ${!isEligible ? 'disabled' : ''}>Continue to demo ${arrow}</button>
      <button class="button ghost" data-action="export" ${!isEligible ? 'disabled' : ''}>Export configuration <span aria-hidden="true">↓</span></button>
    </aside></div>${latestEvidence()}
  </section>`;
}

function demoScreen() {
  const busy = ['running', 'cancelling'].includes(state.demo);
  const live = taskProvider.mode === 'live';
  const scenario = PROMPTS.find(item => item.id === state.scenario);
  let request; let setupError;
  const route = state.comparison === 'routing' ? routingRoute(liveCapabilities, state.routingSelection) : null;
  try { request = createComparisonRequest(state.snapshot, currentRow(), state.metric, state.comparison, state.scenario, 'preview-layout', { routingSelection: state.routingSelection }); }
  catch (error) { setupError = error.message; }
  if (live && !setupError) setupError = liveSetupError || (!liveCapabilities?.available ? 'Live device is unavailable.'
    : state.comparison === 'routing' ? (!liveCapabilities.routing?.available ? 'No route is currently available on the device.' : !routingSelections(liveCapabilities).includes(state.routingSelection) ? 'Choose an advertised route or automatic task policy.' : null)
    : !liveCapabilities.supported_cell_ids.includes(request?.selected?.cell_id) ? 'Select a supported CPU, GPU or NPU configuration on Compare for the live demo.' : null);
  let resolvedRoute = route;
  if (live && request?.routing && state.result?.routing?.selected_route_id) {
    resolvedRoute = routingRoute(liveCapabilities, state.result.routing.selected_route_id);
  } else if (live && state.turboDispatched?.selected_route_id) {
    resolvedRoute = routingRoute(liveCapabilities, state.turboDispatched.selected_route_id);
  }
  const descriptions = request ? comparisonLanes(request, { route: resolvedRoute }) : null;
  const lanes = ['default', 'turbo'].map(key => {
    const lane = state.lanes[key] || { status: 'idle', answer: '' };
    const meta = descriptions?.[key];
    const status = lane.status === 'running' ? 'Writing…' : lane.status === 'completed' ? 'Done' : lane.status === 'failed' ? 'Failed' : lane.status === 'cancelled' ? 'Cancelled' : busy ? 'Queued' : 'Ready';
    const identity = !meta ? 'Configuration unavailable' : `${meta.model} · ${meta.configuration.replace('automatic threads', 'default')}`;
    const dispatched = live && key === 'turbo' && state.turboDispatched;
    const provenance = lane.effective_configuration?.native_provenance;
    const resolved = provenance?.resolved_device;
    const verified = provenance?.dispatch_verified;
    const routeLine = dispatched?.reason ? `<p class="route-reason">${esc(dispatched.reason)}</p>` : '';
    const backendLine = provenance ? `<p class="route-reason">GenieX ${esc(provenance.geniex_version)} · ${esc(provenance.runtime === 'qairt' ? 'Qualcomm QAIRT' : 'llama.cpp')} · ${esc(resolved || (provenance.requested_device === 'cpu' ? 'CPU' : 'unresolved'))}<br>${verified === true ? 'Dispatch verified' : 'SDK placement reported · utilization not measured'}</p>` : '';
    return `<article class="response-column ${key === 'turbo' ? 'response-turbo' : ''}" aria-label="${key === 'turbo' ? 'Local Turbo answer' : 'Default setup answer'}">
      <header class="response-header"><div class="response-title"><h2>${key === 'turbo' ? 'Local Turbo' : 'Default setup'}</h2><span class="response-status ${lane.status === 'running' ? 'active' : ''}">${status}</span></div><p>${esc(identity)}</p>${routeLine}${backendLine}</header>
      <div class="response-text ${lane.status === 'running' ? 'writing' : ''}" data-answer="${key}">${esc(lane.answer)}</div>
      ${live ? `<div class="response-timing"><span>Load + answer + unload</span><strong>${lane.total_time_s == null ? '—' : number(lane.total_time_s) + ' s'}</strong></div><div class="response-timing"><span>First token · native, excludes load</span><strong>${lane.ttft_ms == null ? '—' : number(lane.ttft_ms) + ' ms'}</strong></div><div class="response-timing"><span>Native decode · ${lane.output_tokens == null ? 'tokens unavailable' : lane.output_tokens + ' output tokens'}</span><strong>${lane.native_decode_tps == null ? '—' : number(lane.native_decode_tps) + ' tok/s'}</strong></div>${lane.native_prefill_tps != null ? `<div class="response-timing"><span>Native prefill</span><strong>${number(lane.native_prefill_tps)} tok/s</strong></div>` : ''}` : `<div class="response-timing"><span>Animation time</span><strong data-clock="${key}">${clockText(key)}</strong></div>`}
    </article>`;
  }).join('');
  return `<section class="screen comparison-demo">
    <div class="demo-heading"><h1>Compare answers</h1><div class="comparison-switch" role="group" aria-label="Comparison type"><button data-comparison="speed" aria-pressed="${state.comparison === 'speed'}" ${busy ? 'disabled' : ''}>Speed</button><button data-comparison="routing" aria-pressed="${state.comparison === 'routing'}" ${busy ? 'disabled' : ''}>Model routing</button></div></div>
    <div class="comparison-workspace">
      <div class="prompt-composer"><div class="prompt-controls"><span class="prompt-label">Prompt</span><details class="prompt-picker" ${busy ? 'inert' : ''}><summary aria-label="Example prompt: ${esc(scenario.label)}">${esc(scenario.label)}<span aria-hidden="true">⌄</span></summary><div class="prompt-options" role="group" aria-label="Example prompts">${PROMPTS.map(item => `<button data-scenario="${item.id}" aria-pressed="${state.scenario === item.id}">${item.label}<span aria-hidden="true">${state.scenario === item.id ? '✓' : ''}</span></button>`).join('')}</div></details></div>
        <p class="prompt-copy">${esc(scenario.prompt)}</p>
        ${state.comparison === 'routing' ? `<div class="routing-controls"><label class="routing-label" for="route-select">Route</label><select id="route-select" data-role="route-select" ${busy ? 'disabled' : ''}>${routingSelections(liveCapabilities).map(id => {
          const option = id === 'auto' ? null : routingRoute(liveCapabilities, id);
          const suffix = id === 'auto' ? ' — Task policy · experimental' : option.available === false ? ` — unavailable` : '';
          return `<option value="${esc(id)}" ${state.routingSelection === id ? 'selected' : ''}>${esc(id === 'auto' ? 'Auto' : option.label)}${esc(suffix)}</option>`;
        }).join('')}</select><p class="routing-note">The task policy picks a route by prompt type. It is an experimental choice, not a calibrated speed or quality ranking. The QAIRT option uses a separate compiled artifact.</p></div>` : ''}
        ${state.error || setupError ? `<p class="comparison-error" role="alert">${esc(state.error || setupError)}${live && liveSetupError ? ' <button class="text-button" data-action="reconnect-live">Check connection</button>' : ''}</p>` : ''}
        <button class="button primary run-comparison" data-action="${busy ? 'reset-demo' : 'run-demo'}" ${setupError || state.demo === 'cancelling' ? 'disabled' : ''}>${state.demo === 'cancelling' ? 'Stopping on device…' : busy ? '<span aria-hidden="true">■</span> Stop' : live && taskProvider.pendingRequest() ? 'Check device status' : state.result ? '↻ Run again' : live ? 'Run on Latitude <span aria-hidden="true">→</span>' : 'Run preview <span aria-hidden="true">→</span>'}</button>
      </div>
      <div class="response-grid">${lanes}</div>
    </div>
    <div class="demo-secondary">${live && state.result ? '<button class="button ghost" data-action="download-task">Download device result ↓</button>' : ''}<details class="comparison-info"><summary>How this comparison works</summary><div><p>${state.comparison === 'speed' ? 'Speed compares the same model with its default settings and the configuration selected on the Compare screen.' : 'Model routing runs an experimental task policy: the quick explanation prefers the registered Qualcomm QAIRT bundle, and the schedule question uses the 4B model on CPU. Choose a route above to pin one instead. This policy is not a calibrated speed or quality ranking, and the QAIRT option uses a separately compiled artifact.'}</p><p>${live ? 'Real local inference, sequential on the Latitude. Each lane includes loading and cleanup. Different answer lengths can affect latency; one pair does not establish a speedup. Answer quality is not evaluated. Model and runtime acknowledgements are included in the result.' : 'Scripted preview. Clocks measure each animation, excluding queue time. Live runs will be sequential.'}</p></div></details></div>
    <span class="sr-only" role="status" aria-live="polite">${state.result ? taskProvider.mode === 'live' ? 'Device comparison finished. Results are available.' : 'Comparison preview complete. Both example answers are available.' : busy ? 'Comparison running. Answers appear one at a time.' : ''}</span>
  </section>`;
}

function render({ focus = false } = {}) {
  if (!state.snapshot) return;
  const keepRunFocus = document.activeElement?.classList.contains('run-comparison');
  const keepExplanationOpen = document.querySelector('.comparison-info')?.open;
  document.querySelectorAll('[data-step]').forEach(link => {
    if (link.dataset.step === state.page) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
  });
  $('#mode-tag').innerHTML = `<span class="mode-dot"></span>${state.page === 'demo' ? taskProvider.mode === 'simulated' ? 'Preview · scripted answers' : liveSetupError ? 'Device unavailable' : 'Live · Snapdragon' : 'Recorded results'}`;
  $('#main').innerHTML = state.page === 'device' ? deviceScreen() : state.page === 'calibration' ? calibrationScreen() : demoScreen();
  if (keepExplanationOpen && $('#main .comparison-info')) $('#main .comparison-info').open = true;
  if (!focus && keepRunFocus) $('#main .run-comparison')?.focus({ preventScroll: true });
  if (!focus && !state.reveal) $('#main .screen')?.classList.add('static-screen');
  if (focus) { $('#main').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
  state.reveal = false;
}

function navigate() {
  const next = location.hash.slice(1);
  const page = ['device', 'calibration', 'demo'].includes(next) ? next : 'device';
  if (state.page !== page && ['preparing', 'running', 'cancelling'].includes(state.demo)) {
    if (taskProvider.mode === 'live') { location.hash = 'demo'; notify('Wait for the device result before leaving this task.'); return; }
    resetDemo();
  }
  state.page = page; render({ focus: true });
}

function resetDemo() {
  taskAbort?.abort();
  clearInterval(clockTick); laneClocks = {};
  demoGeneration++; state.demo = 'idle'; state.lanes = {};
  state.result = null; state.error = null; state.turboDispatched = undefined;
}

async function runDemo() {
  if (['preparing', 'running', 'cancelling'].includes(state.demo)) return;
  const pending = taskProvider.mode === 'live' ? taskProvider.pendingRequest() : null;
  resetDemo(); const generation = demoGeneration;
  let request;
  try { request = pending || createComparisonRequest(state.snapshot, currentRow(), state.metric, state.comparison, state.scenario, crypto.randomUUID()); }
  catch (error) { state.error = error.message; render(); return; }
  const controller = new AbortController(); taskAbort = controller;
  const timer = setTimeout(() => controller.abort(new Error('The device did not finish within two minutes. Its execution status is unknown; check the device before retrying.')), 120000);
  let rejectOnAbort;
  const interrupted = new Promise((_, reject) => { rejectOnAbort = () => { if (taskProvider.mode !== 'live') reject(controller.signal.reason); }; controller.signal.addEventListener('abort', rejectOnAbort, { once: true }); });
  state.demo = 'running'; render();
  clockTick = setInterval(updateClocks, 100);
  try {
    const execution = taskProvider.execute(request, { signal: controller.signal, onEvent(event) {
      if (generation !== demoGeneration) return;
      if (event.type === 'route') {
        state.turboDispatched = event.routing;
        render();
      } else if (event.type === 'text') {
        state.lanes[event.lane].answer = event.answer;
        const output = document.querySelector(`[data-answer="${event.lane}"]`);
        if (output) output.textContent = event.answer;
      } else {
        if (event.type === 'start') laneClocks[event.lane] = { started: performance.now() };
        if (event.type === 'complete' && laneClocks[event.lane]) {
          laneClocks[event.lane].elapsed = performance.now() - laneClocks[event.lane].started;
        }
        state.lanes[event.lane] = event.type === 'complete' ? event.result : { status: 'running', answer: '' };
        render();
      }
    } });
    const result = taskProvider.mode === 'live' ? await execution : await Promise.race([interrupted, execution]);
    if (generation !== demoGeneration) return;
    state.result = result; state.lanes = result.lanes; state.demo = result.status === 'failed' ? 'failed' : 'complete'; state.error = result.error || null; render();
  } catch (error) {
    if (generation !== demoGeneration) return;
    state.error = error.message || 'The device run could not be verified. Check its status before retrying.';
    for (const clock of Object.values(laneClocks)) clock.elapsed ??= performance.now() - clock.started;
    state.demo = 'failed'; render();
  } finally { if (generation === demoGeneration) clearInterval(clockTick); clearTimeout(timer); controller.signal.removeEventListener('abort', rejectOnAbort); }
}

function download(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}


function showEvidence() {
  if (!state.snapshot) return;
  const s = state.snapshot; const row = currentRow();
  const latest = state.latest;
  const latestDetails = latest ? `<details><summary>Latest QAIRT and model study</summary><dl class="evidence-list"><div><dt>QAIRT optimization</dt><dd>${number(latest.qairt.control.accuracy_pct, 0)}% → ${number(latest.qairt.optimized.accuracy_pct, 0)}% task success; mean inference ${number(latest.qairt.control.average_inference_ms, 0)} → ${number(latest.qairt.optimized.average_inference_ms, 0)} ms.</dd></div><div><dt>Quality status</dt><dd>No candidate passed the frozen quality gate. Model runs remain separate experiments.</dd></div><div><dt>QAIRT sources</dt><dd class="mono hash">${esc(latest.sources.qairtControl)}<br>${esc(latest.sources.qairtOptimized)}</dd></div><div><dt>Larger-model sources</dt><dd class="mono hash">${esc(latest.sources.qwen4b)}<br>${esc(latest.sources.qwen8b)}</dd></div></dl></details>` : '';
  $('#evidence-content').innerHTML = `<div class="evidence-summary"><span class="mode-tag">Recorded screening</span><p>Measurements from the Dell Latitude, not this browser’s host. These observations do not establish a confirmed speedup or answer quality.</p></div>
    <dl class="evidence-list"><div><dt>Machine</dt><dd>${esc(s.device.name)}</dd></div><div><dt>Recorded</dt><dd>${esc(new Date(s.recordedAt).toUTCString())}</dd></div><div><dt>Timing source</dt><dd>${esc(s.timingSource)}</dd></div><div><dt>Source</dt><dd>${esc(s.source)}</dd></div><div><dt>Model SHA-256</dt><dd class="mono hash">${esc(s.modelHash)}</dd></div><div><dt>Runtime SHA-256</dt><dd class="mono hash">${esc(s.runtimeHash)}</dd></div><div><dt>Workload</dt><dd>${row?.params ? `${row.params.n_prompt} input · ${row.params.n_gen} output · ${row.params.n_ctx} context · ${row.params.warmup} warmup · ${row.params.repetitions} repetitions` : 'Unavailable'}</dd></div><div><dt>Reported device</dt><dd>${esc(row?.resolvedDevice || 'Not reported')} · ${esc(row?.dispatch)}</dd></div><div><dt>Energy scope</dt><dd>SYS channel, full process including initialization and warmup. Energy efficiency unavailable: warmup token counts are missing.</dd></div></dl>
    ${latestDetails}<details><summary>Inspect selected raw result</summary><pre>${esc(JSON.stringify(row?.raw ?? {}, null, 2))}</pre></details><button class="button ghost" data-action="download-evidence">Download recorded evidence ↓</button>`;
  $('#evidence-dialog').showModal();
}

document.addEventListener('click', event => {
  if (event.target.closest('.skip')) { event.preventDefault(); $('#main').focus(); return; }
  const picker = $('.prompt-picker');
  if (picker && !picker.contains(event.target)) picker.open = false;
  const target = event.target.closest('button'); if (!target) return;
  if (taskProvider.mode === 'live' && ['running','cancelling'].includes(state.demo) && target.dataset.action !== 'reset-demo') { notify('Wait for the current device job to finish.'); return; }
  if (taskProvider.mode === 'live' && taskProvider.pendingRequest() && !['run-demo','reset-demo','reconnect-live'].includes(target.dataset.action)) { notify('Check device status before changing the comparison.'); return; }
  const metric = target.dataset.metric;
  if (metric) {
    resetDemo();
    state.metric = metric; state.metricHelp = false; state.selected = rankRows(state.snapshot, metric).leaders[0] ?? null;
    render(); document.querySelector(`[data-metric="${metric}"]`)?.focus({ preventScroll: true }); return;
  }
  if (target.dataset.select) {
    resetDemo(); state.selected = target.dataset.select; render(); document.querySelector(`[data-select="${CSS.escape(state.selected)}"]`)?.focus({ preventScroll: true }); return;
  }
  if (target.dataset.comparison) { state.comparison = target.dataset.comparison; resetDemo(); render(); document.querySelector(`[data-comparison="${state.comparison}"]`)?.focus(); return; }
  if (target.closest('#route-select')) return;
  if (target.dataset.scenario) { state.scenario = target.dataset.scenario; resetDemo(); render(); $('.prompt-picker summary')?.focus({ preventScroll: true }); return; }
  switch (target.dataset.action) {
    case 'reconnect-live': {
      target.disabled = true;
      taskProvider.capabilities().then(caps => { liveCapabilities = caps; liveSetupError = null; state.error = null; })
        .catch(error => { liveSetupError = error.message; }).finally(() => render());
      break;
    }
    case 'metric-help': state.metricHelp = !state.metricHelp; render(); $('.metric-help-button')?.focus({ preventScroll: true }); break;
    case 'explore': state.reveal = true; location.hash = 'calibration'; break;
    case 'try': resetDemo(); location.hash = 'demo'; break;
    case 'back': location.hash = 'calibration'; break;
    case 'export': {
      try { download(exportConfiguration(state.snapshot, currentRow(), state.metric), `local-turbo-${state.selected || currentRow().id}.json`); notify('Provisional configuration exported. Nothing was applied to the device.'); }
      catch (error) { notify(error.message); } break;
    }
    case 'evidence': showEvidence(); break;
    case 'download-evidence': download(state.snapshot.raw, 'local-turbo-recorded-evidence.json'); break;
    case 'download-task': if (state.result?.mode === 'live') download(state.result, `local-turbo-task-${state.result.request_id}.json`); break;
    case 'run-demo': runDemo(); break;
    case 'reset-demo': if (taskProvider.mode === 'live' && ['running','cancelling'].includes(state.demo)) { state.demo = 'cancelling'; taskAbort?.abort(new Error('Cancellation requested')); render(); } else { resetDemo(); render(); } break;
    case 'retry': load(); break;
  }
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const picker = $('.prompt-picker');
  if (picker?.open) { picker.open = false; picker.querySelector('summary').focus(); }
});
$('#evidence-button').addEventListener('click', showEvidence);
$('#close-dialog').addEventListener('click', () => $('#evidence-dialog').close());
$('#evidence-dialog').addEventListener('click', event => { if (event.target === $('#evidence-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });
$('#main').addEventListener('change', event => {
  if (event.target.dataset?.role === 'route-select') { state.routingSelection = event.target.value; resetDemo(); render(); $('#route-select')?.focus({ preventScroll: true }); }
});
window.addEventListener('hashchange', navigate);

async function load() {
  $('#main').innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Opening recorded results…</p></div>';
  try {
    const [snapshotResult, latestResult] = await Promise.allSettled([
      provider.load({ signal: AbortSignal.timeout(10000) }),
      latestProvider.load({ signal: AbortSignal.timeout(10000) }),
    ]);
    if (snapshotResult.status === 'rejected') throw snapshotResult.reason;
    state.snapshot = snapshotResult.value;
    const health = await fetch('/api/health', {signal:AbortSignal.timeout(10000)}).then(r => { if (!r.ok) throw new Error('Demo connection status unavailable'); return r.json(); });
    if (health.live_backend) {
      taskProvider = createLiveComparisonProvider();
      try { liveCapabilities = await taskProvider.capabilities(); liveSetupError = null; } catch (error) { liveSetupError = error.message; }
    }
    state.latest = latestResult.status === 'fulfilled' ? latestResult.value : null;
    state.latestError = latestResult.status === 'rejected' ? latestResult.reason?.message : null;
    resetDemo();
    state.selected = rankRows(state.snapshot).leaders[0] ?? null;
    if (taskProvider.mode === 'live') {
      const pending = taskProvider.pendingRequest();
      if (pending) {
        state.comparison = pending.comparison === 'routing' ? 'routing' : 'speed';
        state.scenario = pending.prompt_id; state.routingSelection = pending.routing?.selection ?? 'auto';
        if (pending.selected) state.selected = pending.selected.cell_id;
      } else if (liveCapabilities?.routing?.selections && !liveCapabilities.routing.selections.includes(state.routingSelection)) {
        state.routingSelection = 'auto';
      }
      else if (liveCapabilities?.available) {
        const ranked = rankRows(state.snapshot);
        state.selected = ranked.rows.find(row => ranked.eligible(row) && liveCapabilities.supported_cell_ids.includes(row.id))?.id ?? state.selected;
      }
    }
    navigate();
  } catch (error) {
    $('#main').innerHTML = `<section class="error-state"><span class="eyebrow">RESULTS UNAVAILABLE</span><h1>We couldn’t open this run.</h1><p>${esc(error.message)}</p><button class="button primary" data-action="retry">Try again ↗</button></section>`;
  }
}
load();
