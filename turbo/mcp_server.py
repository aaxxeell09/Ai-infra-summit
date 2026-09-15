"""MCP stdio server for the local inference tuner.

JSON-RPC 2.0 over stdin/stdout per the Model Context Protocol spec
(initialize / tools/list / tools/call / ping). Loopback HTTP to the local
Turbo gateway only; no shell, no file execution, no arbitrary URLs.
Standard library only.

Parent contract notes (Ai-infra-summit/turbo/service.py, READONLY source):
- /api/modes records carry device/threads/context plus a model hash but no
  reliable runtime model id, so the model is resolved from /api/status
  (configured default model when the record's model_sha256 matches the
  recommendation's) and the mapping source is reported per call.
- /v1/chat/completions derives the routing mode from body["mode"], so every
  completion request carries the requested mode explicitly.
- POST /api/tune expects search_space as an object with exact axis keys,
  never a free-text label.
- POST /api/run takes prompt or task_id (tNN gateway task selector), where
  task_id alone runs and verifies the stored gold fixture prompt.
- POST /api/apply and /api/run responses include the applied runtime config
  (model, mode, config, evidence); it is surfaced on tool results.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "turbo-mcp", "version": "0.3.0"}
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
OBJECTIVE_NAMES = ("fast", "efficient", "balanced", "decode", "prefill")
JSONRPC_PARSE_ERROR = -32700
TASK_ID_RE = re.compile(r"t\d{1,3}")

# Exact search-space axes accepted by the parent POST /api/tune handler
# (SearchSpace.from_dict). Anything else would raise inside the gateway
# mid-sweep or silently change the sweep contract, so validation is exact.
SEARCH_SPACE_AXES = {
    "devices": ("list", str),
    "threads": ("list", int),
    "contexts": ("list", int),
    "prompt_tokens": ("int",),
    "gen_tokens": ("int",),
    "warmup": ("int",),
    "repeats": ("int",),
    "batch": ("optint",),
    "ubatch": ("optint",),
    "energy_channel": ("optstr",),
    "temperature": ("num",),
    "seed": ("int",),
}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_search_space(value):
    """Validate a search_space object with exact gateway axes; None passes."""
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError(
            "search_space must be a nonempty object with keys from: "
            + ", ".join(sorted(SEARCH_SPACE_AXES)))
    unknown = sorted(key for key in value if key not in SEARCH_SPACE_AXES)
    if unknown:
        raise ValueError(
            "unknown search_space keys (%s); allowed: %s"
            % (", ".join(unknown), ", ".join(sorted(SEARCH_SPACE_AXES))))
    out = {}
    for key, kind in SEARCH_SPACE_AXES.items():
        if key not in value:
            continue
        v = value[key]
        label = "search_space.%s" % key
        if kind[0] == "list":
            if not isinstance(v, list) or not v:
                raise ValueError("%s must be a nonempty list" % label)
            if kind[1] is int and not all(_is_int(x) for x in v):
                raise ValueError("%s must contain integers" % label)
            if kind[1] is str and not all(isinstance(x, str) and x for x in v):
                raise ValueError("%s must contain nonempty strings" % label)
        elif kind[0] == "int":
            if not _is_int(v):
                raise ValueError("%s must be an integer" % label)
        elif kind[0] == "optint":
            if v is not None and (not _is_int(v) or v < 0):
                raise ValueError("%s must be a nonnegative integer or null" % label)
        elif kind[0] == "optstr":
            if v is not None and (not isinstance(v, str) or not v):
                raise ValueError("%s must be a nonempty string or null" % label)
        elif kind[0] == "num":
            if not _is_num(v):
                raise ValueError("%s must be a number" % label)
        out[key] = v
    return out


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


def optional_str(args, key, max_chars):
    """String argument that may be absent; explicit null is an error."""
    value = args.get(key)
    if value is None:
        if key in args:
            raise ValueError("%s must be a string of 1..%d characters" % (key, max_chars))
        return None
    return bounded_str(value, key, max_chars)


def _mode_arg(args):
    mode = args.get("mode")
    if mode not in MODE_NAMES:
        raise ValueError("mode must be one of fast, efficient, balanced")
    return mode


SEARCH_SPACE_SCHEMA = {
    "type": "object",
    "properties": {
        "devices": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "threads": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
        "contexts": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
        "prompt_tokens": {"type": "integer", "minimum": 1},
        "gen_tokens": {"type": "integer", "minimum": 1},
        "warmup": {"type": "integer", "minimum": 0},
        "repeats": {"type": "integer", "minimum": 1},
        "batch": {"type": ["integer", "null"], "minimum": 0},
        "ubatch": {"type": ["integer", "null"], "minimum": 0},
        "energy_channel": {"type": ["string", "null"]},
        "temperature": {"type": "number"},
        "seed": {"type": "integer"},
    },
    "additionalProperties": False,
}

TOOLS = [
    {
        "name": "local_models",
        "description": (
            "List locally installed models, measured tuning profiles, approved "
            "modes from the gateway registry (with performance and quality "
            "calibration flags), the current recommendation, and tuning state. "
            "Call before other tools."),
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
            "and local_models shows a recommendation. Returns the applied "
            "runtime config (device, threads, context) with its evidence."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODE_NAMES),
                         "description": "Mode whose validated recommendation to apply."},
                "model_id": {"type": "string",
                             "description": "Optional specific model id; gateway validates it. "
                                            "Defaults to the registry's measured model for the mode."},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_tune",
        "description": (
            "Start a local device sweep via /api/tune for a model id, with an "
            "optional objective and an optional validated search_space object "
            "(exact gateway axes only; no free text, no arbitrary paths). "
            "Inference is paused while the sweep runs."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model id from local_models to sweep."},
                "objective": {"type": "string", "enum": list(OBJECTIVE_NAMES),
                              "description": "Tuning objective; gateway-validated."},
                "search_space": dict(SEARCH_SPACE_SCHEMA,
                                     description="Optional sweep search space; exact axes only."),
            },
            "required": ["model_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_secretary",
        "description": (
            "Run one verified secretary fixture task end to end via /api/run. "
            "Give either a free-form prompt or a gateway task_id (tNN) that "
            "selects a stored gold fixture; task_id alone runs and grades the "
            "stored prompt. Returns the applied runtime config, semantic "
            "correctness (passed), errors, and total task timing. One bounded "
            "task; the agent manages decomposition."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODE_NAMES),
                         "description": "Mode to run the verified task under."},
                "prompt": {"type": "string", "description": "Task request, 1..8000 characters. "
                                                           "Exactly one of prompt or task_id."},
                "task_id": {"type": "string", "pattern": "^t[0-9]{1,3}$",
                            "description": "Gateway task selector (e.g. t13) from the task list; "
                                           "runs and grades the stored gold prompt. "
                                           "Exactly one of prompt or task_id."},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
    },
]

# Strict argument-name enforcement against the declared schemas.
TOOL_ARG_KEYS = {t["name"]: frozenset(t["inputSchema"].get("properties", ()))
                 for t in TOOLS}


class MCPServer:
    def __init__(self, gateway=None, modes_config=None, stdin=None, stdout=None):
        self.gateway = gateway or Gateway()
        # Static fallback {mode: {"model_id": id}}, used only when the gateway
        # does not expose /api/modes. Every entry must name an explicit model
        # id; there is deliberately no default-model fallback here.
        self.modes_config = {m: v for m, v in (modes_config or {}).items() if m in MODE_NAMES}
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.initialized = False
        self._status_cache = None

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
        if self.initialized:
            return self.respond_error(id, -32600, "server already initialized")
        requested = (params or {}).get("protocolVersion")
        version = requested if requested == PROTOCOL_VERSION else PROTOCOL_VERSION
        self.initialized = True
        self.respond(id, {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    def handle_tools_call(self, id, params):
        if not self.initialized:
            return self.respond_error(id, -32002, "server not initialized")
        params = params if isinstance(params, dict) else {}
        name = params.get("name")
        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return self.respond_error(id, -32602, "params.arguments must be an object")
        self._begin_tool_call()
        try:
            allowed = TOOL_ARG_KEYS.get(name)
            if allowed is None:
                return self.respond_error(id, -32602, "unknown tool: %s" % name)
            unexpected = sorted(set(args) - allowed)
            if unexpected:
                raise ValueError("unexpected arguments: %s" % ", ".join(unexpected))
            if name == "local_models":
                result = self._tool_local_models(args)
            elif name == "local_run":
                result = self._tool_local_run(args)
            elif name == "local_apply":
                result = self._tool_local_apply(args)
            elif name == "local_tune":
                result = self._tool_local_tune(args)
            else:
                result = self._tool_local_secretary(args)
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
            return  # non-object frames are notifications; never a response
        method = msg.get("method")
        if method is None or "id" not in msg:
            return  # notifications and malformed frames get no response
        id = msg.get("id")
        if method == "initialize":
            return self.handle_initialize(id, msg.get("params"))
        if method == "notifications/initialized":
            return
        if method == "ping":
            return self.respond(id, {})
        if method == "tools/list":
            return self.respond(id, {"tools": TOOLS})
        if method == "tools/call":
            return self.handle_tools_call(id, msg.get("params"))
        self.respond_error(id, -32601, "method not found: %s" % method)

    def serve_forever(self):
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                # JSON-RPC requires a parse error response with id null.
                self.respond_error(None, JSONRPC_PARSE_ERROR, "parse error: line is not valid JSON")
                continue
            self.dispatch(msg)

    # ---- modes registry -------------------------------------------------
    def _resolve_modes_registry(self):
        """Return ({mode: entry}, raw payload or None, source)."""
        try:
            payload = self.gateway.get("/api/modes")
        except BackendError:
            static = {m: dict(v) for m, v in self.modes_config.items()}
            return static, None, "static_config_fallback"
        modes = {}
        entries = None
        if isinstance(payload, dict):
            entries = payload.get("modes")
            if entries is None:
                entries = payload
        if isinstance(entries, dict):
            modes = {k: v for k, v in entries.items()
                     if isinstance(k, str) and isinstance(v, dict)}
        elif isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    key = entry.get("mode") or entry.get("name")
                    if isinstance(key, str):
                        modes[key] = entry
        return modes, payload, "gateway"

    @staticmethod
    def _status_default_model(status):
        """Configured default model from /api/status; single-model fallback."""
        if not isinstance(status, dict):
            return None
        explicit = status.get("default_model")
        if isinstance(explicit, str) and explicit:
            return explicit
        applied = status.get("applied")
        if isinstance(applied, dict) and isinstance(applied.get("model"), str) and applied["model"]:
            return applied["model"]
        ids = [m.get("id") for m in status.get("models", [])
               if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]]
        return ids[0] if len(ids) == 1 else None

    def _record_model(self, payload, status):
        """Model id for the registry document; None when it identifies none.

        The /api/modes document describes one tuned model: v2 records name it
        with model_id; v1 recommended records carry only model_sha256, in
        which case the model resolves to the configured default from
        /api/status when the recommendation's hash matches the record's hash.
        """
        if not isinstance(payload, dict):
            return None
        model_id = payload.get("model_id")
        if isinstance(model_id, str) and model_id:
            return model_id
        sha = payload.get("model_sha256")
        if isinstance(sha, str) and sha:
            rec = status.get("recommendation") if isinstance(status, dict) else None
            if isinstance(rec, dict) and rec.get("model_sha256") == sha:
                return self._status_default_model(status)
        return None

    def _mode_entry_model(self, entry, payload, status, source="gateway"):
        """Model id for a registry entry; None when the record carries none.

        An entry may name the model directly only when the registry payload
        itself has no document-level identity (plain {mode: {...}} dicts).
        Once the document names the model, every mode entry shares that
        identity and a missing entry means the mode is genuinely unmapped.
        """
        # The static fallback never has document-level identity: a mode that
        # has no explicit entry there is unavailable, by design.
        source_has_identity = source == "gateway"
        if not isinstance(entry, dict):
            return None  # no measured point for this mode: unmapped
        for key in ("model", "model_id"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
        if source_has_identity and isinstance(payload, dict)                 and ("model_id" in payload or "model_sha256" in payload):
            return self._record_model(payload, status)
        return None

    def _resolve_mode_model(self, mode):
        """Return (model_id or None, registry, source) for a mode."""
        registry, payload, source = self._resolve_modes_registry()
        entry = registry.get(mode)
        return self._mode_entry_model(entry, payload, self._fetch_status(), source), registry, source

    def _fetch_status(self):
        """GET /api/status, memoized for one logical tool call.

        A single tool call may need the status payload several times (models,
        registry hash match, default model). The gateway is stateless between
        calls, so the memo is cleared before each logical operation.
        """
        if self._status_cache is None:
            self._status_cache = self.gateway.get("/api/status")
        return self._status_cache

    def _begin_tool_call(self):
        self._status_cache = None

    def _mode_unavailable(self, mode, registry, source):
        entry = registry.get(mode) or {}
        reason = entry.get("reason") if isinstance(entry, dict) else None
        reason = reason or ("no eligible measured profile is mapped to this mode; "
                            "refusing to substitute an unmeasured default")
        return {
            "available": False,
            "mode": mode,
            "mapping_source": source,
            "resolved_model": None,
            "reason": reason,
            "content": None,
            "usage": None,
        }

    # ---- tool implementations ------------------------------------------
    def _tool_local_models(self, args):
        status = self._fetch_status()
        registry, payload, source = self._resolve_modes_registry()
        rec = status.get("recommendation")
        scope = rec.get("scope") if isinstance(rec, dict) else None
        quality_calibrated = bool(isinstance(scope, dict) and scope.get("quality_calibrated"))
        modes = {}
        for m in MODE_NAMES:
            model = self._mode_entry_model(registry.get(m), payload, status, source)
            modes[m] = {
                "available": model is not None,
                "model_id": model,
                "performance_calibrated": model is not None,
                "quality_calibrated": quality_calibrated,
                "source": source if model is not None else None,
            }
        return {
            "runtime_available": status.get("runtime_available"),
            "models": status.get("models", []),
            "profiles": status.get("profiles", []),
            "recommendation": rec,
            "tuning": status.get("tuning"),
            "modes": modes,
        }

    def _tool_local_run(self, args):
        mode = _mode_arg(args)
        messages = validate_messages(args.get("messages"))
        requested_model = optional_str(args, "model", MAX_LABEL_CHARS)
        max_tokens = args.get("max_tokens", 256)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) \
                or not (1 <= max_tokens <= MAX_TOKENS):
            raise ValueError("max_tokens must be an integer 1..%d" % MAX_TOKENS)
        task_id = optional_str(args, "task_id", MAX_LABEL_CHARS)

        evidence = {"mode": mode, "requested_model": requested_model, "mapping_source": None}
        model = requested_model
        if model is None:
            model, registry, source = self._resolve_mode_model(mode)
            evidence["mapping_source"] = source
            if model is None:
                return self._mode_unavailable(mode, registry, source)
        else:
            evidence["mapping_source"] = "explicit_request"
        evidence["resolved_model"] = model

        # The parent derives the routing mode from body["mode"]; omitting it
        # silently ran every request under the fast default.
        completion = self.gateway.post(
            "/v1/chat/completions",
            {"mode": mode, "messages": messages, "max_tokens": max_tokens, "model": model})
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
        model_id = optional_str(args, "model_id", MAX_LABEL_CHARS)
        body = {"mode": mode}
        if model_id is not None:
            body["model_id"] = model_id
        else:
            resolved, _, _ = self._resolve_mode_model(mode)
            if resolved is not None:
                body["model_id"] = resolved
        start = time.monotonic()
        resp = self.gateway.post("/api/apply", body)
        elapsed_s = time.monotonic() - start
        applied_model = resp.get("model") if isinstance(resp, dict) else None
        return {
            "applied": bool(resp.get("applied", True)),
            "mode": resp.get("mode") or mode,
            "model_id": applied_model or model_id or body.get("model_id"),
            "runtime": resp.get("config") if isinstance(resp, dict) else None,
            "evidence": resp.get("evidence") if isinstance(resp, dict) else None,
            "elapsed_s": elapsed_s,
            "gateway_response": resp,
        }

    def _tool_local_tune(self, args):
        model_id = optional_str(args, "model_id", MAX_LABEL_CHARS)
        if model_id is None:
            raise ValueError("model_id must be a nonempty string")
        objective = optional_str(args, "objective", MAX_OBJECTIVE_CHARS)
        if objective is not None and objective not in OBJECTIVE_NAMES:
            raise ValueError("objective must be one of %s" % ", ".join(OBJECTIVE_NAMES))
        search_space = validate_search_space(args.get("search_space"))
        known = {m.get("id") for m in self._fetch_status().get("models", [])}
        if model_id not in known:
            raise ValueError("unknown model_id: %s; call local_models first" % model_id)
        body = {"model_id": model_id}
        if objective is not None:
            body["objective"] = objective
        if search_space is not None:
            body["search_space"] = search_space
        start = time.monotonic()
        resp = self.gateway.post("/api/tune", body)
        elapsed_s = time.monotonic() - start
        return {"accepted": True, "requested": body, "gateway_response": resp, "elapsed_s": elapsed_s}

    def _tool_local_secretary(self, args):
        mode = _mode_arg(args)
        prompt = optional_str(args, "prompt", MAX_PROMPT_CHARS)
        task_id = optional_str(args, "task_id", MAX_LABEL_CHARS)
        if (prompt is None) == (task_id is None):
            raise ValueError("exactly one of prompt or task_id is required")
        if prompt is not None and not prompt.strip():
            raise ValueError("prompt must not be blank")
        if task_id is not None:
            # task_id is a gateway gold-fixture task selector, never an
            # arbitrary correlation id; verify it exists before running.
            if not TASK_ID_RE.fullmatch(task_id):
                raise ValueError("task_id must be a gateway task selector like t13")
            known = {t.get("id") for t in self.gateway.get("/api/tasks") if isinstance(t, dict)}
            if task_id not in known:
                raise ValueError("unknown task_id: %s" % task_id)
        body = {"mode": mode}
        if prompt is not None:
            body["prompt"] = prompt
        else:
            body["task_id"] = task_id
        start = time.monotonic()
        resp = self.gateway.post("/api/run", body)
        gateway_elapsed_s = time.monotonic() - start
        applied = resp.get("applied") if isinstance(resp, dict) else None
        runtime_config = applied if isinstance(applied, dict) else None
        resolved_model = resp.get("model")
        if resolved_model is None and isinstance(runtime_config, dict):
            resolved_model = runtime_config.get("model")
        content = resp.get("content")
        if content is None and isinstance(resp, dict):
            content = resp.get("text")
        profile = resp.get("profile") if isinstance(resp, dict) else None
        usage = resp.get("usage")
        if usage is None and isinstance(profile, dict):
            usage = {"prompt_tokens": profile.get("prompt_tokens"),
                     "completion_tokens": profile.get("generated_tokens")}
        return {
            "available": True,
            "mode": resp.get("mode") or mode,
            "task_id": resp.get("task_id") or task_id,
            "resolved_model": resolved_model,
            "content": content,
            "result": resp.get("result") if isinstance(resp, dict) else None,
            "passed": resp.get("passed") if isinstance(resp, dict) else None,
            "errors": resp.get("errors") if isinstance(resp, dict) else None,
            "verification": resp.get("verification") if isinstance(resp, dict) else None,
            "usage": usage,
            "runtime_config": runtime_config,
            "elapsed_s": resp.get("elapsed_s") if isinstance(resp, dict) else None,
            "gateway_elapsed_s": gateway_elapsed_s,
            "gateway_response": resp,
        }


def main():
    base_url = os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL)
    MCPServer(Gateway(base_url)).serve_forever()


if __name__ == "__main__":
    main()
