/* Local Inspection — frontend console. Vanilla JS, no network beyond the local API. */
(function () {
  'use strict';

  var POLL_MS = 1000;
  var FRAME_POST_MS = 2000;
  var FETCH_TIMEOUT_MS = 3000;
  var MAX_DIM = 1280;
  var JPEG_QUALITY = 0.85;
  var STALE_POLLS = 2;

  var el = {
    conn: document.getElementById('conn-pill'),
    video: document.getElementById('video'),
    videoPlaceholder: document.getElementById('video-placeholder'),
    btnCamera: document.getElementById('btn-camera'),
    btnSnapshot: document.getElementById('btn-snapshot'),
    fileInput: document.getElementById('file-input'),
    frameMeta: document.getElementById('frame-meta'),
    preview: document.getElementById('preview'),
    previewWrap: document.getElementById('preview-wrap'),
    previewEmpty: document.getElementById('preview-empty'),
    badge: document.getElementById('status-badge'),
    explanation: document.getElementById('explanation'),
    latency: document.getElementById('latency'),
    requestId: document.getElementById('request-id'),
    instructionVersion: document.getElementById('instruction-version'),
    boardState: document.getElementById('board-state'),
    runtimeState: document.getElementById('runtime-state'),
    backendEvidence: document.getElementById('backend-evidence'),
    counters: document.getElementById('counters'),
    btnInspect: document.getElementById('btn-inspect'),
    btnClear: document.getElementById('btn-clear'),
    instruction: document.getElementById('instruction'),
    instructionPending: document.getElementById('instruction-pending'),
    btnApply: document.getElementById('btn-apply'),
    presetNote: document.getElementById('preset-note'),
    presetList: document.getElementById('preset-list'),
    events: document.getElementById('events'),
    errorBanner: document.getElementById('error-banner')
  };

  var camera = { stream: null, enabled: false, timer: null };
  var pendingFrame = null; // { dataUrl, source: 'camera' | 'upload' }
  var inspectBusy = false;
  var serverBusy = false; // set on 409 until the server reports busy=false
  var state = null;
  var pollFailures = 0;
  var connected = false;
  var expiryTimer = null;
  /* Serialized /api/frame traffic: one POST in flight at a time, so a queued
     clear always lands after any in-flight frame and cannot be undone by it. */
  var frameChain = Promise.resolve();
  var frameQueued = false; // a frame post is queued or in flight
  var cameraGen = 0; // bumped on stop; queued camera frames from older generations are dropped

  function setText(node, value) {
    node.textContent = (value === null || value === undefined || value === '') ? '\u2014' : String(value);
  }

  function showError(message) {
    el.errorBanner.textContent = message;
    el.errorBanner.hidden = false;
  }

  function clearError() {
    el.errorBanner.hidden = true;
    el.errorBanner.textContent = '';
  }

  function fetchJSON(path, options) {
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, FETCH_TIMEOUT_MS);
    var opts = options || {};
    opts.signal = ctrl.signal;
    return fetch(path, opts).then(function (res) {
      clearTimeout(timer);
      return res.text().then(function (bodyText) {
        var body = null;
        try { body = bodyText ? JSON.parse(bodyText) : null; } catch (e) { body = null; }
        return { ok: res.ok, status: res.status, body: body };
      });
    }, function (err) {
      clearTimeout(timer);
      throw err;
    });
  }

  function postJSON(path, payload) {
    return fetchJSON(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {})
    });
  }

  /* ---------- capture ---------- */

  function scaleToDataURL(sourceEl) {
    var w = sourceEl.naturalWidth || sourceEl.videoWidth;
    var h = sourceEl.naturalHeight || sourceEl.videoHeight;
    if (!w || !h) return null;
    var scale = Math.min(1, MAX_DIM / Math.max(w, h));
    var canvas = document.createElement('canvas');
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext('2d').drawImage(sourceEl, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', JPEG_QUALITY);
  }

  function captureVideoFrame() {
    if (!camera.enabled) return null;
    return scaleToDataURL(el.video); // null until the video is actually delivering frames
  }

  function frameKB(dataUrl) {
    var base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
    return Math.round(base64.length * 0.75 / 1024);
  }

  function setPendingFrame(dataUrl, source) {
    pendingFrame = { dataUrl: dataUrl, capturedAt: new Date(), source: source };
    el.preview.src = dataUrl;
    el.preview.hidden = false;
    el.previewEmpty.hidden = true;
    setText(el.frameMeta, source + ' \u00b7 ' + frameKB(dataUrl) + ' KB \u00b7 ' + pendingFrame.capturedAt.toLocaleTimeString());
    renderButtons();
  }

  function clearPendingCameraFrame() {
    if (!pendingFrame || pendingFrame.source !== 'camera') return;
    pendingFrame = null;
    el.preview.hidden = true;
    el.preview.src = '';
    el.previewEmpty.hidden = false;
    el.frameMeta.textContent = '';
    renderButtons();
  }

  /* Uploads to /api/frame: a real new capture, or null to clear the backend cache.
     Clears are never skipped; frame posts are skipped while one is already queued. */
  function postFrame(dataUrl) {
    var isClear = dataUrl === null;
    if (!isClear) {
      if (frameQueued) return;
      frameQueued = true;
    }
    var gen = cameraGen;
    frameChain = frameChain.then(function () {
      if (!isClear && gen !== cameraGen) return; // camera stopped meanwhile; the clear stays authoritative
      return postJSON('/api/frame', { image: dataUrl }).then(function (res) {
        if (!res.ok && dataUrl) showError('Frame cache update failed (' + res.status + '). Inspect still sends the image directly.');
      }).catch(function () {
        /* poll loop surfaces connection loss */
      });
    }).then(function () {
      if (!isClear) frameQueued = false;
    });
  }

  /* Periodic camera tick: capture a fresh scaled frame from the live video, then upload it. */
  function captureTick() {
    if (!camera.enabled) return;
    var dataUrl = captureVideoFrame();
    if (!dataUrl) return;
    setPendingFrame(dataUrl, 'camera');
    postFrame(dataUrl);
  }

  function onTrackEnded() {
    showError('Camera stream ended. Use image upload instead.');
    stopCamera();
  }

  function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showError('This browser does not expose camera access. Use image upload instead.');
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { width: { ideal: MAX_DIM } }, audio: false }).then(function (stream) {
      camera.stream = stream;
      camera.enabled = true;
      el.video.srcObject = stream;
      var track = stream.getVideoTracks()[0];
      if (track) track.addEventListener('ended', onTrackEnded);
      el.video.addEventListener('loadeddata', function onFirstFrame() {
        el.video.removeEventListener('loadeddata', onFirstFrame);
        captureTick();
      });
      el.video.play();
      el.video.hidden = false;
      el.videoPlaceholder.hidden = true;
      el.btnCamera.textContent = 'Stop camera';
      el.btnSnapshot.disabled = false;
      el.previewWrap.classList.add('hidden-when-live');
      camera.timer = setInterval(captureTick, FRAME_POST_MS);
    }).catch(function (err) {
      var reason = (err && err.name === 'NotAllowedError')
        ? 'Camera permission was denied.'
        : (err && err.name ? 'Camera error: ' + err.name + '.' : 'Camera could not be started.');
      showError(reason + ' Use image upload instead.');
    });
  }

  function stopCamera() {
    if (camera.timer) { clearInterval(camera.timer); camera.timer = null; }
    if (camera.stream) {
      camera.stream.getTracks().forEach(function (t) { t.stop(); });
      camera.stream = null;
    }
    camera.enabled = false;
    el.video.srcObject = null;
    el.video.hidden = true;
    el.videoPlaceholder.hidden = false;
    el.btnCamera.textContent = 'Start camera';
    el.btnSnapshot.disabled = true;
    el.previewWrap.classList.remove('hidden-when-live');
    clearPendingCameraFrame();
    cameraGen += 1; // any queued camera frame is now stale; the clear below must win
    postFrame(null); // owner contract: clears the backend frame cache
  }

  function snapshot() {
    var dataUrl = captureVideoFrame();
    if (!dataUrl) { showError('No camera frame available to capture.'); return; }
    setPendingFrame(dataUrl, 'camera');
    postFrame(dataUrl);
  }

  function handleUpload(file) {
    if (!file || !/^image\//.test(file.type)) { showError('Choose an image file to upload.'); return; }
    if (camera.enabled) stopCamera(); // camera ticks would otherwise overwrite the upload
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        var dataUrl = scaleToDataURL(img);
        if (!dataUrl) { showError('Could not decode the uploaded image.'); return; }
        setPendingFrame(dataUrl, 'upload');
        postFrame(dataUrl);
      };
      img.onerror = function () { showError('Could not decode the uploaded image.'); };
      img.src = String(reader.result);
    };
    reader.onerror = function () { showError('Could not read the selected file.'); };
    reader.readAsDataURL(file);
  }

  /* ---------- actions ---------- */

  var lastServerInstruction = null;
  var instructionDirty = false;

  function instructionDiffersFromServer() {
    return !!(connected && instructionDirty && el.instruction.value.trim());
  }

  function updateInstructionPending() {
    var pending = instructionDiffersFromServer();
    el.instructionPending.hidden = !pending;
    if (pending) el.instructionPending.textContent = 'Unapplied \u2014 Inspect applies this rule first';
  }

  function inspect() {
    if (inspectBusy || serverBusy || !connected || !pendingFrame) return;
    if (state && (state.busy === true || state.status === 'INSPECTING')) return;
    if (camera.enabled) {
      var fresh = captureVideoFrame();
      if (fresh) setPendingFrame(fresh, 'camera'); // inspect always sees the live scene
    }
    if (!pendingFrame) return;
    var image = pendingFrame.dataUrl;
    var sentInstruction = el.instruction.value.trim();
    var applyFirst = null;
    if (instructionDiffersFromServer()) {
      applyFirst = postJSON('/api/instruction', { instruction: sentInstruction });
    }
    inspectBusy = true;
    renderButtons();
    (applyFirst || Promise.resolve()).then(function (applied) {
      if (applyFirst) {
        if (!applied || !applied.ok || !applied.body || applied.body.instruction !== sentInstruction) {
          showError('Instruction change was not confirmed by the server; inspection cancelled to avoid the wrong rule.');
          return;
        }
      }
      return postJSON('/api/inspect', { image: image });
    }).then(function (res) {
      if (!res) return; // apply-first was rejected and cancelled the inspection
      if (res.status === 409) {
        serverBusy = true;
        showError('An inspection is already running. Wait for it to finish.');
      } else if (res.status === 400) {
        showError('Inspect was rejected: the server reports a missing image.');
      } else if (!res.ok) {
        showError('Inspect failed (' + res.status + ').');
      }
    }).catch(function () {
      showError('Inspect request could not reach the server.');
    }).finally(function () {
      inspectBusy = false;
      renderButtons();
    });
  }

  function clearResult() {
    postJSON('/api/clear', {}).then(function (res) {
      if (!res.ok) showError('Clear failed (' + res.status + ').');
    }).catch(function () {
      showError('Clear request could not reach the server.');
    });
  }

  function applyInstruction(presetId) {
    var text = el.instruction.value.trim();
    if (!text) { showError('Enter an instruction before applying it.'); return; }
    var payload = { instruction: text };
    if (presetId) payload.preset_id = presetId;
    postJSON('/api/instruction', payload).then(function (res) {
      if (!res.ok) showError('Applying instruction failed (' + res.status + ').');
    }).catch(function () {
      showError('Instruction could not reach the server.');
    });
  }

  /* ---------- state ---------- */

  function poll() {
    fetchJSON('/api/state').then(function (res) {
      if (!res.ok || !res.body) throw new Error('bad response');
      pollFailures = 0;
      if (!connected) clearError();
      connected = true;
      applyState(res.body);
    }).catch(function () {
      pollFailures += 1;
      if (pollFailures >= STALE_POLLS && connected) {
        connected = false;
        showError('Connection to the inspection server was lost. The last result is stale and hidden.');
        renderDisconnected();
      }
    }).finally(function () {
      setTimeout(poll, POLL_MS);
    });
  }

  function applyState(next) {
    state = next;
    if (connected) renderState();
  }

  function clearExpiry() {
    if (expiryTimer) { clearTimeout(expiryTimer); expiryTimer = null; }
  }

  /* Local safety net between polls: an OK/CHECK must not outlive expires_in_ms. */
  function scheduleExpiry() {
    clearExpiry();
    if (!connected || !state) return;
    var expiresIn = state.expires_in_ms;
    var status = state.status;
    if (typeof expiresIn !== 'number' || !isFinite(expiresIn) || expiresIn <= 0) return;
    if (status !== 'OK' && status !== 'CHECK') return;
    expiryTimer = setTimeout(function () {
      expiryTimer = null;
      if (!connected || !state || (state.status !== 'OK' && state.status !== 'CHECK')) return;
      setText(el.badge, 'UNKNOWN');
      el.badge.className = 'badge badge-unknown';
      setText(el.explanation, 'Result expired \u2014 waiting for the server to confirm current state.');
    }, Math.min(expiresIn, 2147483647));
  }

  function renderDisconnected() {
    clearExpiry();
    serverBusy = false;
    setText(el.badge, 'UNKNOWN');
    el.badge.className = 'badge badge-unknown';
    setText(el.explanation, 'Connection lost \u2014 the last result may be stale and is hidden until the server responds.');
    el.conn.textContent = 'Offline';
    el.conn.className = 'pill pill-down';
    renderButtons();
  }

  function renderState() {
    var s = state || {};
    el.conn.textContent = 'Online';
    el.conn.className = 'pill pill-live';

    var status = s.status || 'IDLE';
    if (s.busy === false) serverBusy = false;
    setText(el.badge, status);
    el.badge.className = 'badge badge-' + String(status).toLowerCase();
    setText(el.explanation, s.explanation || (status === 'IDLE' ? 'No current inspection.' : ''));
    setText(el.latency, (s.latency_ms === null || s.latency_ms === undefined) ? null : s.latency_ms + ' ms');
    setText(el.requestId, s.request_id);
    setText(el.instructionVersion, s.instruction_version);
    lastServerInstruction = (s.instruction === null || s.instruction === undefined) ? null : s.instruction;
    if (el.instruction.value === lastServerInstruction) instructionDirty = false;
    if (s.instruction !== null && s.instruction !== undefined && !instructionDirty) {
      el.instruction.value = s.instruction;
    }

    var board = s.board || {};
    el.boardState.textContent = board.connected
      ? 'Online' + (board.device_id ? ' \u00b7 ' + board.device_id : '') +
        ((board.last_seen_seconds !== null && board.last_seen_seconds !== undefined) ? ' \u00b7 last seen ' + Number(board.last_seen_seconds).toFixed(1) + 's ago' : '')
      : 'Offline';

    var runtime = s.runtime || {};
    el.runtimeState.textContent = runtime.connected
      ? 'Connected' + (runtime.model ? ' \u00b7 ' + runtime.model : '')
      : 'Not connected';
    setText(el.backendEvidence, runtime.backend_evidence);

    var c = s.counters || {};
    setText(el.counters, 'inspections ' + (c.inspections || 0) + ' \u00b7 completed ' + (c.completed || 0) + ' \u00b7 unknown ' + (c.unknown || 0));

    renderPresets(s.presets || [], s.preset_id);
    renderEvents(s.events || []);
    renderButtons();
    scheduleExpiry();
  }

  function renderPresets(presets, activeId) {
    el.presetList.textContent = '';
    var hasActive = false;
    presets.forEach(function (p) {
      var li = document.createElement('li');
      var btn = document.createElement('button');
      btn.type = 'button';
      if (p.id === activeId) { btn.className = 'btn preset-active'; hasActive = true; }
      else btn.className = 'btn';
      var label = document.createElement('span');
      label.className = 'preset-label';
      label.textContent = p.label || p.id;
      btn.title = p.instruction || '';
      btn.setAttribute('aria-label', (p.label || p.id) + ': ' + (p.instruction || ''));
      btn.appendChild(label);
      btn.addEventListener('click', function () {
        el.instruction.value = p.instruction || '';
        instructionDirty = false; // applying it right now
        applyInstruction(p.id);
      });
      li.appendChild(btn);
      el.presetList.appendChild(li);
    });
    setText(el.presetNote, (activeId && hasActive)
      ? 'Selected preset: ' + activeId
      : 'Selected preset not reported.');
  }

  function renderEvents(events) {
    el.events.textContent = '';
    if (!events.length) {
      var empty = document.createElement('li');
      empty.className = 'event-empty';
      empty.textContent = 'No events reported yet.';
      el.events.appendChild(empty);
      return;
    }
    events.forEach(function (ev) {
      var li = document.createElement('li');
      li.className = 'event-item ev-' + String(ev.status || 'unknown').toLowerCase();
      var line = document.createElement('div');
      line.className = 'event-line';
      line.textContent = (ev.created_at || '') + ' \u00b7 ' + (ev.request_id || '');
      var st = document.createElement('span');
      st.className = 'event-status';
      st.textContent = ' ' + (ev.status || 'UNKNOWN') + ((ev.latency_ms !== null && ev.latency_ms !== undefined) ? ' \u00b7 ' + ev.latency_ms + ' ms' : '');
      line.appendChild(st);
      li.appendChild(line);
      if (ev.explanation) {
        var ex = document.createElement('p');
        ex.className = 'event-explanation';
        ex.textContent = ev.explanation;
        li.appendChild(ex);
      }
      el.events.appendChild(li);
    });
  }

  function renderButtons() {
    var busy = inspectBusy || serverBusy || (state && (state.busy === true || state.status === 'INSPECTING'));
    el.btnInspect.disabled = !connected || !pendingFrame || !!busy;
    el.btnClear.disabled = !connected || (!!state && state.status === 'IDLE');
    el.btnApply.disabled = !connected;
    updateInstructionPending();
  }

  /* ---------- wiring ---------- */

  el.btnCamera.addEventListener('click', function () {
    if (camera.enabled) stopCamera(); else startCamera();
  });
  el.btnSnapshot.addEventListener('click', snapshot);
  el.fileInput.addEventListener('change', function () {
    if (el.fileInput.files && el.fileInput.files[0]) handleUpload(el.fileInput.files[0]);
    el.fileInput.value = '';
  });
  el.instruction.addEventListener('input', function () {
    instructionDirty = el.instruction.value !== lastServerInstruction;
    updateInstructionPending();
  });
  el.btnInspect.addEventListener('click', inspect);
  el.btnClear.addEventListener('click', clearResult);
  el.btnApply.addEventListener('click', function () { applyInstruction(null); });

  poll();
})();
