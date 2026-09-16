"""Focused tests for the bounded demo CLI; all server replies are faked.

Nothing here loads a model or touches hardware. Coverage: exactly one
correct file move verifies; an unrelated workspace change rejects; a
same-basename move with different contents rejects; malformed replies,
watchdog timeout and structured inner errors exit nonzero with raw
evidence preserved.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import demo_invoice_mcp


INITIAL = {"drafts/hexagon-invoice.md": "a" * 64,
           "notes/ideas.md": "b" * 64}


def structured(final=None, verification=None, completed=True,
               is_error=False, error=None):
    final = INITIAL if final is None else final
    verification = verification or {
        "passed": False, "calls_match": False, "final_state_match": True,
        "execution_ok": True, "task_id": "t13"}
    sc = {"task_id": "t13", "model_id": "qwen4b",
          "output_dir": "/tmp/inner-run", "completed": completed,
          "existing_demo_verification": verification,
          "report": {"loop": {"status": "mutation_executed_awaiting_verification",
                              "elapsed_s": 0.5,
                              "initial_snapshot": INITIAL,
                              "final_snapshot": final,
                              "timing_scope": "loop scope"},
                     "timing_scope": "diagnostic scope"},
          "identity": {"diagnostic_elapsed_s": 1.25,
                       "model_sha256": demo_invoice_mcp.MODEL_SHA256}}
    if is_error:
        sc.update({"isError": True, "error": error})
    return sc


def fake_stdout(sc=None):
    sc = structured() if sc is None else sc
    frames = [
        {"jsonrpc": "2.0", "id": 1,
         "result": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 3, "result": {"tools": [
            {"name": "local_feedback_diagnostic"}]}},
        {"jsonrpc": "2.0", "id": 4,
         "result": {"content": [], "structuredContent": sc,
                    "isError": bool(sc.get("isError"))}},
    ]
    return "".join(json.dumps(f) + "\n" for f in frames).encode("utf-8")


class FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, timeout=False):
        self.pid = 4321
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout = timeout

    def communicate(self, input=None, timeout=None):
        assert timeout == demo_invoice_mcp.TIMEOUT_S
        if self._timeout:
            raise subprocess.TimeoutExpired(cmd="mcp", timeout=timeout,
                                            output=b"partial out",
                                            stderr=b"partial err")
        return self._stdout, self._stderr


class DemoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "qwen4b.json"
        self.config.write_text(json.dumps(
            {"sdk_dir": "/tmp/sdk", "model_path": "/tmp/model.bin"}),
            encoding="utf-8")
        self.output = self.root / "out"
        self.killed = []
        patches = [
            mock.patch.object(demo_invoice_mcp, "_preflight",
                              side_effect=lambda *_: ([], "fakecommit")),
            mock.patch.object(demo_invoice_mcp, "_terminate_tree",
                              side_effect=lambda proc: self.killed.append(
                                  proc.pid)),
            mock.patch.object(demo_invoice_mcp, "Popen",
                              return_value=FakeProc()),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _run_main(self):
        code = demo_invoice_mcp.main(["--config", str(self.config),
                                      "--output", str(self.output),
                                      "--enable-candidate"])
        summary = json.loads(
            (self.output / "summary.json").read_text(encoding="utf-8"))
        return code, summary

    def _set_proc(self, sc=None, timeout=False, stdout=None, returncode=0):
        if sc is not None:
            stdout = fake_stdout(sc)
        elif stdout is None and not timeout:
            stdout = fake_stdout()
        demo_invoice_mcp.Popen.return_value = FakeProc(
            stdout=stdout or b"", stderr=b"", returncode=returncode,
            timeout=timeout)

    def test_correct_single_move_verifies_and_exit_zero(self):
        final = {"invoices/2026/hexagon-invoice.md": "a" * 64,
                 "notes/ideas.md": "b" * 64}
        self._set_proc(sc=structured(final=final))
        code, summary = self._run_main()
        self.assertEqual(code, 0)
        self.assertTrue(summary["transport_completed"])
        self.assertTrue(summary["file_move"]["verified"])
        self.assertEqual(summary["file_move"]["removed"],
                         {"drafts/hexagon-invoice.md": "a" * 64})
        self.assertEqual(summary["file_move"]["added"],
                         {"invoices/2026/hexagon-invoice.md": "a" * 64})
        self.assertEqual(summary["file_move"]["sha256"], "a" * 64)
        self.assertFalse(summary["quality_qualified"])
        self.assertIn("not frozen secretary-eval-v2", summary["scope"])
        self.assertEqual(summary["timing"]["loop"]["elapsed_s"], 0.5)
        self.assertEqual(summary["timing"]["diagnostic"]["elapsed_s"], 1.25)
        self.assertEqual(summary["existing_demo_verification"]["task_id"],
                         "t13")

    def test_unrelated_change_rejects_verification(self):
        final = dict(INITIAL)
        final["invoices/2026/other.md"] = "c" * 64
        self._set_proc(sc=structured(final=final))
        code, summary = self._run_main()
        self.assertEqual(code, 0)
        self.assertFalse(summary["file_move"]["verified"])
        self.assertIn("not exactly", summary["file_move"]["reason"])

    def test_same_basename_wrong_contents_rejects_verification(self):
        final = {"invoices/2026/hexagon-invoice.md": "d" * 64,
                 "notes/ideas.md": "b" * 64}
        self._set_proc(sc=structured(final=final))
        code, summary = self._run_main()
        self.assertEqual(code, 0)
        self.assertFalse(summary["file_move"]["verified"])
        self.assertIn("identical bytes", summary["file_move"]["reason"])

    def test_malformed_reply_exits_nonzero_and_preserves_raw(self):
        self._set_proc(stdout=b"this is not json\n", returncode=1)
        code, summary = self._run_main()
        self.assertEqual(code, 1)
        self.assertFalse(summary["transport_completed"])
        self.assertFalse(summary["ok"])
        self.assertTrue(any("malformed reply" in e for e in summary["errors"]))
        self.assertIn("this is not json",
                      (self.output / "mcp-stdout.txt").read_text(
                          encoding="utf-8"))

    def test_timeout_terminates_owned_tree_and_preserves_output(self):
        self._set_proc(timeout=True)
        code, summary = self._run_main()
        self.assertEqual(code, 1)
        self.assertEqual(self.killed, [4321])
        self.assertFalse(summary["transport_completed"])
        self.assertTrue(any("watchdog" in e for e in summary["errors"]))
        self.assertIn("partial out",
                      (self.output / "mcp-stdout.txt").read_text(
                          encoding="utf-8"))
        self.assertIn("partial err",
                      (self.output / "mcp-stderr.txt").read_text(
                          encoding="utf-8"))

    def test_structured_inner_error_exits_nonzero_and_preserved(self):
        sc = structured(is_error=True, error="grammar canary failed")
        self._set_proc(stdout=fake_stdout(sc))
        code, summary = self._run_main()
        self.assertEqual(code, 1)
        self.assertTrue(summary["transport_completed"])
        self.assertFalse(summary["ok"])
        self.assertTrue(any("grammar canary failed" in e
                            for e in summary["errors"]))

    def test_enable_candidate_flag_is_required(self):
        with self.assertRaises(SystemExit) as caught:
            demo_invoice_mcp.main(["--config", str(self.config),
                                   "--output", str(self.output)])
        self.assertNotEqual(caught.exception.code, 0)

    def test_missing_call_cannot_exit_success(self):
        lines = fake_stdout().splitlines()[:2]
        self._set_proc(stdout=b"\n".join(lines))
        code, summary = self._run_main()
        self.assertEqual(code, 1)
        self.assertFalse(summary["transport_completed"])

    def test_malformed_result_types_fail_without_crashing(self):
        for reply_id in (1, 3, 4):
            with self.subTest(reply_id=reply_id):
                self.output = self.root / ("malformed-%s" % reply_id)
                frames = [json.loads(x) for x in fake_stdout().splitlines()]
                next(f for f in frames if f["id"] == reply_id)["result"] = []
                self._set_proc(stdout=("\n".join(map(json.dumps, frames))).encode())
                code, summary = self._run_main()
                self.assertEqual(code, 1)
                self.assertFalse(summary["transport_completed"])

    def test_mismatched_native_model_is_rejected(self):
        sc = structured()
        sc["identity"]["model_sha256"] = "f" * 64
        self._set_proc(sc=sc)
        code, summary = self._run_main()
        self.assertEqual(code, 1)
        self.assertTrue(any("verified 4B weights" in e for e in summary["errors"]))

    def test_task_and_alias_mismatch_rejected(self):
        for field in ("task_id", "model_id"):
            with self.subTest(field=field):
                self.output = self.root / ("identity-" + field)
                sc = structured()
                sc[field] = "unexpected"
                self._set_proc(sc=sc)
                code, summary = self._run_main()
                self.assertEqual(code, 1)
                self.assertIn("diagnostic task/model identity mismatch", summary["errors"])

    def test_real_recorded_payload_preserves_verdict_and_timing(self):
        # Replay only the committed public MCP response; no inference occurs.
        sc = json.loads((REPO_ROOT / "benchmarks/results/feedback-mcp-1300/result.json").read_text())
        self._set_proc(sc=sc)
        code, summary = self._run_main()
        self.assertEqual(code, 0)
        self.assertTrue(summary["file_move"]["verified"])
        self.assertEqual(summary["existing_demo_verification"], sc["existing_demo_verification"])
        self.assertFalse(summary["existing_demo_verification"]["passed"])
        self.assertEqual(summary["timing"]["loop"]["elapsed_s"], sc["report"]["loop"]["elapsed_s"])
        self.assertEqual(summary["timing"]["diagnostic"]["elapsed_s"], sc["identity"]["diagnostic_elapsed_s"])


class ValidationCase(unittest.TestCase):
    def test_ambiguous_reply_ids_rejected(self):
        original = {"jsonrpc": "2.0", "id": 1, "result": {}}
        for other in (original, {**original, "id": True}, {**original, "id": "1"}):
            with self.subTest(other=other):
                _, _, errors = demo_invoice_mcp._parse_replies(
                    json.dumps(original) + "\n" + json.dumps(other))
                self.assertTrue(errors)

    def test_unverifiable_hashes_do_not_prove_a_move(self):
        result = demo_invoice_mcp._check_move(
            {demo_invoice_mcp.EXPECTED_SOURCE: "same"},
            {demo_invoice_mcp.EXPECTED_DESTINATION: "same"})
        self.assertFalse(result["verified"])

    def test_preflight_output_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = root / "config.json"
            config.write_text('{"sdk_dir":"sdk","model_path":"model"}')
            (root / "local").mkdir()
            (root / "outside").mkdir()
            (root / "local" / "escape").symlink_to(root / "outside", target_is_directory=True)
            for destination, allowed in [
                (root / "local" / "new", True),
                (root / "elsewhere" / "new", False),
                (root / "local", False),
                (root / "local" / "escape" / "new", False),
            ]:
                with self.subTest(destination=destination), mock.patch.object(
                        demo_invoice_mcp, "ROOT", root), mock.patch.object(
                        demo_invoice_mcp.subprocess, "check_output", side_effect=["abc", ""]), mock.patch.object(
                        demo_invoice_mcp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
                    errors, _ = demo_invoice_mcp._preflight(config, destination)
                    self.assertEqual(not errors, allowed)

    def test_not_ignored_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = root / "config.json"
            config.write_text('{"sdk_dir":"sdk","model_path":"model"}')
            with mock.patch.object(demo_invoice_mcp, "ROOT", root), mock.patch.object(
                    demo_invoice_mcp.subprocess, "check_output", side_effect=["abc", ""]), mock.patch.object(
                    demo_invoice_mcp.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
                errors, _ = demo_invoice_mcp._preflight(config, root / "local" / "new")
                self.assertIn("output path must be ignored by Git", errors)


if __name__ == "__main__":
    unittest.main()
