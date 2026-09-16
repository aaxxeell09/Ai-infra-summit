"""Tests for the opt-in feedback diagnostic MCP wrapper.

All subprocess work is faked; nothing here loads a model or touches
hardware. Assertions cover argument restrictions, concurrency rejection,
timeout and failure propagation, and verbatim preservation of the raw
diagnostic record including a failed verification with final_state_match
true.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from turbo import feedback_mcp


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ServerHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "model.json"
        self.config.write_text("{}", encoding="utf-8")
        self.out_root = self.root / "runs"
        self.calls = []

        def runner(argv, **kwargs):
            self.calls.append((argv, kwargs))
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertEqual(kwargs["errors"], "replace")
            out_dir = Path(argv[argv.index("--output") + 1])
            out_dir.mkdir(parents=True, exist_ok=False)
            report = {
                "completed": True,
                "version": "fake-version",
                "git_commit": "fakecommit",
                "model_sha256": "fakehash",
                "sdk_identity": "fake sdk",
                "existing_demo_verification": {
                    "passed": False, "calls_match": False,
                    "final_state_match": True, "execution_ok": False,
                    "task_id": argv[argv.index("--task-id") + 1]},
            }
            (out_dir / 'diagnostic.json').write_text(
                json.dumps(report), encoding="utf-8")
            return FakeResult(0)

        self.server = feedback_mcp.FeedbackMCPServer(
            {"demo": str(self.config)}, self.out_root, runner=runner)
        self.server.initialized = True

    def call(self, args):
        return self.call_named("local_feedback_diagnostic", args)

    def call_named(self, name, args):
        self.server.stdout = StringIO()
        params = {"name": name, "arguments": args}
        self.server.handle_tools_call("req1", params)
        frames = [json.loads(line) for line in self.server.stdout.getvalue().splitlines()]
        self.assertEqual(len(frames), 1)
        return frames[0]["result"]["structuredContent"]

    def test_unknown_tool_is_rejected_without_invoking_runner(self):
        self.server.stdout = StringIO()
        result = self.server.handle_tools_call("req1", {"name": "other_tool",
                                                        "arguments": {}})
        self.assertIsNone(result)
        self.assertEqual(self.calls, [])
        frames = [json.loads(line)
                  for line in self.server.stdout.getvalue().splitlines()]
        self.assertEqual(frames[0]["error"]["code"], -32602)
        self.assertIn("other_tool", frames[0]["error"]["message"])

    def test_unhashable_model_id_is_rejected(self):
        resp = self.call({"task_id": "t01", "model_id": ["demo"]})
        self.assertTrue(resp["isError"])
        self.assertIn("model_id must be a string", resp["error"])
        self.assertEqual(self.calls, [])

    def test_builds_bounded_argv_and_preserves_verification(self):
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertFalse(resp.get("isError"))
        argv, kwargs = self.calls[0]
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1], str(feedback_mcp.SCRIPT))
        self.assertIn("--enable-candidate", argv)
        self.assertIn("--constrain-tools", argv)
        self.assertEqual(argv[argv.index("--config") + 1], str(self.config.resolve()))
        self.assertEqual(argv[argv.index("--task-id") + 1], "t01")
        self.assertNotIn("shell", kwargs)
        out_dir = Path(argv[argv.index("--output") + 1])
        self.assertTrue(str(out_dir).startswith(str(self.out_root.resolve())))
        self.assertEqual(resp["existing_demo_verification"],
                         {"passed": False, "calls_match": False,
                          "final_state_match": True, "execution_ok": False,
                          "task_id": "t01"})
        self.assertEqual(resp["identity"]["version"], "fake-version")

    def test_output_dirs_are_unique_per_invocation(self):
        self.call({"task_id": "t01", "model_id": "demo"})
        self.call({"task_id": "t02", "model_id": "demo"})
        outs = [argv[argv.index("--output") + 1] for argv, _ in self.calls]
        self.assertEqual(len(set(outs)), 2)

    def test_rejects_unknown_model_and_task_and_extra_args(self):
        for args in ({"task_id": "t01", "model_id": "nope"},
                     {"task_id": "tX-not-a-task", "model_id": "demo"},
                     {"task_id": "t01", "model_id": "demo", "output": "/tmp/x"},
                     {"task_id": "t01", "model_id": "demo", "prompt": "hi"}):
            resp = self.call(args)
            self.assertTrue(resp["isError"])
            self.assertEqual(self.calls, [])

    def test_rejects_concurrent_invocations(self):
        real_runner = self.server.runner

        def slow_runner(argv, **kwargs):
            saved = self.server.stdout
            self.server.stdout = StringIO()
            self.server.handle_tools_call(
                "req2", {"name": "local_feedback_diagnostic",
                         "arguments": {"task_id": "t01", "model_id": "demo"}})
            inner_frames = [json.loads(line)
                            for line in self.server.stdout.getvalue().splitlines()]
            self.server.stdout = saved
            assert len(inner_frames) == 1
            inner = inner_frames[0]["result"]["structuredContent"]
            assert inner["isError"]
            assert "already running" in inner["error"]
            return real_runner(argv, **kwargs)

        self.server.runner = slow_runner
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertFalse(resp.get("isError"))

    def test_timeout_propagates_and_preserves_partial_artifacts(self):
        def timeout_runner(argv, **kwargs):
            self.calls.append((argv, kwargs))
            Path(argv[argv.index("--output") + 1]).mkdir(parents=True, exist_ok=False)
            raise subprocess.TimeoutExpired(
                cmd=argv, timeout=feedback_mcp.TIMEOUT_S,
                stderr=b"partial log")

        self.server.runner = timeout_runner
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertTrue(resp["isError"])
        self.assertTrue(resp["timed_out"])
        self.assertEqual(resp["timeout_s"], feedback_mcp.TIMEOUT_S)
        self.assertIn("preserved", resp["error"])
        self.assertIn("partial log", resp["stderr_tail"])

    def test_bytes_timeout_stderr_is_serializable(self):
        def timeout_runner(argv, **kwargs):
            raise subprocess.TimeoutExpired(
                cmd=argv, timeout=feedback_mcp.TIMEOUT_S,
                stderr=b"\xc3\xa9rror tail")

        self.server.runner = timeout_runner
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertTrue(resp["isError"])
        self.assertEqual(resp["stderr_tail"], "\u00e9rror tail")
        json.dumps(resp)  # must not raise

    def test_launch_failure_is_a_structured_error(self):
        self.server.runner = lambda argv, **kw: (_ for _ in ()).throw(
            OSError("spawn failed"))
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertTrue(resp["isError"])
        self.assertIn("spawn failed", resp["error"])
        self.assertNotIn("returncode", resp)

    def test_nonzero_exit_surfaces_stderr(self):
        self.server.runner = lambda argv, **kw: FakeResult(3, stdout="", stderr="boom")
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertTrue(resp["isError"])
        self.assertEqual(resp["returncode"], 3)
        self.assertEqual(resp["stderr_tail"], "boom")

    def test_missing_report_is_an_error(self):
        self.server.runner = lambda argv, **kw: FakeResult(0)
        resp = self.call({"task_id": "t01", "model_id": "demo"})
        self.assertTrue(resp["isError"])
        self.assertIn("diagnostic.json", resp["error"])

    def test_wire_protocol_framing(self):
        server = feedback_mcp.FeedbackMCPServer(
            {"demo": str(self.config)}, self.out_root,
            stdin=iter([]), stdout=StringIO())
        server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": feedback_mcp.PROTOCOL_VERSION}})
        server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        server.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "unknown_tool", "arguments": {}}})
        out = [json.loads(line) for line in server.stdout.getvalue().splitlines()]
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "turbo-feedback-mcp")
        self.assertEqual([t["name"] for t in out[1]["result"]["tools"]],
                         ["local_feedback_diagnostic"])
        self.assertEqual(out[2]["error"]["code"], -32602)
        locked = feedback_mcp.FeedbackMCPServer(
            {"demo": str(self.config)}, self.out_root,
            stdin=iter([]), stdout=StringIO())
        locked.dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                         "params": {"name": "local_feedback_diagnostic",
                                    "arguments": {"task_id": "t01", "model_id": "demo"}}})
        locked_out = [json.loads(line)
                      for line in locked.stdout.getvalue().splitlines()]
        self.assertEqual(locked_out[0]["error"]["code"], -32002)

    def test_startup_flags(self):
        with self.assertRaises(SystemExit):
            feedback_mcp.parse_args(["--output-root", "/tmp/x"])
        with self.assertRaises(SystemExit):
            feedback_mcp.parse_args(["--enable-candidate", "--output-root", "/tmp/x"])
        args = feedback_mcp.parse_args([
            "--enable-candidate", "--model", "demo=" + str(self.config),
            "--output-root", str(self.out_root)])
        self.assertEqual(args.models, {"demo": str(self.config)})
        with self.assertRaises(SystemExit):
            feedback_mcp.parse_args([
                "--enable-candidate",
                "--model", "demo=" + str(self.config),
                "--model", "demo=" + str(self.config),
                "--output-root", str(self.out_root)])


if __name__ == "__main__":
    unittest.main()
