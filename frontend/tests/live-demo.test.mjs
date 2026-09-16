import test from 'node:test';
import assert from 'node:assert/strict';
import { createInvoiceDemoProvider, normalizeInvoiceResult, normalizeInvoiceStatus } from '../public/live-demo.mjs';

const status = { schema_version: 'local-turbo.invoice-demo-status.v1', available: true, running: false,
  device: 'Dell Latitude 7455', model: 'Qwen3-4B', task_id: 't13', reason: null };
const result = { schema_version: 'local-turbo.invoice-demo-result.v1', mode: 'live', run_id: 'invoice-1', task_id: 't13',
  model: 'Qwen3-4B', configuration: { runtime: 'GenieX', device: 'cpu', threads: 10, context: 4096 },
  file_move: { verified: true, source: 'drafts/hexagon-invoice.md', destination: 'invoices/2026/hexagon-invoice.md',
    sha256: 'a'.repeat(64), reason: null },
  exact_call: { passed: false, calls_match: false, final_state_match: true, execution_ok: true },
  timing: { loop_seconds: 20.492, loop_scope: 'model calls and tools', process_seconds: 31.5, process_scope: 'full process' },
  quality_qualified: false };

test('accepts an available fixed-task runner without inventing quality', () => {
  assert.equal(normalizeInvoiceStatus(status).available, true);
  assert.equal(normalizeInvoiceResult(result).quality_qualified, false);
  assert.equal(normalizeInvoiceResult(result).exact_call.passed, false);
});

test('verified moves require matching bytes and independent execution evidence', () => {
  for (const change of [r => r.file_move.sha256 = null, r => r.exact_call.final_state_match = false,
    r => r.exact_call.execution_ok = false, r => r.file_move.destination = 'elsewhere/invoice.md']) {
    const payload = structuredClone(result); change(payload);
    assert.throws(() => normalizeInvoiceResult(payload), /incomplete|verified move/);
  }
});

test('provider never falls back when the live endpoint fails', async () => {
  const provider = createInvoiceDemoProvider(async url => {
    if (url === '/api/demo/status') return new Response(JSON.stringify(status), { status: 200 });
    return new Response(JSON.stringify({ error: 'Latitude unavailable' }), { status: 503 });
  });
  assert.equal((await provider.status()).available, true);
  await assert.rejects(provider.execute(), /Latitude unavailable/);
});

test('provider returns the authoritative live result unchanged', async () => {
  const provider = createInvoiceDemoProvider(async (_url, options) => {
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['X-Local-Turbo-Action'], 'invoice-demo-v1');
    return new Response(JSON.stringify(result), { status: 200 });
  });
  assert.deepEqual(await provider.execute(), result);
});
