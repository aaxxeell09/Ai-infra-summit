"""Config and aggregation invariants for scripts/native_sweep.py (no hardware)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]


def _load_sweep():
    spec = importlib.util.spec_from_file_location(
        "native_sweep", REPO / "scripts" / "native_sweep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_run_cell_factory(calls):
    def fake_run_cell(exe, cfg, timeout):
        calls.append(dict(cfg))
        return {"status": "completed", "runs": [
            {"text": "ok", "profile": {
                "generated_tokens": cfg["max_tokens"],
                "prompt_tokens": 9,
                "prefill_speed": 100.0 + cfg["n_batch"],
                "decoding_speed": 20.0,
                "ttft": 12_000}} for _ in range(cfg["repeats"])],
            "warm_generated_tokens": 1, "telemetry": {}}
    return fake_run_cell


class SweepConfigTests(unittest.TestCase):
    def setUp(self):
        self.sweep = _load_sweep()

    def _main(self, argv, outdir, run_cell=None):
        calls = []
        base = ["native_sweep.py", "--sdk-dir", "/fake/sdk", "--model", "/fake/m.gguf",
                "--output", str(outdir)]
        with mock.patch.object(self.sweep.sys, "argv", base + argv), \
                mock.patch.object(self.sweep, "_run_cell", run_cell or _fake_run_cell_factory(calls)):
            self.sweep.main()
        return calls

    def test_cell_enumeration_and_config_passthrough(self):
        outdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "run"
        calls = self._main(["--contexts", "2048", "4096",
                            "--threads-batch", "4", "8",
                            "--n-batches", "0", "512",
                            "--ubatches", "256"], outdir)
        self.assertEqual(len(calls), 2 * 2 * 2 * 1)
        nb = {c["n_batch"] for c in calls}
        self.assertEqual(nb, {0, 512})
        self.assertEqual({c["ubatch"] for c in calls}, {256})
        cfg = calls[0]
        self.assertEqual(cfg["context"], 2048)
        self.assertEqual(cfg["threads_batch"], 4)
        self.assertEqual(cfg["reset_between_runs"], False)
        self.assertEqual(cfg["warm_sequence"], 1)

    def test_warm_reset_flags_recorded(self):
        outdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "run"
        calls = self._main(["--reset-between-runs", "--warm-sequence", "0"], outdir)
        self.assertTrue(calls[0]["reset_between_runs"])
        self.assertEqual(calls[0]["warm_sequence"], 0)
        record = json.loads((outdir / "sweep.json").read_text())
        self.assertEqual(record["kv_policy"],
                         "reset KV before each timed run")

    def test_aggregation_invariants(self):
        outdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "run"
        self._main(["--contexts", "2048", "--repeats", "2"], outdir)
        record = json.loads((outdir / "sweep.json").read_text())
        self.assertEqual(record["schema_version"], "turbo.native_sweep.v1")
        self.assertEqual(len(record["cells"]), 1)
        cell = record["cells"][0]
        self.assertTrue(cell["lengths_match_max_tokens"])
        self.assertEqual(cell["complete_runs"], 2)
        self.assertEqual(len(cell["generated_text"]), 2)
        self.assertEqual(cell["aggregate"]["decode_tps_median"], 20.0)
        self.assertEqual(cell["aggregate"]["prompt_tokens"], [9, 9])
        self.assertEqual(cell["aggregate"]["ttft_ms"], [12.0, 12.0])
        self.assertNotIn("comparability_note", cell["aggregate"])

    def test_unequal_lengths_flagged_not_compared(self):
        self.sweep._run_cell = lambda exe, cfg, timeout: {  # noqa: SLF001
            "status": "completed", "telemetry": {},
            "runs": [
                {"text": "a" * 5, "profile": {"generated_tokens": 128,
                 "prompt_tokens": 9, "prefill_speed": 1.0,
                 "decoding_speed": 30.0, "ttft": 1000}},
                {"text": "short", "profile": {"generated_tokens": 3,
                 "prompt_tokens": 9, "prefill_speed": 1.0,
                 "decoding_speed": 99.0, "ttft": 1000}}]}
        outdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "run"
        calls = []
        with mock.patch.object(self.sweep.sys, "argv",
                               ["x", "--sdk-dir", "s", "--model", "m",
                                "--output", str(outdir)]), \
                mock.patch.object(self.sweep, "_run_cell", self.sweep._run_cell):
            self.sweep.main()
        cell = json.loads((outdir / "sweep.json").read_text())["cells"][0]
        self.assertFalse(cell["lengths_match_max_tokens"])
        self.assertIn("NOT directly comparable", cell["aggregate"]["comparability_note"])
        self.assertEqual(cell["complete_runs"], 1)

    def test_empty_and_partial_runs_cannot_match_requested_length(self):
        for count in (0, 1):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                def incomplete(exe, cfg, timeout):
                    row = _fake_run_cell_factory([])(exe, cfg, timeout)
                    row.update(status="failed", runs=row["runs"][:count])
                    return row
                out = Path(tmp) / "run"
                self._main(["--repeats", "2"], out, incomplete)
                cell = json.loads((out / "sweep.json").read_text())["cells"][0]
                self.assertFalse(cell["lengths_match_max_tokens"])
                self.assertIn("comparability_note", cell["aggregate"])


# A real child interpreter imports this fake SDK from a temporary repository.
# Keep chat keyword-only so a positional call regression fails in the child.
FAKE_NATIVE = '''
import json, os, time
from pathlib import Path

class NativeRuntime:
    def __init__(self, sdk_dir):
        self.trace = Path(sdk_dir) / "trace.jsonl"
        self.event("runtime_open")
    def event(self, kind, **details):
        with self.trace.open("a") as stream:
            stream.write(json.dumps(dict(kind=kind, **details)) + "\\n")
    def close(self):
        self.event("runtime_close")

class NativeModel:
    def __init__(self, runtime, path, **config):
        self.rt, self.mode, self.calls = runtime, path, 0
        runtime.event("model_open", config=config)
        if path == "create-error":
            raise RuntimeError("fake create failed")
        time.sleep(0.15)
    def chat(self, *, messages, tools, max_tokens, temperature, reset):
        self.calls += 1
        self.rt.event("chat", reset=reset, temperature=temperature, tools=tools)
        if self.calls == 3:
            if self.mode == "chat-error":
                raise RuntimeError("fake generation failed")
            if self.mode == "crash":
                os._exit(23)
            if self.mode == "hang":
                time.sleep(30)
        time.sleep(0.03)
        tokens = 2 if self.calls == 1 else max_tokens
        return dict(text="fake output " + str(self.calls), profile=dict(
            generated_tokens=tokens, prompt_tokens=9, prefill_speed=100.0,
            decoding_speed=20.0, ttft=12000, stop_reason="eos" if tokens == 2 else "limit"))
    def close(self):
        self.rt.event("model_close")
'''


class WorkerProcessTests(unittest.TestCase):
    def setUp(self):
        self.sweep = _load_sweep()
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())) / "repo with spaces"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "turbo").mkdir()
        script = self.root / "scripts" / "native_sweep.py"
        script.write_text((REPO / "scripts" / "native_sweep.py").read_text())
        (self.root / "turbo" / "__init__.py").touch()
        (self.root / "turbo" / "native.py").write_text(FAKE_NATIVE)
        (self.root / "turbo" / "telemetry.py").write_text((REPO / "turbo" / "telemetry.py").read_text())
        self.sweep.__file__ = str(script)
        self.sweep.REPO_ROOT = self.root
        self.cfg = dict(sdk_dir=str(self.root), model="ok", device="cpu", threads=6,
                        context=4096, threads_batch=4, n_batch=512, ubatch=256,
                        prompt="public text", tools=[], max_tokens=5, repeats=2,
                        warm_sequence=1, reset_between_runs=False,
                        result_path=str(self.root / "result.json"))

    def events(self):
        return [json.loads(line) for line in (self.root / "trace.jsonl").read_text().splitlines()]

    def test_real_subprocess_keyword_chat_and_complete_energy_interval(self):
        proc, samples, reads = [], [], []
        popen = self.sweep.subprocess.Popen
        def launch(*args, **kwargs):
            self.assertEqual(len(reads), 1)  # energy read precedes Python startup
            child = popen(*args, **kwargs)
            proc.append(child)
            return child
        def energy_sample():
            if reads:
                self.assertIsNotNone(proc[0].poll())  # final read follows exit
            reads.append(1)
            return dict(monotonic_s=len(reads) * 2, channels_pwh={"SYS": len(reads) * 1_000_000_000}, error=None)
        def memory_sample():
            self.assertIsNone(proc[0].poll())
            samples.append(1)
            return {"peak_working_set_mb": float(len(samples))}
        meter = SimpleNamespace(sample=energy_sample, close=mock.Mock())
        memory = SimpleNamespace(sample=memory_sample, close=mock.Mock())  # no .handle
        with (
            mock.patch.object(self.sweep.subprocess, "Popen", side_effect=launch),
            mock.patch.object(self.sweep, "EnergyMeter", return_value=meter),
            mock.patch.object(self.sweep, "ProcessMemory", return_value=memory),
        ):
            row = self.sweep._run_cell(sys.executable, self.cfg, 5)
        self.assertEqual(row["status"], "completed", Path(row["worker_log"]).read_text())
        self.assertEqual(row["exit_code"], 0)
        self.assertGreater(len(samples), 1)
        self.assertEqual(row["warm_generated_tokens"], 2)
        self.assertEqual(row["telemetry"]["generated_tokens_in_interval"], 12)
        self.assertAlmostEqual(row["telemetry"]["tokens_per_joule"], 12 / 3.6)
        self.assertEqual(row["wall_s"], row["telemetry"]["energy"]["duration_s"])
        self.assertEqual([e["reset"] for e in self.events() if e["kind"] == "chat"], [True, False, False])
        self.assertEqual([e["kind"] for e in self.events()][-2:], ["model_close", "runtime_close"])
        meter.close.assert_called_once()
        memory.close.assert_called_once()

    def test_cold_reset_and_unavailable_telemetry_without_windows(self):
        self.cfg.update(warm_sequence=0, reset_between_runs=True)
        with mock.patch.object(self.sweep.sys, "platform", "darwin"):
            row = self.sweep._run_cell(sys.executable, self.cfg, 5)
        self.assertEqual(row["status"], "completed", Path(row["worker_log"]).read_text())
        self.assertIsNone(row["telemetry"]["tokens_per_joule"])
        self.assertFalse(row["telemetry"]["sys_delta_valid"])
        self.assertGreater(row["wall_s"], 0)
        self.assertEqual(row["runs"][0]["profile"]["stop_reason"], "eos")
        self.assertEqual([e["reset"] for e in self.events() if e["kind"] == "chat"], [True, True])

    def test_failed_creation_closes_runtime_and_logs_cause(self):
        self.cfg["model"] = "create-error"
        row = self.sweep._run_cell(sys.executable, self.cfg, 5)
        self.assertEqual(row["status"], "failed")
        self.assertIn("fake create failed", Path(row["worker_log"]).read_text())
        self.assertEqual(self.events()[-1]["kind"], "runtime_close")

    def test_failures_keep_partial_text_without_energy_token_ratio(self):
        for mode in ("chat-error", "crash", "hang"):
            with self.subTest(mode=mode):
                self.cfg["model"] = mode
                row = self.sweep._run_cell(sys.executable, self.cfg, 1 if mode == "hang" else 5)
                self.assertEqual(row["status"], "timeout" if mode == "hang" else "failed")
                self.assertNotEqual(row["exit_code"], 0)
                self.assertEqual(row["runs"][0]["text"], "fake output 2")
                self.assertEqual(row["warm_generated_tokens"], 2)
                self.assertIsNone(row["telemetry"]["generated_tokens_in_interval"])
                self.assertIsNone(row["telemetry"]["tokens_per_joule"])
                self.assertIn("energy_before", row["telemetry"])
                self.assertIn("energy_after", row["telemetry"])
                if mode == "chat-error":
                    self.assertEqual(self.events()[-1]["kind"], "runtime_close")


if __name__ == "__main__":
    unittest.main()
