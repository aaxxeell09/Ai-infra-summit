"""Run the official native benchmark serially on the machine under test.

No network inference. Every cell preserves its command, exit status and log.
Run from Windows ARM64 Python; the executable must be the ARM64 release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.telemetry import EnergyMeter, ProcessMemory, energy_delta
from turbo.telemetry import power_state


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--timeout", type=int, default=240)
    p.add_argument("--phase", choices=["screen", "confirm", "spec"], default="screen")
    p.add_argument("--winner-device", default="cpu")
    p.add_argument("--winner-threads", type=int, default=6)
    p.add_argument("--prompt-file")
    a = p.parse_args()
    out = Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    exe, model = Path(a.exe).resolve(), Path(a.model).resolve()
    record = {
        "schema_version": "turbo.sweep.v1", "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "model_name": model.name,
        "model_sha256": sha256(model), "runtime_sha256": sha256(exe),
        "phase": a.phase, "cold_kv_each_repetition": True,
        "timing_source": "GenieX native backend profile", "cells": [],
    }
    record["power_state_start"] = power_state()
    if a.phase == "screen":
        cells = [(f"cpu-t{t}", "cpu", t, None) for t in (0, 2, 4, 6, 8, 10, 12)]
        cells += [(d, d, 0, None) for d in ("npu", "gpu", "hybrid")]
    elif a.phase == "confirm":
        # Alternating baseline / tuned pairs, separate process and warmup each.
        cells = []
        for i in range(5):
            pair = [(f"baseline-{i}", "cpu", 0, None),
                    (f"tuned-{i}", a.winner_device, a.winner_threads, None)]
            if i % 2:
                pair.reverse()
            cells.extend(pair)
    else:
        if not a.prompt_file:
            p.error("--phase spec requires --prompt-file for a real repeatable workload")
        cells = [(s, a.winner_device, a.winner_threads, s) for s in
                 ("none", "ngram-simple", "ngram-map-k", "ngram-mod", "ngram-cache")]
    if a.phase == "screen":
        random.Random(42).shuffle(cells)
    for name, device, threads, spec in cells:
        target = out / (name + ".json")
        cmd = [str(exe), "--plugin", "llama_cpp", "--device", device,
               "-m", str(model), "-p", "512", "-n", "128", "-c", "4096",
               "-t", str(threads), "-r", str(a.repeats), "--warmup", str(a.warmup),
               "--temperature", "0", "--seed", "42", "--cell-id", name,
               "--output-json", str(target)]
        if a.prompt_file:
            cmd += ["--prompt-file", str(Path(a.prompt_file).resolve())]
        if spec:
            cmd += ["--spec-type", spec, "--draft-tokens", "8"]
        row = {"id": name, "command": cmd, "started_at": datetime.now(timezone.utc).isoformat()}
        row["power_state_start"] = power_state()
        start = time.perf_counter()
        meter = EnergyMeter()
        energy_before = meter.sample()
        memory_peak = None
        with (out / (name + ".log")).open("w", encoding="utf-8") as log:
            try:
                process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=exe.parent)
                memory = ProcessMemory(process.pid)
                while process.poll() is None:
                    sample = memory.sample()
                    if sample and (memory_peak is None or sample['peak_working_set_mb'] > memory_peak['peak_working_set_mb']):
                        memory_peak = sample
                    if time.perf_counter() - start > a.timeout:
                        process.kill()
                        process.wait()
                        row.update(status="timeout", exit_code=None)
                        break
                    time.sleep(0.05)
                memory.close()
                if 'status' not in row:
                    row["exit_code"] = process.returncode
                    row["status"] = "completed" if process.returncode == 0 and target.exists() else "failed"
            except OSError as exc:
                row.update(status="failed", error=str(exc), exit_code=None)
        energy_after = meter.sample()
        meter.close()
        row["power_state_end"] = power_state()
        row["wall_s"] = time.perf_counter() - start
        # Paired energy reads are evidence even when the trial fails; keep them.
        row["energy_before"] = energy_before
        row["energy_after"] = energy_after
        if target.exists():
            result = json.loads(target.read_text(encoding="utf-8-sig"))
            row["agg"] = result.get("agg")
            row["device_id"] = result.get("device_id")
            row["complete_length_runs"] = sum(r.get("gen_tokens") == 128 for r in result.get("runs", []))
            total_tokens = sum(r.get('gen_tokens', 0) for r in result.get('runs', []))
            energy = energy_delta(energy_before, energy_after, total_tokens if a.warmup == 0 else None)
            sys_energy = energy['channels'].get('SYS', {})
            sys_valid = 'SYS' in energy['channels']
            result['telemetry'] = {**(memory_peak or {}), **sys_energy,
                'energy': energy, 'energy_before': energy_before, 'energy_after': energy_after,
                'energy_channel': 'SYS', 'sys_delta_valid': sys_valid,
                'memory_scope': 'benchmark process peak working set',
                'tokens_per_joule_reason': ('unavailable: SYS counter delta missing or reset' if not sys_valid else
                    'full-trial energy including load; all generated tokens' if a.warmup == 0 else
                    'unavailable: warmup tokens absent from report')}
            target.write_text(json.dumps(result, indent=2), encoding='utf-8')
            row['telemetry'] = result['telemetry']
        record["cells"].append(row)
        (out / "sweep.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(row), flush=True)
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out / "sweep.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
