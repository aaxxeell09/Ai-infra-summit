"""MCP stdio server for the local inference tuner.

JSON-RPC 2.0 over stdin/stdout per the Model Context Protocol spec
(initialize / tools/list / tools/call / ping). Loopback HTTP to the local
Turbo gateway only; no shell, no file execution, no arbitrary URLs.
Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "turbo-mcp", "version": "0.2.0"}
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
BASE_URL_ENV = "TURBO_BASE_URL"
REQUEST_TIMEOUT_S = 120
MAX_TOKENS = 2048
MAX_MESSAGES = 64
MAX_MESSAGE_CHARS = 64_000
MAX_PROMPT_CHARS = 8_000
MAX_LABEL_CHARS = 200
MAX_OBJECTIVE_CHARS = 50
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
MODE_NAMES = ("fast", "efficient", "balanced")


class BackendError(Exception):
    """Gateway returned a non-200 response or is unreachable."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Gateway:
    """Loopback-only HTTP client for the local Turbo gateway."""

    def __init__(self, base_url=DEFAULT_BASE_URL, timeout=REQUEST_TIMEOUT_S):
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or (parsed.hostname or "") not in LOOPBACK_HOSTS:
            raise ValueError(
                "base_url must be an http:// loopback endpoint "
                "(127.0.0.1, ::1, or localhost); remote endpoints are disabled")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise BackendError("gateway returned HTTP %d for %s" % (exc.code, path), exc.code) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise BackendError("gateway unreachable at %s: %s" % (path, exc)) from exc

    def post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise BackendError(
                "gateway returned HTTP %d for %s: %s" % (exc.code, path, detail), exc.code) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise BackendError("gateway unreachable at %s: %s" % (path, exc)) from exc


def validate_messages(messages):
    """Return normalized text-only messages, bounded, or raise ValueError."""
    if not isinstance(messages, list) or not (1 <= len(messages) <= MAX_MESSAGES):
        raise ValueError("messages must be a list of 1..%d objects" % MAX_MESSAGES)
    out = []
    for m in messages:
        if not isinstance(m, dict):
            raise ValueError("each message must be an object")
        role = m.get("role")
        content = m.get("content")
        if role not in ("system", "user", "assistant"):
            raise ValueError("message.role must be system, user, or assistant")
        if not isinstance(content, str) or not content:
            raise ValueError("message.content must be a nonempty string")
        if len(content) > MAX_MESSAGE_CHARS:
            raise ValueError("message.content exceeds %d characters" % MAX_MESSAGE_CHARS)
        out.append({"role": role, "content": content})
    return out


def bounded_str(value, name, max_chars):
    """Optional string argument: None passes through; else 1..max_chars."""
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > max_chars:
        raise ValueError("%s must be a string of 1..%d characters" % (name, max_chars))
    return value


def _mode_arg(args):
    mode = args.get("mode")
    if mode not in MODE_NAMES:
        raise ValueError("mode must be one of fast, efficient, balanced")
    return mode


def _entry_model(entry):
    if not isinstance(entry, dict):
        return None
    model = entry.get("model") or entry.get("model_id")
    return model if isinstance(model, str) and model else None


TOOLS = [
    {
        "name": "local_models",
        "description": (
            "List locally installed models, measured tuning profiles, approved "
            "modes from the gateway registry (with calibrated flags), the "
            "current recommendation, and tuning state. Call before other tools."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "local_run",
        "description": (
            "Run one bounded generic inference request via /v1/chat/completions. "
            "Modes resolve through the gateway's approved-modes registry; an "
            "explicit model overrides the mapping. Sequential single worker."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODE_NAMES),
                         "description": "Routing intent; resolved to a measured model or reported unavailable."},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                        "additionalProperties": False,
                    },
                    "description": "Chat messages; text only.",
                },
                "max_tokens": {"type": "integer", "minimum": 1, "maximum": MAX_TOKENS,
                               "description": "Completion budget, 1..2048."},
                "model": {"type": "string",
                          "description": "Optional explicit model id; overrides the mode mapping."},
                "task_id": {"type": "string", "description": "Caller correlation id, echoed back."},
            },
            "required": ["mode", "messages"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_apply",
        "description": (
            "Apply the gateway's validated tuning recommendation for a mode to "
            "the runtime config via /api/apply. Call after a sweep completes "
            "and local_models shows a recommendation."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODE_NAMES),
                         "description": "Mode whose validated recommendation to apply."},
                "model_id": {"type": "string",
                             "description": "Optional specific model id; gateway validates it."},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_tune",
        "description": (
            "Start a local device sweep via /api/tune for a model id, with "
            "optional objective and search configuration label. Inference is "
            "paused while the sweep runs. No shell, no arbitrary paths."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model id from local_models to sweep."},
                "objective": {"type": "string", "description": "Optional tuning objective label (gateway-validated)."},
                "searchspace": {"type": "string",
                                "description": "Optional search configuration label recorded for traceability."},
            },
            "required": ["model_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_secretary",
        "description": (
            "Run one verified secretary fixture task end to end via /api/run. "
            "Returns the applied runtime config, semantic correctness, and "
            "total task timing. One bounded task; the agent manages decomposition."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODE_NAMES),
                         "description": "Mode to run the verified task under."},
                "prompt": {"type": "string", "description": "Task request, 1..8000 characters."},
                "task_id": {"type": "string", "description": "Caller correlation id, echoed back."},
            },
            "required": ["mode", "prompt"],
            "additionalProperties": False,
        },
    },
]


class MCPServer:
    def __init__(self, gateway=None, modes_config=None, stdin=None, stdout=None):
        self.gateway = gateway or Gateway()
        # Static fallback {mode: {"model": id} | None}, used only when the
        # gateway does not expose /api/modes yet. The gateway registry is the
        # source of truth whenever it is reachable.
        self.modes_config = {m: v for m, v in (modes_config or {}).items() if m in MODE_NAMES}
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.initialized = False

    # ---- wire helpers -------------------------------------------------
    def _write(self, payload):
        self.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.stdout.flush()

    def respond(self, id, result):
        self._write({"jsonrpc": "2.0", "id": id, "result": result})

    def respond_error(self, id, code, message):
        self._write({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})

    # ---- MCP handlers -------------------------------------------------
    def handle_initialize(self, id, params):
        requested = (params or {}).get("protocolVersion")
        version = requested if requested == PROTOCOL_VERSION else PROTOCOL_VERSION
        self.respond(id, {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    def handle_tools_call(self, id, params):
        if not self.initialized:
            return self.respond_error(id, -32002, "server not initialized")
        name = (params or {}).get("name")
        args = (params or {}).get("arguments") or {}
        try:
            if name == "local_models":
                result = self._tool_local_models(args)
            elif name == "local_run":
                result = self._tool_local_run(args)
            elif name == "local_apply":
                result = self._tool_local_apply(args)
            elif name == "local_tune":
                result = self._tool_local_tune(args)
            elif name == "local_secretary":
                result = self._tool_local_secretary(args)
            else:
                return self.respond_error(id, -32602, "unknown tool: %s" % name)
        except BackendError as exc:
            result = {"error": str(exc), "status": exc.status, "isError": True}
        except (ValueError, KeyError, TypeError) as exc:
            result = {"error": str(exc), "isError": True}
        self.respond(id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "structuredContent": result,
            "isError": bool(result.get("isError")),
        })

    def dispatch(self, msg):
        if not isinstance(msg, dict):
            return
        method = msg.get("method")
        id = msg.get("id")
        if method == "initialize":
            return self.handle_initialize(id, msg.get("params"))
        if method == "notifications/initialized":
            self.initialized = True
            return
        if method == "ping":
            return self.respond(id if "id" in msg else None, {})
        if method == "tools/list":
            return self.respond(id, {"tools": TOOLS})
        if method == "tools/call":
            return self.handle_tools_call(id, msg.get("params"))
        if "id" in msg:
            self.respond_error(id, -32601, "method not found: %s" % method)

    def serve_forever(self):
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # malformed frame; cannot be correlated to an id
            self.dispatch(msg)

    # ---- modes registry -------------------------------------------------
    def _resolve_modes_registry(self):
        """Return ({mode: entry}, source). Gateway first, static fallback second."""
        try:
            payload = self.gateway.get("/api/modes")
        except BackendError:
            return dict(self.modes_config), "static_config_fallback"
        modes = {}
        entries = payload.get("modes") if isinstance(payload, dict) else None
        if entries is None and isinstance(payload, dict):
            entries = payload
        if isinstance(entries, dict):
            for key, entry in entries.items():
                if isinstance(key, str) and isinstance(entry, dict):
                    modes[key] = entry
        elif isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    key = entry.get("mode") or entry.get("name")
                    if isinstance(key, str):
                        modes[key] = entry
        return modes, "gateway"

    def _mode_unavailable(self, mode, registry, source):
        entry = registry.get(mode) or {}
        reason = entry.get("reason") if isinstance(entry, dict) else None
        reason = reason or ("no eligible measured profile is mapped to this mode; "
                            "refusing to substitute an unmeasured default")
        return {
            "available": False,
            "mode": mode,
            "resolved_model": None,
            "mapping_source": source,
            "reason": reason,
            "content": None,
            "usage": None,
        }

    # ---- tool implementations ------------------------------------------
    def _tool_local_models(self, args):
        status = self.gateway.get("/api/status")
        registry, source = self._resolve_modes_registry()
        modes = {}
        for m in MODE_NAMES:
            model = _entry_model(registry.get(m))
            modes[m] = {
                "eligible_model": model,
                "calibrated": model is not None,
                "source": source if model is not None else None,
            }
        return {
            "runtime_available": status.get("runtime_available"),
            "models": status.get("models", []),
            "profiles": status.get("profiles", []),
            "recommendation": status.get("recommendation"),
            "tuning": status.get("tuning"),
            "modes": modes,
        }

    def _tool_local_run(self, args):
        mode = _mode_arg(args)
        messages = validate_messages(args.get("messages"))
        requested_model = bounded_str(args.get("model"), "model", MAX_LABEL_CHARS)
        max_tokens = args.get("max_tokens", 256)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) \
                or not (1 <= max_tokens <= MAX_TOKENS):
            raise ValueError("max_tokens must be an integer 1..%d" % MAX_TOKENS)
        task_id = bounded_str(args.get("task_id"), "task_id", MAX_LABEL_CHARS)

        evidence = {"mode": mode, "requested_model": requested_model, "mapping_source": None}
        model = requested_model
        if model is None:
            registry, source = self._resolve_modes_registry()
            evidence["mapping_source"] = source
            model = _entry_model(registry.get(mode))
            if model is None:
                return self._mode_unavailable(mode, registry, source)
        evidence["resolved_model"] = model

        completion = self.gateway.post(
            "/v1/chat/completions",
            {"messages": messages, "max_tokens": max_tokens, "model": model})
        choice = (completion.get("choices") or [{}])[0]
        route = (completion.get("turbo") or {}).get("route") or {}
        return {
            "available": True,
            "mode": mode,
            "resolved_model": completion.get("model") or model,
            "route": route or None,
            "task_id": task_id,
            "content": (choice.get("message") or {}).get("content"),
            "finish_reason": choice.get("finish_reason"),
            "usage": completion.get("usage"),
            "estimate_only": route.get("estimate_only"),
            "prompt_size_method": route.get("prompt_size_method"),
            "evidence": evidence,
        }

    def _tool_local_apply(self, args):
        mode = _mode_arg(args)
        model_id = bounded_str(args.get("model_id"), "model_id", MAX_LABEL_CHARS)
        body = {"mode": mode}
        if model_id is not None:
            body["model_id"] = model_id
        resp = self.gateway.post("/api/apply", body)
        return {
            "applied": bool(resp.get("applied", True)),
            "mode": mode,
            "model_id": model_id,
            "gateway_response": resp,
        }

    def _tool_local_tune(self, args):
        model_id = bounded_str(args.get("model_id"), "model_id", MAX_LABEL_CHARS)
        if model_id is None:
            raise ValueError("model_id must be a nonempty string")
        objective = bounded_str(args.get("objective"), "objective", MAX_OBJECTIVE_CHARS)
        searchspace = bounded_str(args.get("searchspace"), "searchspace", MAX_LABEL_CHARS)
        known = {m.get("id") for m in self.gateway.get("/api/status").get("models", [])}
        if model_id not in known:
            raise ValueError("unknown model_id: %s; call local_models first" % model_id)
        body = {"model_id": model_id}
        if objective is not None:
            body["objective"] = objective
        if searchspace is not None:
            body["searchspace"] = searchspace
        resp = self.gateway.post("/api/tune", body)
        return {"accepted": True, "requested": body, "gateway_response": resp}

    def _tool_local_secretary(self, args):
        mode = _mode_arg(args)
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError("prompt must be a nonempty string of at most %d characters" % MAX_PROMPT_CHARS)
        task_id = bounded_str(args.get("task_id"), "task_id", MAX_LABEL_CHARS)
        body = {"mode": mode, "prompt": prompt}
        if task_id is not None:
            body["task_id"] = task_id
        resp = self.gateway.post("/api/run", body)
        runtime_config = resp.get("runtime_config") or resp.get("runtime") or resp.get("config")
        resolved_model = resp.get("model")
        if resolved_model is None and isinstance(runtime_config, dict):
            resolved_model = runtime_config.get("model")
        return {
            "available": True,
            "mode": resp.get("mode") or mode,
            "task_id": resp.get("task_id") or task_id,
            "resolved_model": resolved_model,
            "content": resp.get("content") if "content" in resp else resp.get("result"),
            "passed": resp.get("passed"),
            "errors": resp.get("errors"),
            "usage": resp.get("usage"),
            "runtime_config": runtime_config,
            "elapsed_s": resp.get("elapsed_s"),
            "gateway_response": resp,
        }


def main():
    base_url = os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL)
    MCPServer(Gateway(base_url)).serve_forever()


if __name__ == "__main__":
    main()
