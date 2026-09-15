"""Device registry and routing with a board HTTP inference client (stdlib).

The Arduino UNO Q (ABX00162) registers as a Linux ARM64 inference device.
Its connectivity and on-board status are UNVERIFIED unless the caller passes
explicit evidence; nothing here claims NPU, GPU or any speed advantage. The
"cpu" compute label records the intended runtime placement, not a hardware
limit: the QRB2210 SoC also contains a GPU that nobody has measured here.
Routing escalates to the laptop whenever the board cannot serve a request.
Capabilities come from configured facts, never from optimistic defaults,
and measured profiles must carry their own recorded numbers.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

DEFAULT_TIMEOUT_S = 10.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class EdgeDeviceError(RuntimeError):
    """A configured edge device failed its request."""


def uno_q_board(device_id="uno-q", endpoint=None, connectivity=None):
    """Registry entry template for the UNO Q board.

    endpoint is a configured local LAN URL (for example http://192.168.x.x:8080)
    provided by the operator; it is never invented here. connectivity
    defaults to unverified; a caller that actually probed the board passes
    its evidence dict (which must carry a boolean "verified") explicitly.
    No serial numbers or per-board RAM/disk readings are defaults: those are
    observations of one unit at one time and belong to the caller's evidence.
    """
    if connectivity is None:
        connectivity = {"method": "usb-adb", "verified": False}
    else:
        if not isinstance(connectivity, dict) or not isinstance(connectivity.get("verified"), bool):
            raise ValueError("connectivity evidence must be a dict with a boolean 'verified'")
        connectivity = dict(connectivity)
    return {
        "device_id": device_id,
        "kind": "board",
        "arch": "linux-arm64",
        "compute": "cpu",
        "status": "unverified",
        "endpoint": endpoint,
        "use_npu": False,
        "capabilities": [],
        "measured_profiles": {},
        "connectivity": connectivity,
    }


def register_device(registry, entry):
    """Validate and add one device entry; returns the registry for chaining."""
    for field in ("device_id", "kind", "arch", "compute", "endpoint"):
        if field not in entry:
            raise ValueError("device entry missing field: %s" % field)
    if entry["compute"] not in ("cpu", "gpu", "npu"):
        raise ValueError("compute must be cpu, gpu or npu")
    if entry["compute"] == "npu" and not entry.get("measured_profiles"):
        raise ValueError("npu compute requires measured profile evidence")
    known = {d.get("device_id") for d in registry}
    if entry["device_id"] in known:
        raise ValueError("duplicate device_id: %s" % entry["device_id"])
    registry.append(dict(entry))
    return registry


def is_eligible(device, prompt_tokens=0, output_tokens=0):
    """Fail-closed serving rule shared by route() and fallback escalation.

    A device is eligible only when its status is verified, its capabilities
    cover llm, and its recorded context_tokens is a positive finite integer
    that fits the explicit prompt plus output budget. A missing, zero or
    non-integer context is never treated as unlimited.
    """
    if device.get("status") != "verified":
        return False
    if "llm" not in device.get("capabilities", []):
        return False
    context = device.get("context_tokens")
    if isinstance(context, bool) or not isinstance(context, int) \
            or context <= 0 or not math.isfinite(context):
        return False
    return prompt_tokens + output_tokens <= context


def _checked_tokens(prompt_tokens, output_tokens):
    for value, name in ((prompt_tokens, "prompt_tokens"), (output_tokens, "output_tokens")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("%s must be a non-negative int" % name)


def route(prompt_tokens, devices, prefer="board", output_tokens=0):
    """Pick a verified device id for a task, or raise when none fits.

    Deterministic policy: only entries whose status is verified, whose
    capabilities cover llm, and whose recorded context_tokens is a positive
    finite integer that fits the explicit prompt plus output budget are
    eligible. A device without a recorded context is never eligible: an
    unmeasured context is not unlimited. The first eligible entry wins;
    unverified or unbounded entries are skipped, so routing fails closed
    with EdgeDeviceError instead of guessing.
    """
    if not devices:
        raise EdgeDeviceError("device registry is empty")
    _checked_tokens(prompt_tokens, output_tokens)

    ordered = sorted(devices, key=lambda d: (d.get("kind") != prefer, d.get("device_id", "")))
    for device in ordered:
        if is_eligible(device, prompt_tokens, output_tokens):
            return device["device_id"]
    raise EdgeDeviceError("no verified device with a fitting recorded context")


class BoardInferenceClient:
    """OpenAI-compatible /v1/chat/completions client for the board endpoint.

    Latency here includes USB/LAN transfer plus remote inference: the caller
    sees one number covering the whole round trip. Any transport or HTTP
    failure surfaces as EdgeDeviceError so the host can fall back to the
    laptop GPU path without retry loops hiding the outage.
    """

    def __init__(self, endpoint, timeout_s=DEFAULT_TIMEOUT_S, opener=urllib.request.urlopen):
        if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must be a configured http(s) local LAN URL")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) \
                or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be a finite positive number of seconds")
        self.endpoint = endpoint.rstrip("/")
        self.timeout_s = timeout_s
        self.opener = opener

    def _read_bounded(self, response, started):
        chunks = []
        remaining = MAX_RESPONSE_BYTES
        while True:
            chunk = response.read(min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                self._fail("board response exceeds %d bytes" % MAX_RESPONSE_BYTES,
                           started)
        return b"".join(chunks)

    def _fail(self, message, started):
        error = EdgeDeviceError(message)
        error.latency_ms = round((time.monotonic() - started) * 1000, 1)
        raise error

    def chat(self, model, messages, temperature=0.2, max_tokens=256):
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint + "/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with self.opener(request, timeout=self.timeout_s) as response:
                body = json.loads(self._read_bounded(response, started))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._fail("board inference failed: %s" % exc, started)
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        if not isinstance(body, dict):
            self._fail("board returned an unreadable completion body", started)
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self._fail("board returned an unreadable completion body", started)
        if not isinstance(text, str):
            self._fail("board returned a non-string completion text", started)
        return {"text": text, "latency_ms": latency_ms, "device": "board", "endpoint": self.endpoint}


def escalate_to_laptop(client_call, registry, route_result,
                       prompt_tokens=0, output_tokens=0, **call_kwargs):
    """Run client_call on the routed device; on EdgeDeviceError try the laptop.

    route_result is the device id returned by route(). The laptop is the first
    registry entry whose kind is laptop and that passes the same eligibility
    rule as route() for the explicit prompt_tokens plus output_tokens budget
    (defaults 0): verified status, llm capability and a recorded positive
    integer context that fits the budget. An unverified or unbounded laptop
    is never called, and failure of all paths re-raises the board error so
    the caller sees a real outage instead of silent degradation.
    The returned latency includes the failed board attempt when the error
    carries its latency_ms (BoardInferenceClient errors do), so end-to-end
    timing never hides the cost of the failed try.
    """
    devices = {d["device_id"]: d for d in registry}
    failed_latency_ms = 0.0
    _checked_tokens(prompt_tokens, output_tokens)
    try:
        return client_call(route_result, **call_kwargs)
    except EdgeDeviceError as exc:
        failed_latency_ms += getattr(exc, "latency_ms", 0.0) or 0.0
        laptop = next((d for d in registry
                       if d.get("kind") == "laptop"
                       and d.get("device_id") != route_result
                       and is_eligible(d, prompt_tokens, output_tokens)), None)
        if laptop is None:
            raise
        result = client_call(laptop["device_id"], **call_kwargs)
        if isinstance(result, dict):
            result["latency_ms"] = round(result.get("latency_ms", 0.0) + failed_latency_ms, 1)
        return result
