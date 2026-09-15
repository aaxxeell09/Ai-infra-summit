import { createRecordedProvider, METRICS, rankRows, exportConfiguration } from './data.mjs';
import { SCENARIOS, initialFiles, createTaskRequest, createPreviewTaskProvider } from './demo.mjs';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const number = (value, digits = 2) => value === null || value === undefined ? 'Unavailable' : value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const date = value => new Date(value).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const arrow = '<span aria-hidden="true">↗</span>';
const provider = createRecordedProvider();
// Replace this one provider with createLiveTaskProvider(deviceBridge) at integration.
const taskProvider = createPreviewTaskProvider();
const state = { snapshot: null, page: 'device', metric: 'decode', selected: null, scenario: 'move', demo: 'idle', files: initialFiles(), result: null, session: null, error: null, reveal: false };
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

function deviceScreen() {
  const s = state.snapshot;
  const cpus = s.rows.filter(row => row.device === 'cpu').length;
  return `<section class="screen device-screen">
    <div class="device-copy"><div class="eyebrow"><span class="tiny-line"></span> LOCAL INFERENCE TUNING</div>
      <h1><span>Tune your model.</span> <em>For this machine.</em></h1>
      <p class="lead">${s.rows.length} configurations tested on the same model.<br>Compare the measurements. Choose how it runs.</p>
      <button class="button primary large" data-action="explore">Compare configurations ${arrow}</button>
      <p class="quiet provenance">Recorded on the Latitude · ${esc(date(s.recordedAt))}</p>
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
    const annotation = winner ? (leaders.length > 1 ? 'Tied best' : 'Best measured') : row.id === 'cpu-t0' ? 'Default' : '';
    return `<button class="result-row ${winner ? 'winner' : ''} ${selected ? 'selected' : ''} ${!valid ? 'invalid' : ''}" data-select="${esc(row.id)}" aria-pressed="${selected}" aria-label="${esc(row.label)}, ${valid ? `${number(value)} ${metric.unit}` : esc(row.reason || 'Not comparable')}" style="--delay:${Math.min(index * 55, 500)}ms">
      <span class="row-label">${esc(row.label)}${annotation ? `<span class="row-annotation">${annotation}</span>` : ''}</span>
      <span class="bar-track"><span class="bar" style="--bar:${valid ? value / max * 100 : 0}%"></span></span>
      <span class="row-value">${valid ? number(value) : '—'}</span><span class="row-chevron" aria-hidden="true">↗</span>
    </button>`;
  }).join('');
  const isEligible = chosen && eligible(chosen);
  const isLeader = chosen && leaders.includes(chosen.id);
  const secondaryMetric = state.metric === 'ttft' ? ['Generation speed', chosen?.metrics.decode, 'tok/s'] : ['Time to first token', chosen?.metrics.ttft, 'ms'];
  return `<section class="screen calibration-screen ${state.reveal ? 'reveal' : ''}">
    <div class="section-heading"><div><div class="eyebrow">SAME MODEL. SAME WORKLOAD.</div><h1>Choose how it runs.</h1></div><span class="record-label">${esc(s.model.replace(/\.gguf$/, ''))}</span></div>
    <div class="calibration-layout"><div class="chart-panel">
      <div class="chart-toolbar"><div class="metric-tabs" role="group" aria-label="Measurement to compare">${Object.entries(METRICS).map(([key, m]) => `<button data-metric="${key}" aria-pressed="${state.metric === key}" class="${state.metric === key ? 'active' : ''}">${key === 'decode' ? 'Generation' : key === 'prefill' ? 'Prompt processing' : 'First token'}</button>`).join('')}</div><span class="chart-unit">${metric.unit} · ${metric.hint}</span></div>
      <div class="chart" aria-label="${esc(metric.label)} comparison">${chartRows}</div>
      <div class="chart-foot"><span>${baseline?.params ? `Median of ${baseline.params.repetitions} repetitions · ${baseline.params.n_prompt} input / ${baseline.params.n_gen} output tokens` : 'No comparable workload available'}</span></div>
    </div><aside class="selection-panel">
      <div class="selection-top"><span class="eyebrow">SELECTED CONFIGURATION</span><span class="selection-icon" aria-hidden="true">${isLeader ? '↗' : '◇'}</span></div>
      <h2>${chosen ? esc(chosen.label.replace(' · ', '<|>').split('<|>')[0]) : 'No result'}<span>${chosen?.device === 'cpu' ? esc(chosen.threads === 0 ? 'Automatic threads' : `${chosen.threads} threads`) : 'Recorded configuration'}</span></h2>
      <p class="selection-caption">${isEligible ? (isLeader ? `Best measured ${state.metric === 'ttft' ? 'time to first token' : state.metric === 'prefill' ? 'prompt processing speed' : 'generation speed'} in this run.` : 'Selected for the task demo. Other settings may be faster.') : esc(chosen?.reason || 'No comparable result available.')}</p>
      <div class="selection-metrics"><div><span>${secondaryMetric[0]}</span><strong>${number(secondaryMetric[1])}<small>${secondaryMetric[1] == null ? '' : secondaryMetric[2]}</small></strong></div><div><span>Peak process memory</span><strong>${chosen?.memory_mb == null ? 'Unavailable' : number(chosen.memory_mb / 1024, 2)}<small>${chosen?.memory_mb == null ? '' : 'GiB'}</small></strong></div></div>
      <div class="evidence-note"><span class="note-dot"></span><p>Preliminary measurements.<br>Repeat comparison and task checks pending.${chosen && ['npu', 'hybrid'].includes(chosen.device) ? '<br>NPU execution is not yet verified.' : ''}</p></div>
      <button class="button primary" data-action="try" ${!isEligible ? 'disabled' : ''}>Continue to task ${arrow}</button>
      <button class="button ghost" data-action="export" ${!isEligible ? 'disabled' : ''}>Export configuration <span aria-hidden="true">↓</span></button>
    </aside></div>
  </section>`;
}

function fileMarkup(file) {
  const moved = file.folder === 'Presentation';
  const kind = file.kind === 'csv' ? 'csv' : 'md';
  return `<div class="file ${moved ? 'file-arrived' : ''}" data-file="${esc(file.name)}"><span class="file-icon ${kind}" aria-hidden="true">${kind === 'csv' ? '▦' : '≡'}</span><div><strong>${esc(file.name)}</strong><span>${esc(file.size)} · ${file.kind === 'csv' ? 'Spreadsheet' : file.kind === 'md' ? 'Markdown' : 'File'}</span></div>${moved ? '<span class="file-check" aria-hidden="true">✓</span>' : ''}</div>`;
}

function demoScreen() {
  const row = currentRow();
  const scenario = SCENARIOS.find(item => item.id === state.scenario);
  const busy = ['preparing', 'running'].includes(state.demo);
  const result = state.result;
  const preview = taskProvider.mode === 'simulated';
  const valid = row && rankRows(state.snapshot, state.metric).eligible(row);
  const source = state.files.filter(file => file.folder === 'Workspace');
  const destination = state.files.filter(file => file.folder === 'Presentation');
  const passed = !preview && result?.quality.status === 'passed' && result.status === 'completed';
  const failed = state.error || result?.status === 'failed' || result?.quality.status === 'failed';
  const outcomeTitle = failed ? 'This run needs attention.' : result?.status === 'clarification' ? 'A file choice is needed.' : preview ? 'Preview complete.' : passed ? 'Task checks passed.' : 'Task finished. Checks pending.';
  const configStatus = preview ? 'Selected for preview · not applied' : state.session ? 'Applied on the device' : 'Will be verified before running';
  const runLabel = busy ? preview ? 'Playing preview…' : state.demo === 'preparing' ? 'Preparing the model…' : 'Running on the Latitude…' : preview ? result ? 'Replay preview' : 'Preview task' : result ? 'Run a new task' : 'Run on the Latitude';
  const outcome = busy ? `<span class="eyebrow">${preview ? 'TASK PREVIEW' : state.demo === 'preparing' ? 'PREPARING' : 'RUNNING'}</span><p>${preview ? 'Showing the example action and its effect.' : state.demo === 'preparing' ? 'Verifying the model, settings and isolated workspace.' : 'The model is handling the request. Waiting for the device result.'}</p>` : state.error ? `<h2>${outcomeTitle}</h2><p>${esc(state.error)}</p>` : result ? `<span class="outcome-symbol ${passed ? 'verified' : ''}">${failed ? '!' : result.status === 'clarification' ? '?' : passed ? '✓' : '→'}</span><h2>${outcomeTitle}</h2><p>${esc(result.message)}</p>${preview ? '<span class="quiet">Example outcome only. The model has not run.</span>' : `<dl class="task-measures"><div><dt>Total task time</dt><dd>${number(result.task_time_s)}${result.task_time_s == null ? '' : ' s'}</dd></div><div><dt>Time to first token</dt><dd>${number(result.ttft_ms)}${result.ttft_ms == null ? '' : ' ms'}</dd></div></dl><span class="quiet">${esc(result.timing_scope || 'Timing scope unavailable.')}</span>`}` : `<span class="eyebrow">${preview ? 'PREVIEW THE FINAL STEP' : 'READY TO RUN'}</span><p>${preview ? 'The connected version will run this request with the selected model and settings.' : 'Run the selected model, then inspect the file changes and task checks.'}</p>`;
  return `<section class="screen demo-screen">
    <div class="section-heading"><div><div class="eyebrow">FROM MEASUREMENTS TO ACTION</div><h1>Your model. In action.</h1></div></div>
    <div class="run-context"><div><span class="eyebrow">${preview || !state.session ? 'SELECTED MODEL' : 'ACTIVE MODEL'}</span><strong>${esc(state.snapshot.model.replace(/\.gguf$/, ''))}</strong></div><div><strong>${row ? esc(row.label) : 'No configuration selected'}</strong><span>${configStatus}</span></div></div>
    <div class="demo-layout"><div class="task-panel">
      <h2 class="eyebrow">THE REQUEST</h2>
      <div class="scenario-picker" role="group" aria-label="Demo request">${SCENARIOS.map(item => `<button data-scenario="${item.id}" class="${item.id === state.scenario ? 'active' : ''}" aria-pressed="${item.id === state.scenario}" ${busy ? 'disabled' : ''}>${esc(item.label)}</button>`).join('')}</div>
      <blockquote>${esc(scenario.prompt)}</blockquote>
      <div class="task-actions"><button class="button primary" data-action="run-demo" ${busy || !valid ? 'disabled' : ''}>${busy ? '<span class="spinner small"></span>' : ''}${runLabel} ${busy ? '' : arrow}</button>${preview ? '<button class="icon-button" data-action="reset-demo" aria-label="Reset preview" title="Reset preview">↺</button>' : ''}</div>
      <div class="task-outcome ${result ? 'outcome-ready' : ''}" role="status" aria-live="polite">${outcome}</div>
    </div><div class="workspace-panel">
      <div class="workspace-head"><span class="folder-outline" aria-hidden="true">▱</span><h2>Task workspace</h2><span class="sandbox-label">${preview ? 'Preview files' : state.session ? 'Device fixture' : 'Awaiting device'}</span></div>
      <div class="folder-section"><div class="folder-title"><span>Workspace</span><span>${source.length} files</span></div><div class="file-list">${source.map(fileMarkup).join('')}</div></div>
      <div class="destination-section ${busy && preview && state.scenario === 'move' ? 'receiving' : ''}"><div class="folder-title"><span>▱ &nbsp; Presentation</span><span>${destination.length} ${destination.length === 1 ? 'file' : 'files'}</span></div><div class="file-list">${destination.length ? destination.map(fileMarkup).join('') : '<div class="empty-folder"><p>No files in this folder</p></div>'}</div></div>
    </div></div>
    ${result ? `<details class="task-details"><summary>${preview ? 'Preview details' : 'Run evidence'}</summary><dl class="task-detail-list"><div><dt>${preview ? 'Example action' : 'Returned action'}</dt><dd><code>${esc(result.action ? JSON.stringify(result.action) : result.clarification || 'No action returned')}</code></dd></div><div><dt>Task checks</dt><dd>${preview ? 'Not evaluated — no model was run.' : esc(result.quality.status.replaceAll('_', ' '))}</dd></div></dl>${!preview ? `<pre>${esc(JSON.stringify(result, null, 2))}</pre><button class="text-button" data-action="download-task">Download run evidence ↓</button>` : ''}</details>` : ''}
    <div class="demo-bottom"><button class="text-button" data-action="back">← Back to comparison</button></div>
  </section>`;
}

function render({ focus = false } = {}) {
  if (!state.snapshot) return;
  document.querySelectorAll('[data-step]').forEach(link => {
    if (link.dataset.step === state.page) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
  });
  $('#mode-tag').innerHTML = `<span class="mode-dot"></span>${state.page === 'demo' ? taskProvider.mode === 'simulated' ? 'Preview · no model connected' : 'Device task' : 'Recorded results'}`;
  $('#main').innerHTML = state.page === 'device' ? deviceScreen() : state.page === 'calibration' ? calibrationScreen() : demoScreen();
  if (!focus && !state.reveal) $('#main .screen')?.classList.add('static-screen');
  if (focus) { $('#main').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
  state.reveal = false;
}

function navigate() {
  const next = location.hash.slice(1);
  const page = ['device', 'calibration', 'demo'].includes(next) ? next : 'device';
  if (state.page !== page && ['preparing', 'running'].includes(state.demo)) {
    if (taskProvider.mode === 'live') { location.hash = 'demo'; notify('Wait for the device result before leaving this task.'); return; }
    resetDemo();
  }
  state.page = page; render({ focus: true });
}

function resetDemo() {
  taskAbort?.abort();
  demoGeneration++; state.demo = 'idle'; state.files = taskProvider.mode === 'simulated' ? initialFiles() : [];
  state.result = null; state.session = null; state.error = null;
}

async function runDemo() {
  if (['preparing', 'running'].includes(state.demo)) return;
  if (!rankRows(state.snapshot, state.metric).eligible(currentRow())) return;
  resetDemo(); const generation = demoGeneration;
  const request = createTaskRequest(state.snapshot, currentRow(), METRICS[state.metric].key, state.scenario, crypto.randomUUID());
  const controller = new AbortController(); taskAbort = controller;
  const timer = setTimeout(() => controller.abort(new Error('The device did not finish within two minutes. Its execution status is unknown; check the device before retrying.')), 120000);
  let rejectOnAbort;
  const interrupted = new Promise((_, reject) => { rejectOnAbort = () => reject(controller.signal.reason); controller.signal.addEventListener('abort', rejectOnAbort, { once: true }); });
  state.demo = taskProvider.mode === 'simulated' ? 'running' : 'preparing'; render();
  try {
    const result = await Promise.race([interrupted, taskProvider.execute(request, { signal: controller.signal, onPrepared(session) {
      if (generation !== demoGeneration) return;
      state.session = session; state.files = session.files; state.demo = 'running'; render();
    } })]);
    if (generation !== demoGeneration) return;
    state.result = result; state.files = result.files; state.demo = 'complete'; render();
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
  $('#evidence-content').innerHTML = `<div class="evidence-summary"><span class="mode-tag">Recorded screening</span><p>Measurements from the Dell Latitude, not this browser’s host. These observations do not establish a confirmed speedup or file-task accuracy.</p></div>
    <dl class="evidence-list"><div><dt>Recorded</dt><dd>${esc(new Date(s.recordedAt).toUTCString())}</dd></div><div><dt>Timing source</dt><dd>${esc(s.timingSource)}</dd></div><div><dt>Source</dt><dd>${esc(s.source)}</dd></div><div><dt>Model SHA-256</dt><dd class="mono hash">${esc(s.modelHash)}</dd></div><div><dt>Runtime SHA-256</dt><dd class="mono hash">${esc(s.runtimeHash)}</dd></div><div><dt>Workload</dt><dd>${row?.params ? `${row.params.n_prompt} input · ${row.params.n_gen} output · ${row.params.n_ctx} context · ${row.params.warmup} warmup · ${row.params.repetitions} repetitions` : 'Unavailable'}</dd></div><div><dt>Reported device</dt><dd>${esc(row?.resolvedDevice || 'Not reported')} · ${esc(row?.dispatch)}</dd></div><div><dt>Energy scope</dt><dd>SYS channel, full process including initialization and warmup. Energy efficiency unavailable: warmup token counts are missing.</dd></div></dl>
    <details><summary>Inspect selected raw result</summary><pre>${esc(JSON.stringify(row?.raw ?? {}, null, 2))}</pre></details><button class="button ghost" data-action="download-evidence">Download recorded evidence ↓</button>`;
  $('#evidence-dialog').showModal();
}

document.addEventListener('click', event => {
  if (event.target.closest('.skip')) { event.preventDefault(); $('#main').focus(); return; }
  const target = event.target.closest('button'); if (!target) return;
  const metric = target.dataset.metric;
  if (metric) {
    resetDemo();
    state.metric = metric; state.selected = rankRows(state.snapshot, metric).leaders[0] ?? null;
    render(); document.querySelector(`[data-metric="${metric}"]`)?.focus({ preventScroll: true }); return;
  }
  if (target.dataset.select) {
    resetDemo(); state.selected = target.dataset.select; render(); document.querySelector(`[data-select="${CSS.escape(state.selected)}"]`)?.focus({ preventScroll: true }); return;
  }
  if (target.dataset.scenario) { state.scenario = target.dataset.scenario; resetDemo(); render(); document.querySelector(`[data-scenario="${state.scenario}"]`)?.focus(); return; }
  switch (target.dataset.action) {
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
    case 'reset-demo': resetDemo(); render(); break;
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
    state.snapshot = await provider.load({ signal: AbortSignal.timeout(10000) });
    resetDemo();
    state.selected = rankRows(state.snapshot).leaders[0] ?? null;
    navigate();
  } catch (error) {
    $('#main').innerHTML = `<section class="error-state"><span class="eyebrow">RESULTS UNAVAILABLE</span><h1>We couldn’t open this run.</h1><p>${esc(error.message)}</p><button class="button primary" data-action="retry">Try again ↗</button></section>`;
  }
}
load();
