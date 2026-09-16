import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createLiveProxy, parseLiveBaseUrl, isSafeRequestId } from '../live-proxy.mjs';

function startUpstream(handler) {
  return new Promise(resolve => {
    const server = http.createServer(handler);
    server.listen(0, '127.0.0.1', () => resolve({ server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

function serveProxy(proxy) {
  return new Promise(resolve => {
    const server = http.createServer((req, res) => proxy.handle(req, res, req.url));
    server.listen(0, '127.0.0.1', () => resolve({ server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

async function request(base, method, path, { body, headers } = {}) {
  const response = await fetch(new URL(path, base), { method, body, headers, redirect: 'manual' });
  const text = await response.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* binary or empty */ }
  return { status: response.status, text, json, headers: response.headers };
}

test('parseLiveBaseUrl accepts only loopback http URLs', () => {
  assert.ok(parseLiveBaseUrl('http://127.0.0.1:8901'));
  assert.ok(parseLiveBaseUrl('http://localhost:8901'));
  assert.equal(parseLiveBaseUrl('http://example.com:8901'), null);
  assert.equal(parseLiveBaseUrl('https://127.0.0.1:8901'), null);
  assert.equal(parseLiveBaseUrl('http://0.0.0.0:8901'), null);
  assert.equal(parseLiveBaseUrl('http://user:pass@127.0.0.1:8901'), null);
  assert.equal(parseLiveBaseUrl('http://127.0.0.1:8901/api'), null);
  assert.equal(parseLiveBaseUrl('http://127.0.0.1:8901?x=1'), null);
  assert.equal(parseLiveBaseUrl('http://127.0.0.1:8901#frag'), null);
  assert.equal(parseLiveBaseUrl(''), null);
  assert.equal(parseLiveBaseUrl(undefined), null);
});

test('isSafeRequestId rejects traversal and odd characters', () => {
  assert.ok(isSafeRequestId('abc-123_4.5'));
  assert.ok(!isSafeRequestId('../admin'));
  assert.ok(!isSafeRequestId('.hidden'));
  assert.ok(!isSafeRequestId('a'.repeat(200)));
  assert.ok(!isSafeRequestId(''));
});

test('proxy relays capabilities and status snapshots unchanged', async () => {
  const upstream = await startUpstream((req, res) => {
    if (req.url === '/api/live-comparisons/capabilities') {
      res.writeHead(200); res.end(JSON.stringify({ available: true, supported_cell_ids: ['cpu-t0'] }));
    } else if (req.url === '/api/live-comparisons/abc-1') {
      res.writeHead(200); res.end(JSON.stringify({ request_id: 'abc-1', state: 'completed' }));
    } else { res.writeHead(404); res.end('{}'); }
  });
  const proxy = createLiveProxy({ baseUrl: new URL(upstream.base) });
  const node = await serveProxy(proxy);
  try {
    const caps = await request(node.base, 'GET', '/api/live-comparisons/capabilities');
    assert.equal(caps.status, 200); assert.equal(caps.json.available, true);
    const snap = await request(node.base, 'GET', '/api/live-comparisons/abc-1');
    assert.equal(snap.status, 200); assert.equal(snap.json.state, 'completed');
  } finally { node.server.close(); upstream.server.close(); }
});

test('proxy forwards valid creation bodies and rejects bad ones without forwarding', async () => {
  let forwarded = 0;
  const upstream = await startUpstream((req, res) => {
    forwarded += 1;
    let raw = '';
    req.on('data', c => { raw += c; });
    req.on('end', () => {
      const parsed = JSON.parse(raw);
      res.writeHead(202); res.end(JSON.stringify({ request_id: parsed.request_id || 'srv-1', state: 'running', events: [], result: null }));
    });
  });
  const proxy = createLiveProxy({ baseUrl: new URL(upstream.base) });
  const node = await serveProxy(proxy);
  try {
    const ok = await request(node.base, 'POST', '/api/live-comparisons', {
      body: JSON.stringify({ schema_version: 'local-turbo.comparison-request.v1', request_id: 'r1' }),
      headers: { 'content-type': 'application/json' },
    });
    assert.equal(ok.status, 202); assert.equal(ok.json.state, 'running');
    assert.equal(forwarded, 1);
    const wrongType = await request(node.base, 'POST', '/api/live-comparisons', {
      body: 'x=1', headers: { 'content-type': 'text/plain' },
    });
    assert.equal(wrongType.status, 415); assert.equal(forwarded, 1);
    const badJson = await request(node.base, 'POST', '/api/live-comparisons', {
      body: '{nope', headers: { 'content-type': 'application/json' },
    });
    assert.equal(badJson.status, 400); assert.equal(forwarded, 1);
    const array = await request(node.base, 'POST', '/api/live-comparisons', {
      body: '[]', headers: { 'content-type': 'application/json' },
    });
    assert.equal(array.status, 400); assert.equal(forwarded, 1);
    const wrongMethod = await request(node.base, 'GET', '/api/live-comparisons');
    assert.equal(wrongMethod.status, 405); assert.equal(forwarded, 1);
  } finally { node.server.close(); upstream.server.close(); }
});

test('cancel posts a JSON body and requires a safe id', async () => {
  const upstream = await startUpstream((req, res) => {
    let raw = '';
    req.on('data', c => { raw += c; });
    req.on('end', () => {
      // Cancel always forwards a canonical empty JSON object upstream.
      assert.equal(raw, '{}');
      res.writeHead(200); res.end(JSON.stringify({ request_id: 'ok-1', state: 'cancelled' }));
    });
  });
  const proxy = createLiveProxy({ baseUrl: new URL(upstream.base) });
  const node = await serveProxy(proxy);
  try {
    const ok = await request(node.base, 'POST', '/api/live-comparisons/ok-1/cancel', {
      body: JSON.stringify({ nested: false }), headers: { 'content-type': 'application/json' },
    });
    assert.equal(ok.status, 200); assert.equal(ok.json.state, 'cancelled');
    const traversal = await request(node.base, 'POST', '/api/live-comparisons/..%2Fadmin/cancel', {
      body: '{}', headers: { 'content-type': 'application/json' },
    });
    assert.equal(traversal.status, 404);
  } finally { node.server.close(); upstream.server.close(); }
});

test('upstream failures and malformed JSON map to bounded statuses without leaking the address', async () => {
  const upstream = await startUpstream((req, res) => {
    res.writeHead(500, { 'content-type': 'text/html' }); res.end('<html>secret-backend-error</html>');
  });
  const proxy = createLiveProxy({ baseUrl: new URL(upstream.base), upstreamTimeoutMs: 250 });
  const node = await serveProxy(proxy);
  try {
    const caps = await request(node.base, 'GET', '/api/live-comparisons/capabilities');
    assert.equal(caps.status, 502);
    assert.match(caps.json.error, /non-JSON/);
    assert.ok(!caps.text.includes('127.0.0.1'));
    assert.ok(!caps.text.includes(String(upstream.server.address().port)));
  } finally { node.server.close(); upstream.server.close(); }
});

test('unreachable upstream yields 503 with the generic message', async () => {
  const { server } = await startUpstream(() => {});
  const port = server.address().port;
  server.close();
  await new Promise(resolve => server.closeAllConnections?.(() => resolve()) ?? resolve());
  const proxy = createLiveProxy({ baseUrl: new URL(`http://127.0.0.1:${port}`), upstreamTimeoutMs: 300 });
  const node = await serveProxy(proxy);
  try {
    const caps = await request(node.base, 'GET', '/api/live-comparisons/capabilities');
    assert.equal(caps.status, 503);
    assert.match(caps.json.error, /unavailable/i);
    assert.ok(!caps.text.includes(String(port)));
  } finally { node.server.close(); }
});

test('slow upstream aborts into a 504', async () => {
  const upstream = await startUpstream((req, res) => { setTimeout(() => { res.writeHead(200); res.end('{}'); }, 500); });
  const proxy = createLiveProxy({ baseUrl: new URL(upstream.base), upstreamTimeoutMs: 80 });
  const node = await serveProxy(proxy);
  try {
    const caps = await request(node.base, 'GET', '/api/live-comparisons/capabilities');
    assert.equal(caps.status, 504);
  } finally { node.server.close(); upstream.server.close(); }
});
