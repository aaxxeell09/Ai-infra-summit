import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const resultsRoot = path.resolve(here, '../benchmarks/results/screen-01');
const assets = new Map([
  ['/', ['index.html', 'text/html']],
  ['/styles.css', ['styles.css', 'text/css']],
  ['/brand-manrope.woff2', ['brand-manrope.woff2', 'font/woff2']],
  ['/app.mjs', ['app.mjs', 'text/javascript']],
  ['/data.mjs', ['data.mjs', 'text/javascript']],
  ['/latest.mjs', ['latest.mjs', 'text/javascript']],
  ['/live-demo.mjs', ['live-demo.mjs', 'text/javascript']],
  ['/demo.mjs', ['demo.mjs', 'text/javascript']],
  ['/comparison.mjs', ['comparison.mjs', 'text/javascript']],
  ['/favicon.svg', ['favicon.svg', 'image/svg+xml']],
]);

const demoConfig = process.env.LOCAL_TURBO_DEMO_CONFIG?.trim() || '';
const demoConfigPath = demoConfig ? (path.isAbsolute(demoConfig) ? demoConfig : path.resolve(repoRoot, demoConfig)) : '';
const demoPython = process.env.LOCAL_TURBO_DEMO_PYTHON?.trim() || (process.platform === 'win32' ? 'python' : 'python3');
let demoRunning = false;

const publicDemoStatus = (available, reason = null) => ({
  schema_version: 'local-turbo.invoice-demo-status.v1',
  available,
  running: demoRunning,
  device: 'Dell Latitude 7455',
  model: 'Qwen3-4B-Instruct-2507 Q4_0',
  task_id: 't13',
  reason,
});

async function demoStatus() {
  if (!demoConfig) return publicDemoStatus(false, 'The Latitude runner is not configured on this server.');
  try {
    const config = JSON.parse(await readFile(demoConfigPath, 'utf8'));
    const ready = typeof config?.sdk_dir === 'string' && typeof config?.model_path === 'string';
    return publicDemoStatus(ready, ready ? null : 'The native model configuration is incomplete.');
  } catch {
    return publicDemoStatus(false, 'The native model configuration is unavailable.');
  }
}

function runPresenter(outputPath) {
  return new Promise((resolve, reject) => {
    const args = ['-X', 'utf8', path.join(repoRoot, 'scripts/demo_invoice_mcp.py'), '--enable-candidate', '--config', demoConfigPath, '--output', outputPath];
    const child = spawn(demoPython, args, { cwd: repoRoot, shell: false, windowsHide: true });
    let stdout = '';
    let stderr = '';
    const limit = 2 * 1024 * 1024;
    const timer = setTimeout(() => {
      child.kill();
      const error = new Error('The live runner exceeded its bounded execution window.');
      error.publicMessage = 'The live runner exceeded its bounded execution window. Its device state must be checked before retrying.';
      reject(error);
    }, 260_000);
    child.stdout.on('data', chunk => { if (stdout.length < limit) stdout += chunk; });
    child.stderr.on('data', chunk => { if (stderr.length < limit) stderr += chunk; });
    child.on('error', cause => {
      clearTimeout(timer);
      const error = new Error(`Could not start the native runner: ${cause.message}`);
      error.publicMessage = 'The native runner could not start on the Latitude.';
      reject(error);
    });
    child.on('close', code => {
      clearTimeout(timer);
      let summary;
      try { summary = JSON.parse(stdout); }
      catch {
        const error = new Error(`The live runner returned an unreadable result${stderr ? `: ${stderr.slice(-240)}` : '.'}`);
        error.publicMessage = 'The native runner returned no verifiable result. Inspect its preserved local artifacts.';
        reject(error); return;
      }
      if (code !== 0 || summary?.ok !== true) {
        const error = new Error(summary?.errors?.join(' ') || `The live runner exited with code ${code}.`);
        error.publicMessage = 'The native runner failed before a verifiable result was available. Inspect its preserved local artifacts.';
        reject(error); return;
      }
      resolve(summary);
    });
  });
}

function publicDemoResult(summary, runId) {
  const move = summary.file_move ?? {};
  const verdict = summary.existing_demo_verification ?? {};
  const config = summary.native_config ?? {};
  return {
    schema_version: 'local-turbo.invoice-demo-result.v1',
    mode: 'live',
    run_id: runId,
    task_id: 't13',
    model: 'Qwen3-4B-Instruct-2507 Q4_0',
    configuration: {
      runtime: 'GenieX 0.6.1 · llama.cpp',
      device: config.device ?? 'cpu',
      threads: Number.isInteger(config.threads) ? config.threads : null,
      context: Number.isInteger(config.context) ? config.context : null,
    },
    file_move: {
      verified: move.verified === true,
      source: move.expected_source ?? 'drafts/hexagon-invoice.md',
      destination: move.expected_destination ?? 'invoices/2026/hexagon-invoice.md',
      sha256: move.sha256 ?? null,
      reason: move.reason ?? null,
    },
    exact_call: {
      passed: verdict.passed === true,
      calls_match: verdict.calls_match === true,
      final_state_match: verdict.final_state_match === true,
      execution_ok: verdict.execution_ok === true,
    },
    timing: {
      loop_seconds: summary.timing?.loop?.elapsed_s ?? null,
      loop_scope: summary.timing?.loop?.timing_scope ?? null,
      process_seconds: summary.mcp_process_elapsed_s ?? null,
      process_scope: summary.mcp_process_timing_scope ?? null,
    },
    quality_qualified: false,
  };
}

async function runInvoiceDemo() {
  const status = await demoStatus();
  if (!status.available) {
    const error = new Error(status.reason);
    error.publicMessage = status.reason;
    throw error;
  }
  if (demoRunning) {
    const error = new Error('A live device run is already in progress.');
    error.statusCode = 409;
    error.publicMessage = error.message;
    throw error;
  }
  demoRunning = true;
  const runId = `invoice-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`;
  const outputPath = path.join(repoRoot, 'local', 'ui-demo-runs', runId);
  try { return publicDemoResult(await runPresenter(outputPath), runId); }
  finally { demoRunning = false; }
}

const readJson = async relativePath => JSON.parse(await readFile(path.join(repoRoot, relativePath), 'utf8'));

async function latestResults() {
  const sources = {
    qairtControl: 'eval/results/candidate_qairt-stop-control-full-v1.json',
    qairtOptimized: 'eval/results/candidate_qairt-stop-candidate-full-v1.json',
    qwen4b: 'eval/results/candidate_qwen4b-cpu10-v2.json',
    qwen8b: 'eval/results/qwen8b-full-1200/kpi.json',
  };
  const [control, optimized, qwen4b, qwen8b] = await Promise.all(Object.values(sources).map(readJson));
  const candidate = (result, label, size, runtime) => ({
    label, size, runtime,
    correct: result.metrics.task_success,
    total: result.metrics.total_prompts,
    accuracy_pct: result.metrics.task_accuracy,
    average_inference_ms: result.metrics.avg_latency_ms,
    median_inference_ms: result.metrics.median_latency_ms,
    invalid_rate: result.metrics.invalid_output_rate,
    quality_status: result.comparison?.status ?? 'NOT_COMPARABLE',
  });
  return {
    schema_version: 'local-turbo.latest-results.v1',
    device: 'Dell Latitude 7455 · Snapdragon X Elite X1E-80-100',
    qairt: {
      model: optimized.model_label,
      runtime: optimized.inference_backend.runtime,
      requested_device: optimized.inference_backend.requested_device,
      resolved_device: optimized.inference_backend.resolved_device,
      dispatch_verified: optimized.inference_backend.dispatch_verified,
      control: candidate(control, 'Standard generation', '0.6B', 'QAIRT'),
      optimized: candidate(optimized, 'Stop after tool call', '0.6B', 'QAIRT'),
    },
    candidates: [
      candidate(optimized, 'Qwen3 0.6B', '0.6B', 'QAIRT · NPU'),
      candidate(qwen4b, 'Qwen3 4B', '4B', 'llama.cpp · CPU'),
      {
        label: 'Qwen3 8B', size: '8B', runtime: 'llama.cpp · CPU',
        correct: qwen8b.correct_tasks, total: qwen8b.total_tasks,
        accuracy_pct: qwen8b.success_rate_pct,
        average_inference_ms: qwen8b.inference_latency_ms.mean,
        median_inference_ms: qwen8b.inference_latency_ms.median,
        invalid_rate: qwen8b.invalid_rate,
        quality_status: 'NOT_QUALIFIED',
      },
    ],
    quality_gate_passed: false,
    sources,
  };
}

async function snapshot() {
  const manifestBytes = await readFile(path.join(resultsRoot, 'sweep.json'));
  const manifest = JSON.parse(manifestBytes);
  const reports = {};
  for (const cell of manifest.cells) {
    if (!/^[a-z0-9-]+$/i.test(cell.id)) throw new Error('Invalid recorded cell ID');
    try {
      reports[cell.id] = JSON.parse(await readFile(path.join(resultsRoot, `${cell.id}.json`), 'utf8'));
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      reports[cell.id] = null;
    }
  }
  return {
    schema_version: 'local-turbo.recorded.v1', mode: 'recorded',
    manifest_sha256: createHash('sha256').update(manifestBytes).digest('hex'),
    source: 'benchmarks/results/screen-01',
    device: { name: 'Dell Latitude 7455', processor: 'Snapdragon X Elite',
      chipset: 'X1E-80-100', ram_gb: 32, gpu: 'Adreno X1-85', platform: 'Windows ARM64' },
    runtime: 'GenieX 0.6.1', manifest, reports,
  };
}

const server = http.createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'");
  let url;
  try { url = new URL(req.url, 'http://localhost'); }
  catch { res.writeHead(400); res.end('Invalid request URL'); return; }
  const isDemoPost = req.method === 'POST' && url.pathname === '/api/demo/invoice';
  if (!['GET', 'HEAD'].includes(req.method) && !isDemoPost) {
    res.writeHead(405, { Allow: 'GET, HEAD, POST' }); res.end(); return;
  }
  try {
    let body;
    let type;
    if (isDemoPost) {
      if (req.headers['x-local-turbo-action'] !== 'invoice-demo-v1') {
        res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'Missing local demo action proof.' }));
        return;
      }
      body = JSON.stringify(await runInvoiceDemo()); type = 'application/json';
    } else if (url.pathname === '/api/demo/status') {
      body = JSON.stringify(await demoStatus()); type = 'application/json';
    } else if (url.pathname === '/api/recorded') {
      body = JSON.stringify(await snapshot()); type = 'application/json';
    } else if (url.pathname === '/api/latest-results') {
      body = JSON.stringify(await latestResults()); type = 'application/json';
    } else if (url.pathname === '/api/health') {
      const status = await demoStatus();
      body = JSON.stringify({ ok: true, mode: status.available ? 'live-ready' : 'recorded', live_backend: status.available }); type = 'application/json';
    } else if (assets.has(url.pathname)) {
      const [filename, mime] = assets.get(url.pathname);
      body = await readFile(path.join(here, 'public', filename)); type = mime;
    } else {
      res.writeHead(404); res.end('Not found'); return;
    }
    res.writeHead(200, { 'Content-Type': `${type}; charset=utf-8` });
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch (error) {
    console.error(error.message);
    const statusCode = error.statusCode ?? 503;
    res.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: isDemoPost ? (error.publicMessage || 'The Latitude runner could not complete the task.') : 'Recorded results could not be loaded. Check benchmarks/results/screen-01.' }));
  }
});
const port = Number(process.env.PORT || 4173);
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Local Turbo ready at http://127.0.0.1:${port}`));
