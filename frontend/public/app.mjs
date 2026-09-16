import { createRecordedProvider, METRICS, rankRows, exportConfiguration } from './data.mjs';
import { createLatestResultsProvider } from './latest.mjs';
import { createInvoiceDemoProvider, INVOICE_TASK } from './live-demo.mjs';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const number = (value, digits = 2) => value === null || value === undefined ? 'Unavailable' : value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const arrow = '<span aria-hidden="true">↗</span>';
const provider = createRecordedProvider();
const latestProvider = createLatestResultsProvider();
const taskProvider = createInvoiceDemoProvider();
const state = { snapshot: null, latest: null, latestError: null, demoStatus: null, page: 'device', metric: 'decode', metricHelp: false, selected: null, demo: 'idle', result: null, error: null, reveal: false };
let demoGeneration = 0;
let taskAbort;
let toastTimer;

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
  const busy = state.demo === 'running';
  const available = state.demoStatus?.available === true;
  const result = state.result;
  const moved = result?.file_move?.verified === true;
  const configuration = result?.configuration;
  const configurationLabel = configuration
    ? `${configuration.runtime} · ${configuration.device.toUpperCase()}${configuration.threads ? ` · ${configuration.threads} threads` : ''}`
    : 'Qwen3-4B · GenieX · CPU';
  const runStatus = busy
    ? `<div class="action-status running"><span class="live-spinner" aria-hidden="true"></span><div><strong>Running locally</strong><small>Waiting for the Latitude and independent file verification</small></div></div>`
    : result
      ? `<div class="action-status ${moved ? 'verified' : 'rejected'}"><span class="status-mark" aria-hidden="true">${moved ? '✓' : '×'}</span><div><strong>${moved ? 'Move verified' : 'Move not verified'}</strong><small>${moved ? `${result.timing.loop_seconds == null ? 'Task complete' : `${number(result.timing.loop_seconds, 1)} s`} · same content hash · unrelated files unchanged` : esc(result.file_move.reason || 'Inspect the preserved run evidence')}</small></div></div>`
      : `<div class="action-status ${available ? 'ready' : 'offline'}"><span class="status-mark" aria-hidden="true">${available ? '●' : '○'}</span><div><strong>${available ? 'Ready on the Latitude' : 'Latitude connection required'}</strong><small>${available ? 'The next result will come from the local model' : 'The interface will not simulate a successful run'}</small></div></div>`;
  return `<section class="screen live-demo">
    <header class="live-demo-heading"><div><span class="eyebrow">LIVE ON THE LATITUDE</span><h1>From request to verified action.</h1><p>The model reads the task, calls local tools, and we check what changed.</p></div><span class="device-state ${available ? 'connected' : 'offline'}"><i></i>${available ? 'Connected' : 'Not connected'}</span></header>
    <div class="live-workspace">
      <div class="live-prompt"><div><span class="prompt-label">TASK ${esc(INVOICE_TASK.id)}</span><p>${esc(INVOICE_TASK.prompt)}</p></div><button class="button primary run-live" data-action="run-demo" ${!available || busy ? 'disabled' : ''}>${busy ? 'Running…' : !available ? 'Connect Latitude' : result ? 'Run again ↗' : 'Run live →'}</button></div>
      <div class="file-action-stage ${busy ? 'working' : ''} ${moved ? 'complete' : ''}">
        <article class="folder-card source-folder"><header><span class="folder-icon" aria-hidden="true"></span><div><strong>drafts</strong><small>Source folder</small></div></header><div class="file-list">${moved ? `<div class="file-row moved"><span>✓</span><div><strong>hexagon-invoice.md</strong><small>Moved successfully</small></div></div>` : `<div class="file-row target"><span>MD</span><div><strong>hexagon-invoice.md</strong><small>Invoice draft</small></div></div>`}<div class="file-row quiet"><span>MD</span><div><strong>q3-summary.md</strong><small>Unchanged</small></div></div></div></article>
        <div class="model-bridge"><span class="bridge-line"></span><div><span class="bridge-mark">lt</span><strong>Local model</strong><small>${esc(configurationLabel)}</small></div><span class="bridge-arrow" aria-hidden="true">→</span></div>
        <article class="folder-card destination-folder"><header><span class="folder-icon" aria-hidden="true"></span><div><strong>invoices/2026</strong><small>Destination folder</small></div></header><div class="file-list">${moved ? `<div class="file-row arrived"><span>✓</span><div><strong>hexagon-invoice.md</strong><small>Bytes preserved</small></div></div>` : `<div class="destination-slot"><span>Destination</span><small>The verified file will appear here</small></div>`}</div></article>
      </div>
      <div class="live-status-bar">${runStatus}<div class="verification-note"><span>Protected fixture</span><span>Hash checked</span><span>No cloud inference</span></div></div>
    </div>
    ${state.error ? `<p class="live-error" role="alert">${esc(state.error)}</p>` : ''}
    ${result ? `<details class="live-disclosure"><summary>Verification details</summary><div><p><strong>Physical result:</strong> ${moved ? 'source removed, destination added, bytes preserved.' : 'not verified.'}</p><p><strong>Exact-call check:</strong> ${result.exact_call.passed ? 'passed.' : 'failed because the model used extra search/list calls.'}</p><p>This public-fixture diagnostic is not a production quality pass.</p></div></details>` : ''}
    <span class="sr-only" role="status" aria-live="polite">${busy ? 'The task is running on the Latitude.' : result ? (moved ? 'The file move was verified.' : 'The file move was not verified.') : ''}</span>
  </section>`;
}

function render({ focus = false } = {}) {
  if (!state.snapshot) return;
  const keepRunFocus = document.activeElement?.classList.contains('run-live');
  document.querySelectorAll('[data-step]').forEach(link => {
    if (link.dataset.step === state.page) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
  });
  $('#mode-tag').innerHTML = `<span class="mode-dot"></span>${state.page === 'demo' ? state.demoStatus?.available ? 'Device task · ready' : 'Device task · offline' : 'Recorded results'}`;
  $('#main').innerHTML = state.page === 'device' ? deviceScreen() : state.page === 'calibration' ? calibrationScreen() : demoScreen();
  if (!focus && keepRunFocus) $('#main .run-live')?.focus({ preventScroll: true });
  if (!focus && !state.reveal) $('#main .screen')?.classList.add('static-screen');
  if (focus) { $('#main').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
  state.reveal = false;
}

function navigate() {
  const next = location.hash.slice(1);
  const page = ['device', 'calibration', 'demo'].includes(next) ? next : 'device';
  if (state.page !== page && ['preparing', 'running'].includes(state.demo)) {
    location.hash = 'demo'; notify('Wait for the device result before leaving this task.'); return;
  }
  state.page = page; render({ focus: true });
}

function resetDemo() {
  taskAbort?.abort();
  demoGeneration++; state.demo = 'idle';
  state.result = null; state.error = null;
}

async function runDemo() {
  if (['preparing', 'running'].includes(state.demo)) return;
  resetDemo(); const generation = demoGeneration;
  const controller = new AbortController(); taskAbort = controller;
  const timer = setTimeout(() => controller.abort(new Error('The device did not finish within four and a half minutes. Its execution status is unknown; check the device before retrying.')), 270000);
  let rejectOnAbort;
  const interrupted = new Promise((_, reject) => { rejectOnAbort = () => reject(controller.signal.reason); controller.signal.addEventListener('abort', rejectOnAbort, { once: true }); });
  state.demo = 'running'; render();
  try {
    const result = await Promise.race([interrupted, taskProvider.execute({ signal: controller.signal })]);
    if (generation !== demoGeneration) return;
    state.result = result; state.demo = 'complete'; render();
  } catch (error) {
    if (generation !== demoGeneration) return;
    state.error = error.message || 'The device run could not be verified. Check its status before retrying.';
    state.demo = 'failed'; render();
  } finally { clearTimeout(timer); controller.signal.removeEventListener('abort', rejectOnAbort); }
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
  const target = event.target.closest('button'); if (!target) return;
  const metric = target.dataset.metric;
  if (metric) {
    resetDemo();
    state.metric = metric; state.metricHelp = false; state.selected = rankRows(state.snapshot, metric).leaders[0] ?? null;
    render(); document.querySelector(`[data-metric="${metric}"]`)?.focus({ preventScroll: true }); return;
  }
  if (target.dataset.select) {
    resetDemo(); state.selected = target.dataset.select; render(); document.querySelector(`[data-select="${CSS.escape(state.selected)}"]`)?.focus({ preventScroll: true }); return;
  }
  switch (target.dataset.action) {
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
    case 'download-task': if (state.result?.mode === 'live') download(state.result, `local-turbo-task-${state.result.run_id}.json`); break;
    case 'run-demo': runDemo(); break;
    case 'retry': load(); break;
  }
});
$('#evidence-button').addEventListener('click', showEvidence);
$('#close-dialog').addEventListener('click', () => $('#evidence-dialog').close());
$('#evidence-dialog').addEventListener('click', event => { if (event.target === $('#evidence-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });
window.addEventListener('hashchange', navigate);

async function load() {
  $('#main').innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Opening recorded results…</p></div>';
  try {
    const [snapshotResult, latestResult, demoStatusResult] = await Promise.allSettled([
      provider.load({ signal: AbortSignal.timeout(10000) }),
      latestProvider.load({ signal: AbortSignal.timeout(10000) }),
      taskProvider.status({ signal: AbortSignal.timeout(10000) }),
    ]);
    if (snapshotResult.status === 'rejected') throw snapshotResult.reason;
    state.snapshot = snapshotResult.value;
    state.latest = latestResult.status === 'fulfilled' ? latestResult.value : null;
    state.latestError = latestResult.status === 'rejected' ? latestResult.reason?.message : null;
    state.demoStatus = demoStatusResult.status === 'fulfilled' ? demoStatusResult.value : {
      schema_version: 'local-turbo.invoice-demo-status.v1', available: false, running: false,
      task_id: 't13', device: 'Dell Latitude 7455', model: 'Qwen3-4B-Instruct-2507 Q4_0',
      reason: demoStatusResult.reason?.message || 'The Latitude runner is unavailable.',
    };
    resetDemo();
    state.selected = rankRows(state.snapshot).leaders[0] ?? null;
    navigate();
  } catch (error) {
    $('#main').innerHTML = `<section class="error-state"><span class="eyebrow">RESULTS UNAVAILABLE</span><h1>We couldn’t open this run.</h1><p>${esc(error.message)}</p><button class="button primary" data-action="retry">Try again ↗</button></section>`;
  }
}
load();
