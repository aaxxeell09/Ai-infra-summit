import { createRecordedProvider } from './data.mjs';
import { createConfirmedProvider, exportConfirmedProfile } from './confirmed.mjs';
import { PROMPTS, createConfirmedComparisonRequest, comparisonLanes, createPreviewComparisonProvider } from './comparison.mjs';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const number = (value, digits = 2) => value === null || value === undefined ? 'Unavailable' : value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const arrow = '<span aria-hidden="true">↗</span>';
const provider = createRecordedProvider();
const confirmedProvider = createConfirmedProvider();
// Replace this provider with a device comparison provider at integration.
const taskProvider = createPreviewComparisonProvider();
const state = { snapshot: null, confirmed: null, page: 'device', scenario: 'quick', comparison: 'speed', demo: 'idle', lanes: {}, result: null, error: null };
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
  const s = state.snapshot; const c = state.confirmed;
  const fast = c.fast.metrics; const efficient = c.efficient.metrics;
  return `<section class="screen confirmed-screen">
    <div class="confirmed-intro"><div><span class="eyebrow">MEASURED ON THE LATITUDE · BATTERY POWER</span>
      <h1>Automatic chose NPU.<br><em>Speed chose CPU.</em></h1>
      <p>Same Qwen model, same weights and workload. Five alternating trial pairs reveal two useful modes, depending on what matters to you.</p></div>
      <span class="confirmed-model">${esc(s.model.replace(/\.gguf$/, ''))}<small>${c.scope.prompt_tokens} input · ${c.scope.generated_tokens} output tokens</small></span>
    </div>
    <div class="confirmed-statline" aria-label="Measured trade-off">
      <div><span>FASTER ANSWER GENERATION</span><strong>${number(c.decodeRatio)}×</strong><p>CPU versus automatic NPU · native decode rate</p></div>
      <div><span>BETTER FULL-TRIAL EFFICIENCY</span><strong>${number(c.energyRatio)}×</strong><p>NPU versus CPU · generated tokens per SYS joule</p></div>
    </div>
    <div class="confirmed-grid">
      <article class="mode-card mode-fast"><div class="mode-card-top"><span class="mode-index">01 / FAST</span><span class="mode-status">Confirmed · CPU</span></div>
        <h2>When response speed matters.</h2><div class="mode-primary-number">${number(fast.decode_tps)}<span>tok/s</span></div>
        <p class="mode-number-label">Aggregate native answer generation · 10 threads</p>
        <dl class="mode-measures"><div><dt>First token</dt><dd>${number(fast.median_ttft_ms, 0)} ms</dd></div><div><dt>Full-trial efficiency</dt><dd>${number(fast.tokens_per_joule)} tokens/J</dd></div><div><dt>Process peak memory</dt><dd>${number(fast.median_peak_mib / 1024)} GiB</dd></div></dl>
        <button class="mode-export" data-profile="fast">Export fast profile <span aria-hidden="true">↗</span></button>
      </article>
      <article class="mode-card mode-efficient"><div class="mode-card-top"><span class="mode-index">02 / EFFICIENT</span><span class="mode-status">Confirmed · NPU HTP0</span></div>
        <h2>When energy matters.</h2><div class="mode-primary-number">${number(efficient.tokens_per_joule)}<span>tokens/J</span></div>
        <p class="mode-number-label">Generated output / full-trial SYS energy · automatic placement</p>
        <dl class="mode-measures"><div><dt>Answer generation</dt><dd>${number(efficient.decode_tps)} tok/s</dd></div><div><dt>First token</dt><dd>${number(efficient.median_ttft_ms, 0)} ms</dd></div><div><dt>Process peak memory</dt><dd>${number(efficient.median_peak_mib / 1024)} GiB</dd></div></dl>
        <button class="mode-export" data-profile="efficient">Export efficient profile <span aria-hidden="true">↗</span></button>
      </article>
    </div>
    <div class="qairt-study"><div><span class="eyebrow">NEXT NPU STUDY</span><h2>Qualcomm AI Engine Direct <span>· qairt</span></h2><p>Compiled NPU bundles use a different runtime and model format. Its performance and task quality need separate device measurements.</p></div><span class="study-status">Awaiting measurements</span></div>
    <div class="confirmed-bottom"><p>Confirmed engine performance for this fixed model and workload. Quality-calibrated task recommendations are still pending. NPU operations were verified in a separate diagnostic run.</p><button class="button primary" data-action="try">Open answer preview ${arrow}</button></div>
  </section>`;
}

function demoScreen() {
  const busy = state.demo === 'running';
  const scenario = PROMPTS.find(item => item.id === state.scenario);
  let request; let setupError;
  try { request = createConfirmedComparisonRequest(state.snapshot, state.confirmed, state.comparison, state.scenario, 'preview-layout'); }
  catch (error) { setupError = error.message; }
  const descriptions = request ? comparisonLanes(request) : null;
  const lanes = ['default', 'turbo'].map(key => {
    const lane = state.lanes[key] || { status: 'idle', answer: '' };
    const meta = descriptions?.[key];
    const status = lane.status === 'running' ? 'Writing…' : lane.status === 'completed' ? 'Done' : busy ? 'Queued' : '';
    const identity = !meta ? 'Configuration unavailable' : state.comparison === 'speed'
      ? `${meta.model} · ${meta.configuration}`
      : key === 'default' ? `${meta.model} · fixed` : `${meta.model} · illustrative`;
    return `<article class="response-column ${key === 'turbo' ? 'response-turbo' : ''}" aria-label="${key === 'turbo' ? 'Local Turbo answer' : 'Automatic setup answer'}">
      <header class="response-header"><div class="response-title"><h2>${key === 'turbo' ? 'Local Turbo' : 'Automatic setup'}</h2><span class="response-status ${lane.status === 'running' ? 'active' : ''}">${status}</span></div><p>${esc(identity)}</p></header>
      <div class="response-text ${lane.status === 'running' ? 'writing' : ''}" data-answer="${key}">${esc(lane.answer)}</div>
      <div class="response-timing"><span>Animation time</span><strong data-clock="${key}">${clockText(key)}</strong></div>
    </article>`;
  }).join('');
  return `<section class="screen comparison-demo">
    <div class="demo-heading"><div><span class="eyebrow">SCRIPTED INTERFACE PREVIEW</span><h1>See the comparison flow.</h1></div><div class="comparison-switch" role="group" aria-label="Comparison type"><button data-comparison="speed" aria-pressed="${state.comparison === 'speed'}" ${busy ? 'disabled' : ''}>Speed</button><button data-comparison="routing" aria-pressed="${state.comparison === 'routing'}" ${busy ? 'disabled' : ''}>Model routing</button></div></div>
    <div class="comparison-workspace">
      <div class="prompt-composer"><div class="prompt-controls"><span class="prompt-label">Prompt</span><details class="prompt-picker" ${busy ? 'inert' : ''}><summary aria-label="Example prompt: ${esc(scenario.label)}">${esc(scenario.label)}<span aria-hidden="true">⌄</span></summary><div class="prompt-options" role="group" aria-label="Example prompts">${PROMPTS.map(item => `<button data-scenario="${item.id}" aria-pressed="${state.scenario === item.id}">${item.label}<span aria-hidden="true">${state.scenario === item.id ? '✓' : ''}</span></button>`).join('')}</div></details></div>
        <p class="prompt-copy">${esc(scenario.prompt)}</p>
        <button class="button primary run-comparison" data-action="${busy ? 'reset-demo' : 'run-demo'}" ${setupError ? 'disabled' : ''}>${busy ? '<span aria-hidden="true">■</span> Stop' : state.result ? '↻ Replay' : 'Run preview <span aria-hidden="true">→</span>'}</button>
      </div>
      <div class="response-grid">${lanes}</div>
    </div>
    ${state.error || setupError ? `<p class="comparison-error" role="alert">${esc(state.error || setupError)}</p>` : ''}
    <div class="demo-secondary"><details class="comparison-info"><summary>How this comparison works</summary><div><p>${state.comparison === 'speed' ? 'The labels use the confirmed automatic NPU and fast CPU profiles. The answers below are scripted and use neither configuration.' : 'Routing illustrates possible model roles. Actual model choices need calibrated speed and quality profiles.'}</p><p>Clocks measure browser animation only. Live task time and answer quality are unavailable here.</p></div></details></div>
    <span class="sr-only" role="status" aria-live="polite">${state.result ? 'Comparison preview complete. Both example answers are available.' : busy ? 'Comparison running. Answers appear one at a time.' : ''}</span>
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
  $('#mode-tag').innerHTML = `<span class="mode-dot"></span>${state.page === 'demo' ? taskProvider.mode === 'simulated' ? 'Preview · scripted answers' : 'Device task' : state.page === 'calibration' ? 'Confirmed device results' : 'Recorded device results'}`;
  $('#main').innerHTML = state.page === 'device' ? deviceScreen() : state.page === 'calibration' ? calibrationScreen() : demoScreen();
  if (keepExplanationOpen && $('#main .comparison-info')) $('#main .comparison-info').open = true;
  if (!focus && keepRunFocus) $('#main .run-comparison')?.focus({ preventScroll: true });
  if (!focus) $('#main .screen')?.classList.add('static-screen');
  if (focus) { $('#main').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }); }
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
  clearInterval(clockTick); laneClocks = {};
  demoGeneration++; state.demo = 'idle'; state.lanes = {};
  state.result = null; state.error = null;
}

async function runDemo() {
  if (['preparing', 'running'].includes(state.demo)) return;
  resetDemo(); const generation = demoGeneration;
  let request;
  try { request = createConfirmedComparisonRequest(state.snapshot, state.confirmed, state.comparison, state.scenario, crypto.randomUUID()); }
  catch (error) { state.error = error.message; render(); return; }
  const controller = new AbortController(); taskAbort = controller;
  const timer = setTimeout(() => controller.abort(new Error('The device did not finish within two minutes. Its execution status is unknown; check the device before retrying.')), 120000);
  let rejectOnAbort;
  const interrupted = new Promise((_, reject) => { rejectOnAbort = () => reject(controller.signal.reason); controller.signal.addEventListener('abort', rejectOnAbort, { once: true }); });
  state.demo = 'running'; render();
  clockTick = setInterval(updateClocks, 100);
  try {
    const result = await Promise.race([interrupted, taskProvider.execute(request, { signal: controller.signal, onEvent(event) {
      if (generation !== demoGeneration) return;
      if (event.type === 'text') {
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
    } })]);
    if (generation !== demoGeneration) return;
    state.result = result; state.lanes = result.lanes; state.demo = 'complete'; render();
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
  if (!state.snapshot || !state.confirmed) return;
  const s = state.snapshot; const c = state.confirmed;
  $('#evidence-content').innerHTML = `<div class="evidence-summary"><span class="mode-tag">Confirmed on the Latitude</span><p>CPU and automatic NPU were measured on the same model and fixed workload, in five alternating battery-powered pairs. These results establish engine performance, not task correctness.</p></div>
    <dl class="evidence-list"><div><dt>Machine</dt><dd>${esc(s.device.name)}</dd></div><div><dt>Confirmed source</dt><dd>${esc(c.source)} · ${esc(c.scope.evidence)}</dd></div><div><dt>Model SHA-256</dt><dd class="mono hash">${esc(c.modelHash)}</dd></div><div><dt>Recommendation SHA-256</dt><dd class="mono hash">${esc(c.recommendationHash)}</dd></div><div><dt>Trial manifest SHA-256</dt><dd class="mono hash">${esc(c.manifestHash)}</dd></div><div><dt>Workload</dt><dd>${c.scope.prompt_tokens} input · ${c.scope.generated_tokens} output · ${c.scope.context} context · cold KV · battery</dd></div><div><dt>Native decode</dt><dd>Generated tokens divided by native decode time across all clean repetitions. CPU ${number(c.fast.metrics.decode_tps)}; automatic NPU ${number(c.efficient.metrics.decode_tps)} tok/s.</dd></div><div><dt>Energy scope</dt><dd>${esc(c.energyChannel)} counter; generated output divided by full-trial joules including loading, prefill and decode. Not decode-only power or wall-socket energy.</dd></div><div><dt>NPU dispatch</dt><dd>HTP0 operations were captured in a separate diagnostic run (${esc(c.dispatchEvidence)}). Profiling timings are excluded from the clean comparison.</dd></div><div><dt>Quality</dt><dd>Not calibrated. No task-quality claim follows from these throughput results.</dd></div></dl>
    <details><summary>Inspect confirmed recommendation</summary><pre>${esc(JSON.stringify(c.raw.recommendation, null, 2))}</pre></details>
    <details><summary>Initial screening, kept for context</summary><p>Earlier three-repetition screening is not the confirmed CPU-versus-auto baseline. Source: ${esc(s.source)}.</p><pre>${esc(JSON.stringify(s.manifest, null, 2))}</pre></details>
    <button class="button ghost" data-action="download-evidence">Download confirmed evidence ↓</button>`;
  $('#evidence-dialog').showModal();
}

document.addEventListener('click', event => {
  if (event.target.closest('.skip')) { event.preventDefault(); $('#main').focus(); return; }
  const picker = $('.prompt-picker');
  if (picker && !picker.contains(event.target)) picker.open = false;
  const target = event.target.closest('button'); if (!target) return;
  if (target.dataset.profile) {
    try { download(exportConfirmedProfile(state.confirmed, target.dataset.profile), `local-turbo-${target.dataset.profile}-profile.json`); notify('Measured profile exported. Task quality is not yet calibrated.'); }
    catch (error) { notify(error.message); }
    return;
  }
  if (target.dataset.comparison) { state.comparison = target.dataset.comparison; resetDemo(); render(); document.querySelector(`[data-comparison="${state.comparison}"]`)?.focus(); return; }
  if (target.dataset.scenario) { state.scenario = target.dataset.scenario; resetDemo(); render(); $('.prompt-picker summary')?.focus({ preventScroll: true }); return; }
  switch (target.dataset.action) {
    case 'explore': location.hash = 'calibration'; break;
    case 'try': resetDemo(); location.hash = 'demo'; break;
    case 'back': location.hash = 'calibration'; break;
    case 'evidence': showEvidence(); break;
    case 'download-evidence': download(state.confirmed.raw, 'local-turbo-confirmed-evidence.json'); break;
    case 'download-task': if (state.result?.mode === 'live') download(state.result, `local-turbo-task-${state.result.request_id}.json`); break;
    case 'run-demo': runDemo(); break;
    case 'reset-demo': resetDemo(); render(); break;
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
window.addEventListener('hashchange', navigate);

async function load() {
  $('#main').innerHTML = '<div class="loading-state"><span class="spinner"></span><p>Opening device results…</p></div>';
  try {
    [state.snapshot, state.confirmed] = await Promise.all([
      provider.load({ signal: AbortSignal.timeout(10000) }),
      confirmedProvider.load({ signal: AbortSignal.timeout(10000) }),
    ]);
    if (state.snapshot.modelHash !== state.confirmed.modelHash) throw new Error('The screening and confirmation use different model weights.');
    resetDemo();
    navigate();
  } catch (error) {
    $('#main').innerHTML = `<section class="error-state"><span class="eyebrow">RESULTS UNAVAILABLE</span><h1>We couldn’t open this run.</h1><p>${esc(error.message)}</p><button class="button primary" data-action="retry">Try again ↗</button></section>`;
  }
}
load();
