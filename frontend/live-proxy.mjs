// Opt-in same-origin proxy for the owner's native live comparison backend.
// The upstream address lives only in this process (LOCAL_TURBO_LIVE_URL);
// browser responses never include it, credentials, or redirect targets.

const MAX_REQUEST_BODY = 64 * 1024;
const MAX_UPSTREAM_BODY = 1024 * 1024;
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

export function parseLiveBaseUrl(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return null;
  let url;
  try { url = new URL(raw.trim()); }
  catch { return null; }
  if (url.protocol !== 'http:' || !LOOPBACK_HOSTS.has(url.hostname)) return null;
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') return null;
  return url;
}

export function isSafeRequestId(id) {
  return typeof id === 'string' && !id.includes('..') &&
    /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id);
}

function httpError(message, statusCode) {
  return Object.assign(new Error(message), { statusCode });
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', chunk => {
      size += chunk.length;
      if (size > limit) {
        reject(httpError('Request body too large.', 413));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', error => reject(error));
  });
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload));
}

function allow(res, ...methods) {
  res.writeHead(405, { Allow: methods.join(', ') });
  res.end();
}

export function createLiveProxy({
  baseUrl,
  fetchImpl = fetch,
  upstreamTimeoutMs = Number(process.env.LOCAL_TURBO_LIVE_TIMEOUT_MS) || 10000,
} = {}) {
  async function forward(pathname, { method = 'GET', body, contentType } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), upstreamTimeoutMs);
    try {
      const response = await fetchImpl(new URL(pathname, baseUrl), {
        method, body, redirect: 'error', signal: controller.signal,
        headers: body === undefined ? {} : { 'content-type': contentType },
      });
      const text = await response.text();
      if (text.length > MAX_UPSTREAM_BODY) throw httpError('Live backend response too large.', 502);
      return { status: response.status, text };
    } catch (error) {
      if (error.name === 'AbortError') throw httpError('Live backend timed out.', 504);
      if (error.statusCode) throw error;
      throw httpError('Live backend unavailable.', 503);
    } finally { clearTimeout(timer); }
  }

  async function relay(res, pathname, options = {}) {
    const { status, text } = await forward(pathname, options);
    try { JSON.parse(text); }
    catch { throw httpError('Live backend returned a non-JSON response.', 502); }
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(text);
  }

  return {
    mode: 'live',
    configured: Boolean(baseUrl),
    async handle(req, res, pathname) {
      const segments = pathname.split('/').filter(Boolean);
      // segments: ['api', 'live-comparisons']            -> creation (POST)
      //           ['api', 'live-comparisons', 'x']       -> capabilities or snapshot (GET)
      //           ['api', 'live-comparisons', 'x', 'y']  -> cancel (POST) only
      try {
        if (segments.length === 2) {
          if (req.method !== 'POST') { allow(res, 'POST'); return; }
          const contentType = String(req.headers['content-type'] || '');
          if (!contentType.startsWith('application/json')) {
            sendJson(res, 415, { error: 'Content-Type must be application/json.' });
            return;
          }
          const body = (await readBody(req, MAX_REQUEST_BODY)).toString('utf8');
          let parsed;
          try { parsed = JSON.parse(body); }
          catch { throw httpError('Request body must be valid JSON.', 400); }
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw httpError('Request body must be a JSON object.', 400);
          }
          await relay(res, pathname, { method: 'POST', body, contentType });
          return;
        }
        if (segments.length === 3 && segments[2] === 'capabilities') {
          if (req.method !== 'GET' && req.method !== 'HEAD') { allow(res, 'GET'); return; }
          await relay(res, pathname);
          return;
        }
        if (segments.length === 3) {
          const id = decodeURIComponent(segments[2]);
          if (!isSafeRequestId(id)) { sendJson(res, 404, { error: 'Unknown comparison request.' }); return; }
          if (req.method !== 'GET' && req.method !== 'HEAD') { allow(res, 'GET'); return; }
          await relay(res, pathname);
          return;
        }
        if (segments.length === 4) {
          const id = decodeURIComponent(segments[2]);
          if (!isSafeRequestId(id)) { sendJson(res, 404, { error: 'Unknown comparison request.' }); return; }
          if (segments[3] === 'cancel') {
            if (req.method !== 'POST') { allow(res, 'POST'); return; }
            await readBody(req, MAX_REQUEST_BODY);
            await relay(res, pathname, { method: 'POST', body: '{}', contentType: 'application/json' });
            return;
          }
        }
        sendJson(res, 404, { error: 'Unknown live comparison endpoint.' });
      } catch (error) {
        sendJson(res, error.statusCode || 502, { error: error.message || 'Live comparison proxy failed.' });
      }
    },
  };
}
