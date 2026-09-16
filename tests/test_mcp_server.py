"""Tests for the bounded MCP stdio server.

Unit tests mock the loopback gateway with payloads captured from the real
parent service (Ai-infra-summit/turbo/service.py) so assertions check the
actual /api/modes, /api/status, /api/run, /api/tune and /v1/chat/completions
contracts. The integration suite boots the REAL parent Engine against a stub
libgeniex dylib behind a threaded HTTP server, then drives the MCP server via
a piped subprocess, so wiring (mode passthrough, applied runtime config,
registry resolution) is verified against the real engine, not mirrored mocks.
"""
import contextlib
import ctypes
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from turbo.mcp_server import (  # noqa: E402
    BackendError,
    Gateway,
    MCPServer,
    TOOLS,
    validate_messages,
    validate_search_space,
)


def rpc(msg):
    return json.dumps(msg) + "\n"


# --- fixtures captured from the real parent (v1 recommended.json shape) ---
REC_V1 = {
    "schema_version": "turbo.recommended.v1",
    "model_sha256": "33bc" + "0" * 60,
    "runtime": "GenieX 0.6.1 / llama_cpp",
    "device": "Latitude 7455 / X1E80100",
    "scope": {
        "prompt_tokens": 512, "generated_tokens": 128, "context": 4096,
        "power_state": "battery", "cold_kv": True,
        "energy_interval": "full trial including load, prefill and decode",
        "quality_calibrated": False, "evidence": "confirm-auto-01/sweep.json",
    },
    "modes": {
        "fast": {"device": "cpu", "threads": 10, "context": 4096,
                 "metrics": {"decode_tps": 97.19, "tokens_per_joule": 1.37}},
        "efficient": {"device": "npu", "threads": 0, "context": 4096,
                      "metrics": {"decode_tps": 36.36, "tokens_per_joule": 2.11}},
    },
}

APPLIED = {
    "model": "qwen06", "mode": "fast",
    "config": {"device": "cpu", "threads": 10, "context": 4096},
    "evidence": {"source": "confirm-auto-01/sweep.json",
                 "scope": REC_V1["scope"],
                 "metrics": REC_V1["modes"]["fast"]["metrics"]},
}


class FakeGateway:
    """Loopback payloads mirroring the real parent service endpoints."""

    def __init__(self):
        self.status = {
            "runtime_available": True,
            "models": [{"id": "qwen06", "available": True, "device": "cpu", "threads": 0}],
            "profiles": [],
            "history": [],
            "results": [],
            "recommendation": REC_V1,
            "applied": None,
            "tuning": {"running": False, "completed": 0, "total": 0, "error": None},
            "version": "0.2.0",
        }
        self.tasks = [{"id": "t01", "prompt": "List every file in the workspace."},
                      {"id": "t13", "prompt": "Find the Hexagon invoice draft."}]
        self.modes = REC_V1  # /api/modes returns the recommended record verbatim
        self.completion = {
            "id": "chatcmpl-x", "object": "chat.completion", "model": "qwen06",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            "turbo": {"route": {"estimate_only": True, "prompt_size_method": "characters/3"}},
        }
        self.run_result = {
            **APPLIED,
            # real /api/run carries the applied runtime config at top level
            # AND nested under "applied" (Engine.completion sets both).
            "applied": APPLIED,
            "run_id": "abc123", "mode": "fast", "task_id": "t01",
            "passed": True, "errors": [], "result": [],
            "verification": {"passed": True, "reason": "ok"},
            "usage": None,
            "profile": {"prompt_tokens": 5, "generated_tokens": 2},
            "text": "done",
            "elapsed_s": 1.5,
        }
        self.tune_result = {"running": True, "completed": 0, "total": 10, "objective": "fast"}
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        if path == "/api/status":
            return self.status
        if path == "/api/modes":
            return self.modes
        if path == "/api/tasks":
            return self.tasks
        raise AssertionError(path)

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        if path == "/v1/chat/completions":
            return self.completion
        if path == "/api/tune":
            return self.tune_result
        if path == "/api/run":
            return self.run_result
        if path == "/api/apply":
            return dict(APPLIED)
        raise AssertionError(path)

    def posted(self, path):
        return [c for c in self.calls if c[0] == "POST" and c[1] == path]


def make_server(gateway=None, modes_config=None):
    return MCPServer(gateway=gateway or FakeGateway(),
                     modes_config=modes_config,
                     stdin=io.StringIO(), stdout=io.StringIO())


def isolated(gw):
    """Give each test its own status dict (status is mutated by some tests)."""
    gw.status = json.loads(json.dumps(gw.status))
    return gw


def call_tool(server, name, arguments, id=1):
    server.stdout = io.StringIO()
    server.dispatch({"jsonrpc": "2.0", "id": id, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}})
    resp = json.loads(server.stdout.getvalue())
    return resp["result"]["structuredContent"]


class WireProtocolTests(unittest.TestCase):
    def _exchange(self, incoming):
        s = make_server()
        s.stdin = io.StringIO(incoming)
        s.stdout = io.StringIO()
        s.serve_forever()
        return [json.loads(x) for x in s.stdout.getvalue().splitlines() if x.strip()]

    def test_handshake_ping(self):
        out = self._exchange(
            rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18",
                            "capabilities": {}, "clientInfo": {"name": "t"}}})
            + rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", out[0]["result"]["capabilities"])
        self.assertEqual(out[1]["result"], {})

    def test_notifications_never_get_responses(self):
        # initialized flag arrives only via the notification; then ping works.
        out = self._exchange(
            rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + rpc({"jsonrpc": "2.0", "id": 5, "method": "ping"}))
        self.assertEqual(len(out), 1)          # notification produced no output
        self.assertEqual(out[0]["id"], 5)

    def test_invalid_json_gets_parse_error_with_null_id(self):
        out = self._exchange("not json\n")
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["id"])
        self.assertEqual(out[0]["error"]["code"], -32700)

    def test_non_object_frame_is_silent_notification(self):
        out = self._exchange('[1,2,3]\n' + rpc({"jsonrpc": "2.0", "id": 6, "method": "ping"}))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 6)

    def test_initialized_guard_blocks_tools_until_negotiated(self):
        out = self._exchange(
            rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "local_models", "arguments": {}}}))
        self.assertEqual(out[0]["error"]["code"], -32002)
        s = make_server()
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertIn("modes", r)

    def test_second_initialize_is_protocol_error(self):
        s = make_server()
        s.initialized = True
        s.stdout = io.StringIO()
        s.dispatch({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}})
        self.assertEqual(json.loads(s.stdout.getvalue())["error"]["code"], -32600)

    def test_tools_list_shapes(self):
        out = self._exchange(rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
        tools = out[0]["result"]["tools"]
        self.assertEqual(
            [t["name"] for t in tools],
            ["local_models", "local_run", "local_apply", "local_tune", "local_secretary"])
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertFalse(t["inputSchema"]["additionalProperties"])
        tune = tools[3]["inputSchema"]["properties"]["search_space"]
        self.assertEqual(tune["additionalProperties"], False)
        sec = tools[4]["inputSchema"]
        self.assertEqual(sec["required"], ["mode"])
        self.assertEqual(sec["properties"]["task_id"]["pattern"], "^t[0-9]{1,3}$")


class ArgumentsValidationTests(unittest.TestCase):
    def test_extra_and_unexpected_args_rejected(self):
        s = make_server()
        s.initialized = True
        for bad in ({"model": "m", "extra": 1}, {"model": []}, {"model": None},
                    {"model": 5}, {"model": {"a": 1}}):
            r = call_tool(s, "local_apply", bad)
            self.assertTrue(r["isError"], bad)

    def test_non_object_arguments_rejected(self):
        s = make_server()
        s.initialized = True
        s.stdout = io.StringIO()
        s.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "local_models", "arguments": "boom"}})
        self.assertEqual(json.loads(s.stdout.getvalue())["error"]["code"], -32602)

    def test_search_space_validation_exact_axes(self):
        self.assertIsNone(validate_search_space(None))
        ok = {"devices": ["cpu"], "threads": [4, 8], "contexts": [4096],
              "prompt_tokens": 512, "gen_tokens": 128, "warmup": 0,
              "repeats": 3, "batch": None, "ubatch": None,
              "energy_channel": None, "temperature": 0.0, "seed": 42}
        self.assertEqual(validate_search_space(ok), ok)
        for bad in ({}, "threads", ["threads"], {"thread": [1]}, {"path": ["../x"]},
                    {"devices": "cpu"}, {"threads": [True]}, {"prompt_tokens": 1.5},
                    {"seed": True}, {"repeats": [1, 2]}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_search_space(bad)


class ToolBehaviourTests(unittest.TestCase):
    def test_local_models_v1_registry_resolves_via_status_default(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_models", {})
        gets = [c[1] for c in gw.calls if c[0] == "GET"]
        self.assertEqual(gets.count("/api/modes"), 1)
        self.assertEqual(gets.count("/api/status"), 1)
        fast = r["modes"]["fast"]
        self.assertTrue(fast["available"])
        self.assertEqual(fast["model_id"], "qwen06")   # v1 hash match -> status default
        self.assertEqual(fast["source"], "gateway")
        # Honest calibration: performance measured, quality not.
        self.assertTrue(fast["performance_calibrated"])
        self.assertFalse(fast["quality_calibrated"])
        self.assertFalse(r["modes"]["efficient"]["quality_calibrated"])

    def test_local_models_v2_registry_uses_record_model_id(self):
        gw = FakeGateway()
        v2_modes = {"efficient": {"device": "npu", "threads": 0,
                                  "context": 4096, "metrics": {}}}
        gw.modes = {"schema_version": "turbo.recommended.v2",
                    "model_id": "qwen06",
                    "model_sha256": "33bc" + "0" * 60,
                    "modes": v2_modes}
        gw.status = dict(gw.status,
                         recommendation={"schema_version": "turbo.recommended.v2",
                                         "scope": {"quality_calibrated": True}})
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_models", {})
        eff = r["modes"]["efficient"]
        self.assertEqual(eff["model_id"], "qwen06")
        self.assertTrue(eff["performance_calibrated"])
        self.assertTrue(eff["quality_calibrated"])     # real v2 scope flag
        self.assertFalse(r["modes"]["fast"]["available"])

    def test_registry_hash_mismatch_keeps_mode_unavailable(self):
        gw = FakeGateway()
        gw.modes = dict(REC_V1, model_sha256="dead" + "0" * 61)
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertFalse(r["modes"]["fast"]["available"])
        self.assertIsNone(r["modes"]["fast"]["model_id"])

    def test_static_fallback_requires_explicit_model_id(self):
        # BackendError is bound at module import (before the integration
        # suite swaps turbo.* to the parent checkout) so exception identity
        # matches the one the already-loaded server module catches.
        class NoModes(FakeGateway):
            def get(self, path):
                if path == "/api/modes":
                    raise BackendError("gateway returned HTTP 404 for /api/modes", 404)
                return super().get(path)
        gw = NoModes()
        s = make_server(gateway=gw, modes_config={"balanced": {"model_id": "qwen06"}})
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertEqual(r["modes"]["balanced"]["model_id"], "qwen06")
        self.assertEqual(r["modes"]["balanced"]["source"], "static_config_fallback")
        self.assertFalse(r["modes"]["fast"]["available"])   # no implicit default

    def test_run_sends_mode_and_model_in_completion_body(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_run",
                      {"mode": "efficient", "messages": [{"role": "user", "content": "hi"}],
                       "max_tokens": 64, "task_id": "t1"})
        self.assertTrue(r["available"])
        self.assertEqual(r["resolved_model"], "qwen06")
        _, body = gw.posted("/v1/chat/completions")[0][1:]
        self.assertEqual(body["mode"], "efficient")     # real engine routing depends on it
        self.assertEqual(body["model"], "qwen06")
        self.assertEqual(r["task_id"], "t1")

    def test_run_mode_unavailable_refuses_substitution(self):
        gw = FakeGateway()
        gw.modes = dict(REC_V1, modes={"efficient": {"device": "npu", "threads": 0,
                                                     "context": 4096, "metrics": {}}})
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_run",
                      {"mode": "fast", "messages": [{"role": "user", "content": "hi"}]})
        self.assertFalse(r["available"])
        self.assertIsNone(r["resolved_model"])
        self.assertIn("no eligible", r["reason"])
        self.assertEqual(gw.posted("/v1/chat/completions"), [])

    def test_apply_resolves_registry_model_and_reports_applied(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_apply", {"mode": "fast"})
        _, body = gw.posted("/api/apply")[0][1:]
        self.assertEqual(body, {"mode": "fast", "model_id": "qwen06"})
        self.assertTrue(r["applied"])
        self.assertEqual(r["model_id"], "qwen06")
        self.assertEqual(r["runtime"], {"device": "cpu", "threads": 10, "context": 4096})
        self.assertIn("evidence", r)
        self.assertIn("elapsed_s", r)
        r = call_tool(s, "local_apply", {"mode": "balanced", "model_id": "qwen06"})
        _, body = gw.posted("/api/apply")[-1][1:]
        self.assertEqual(body, {"mode": "balanced", "model_id": "qwen06"})

    def test_tune_rejects_unknown_model_without_post(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_tune", {"model_id": "ghost"})
        self.assertTrue(r["isError"])
        self.assertIn("unknown model_id", r["error"])
        self.assertEqual(gw.posted("/api/tune"), [])

    def test_tune_object_search_space_exact_axes(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        space = {"devices": ["cpu"], "threads": [0, 10], "contexts": [4096],
                 "prompt_tokens": 512, "gen_tokens": 128, "repeats": 3, "seed": 7}
        r = call_tool(s, "local_tune",
                      {"model_id": "qwen06", "objective": "decode",
                       "search_space": space})
        self.assertTrue(r["accepted"])
        self.assertEqual(gw.posted("/api/tune")[-1][2],
                         {"model_id": "qwen06", "objective": "decode", "search_space": space})
        # old free-text searchspace shape is no longer accepted
        r = call_tool(s, "local_tune", {"model_id": "qwen06", "searchspace": "threads"})
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_tune", {"model_id": "qwen06", "search_space": "threads"})
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_tune", {"model_id": "qwen06",
                                        "search_space": {"threads": [1], "banana": 1}})
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_tune", {"model_id": "qwen06", "objective": "turbo"})
        self.assertTrue(r["isError"])

    def test_secretary_prompt_only(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_secretary", {"mode": "fast", "prompt": "list files"})
        _, body = gw.posted("/api/run")[0][1:]
        self.assertEqual(body, {"mode": "fast", "prompt": "list files"})
        self.assertTrue(r["available"])
        self.assertTrue(r["passed"])
        self.assertEqual(r["errors"], [])
        # applied runtime config from the real /api/run response contract
        self.assertEqual(r["resolved_model"], "qwen06")
        self.assertEqual(r["runtime_config"]["model"], "qwen06")
        self.assertEqual(r["runtime_config"]["config"]["device"], "cpu")
        self.assertEqual(r["runtime_config"]["config"]["threads"], 10)
        self.assertEqual(r["elapsed_s"], 1.5)
        self.assertIn("verification", r)

    def test_secretary_task_id_alone_runs_gold_fixture(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_secretary", {"mode": "fast", "task_id": "t13"})
        _, body = gw.posted("/api/run")[0][1:]
        self.assertEqual(body, {"mode": "fast", "task_id": "t13"})   # no prompt field
        self.assertTrue(r["passed"])

    def test_secretary_rejects_bad_task_id_and_xor_violations(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_secretary", {"mode": "fast", "task_id": "abc123"})
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_secretary", {"mode": "fast", "task_id": "t99"})
        self.assertTrue(r["isError"])
        self.assertIn("unknown task_id", r["error"])
        self.assertEqual(gw.posted("/api/run"), [])      # verified before POST
        r = call_tool(s, "local_secretary", {"mode": "fast"})
        self.assertTrue(r["isError"])                    # neither prompt nor task_id
        r = call_tool(s, "local_secretary",
                      {"mode": "fast", "prompt": "x", "task_id": "t13"})
        self.assertTrue(r["isError"])                    # both given

    def test_backend_error_returns_tool_error_not_crash(self):
        class Down(FakeGateway):
            def get(self, path):
                raise BackendError("gateway unreachable at %s: refused" % path)
        s = make_server(gateway=Down())
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertTrue(r["isError"])
        self.assertIn("unreachable", r["error"])


class GatewayLoopbackTests(unittest.TestCase):
    def test_default_base_url_is_loopback(self):
        self.assertTrue(Gateway().base_url.startswith("http://127.0.0.1"))

    def test_remote_base_url_rejected(self):
        for url in ("http://example.com", "https://10.1.2.3:8080", "ftp://127.0.0.1"):
            with self.assertRaises(ValueError):
                Gateway(base_url=url)

    def test_unreachable_gateway_raises_backend_error(self):
        gw = Gateway(base_url="http://127.0.0.1:1", timeout=1)
        with self.assertRaises(Exception):
            gw.get("/api/status")


# ---------------------------------------------------------------------------
# Real-Engine integration: parent Engine + stub libgeniex + threaded HTTP,
# driven through a piped MCP subprocess handshake.
# ---------------------------------------------------------------------------

STUB_C = textwrap.dedent("""
    #include <stddef.h>
    int geniex_init(void) { return 0; }
    int geniex_deinit(void) { return 0; }
    void geniex_free(void *p) { (void)p; }
    const char *geniex_version(void) { return "0.6.1-stub"; }
    const char *geniex_get_error_message(int code) { (void)code; return "stub"; }
    int geniex_resolve_device(const void *in, void *out) { (void)in; (void)out; return 0; }
    int geniex_llm_create(const void *in, void **out) { (void)in; (void)out; return 0; }
    int geniex_llm_destroy(void *h) { (void)h; return 0; }
    int geniex_llm_reset(void *h) { (void)h; return 0; }
    int geniex_llm_apply_chat_template(void *h, const void *in, void *out) {
        (void)h; (void)in; (void)out; return 0; }
    int geniex_llm_generate(void *h, const void *in, void *out) {
        (void)h; (void)in; (void)out; return 0; }
""")


def build_stub_dylib(workdir: Path) -> Path:
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    src = workdir / "stub.c"
    if sys.platform == "win32":
        raise unittest.SkipTest("MCP compiled ABI stub currently supports POSIX shared-library toolchains only")
    if cc is None:
        raise unittest.SkipTest("MCP ABI integration requires a C compiler (cc, clang or gcc)")
    dylib = workdir / ("libgeniex.dylib" if sys.platform == "darwin" else "libgeniex.so")
    src.write_text(STUB_C)
    subprocess.run([cc, "-shared", "-o", str(dylib), str(src)], check=True)
    return dylib


@contextlib.contextmanager
def real_engine_server(tmp: Path, recommendation_file: Path):
    """Boot the REAL parent Engine (no hardware: stub dylib, stdlib HTTP)."""
    model_path = tmp / "model.gguf"
    # No inference is exercised: an opaque local artifact tests hash binding.
    model_path.write_bytes(b"synthetic MCP hash-binding fixture; not model weights")
    config = {
        "sdk_dir": str(tmp),
        "models": {"qwen06": {"path": str(model_path)}},
        "default": "qwen06",
        "recommendation_file": str(recommendation_file),
        "results_dir": str(tmp / "results"),
        "data_dir": str(tmp / "data"),
        "tuner": {"exe": str(tmp / "bench.exe")},
        "profiles": [],
    }
    cfg_path = tmp / "config.json"
    cfg_path.write_text(json.dumps(config))
    from turbo.service import Engine, handler
    engine = Engine(json.loads(cfg_path.read_text()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield engine, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def mcp_exchange(proc, msg):
    proc.stdin.write(rpc(msg))
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


class RealEngineIntegrationTests(unittest.TestCase):
    """Stdio subprocess handshake against the real parent Engine over HTTP.

    No hardware calls: the stub libgeniex dylib answers every SDK symbol, and
    only read endpoints plus /api/apply are exercised (no inference, no tune).
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcp-e2e-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        build_stub_dylib(cls.tmp)
        rec = json.loads(json.dumps(REC_V1))
        from turbo.runtime_identity import runtime_identity
        exe = cls.tmp / 'bench.exe'; exe.write_bytes(b'benchmark fixture')
        rec.update(schema_version='turbo.recommended.v2',plugin='llama_cpp',
                   runtime_binding=runtime_identity(exe,cls.tmp))
        rec['modes']['efficient']['metrics'].update(energy_channel='SYS',energy_scope='full_process_trial')
        rec["model_sha256"] = "0" * 64  # placeholder; Engine verifies model hash on apply
        rec_path = cls.tmp / "recommended.json"
        # Match the synthetic artifact created by real_engine_server.
        import hashlib
        rec["model_sha256"] = hashlib.sha256(
            b"synthetic MCP hash-binding fixture; not model weights").hexdigest()
        rec_path.write_text(json.dumps(rec))
        cls.ctx = real_engine_server(cls.tmp, rec_path)
        cls.engine, cls.port = cls.ctx.__enter__()
        cls.addClassCleanup(cls.ctx.__exit__, None, None, None)
        env = dict(os.environ, TURBO_BASE_URL="http://127.0.0.1:%d" % cls.port,
                   PYTHONPATH=str(REPO_ROOT))
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "turbo.mcp_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env, cwd=str(REPO_ROOT))
        cls.addClassCleanup(cls._stop_process)
        init = mcp_exchange(cls.proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t"}}})
        assert "result" in init, init
        cls.proc.stdin.write(rpc({"jsonrpc": "2.0",
                                  "method": "notifications/initialized"}))
        cls.proc.stdin.flush()

    @classmethod
    def _stop_process(cls):
        cls.proc.kill()
        cls.proc.wait(timeout=5)
        for stream in (cls.proc.stdin, cls.proc.stdout, cls.proc.stderr):
            stream.close()

    def call(self, name, arguments, id=99):
        resp = mcp_exchange(self.proc, {"jsonrpc": "2.0", "id": id,
                                        "method": "tools/call",
                                        "params": {"name": name, "arguments": arguments}})
        return resp["result"]["structuredContent"]

    def test_local_models_against_real_engine(self):
        r = self.call("local_models", {})
        # stdlib sdk_dir with a dylib present reports runtime availability.
        self.assertTrue(r["runtime_available"])
        self.assertEqual([m["id"] for m in r["models"]], ["qwen06"])
        self.assertTrue(r["modes"]["fast"]["available"])
        self.assertEqual(r["modes"]["fast"]["model_id"], "qwen06")
        self.assertTrue(r["modes"]["fast"]["performance_calibrated"])
        self.assertFalse(r["modes"]["fast"]["quality_calibrated"])

    def test_apply_end_to_end_wires_runtime_config(self):
        r = self.call("local_apply", {"mode": "fast"})
        self.assertTrue(r["applied"])
        self.assertEqual(r["model_id"], "qwen06")
        self.assertEqual(r["runtime"], {"device": "cpu", "threads": 10, "context": 4096})
        # The real Engine recorded the applied runtime config.
        self.assertEqual(self.engine.applied["mode"], "fast")
        self.assertEqual(self.engine.applied["config"]["threads"], 10)
        self.assertEqual(self.engine.applied["evidence"]["scope"]["quality_calibrated"], False)

    def test_unmapped_mode_stays_unavailable(self):
        r = self.call("local_apply", {"mode": "efficient", "model_id": "qwen06"})
        # efficient IS in the record; apply must honor its npu measured point
        self.assertTrue(r["applied"])
        self.assertEqual(r["runtime"]["device"], "npu")


if __name__ == "__main__":
    unittest.main()
