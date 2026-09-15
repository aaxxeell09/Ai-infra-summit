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
import time
from datetime import datetime, timezone
from pathlib import Path


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
               "-t", str(threads), "-r", str(a.repeats), "--warmup", "1",
               "--temperature", "0", "--seed", "42", "--cell-id", name,
               "--output-json", str(target)]
        if a.prompt_file:
            cmd += ["--prompt-file", str(Path(a.prompt_file).resolve())]
        if spec:
            cmd += ["--spec-type", spec, "--draft-tokens", "8"]
        row = {"id": name, "command": cmd, "started_at": datetime.now(timezone.utc).isoformat()}
        start = time.perf_counter()
        with (out / (name + ".log")).open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                        cwd=exe.parent, timeout=a.timeout)
                row["exit_code"] = result.returncode
                row["status"] = "completed" if result.returncode == 0 and target.exists() else "failed"
            except subprocess.TimeoutExpired:
                row.update(status="timeout", exit_code=None)
        row["wall_s"] = time.perf_counter() - start
        if target.exists():
            result = json.loads(target.read_text(encoding="utf-8-sig"))
            row["agg"] = result.get("agg")
            row["device_id"] = result.get("device_id")
            row["complete_length_runs"] = sum(r.get("gen_tokens") == 128 for r in result.get("runs", []))
        record["cells"].append(row)
        (out / "sweep.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(row), flush=True)
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out / "sweep.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
