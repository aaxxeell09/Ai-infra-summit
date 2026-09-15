"""Tests for the bounded MCP stdio server (mocked gateway)."""
import io
import json
import unittest

from turbo.mcp_server import (
    Gateway,
    MCPServer,
    validate_messages,
)


def rpc(msg):
    return json.dumps(msg) + "\n"


class FakeGateway:
    def __init__(self):
        self.status = {
            "runtime_available": True,
            "models": [{"id": "m1", "available": True, "device": "cpu", "threads": 4}],
            "profiles": [{"name": "p1", "model": "m1", "decode_tps": 10.0}],
            "recommendation": {"id": "cell1", "decode_tps": 10.0},
            "tuning": {"running": False, "completed": 0, "total": 10, "error": None},
        }
        self.modes = {
            "fast": {"model": "m1", "calibrated": True},
            "efficient": None,
        }
        self.completion = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "m1",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            "turbo": {"route": {"estimate_only": True, "prompt_size_method": "characters/3"}},
        }
        self.run_result = {
            "mode": "fast",
            "passed": True,
            "errors": [],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            "runtime_config": {"model": "m1", "device": "cpu"},
            "elapsed_s": 1.5,
            "result": {"answer": "42"},
        }
        self.tune_result = {"running": True, "completed": 0, "total": 10}
        self.apply_result = {"applied": True, "mode": "fast", "model_id": "m1"}
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        if path == "/api/status":
            return self.status
        if path == "/api/modes":
            return {"modes": self.modes}
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
            return self.apply_result
        raise AssertionError(path)


def make_server(gateway=None, modes_config=None):
    return MCPServer(gateway=gateway or FakeGateway(),
                     modes_config=modes_config,
                     stdin=io.StringIO(), stdout=io.StringIO())


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

    def test_handshake_ping_initialized(self):
        out = self._exchange(
            rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18",
                            "capabilities": {}, "clientInfo": {"name": "t"}}})
            + rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", out[0]["result"]["capabilities"])
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "turbo-mcp")
        self.assertEqual(out[1]["result"], {})

    def test_initialize_negotiates_unsupported_version(self):
        out = self._exchange(
            rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "1999-01-01"}}))
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")

    def test_tools_list_exposes_five_tools_with_schemas(self):
        out = self._exchange(rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
        tools = out[0]["result"]["tools"]
        self.assertEqual(
            [t["name"] for t in tools],
            ["local_models", "local_run", "local_apply", "local_tune", "local_secretary"])
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertFalse(t["inputSchema"]["additionalProperties"])
        run = tools[1]["inputSchema"]
        self.assertEqual(run["required"], ["mode", "messages"])
        self.assertEqual(run["properties"]["mode"]["enum"], ["fast", "efficient", "balanced"])
        self.assertEqual(run["properties"]["max_tokens"]["maximum"], 2048)
        sec = tools[4]["inputSchema"]
        self.assertEqual(sec["required"], ["mode", "prompt"])

    def test_tools_call_before_init_is_protocol_error(self):
        s = make_server()
        s.stdout = io.StringIO()
        s.dispatch({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                    "params": {"name": "local_models", "arguments": {}}})
        resp = json.loads(s.stdout.getvalue())
        self.assertEqual(resp["error"]["code"], -32002)

    def test_unknown_tool_and_method(self):
        s = make_server()
        s.initialized = True
        s.stdout = io.StringIO()
        s.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "nope", "arguments": {}}})
        self.assertEqual(json.loads(s.stdout.getvalue())["error"]["code"], -32602)
        s.stdout = io.StringIO()
        s.dispatch({"jsonrpc": "2.0", "id": 2, "method": "no/such"})
        self.assertEqual(json.loads(s.stdout.getvalue())["error"]["code"], -32601)

    def test_malformed_line_skipped(self):
        out = self._exchange("not json\n" + rpc({"jsonrpc": "2.0", "id": 4, "method": "ping"}))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["result"], {})


class ValidationTests(unittest.TestCase):
    def test_messages_validation(self):
        with self.assertRaises(ValueError):
            validate_messages([])
        with self.assertRaises(ValueError):
            validate_messages([{"role": "root", "content": "x"}])
        with self.assertRaises(ValueError):
            validate_messages([{"role": "user", "content": ""}])
        with self.assertRaises(ValueError):
            validate_messages([{"role": "user", "content": "x" * 65_000}])
        self.assertEqual(validate_messages([{"role": "user", "content": "hi"}]),
                         [{"role": "user", "content": "hi"}])

    def test_invalid_mode_and_max_tokens(self):
        s = make_server()
        s.initialized = True
        base = {"messages": [{"role": "user", "content": "hi"}]}
        r = call_tool(s, "local_run", dict(base, mode="turbo"))
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_run", dict(base, mode="fast", max_tokens=0))
        self.assertTrue(r["isError"])
        self.assertIn("max_tokens", r["error"])
        r = call_tool(s, "local_run", dict(base, mode="fast", max_tokens=2049))
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_run", dict(base, mode="fast", max_tokens=True))
        self.assertTrue(r["isError"])

    def test_oversized_prompt_rejected(self):
        s = make_server()
        s.initialized = True
        r = call_tool(s, "local_secretary", {"mode": "fast", "prompt": "x" * 8001})
        self.assertTrue(r["isError"])
        r = call_tool(s, "local_secretary", {"mode": "fast", "prompt": "   "})
        self.assertTrue(r["isError"])


class ToolBehaviourTests(unittest.TestCase):
    def test_local_models_reports_gateway_registry(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertTrue(r["runtime_available"])
        self.assertEqual(r["models"][0]["id"], "m1")
        self.assertTrue(r["modes"]["fast"]["calibrated"])
        self.assertEqual(r["modes"]["fast"]["eligible_model"], "m1")
        self.assertFalse(r["modes"]["efficient"]["calibrated"])
        self.assertEqual(gw.calls[0][1], "/api/status")

    def test_local_models_falls_back_to_static_config(self):
        from turbo.mcp_server import BackendError

        class NoModes(FakeGateway):
            def get(self, path):
                if path == "/api/modes":
                    raise BackendError("gateway returned HTTP 404 for /api/modes", 404)
                return super().get(path)
        gw = NoModes()
        s = make_server(gateway=gw, modes_config={"balanced": {"model": "m1"}})
        s.initialized = True
        r = call_tool(s, "local_models", {})
        self.assertTrue(r["modes"]["balanced"]["calibrated"])
        self.assertEqual(r["modes"]["balanced"]["source"], "static_config_fallback")
        self.assertFalse(r["modes"]["fast"]["calibrated"])

    def test_run_resolves_mode_via_registry(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_run",
                      {"mode": "fast", "messages": [{"role": "user", "content": "hi"}],
                       "max_tokens": 64, "task_id": "t1"})
        self.assertTrue(r["available"])
        self.assertEqual(r["resolved_model"], "m1")
        self.assertEqual(r["task_id"], "t1")
        self.assertEqual(r["usage"]["prompt_tokens"], 3)
        self.assertTrue(r["estimate_only"])  # estimate labeled as estimate
        method, path, body = gw.calls[-1]
        self.assertEqual((method, path), ("POST", "/v1/chat/completions"))
        self.assertEqual(body["model"], "m1")

    def test_run_mode_unavailable_refuses_substitution(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_run",
                      {"mode": "efficient", "messages": [{"role": "user", "content": "hi"}]})
        self.assertFalse(r["available"])
        self.assertIsNone(r["resolved_model"])
        self.assertIn("no eligible", r["reason"])
        self.assertNotIn(("POST", "/v1/chat/completions"),
                         [(c[0], c[1]) for c in gw.calls])

    def test_run_explicit_model_bypasses_registry(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_run",
                      {"mode": "fast", "model": "m1",
                       "messages": [{"role": "user", "content": "hi"}]})
        self.assertTrue(r["available"])
        self.assertEqual(gw.calls[-1][2]["model"], "m1")

    def test_apply_posts_mode_and_optional_model(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_apply", {"mode": "fast", "model_id": "m1"})
        self.assertTrue(r["applied"])
        self.assertEqual(gw.calls[-1][1:3], ("/api/apply", {"mode": "fast", "model_id": "m1"}))
        r = call_tool(s, "local_apply", {"mode": "balanced"})
        self.assertEqual(gw.calls[-1][2], {"mode": "balanced"})

    def test_tune_unknown_model_rejected_without_post(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_tune", {"model_id": "ghost"})
        self.assertTrue(r["isError"])
        self.assertIn("unknown model_id", r["error"])
        self.assertNotIn(("POST", "/api/tune"), [(c[0], c[1]) for c in gw.calls])

    def test_tune_known_model_posts_full_body(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_tune",
                      {"model_id": "m1", "objective": "decode", "searchspace": "threads"})
        self.assertTrue(r["accepted"])
        self.assertEqual(gw.calls[-1][2],
                         {"model_id": "m1", "objective": "decode", "searchspace": "threads"})

    def test_secretary_maps_run_contract(self):
        gw = FakeGateway()
        s = make_server(gateway=gw)
        s.initialized = True
        r = call_tool(s, "local_secretary",
                      {"mode": "fast", "prompt": "list files", "task_id": "t13"})
        self.assertTrue(r["available"])
        self.assertEqual(r["task_id"], "t13")
        self.assertTrue(r["passed"])
        self.assertEqual(r["runtime_config"]["model"], "m1")
        self.assertEqual(r["elapsed_s"], 1.5)
        self.assertEqual(gw.calls[-1][1:3],
                         ("/api/run", {"mode": "fast", "prompt": "list files", "task_id": "t13"}))

    def test_backend_error_returns_tool_error_not_crash(self):
        from turbo.mcp_server import BackendError

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

    def test_loopback_aliases_accepted(self):
        self.assertEqual(Gateway(base_url="http://localhost:9999").base_url,
                         "http://localhost:9999")
        self.assertEqual(Gateway(base_url="http://[::1]:8080").base_url,
                         "http://[::1]:8080")

    def test_unreachable_gateway_raises_backend_error(self):
        gw = Gateway(base_url="http://127.0.0.1:1", timeout=1)
        with self.assertRaises(Exception):
            gw.get("/api/status")


if __name__ == "__main__":
    unittest.main()
