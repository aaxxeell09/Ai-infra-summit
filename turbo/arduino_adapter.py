"""Transport-independent controller for the UNO Q mode pad (stdlib only).

The board emits newline-delimited JSON events; any transport that yields lines
(stdin, serial pipe, socket) can drive ModeController. This module owns event
validation and debouncing. It never opens URLs itself: the returned action is
structured JSON the host forwards to the parent service POST /api/apply.
"""
from __future__ import annotations

import json
import time

MODES = ("fast", "efficient", "balanced")


class EventError(ValueError):
    """A control event failed validation."""


class ModeController:
    """Validate raw control events; one service action per accepted press."""

    def __init__(self, debounce_ms=250, now=time.monotonic):
        if not 0 <= debounce_ms <= 2000:
            raise ValueError("debounce_ms must be between 0 and 2000")
        self.debounce_s = debounce_ms / 1000
        self.now = now
        self.last_press = {}  # source -> monotonic time of last accepted press

    def handle_line(self, line):
        """Parse one transport line; return an action dict, or None for bounce."""
        try:
            event = json.loads(line)
        except ValueError:
            raise EventError("malformed JSON event line") from None
        return self.handle(event)

    def handle(self, event):
        """Validate one event dict; return an action dict or None on bounce.

        Raises EventError for an invalid event body so the host can log and
        drop it; duplicate presses inside the debounce window are None.
        """
        if not isinstance(event, dict):
            raise EventError("event must be a JSON object")
        kind = event.get("event")
        if kind == "button":
            return self._button(event)
        if kind == "knob":
            return self._knob(event)
        raise EventError("unknown event kind: %r" % (kind,))

    def _fresh_press(self, source):
        now = self.now()
        last = self.last_press.get(source)
        self.last_press[source] = now
        return last is None or (now - last) >= self.debounce_s

    def _button(self, event):
        source, mode = event.get("source"), event.get("mode")
        if source not in MODES or mode != source:
            raise EventError("button source and mode must name a known mode")
        if not self._fresh_press(source):
            return None
        return {"action": "apply", "mode": source}

    def _knob(self, event):
        direction = event.get("direction")
        if direction not in (-1, 1):
            raise EventError("knob direction must be -1 or 1")
        if not self._fresh_press("knob"):
            return None
        current = event.get("mode")
        order = MODES.index(current) if current in MODES else 0
        selected = MODES[(order + direction) % len(MODES)]
        return {"action": "apply", "mode": selected, "via": "knob"}


def handle_output(status):
    """Render service status as one compact JSON line for board output.

    status is the parsed /api/status body (or a subset): pixels map model ids
    to cpu/npu/gpu placement, progress covers a running tune, and vibrate
    marks a finished secretary run for the Vibro module.

    models[].device is the configured default placement, not an observation;
    when status.applied names the model it acknowledged, its config.device
    overrides the pixel because that placement was actually applied. There
    is no run_finished field on the real /api/status body: completion is a
    caller-derived event (the host knows when its own run ends) and this
    renderer only honors it if the caller attaches it.
    """
    if not isinstance(status, dict):
        raise ValueError("status must be a dict from the /api/status body")
    out = {"pixels": {}, "progress": None, "vibrate": False}
    models = status.get("models")
    applied = status.get("applied")
    applied_device = None
    if isinstance(applied, dict):
        cfg = applied.get("config")
        if applied.get("mode") in MODES and isinstance(cfg, dict) \
                and cfg.get("device") in ("cpu", "npu", "gpu"):
            applied_device = cfg["device"]
    if isinstance(models, list):
        for model in models:
            if not (isinstance(model, dict) and model.get("id")
                    and model.get("device") in ("cpu", "npu", "gpu")):
                continue
            if applied_device and isinstance(applied, dict) \
                    and model.get("id") == applied.get("model"):
                out["pixels"][model["id"]] = applied_device
            else:
                out["pixels"][model["id"]] = model["device"]
    tuning = status.get("tuning")
    if isinstance(tuning, dict) and tuning.get("running"):
        total = tuning.get("total") or 1
        done = min(tuning.get("completed", 0), total)
        out["progress"] = round(max(done, 0) / total, 3)
    out["vibrate"] = status.get("run_finished") is True
    if isinstance(applied, dict) and applied.get("mode") in MODES:
        out["active_mode"] = applied["mode"]
        cfg = applied.get("config")
        out["config"] = {k: cfg[k] for k in ("device", "threads", "context") if isinstance(cfg, dict) and k in cfg}
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def bridge_action_to_event(code, current_mode=MODES[0]):
    """Map the archive Bridge get_action() packed int to a controller event.

    Low byte is a button number (1..3 map to fast/efficient/balanced), high
    byte is a signed knob direction. Provisional mapping from the archive
    inspection app; confirm against the compiled sketch on the bench.
    """
    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 0xFFFF:
        raise EventError("bridge action must be a 16-bit int")
    direction = (code >> 8) & 0xFF
    if direction >= 0x80:
        direction -= 0x100
    button = code & 0xFF
    if direction:
        return {"event": "knob", "direction": 1 if direction > 0 else -1, "mode": current_mode}
    if not button:
        return None
    if button > len(MODES):
        raise EventError("bridge button index out of range: %d" % button)
    mode = MODES[button - 1]
    return {"event": "button", "source": mode, "mode": mode}


def apply_request(mode):
    """Body for POST /api/apply; the mode must be a measured one."""
    if mode not in MODES:
        raise EventError("apply mode must be one of %s" % (MODES,))
    return {"mode": mode}


def apply_response(body):
    """Require evidence of the actually applied native config.

    The parent service returns model, mode, config and measured evidence;
    anything less cannot drive real control-plane feedback, so it is an
    error instead of a silent visual-only ack.
    """
    if not isinstance(body, dict):
        raise EventError("apply response must be a JSON object")
    mode = body.get("mode")
    cfg = body.get("config")
    evidence = body.get("evidence")
    if mode not in MODES or not isinstance(cfg, dict) or \
            not {"device", "threads", "context"} <= set(cfg):
        raise EventError("apply response lacks an applied config for the mode")
    if not isinstance(evidence, dict) or not evidence.get("source"):
        raise EventError("apply response lacks measured evidence")
    return {"mode": mode, "config": {k: cfg[k] for k in ("device", "threads", "context")},
            "evidence_source": evidence["source"]}
