import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash } from 'node:crypto';

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
  ['/demo.mjs', ['demo.mjs', 'text/javascript']],
  ['/comparison.mjs', ['comparison.mjs', 'text/javascript']],
  ['/favicon.svg', ['favicon.svg', 'image/svg+xml']],
]);

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
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }); res.end(); return;
  }
  let url;
  try { url = new URL(req.url, 'http://localhost'); }
  catch { res.writeHead(400); res.end('Invalid request URL'); return; }
  try {
    let body;
    let type;
    if (url.pathname === '/api/recorded') {
      body = JSON.stringify(await snapshot()); type = 'application/json';
    } else if (url.pathname === '/api/latest-results') {
      body = JSON.stringify(await latestResults()); type = 'application/json';
    } else if (url.pathname === '/api/health') {
      body = JSON.stringify({ ok: true, mode: 'recorded', live_backend: false }); type = 'application/json';
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
    res.writeHead(503, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Recorded results could not be loaded. Check benchmarks/results/screen-01.' }));
  }
});
const port = Number(process.env.PORT || 4173);
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Local Turbo ready at http://127.0.0.1:${port}`));
