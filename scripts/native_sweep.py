"""Serial SDK-context/threads_batch/n_batch/ubatch sweep on the machine under test.

Run from Windows ARM64 Python next to the verified native adapter. One
benchmark worker subprocess per cell keeps native crashes from killing the
sweep; records stay visible for failed cells.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.telemetry import EnergyMeter, ProcessMemory, energy_delta, power_state

SCHEMA = "turbo.native_sweep.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _worker_json() -> None:
    """In-process cell runner: one model, --warm-sequence then timed runs."""
    import turbo.native as native

    cfg = json.loads(sys.argv[sys.argv.index("--worker-config") + 1])
    payload = {"runs": [], "warm_runs": [], "warm_generated_tokens": 0}
    target = Path(cfg["result_path"])
    def save():
        pending = target.with_suffix(".tmp")
        pending.write_text(json.dumps(payload), encoding="utf-8")
        pending.replace(target)
    save()
    rt = native.NativeRuntime(cfg["sdk_dir"])
    model = None
    try:
        model = native.NativeModel(
            rt, cfg["model"], device=cfg["device"], threads=cfg["threads"],
            context=cfg["context"], threads_batch=cfg["threads_batch"],
            ubatch=cfg["ubatch"], n_batch=cfg["n_batch"])
        messages = [{"role": "user", "content": cfg["prompt"]}]
        kwargs = dict(messages=messages, tools=cfg.get("tools"),
                      max_tokens=cfg["max_tokens"], temperature=0.0)
        for i in range(cfg["warm_sequence"]):
            result = model.chat(**kwargs, reset=(i == 0))
            payload["warm_runs"].append(result)
            payload["warm_generated_tokens"] += result["profile"]["generated_tokens"]
            save()
        for i in range(cfg["repeats"]):
            reset = cfg["reset_between_runs"] or (not cfg["warm_sequence"] and i == 0)
            payload["runs"].append(model.chat(**kwargs, reset=reset))
            save()
    finally:
        try:
            if model is not None:
                model.close()
        finally:
            rt.close()


def _run_cell(exe: str, cfg: dict, timeout: float) -> dict:
    cmd = [exe, str(Path(__file__).resolve()), "--worker-config", json.dumps(cfg)]
    row: dict = {"status": "failed", "runs": [], "command": cmd,
                 "warm_generated_tokens": None}
    row["power_state_start"] = power_state()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result_path = Path(cfg["result_path"])
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.unlink(missing_ok=True)
    log = result_path.with_suffix(".log")
    with log.open("w", encoding="utf-8") as logf:
        meter = EnergyMeter()
        proc = mem = None
        before = meter.sample()
        peak = None
        try:
            deadline = time.monotonic() + timeout
            proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env)
            mem = ProcessMemory(proc.pid)
            while proc.poll() is None:
                sample = mem.sample()
                if sample and (peak is None or sample["peak_working_set_mb"] > peak["peak_working_set_mb"]):
                    peak = sample
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    row["status"] = "timeout"
                    break
                try:
                    proc.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    pass
        except Exception as exc:
            row["error"] = repr(exc)
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
            after = meter.sample()
            meter.close()
            if mem is not None:
                mem.close()
    row["worker_log"] = str(log)
    row["exit_code"] = proc.returncode if proc is not None else None
    row["power_state_end"] = power_state()
    row["wall_s"] = after["monotonic_s"] - before["monotonic_s"]
    try:
        if result_path.is_file():
            row.update(json.loads(result_path.read_text(encoding="utf-8")))
        complete = (len(row["runs"]) == cfg["repeats"] and
                    len(row.get("warm_runs", [])) == cfg["warm_sequence"])
        if row["exit_code"] == 0 and complete and row["status"] != "timeout" and "error" not in row:
            row["status"] = "completed"
    except (ValueError, TypeError, KeyError) as exc:
        row["error"] = repr(exc)
    total = None
    if row["status"] == "completed":
        total = sum(r["profile"]["generated_tokens"] for r in row["runs"]) + row["warm_generated_tokens"]
    energy = energy_delta(before, after, total)
    energy["scope"] = "full worker process: startup, load, warm sequence, measured runs, result I/O and teardown"
    sysj = energy["channels"].get("SYS", {})
    row["telemetry"] = {**(peak or {}), "energy": energy,
                        "energy_before": before, "energy_after": after,
                        "energy_channel": "SYS", "sys_delta_valid": bool(sysj),
                        "generated_tokens_in_interval": total,
                        "tokens_per_joule": sysj.get("tokens_per_joule"),
                        "memory_scope": "maximum observed worker peak working set, sampled while running",
                        "tokens_per_joule_note": (
                            "unavailable: cell incomplete or failed" if total is None else
                            "unavailable: SYS counter delta missing or reset" if not sysj else
                            "full-trial SYS energy; all measured and warm generated tokens counted")}
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk-dir", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--prompt", default="List the files in the current directory as a JSON array.")
    p.add_argument("--tools", help="path to JSON tools array for structured-mode cells")
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warm-sequence", type=int, default=1,
                   help="warm generations before measured runs (0 skips warmup; use --reset-between-runs for cold KV)")
    p.add_argument("--reset-between-runs", action="store_true",
                   help="reset KV before each timed run (default: stable prefix warm)")
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--contexts", type=int, nargs="+", default=[4096])
    p.add_argument("--threads-batch", type=int, nargs="+", default=[0])
    p.add_argument("--n-batches", type=int, nargs="+", default=[0])
    p.add_argument("--ubatches", type=int, nargs="+", default=[0])
    a = p.parse_args()
    if (a.repeats < 1 or a.max_tokens < 1 or a.warm_sequence < 0 or
            not 0 < a.timeout < float("inf")):
        p.error("repeats/max-tokens/timeout must be positive; warm-sequence must be nonnegative")
    out = Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    tools = json.loads(Path(a.tools).read_text()) if a.tools else None
    record = {
        "schema_version": SCHEMA,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(),
        "model": str(Path(a.model).resolve()),
        "device": a.device, "threads": a.threads,
        "max_tokens": a.max_tokens, "repeats": a.repeats,
        "prompt_chars": len(a.prompt), "tools_mode": tools is not None,
        "warm_sequence": a.warm_sequence,
        "reset_between_runs": a.reset_between_runs,
        "kv_policy": ("reset KV before each timed run"
                      if a.reset_between_runs else
                      "stable prefix: KV kept across warm sequence and timed runs"),
        "token_source": "geniex_ProfileData generated_tokens (never chunks)",
        "timing_source": "geniex_ProfileData times in microseconds",
        "cells": [],
    }
    for ctx in a.contexts:
        for tb in a.threads_batch:
            for nb in a.n_batches:
                for ub in a.ubatches:
                    name = f"ctx{ctx}-tb{tb}-nb{nb}-ub{ub}"
                    cfg = {"sdk_dir": str(Path(a.sdk_dir).resolve()),
                           "model": str(Path(a.model).resolve()), "device": a.device,
                           "threads": a.threads, "context": ctx,
                           "threads_batch": tb, "n_batch": nb, "ubatch": ub,
                           "prompt": a.prompt, "tools": tools,
                           "max_tokens": a.max_tokens, "repeats": a.repeats,
                           "warm_sequence": a.warm_sequence,
                           "reset_between_runs": a.reset_between_runs,
                           "result_path": str(out / (name + ".result.json"))}
                    row = {"id": name, "config": cfg,
                           "started_at": datetime.now(timezone.utc).isoformat()}
                    try:
                        row.update(_run_cell(sys.executable, cfg, a.timeout))
                    except Exception as exc:  # keep the cell visible
                        row.update(status="failed", error=repr(exc))
                    runs = row.get("runs") or []
                    gt = [r["profile"]["generated_tokens"] for r in runs]
                    expected = a.max_tokens
                    row["complete_runs"] = sum(1 for t in gt if t == expected)
                    row["lengths_match_max_tokens"] = bool(gt) and len(gt) == a.repeats and all(t == expected for t in gt)
                    row["generated_text"] = [r["text"] for r in runs]
                    row["aggregate"] = {
                        "prefill_tps": [r["profile"]["prefill_speed"] for r in runs],
                        "decode_tps": [r["profile"]["decoding_speed"] for r in runs],
                        "ttft_ms": [r["profile"]["ttft"] / 1000.0 for r in runs],
                        "generated_tokens": gt,
                        "prompt_tokens": [r["profile"]["prompt_tokens"] for r in runs],
                        "decode_tps_median": statistics.median(r["profile"]["decoding_speed"] for r in runs) if runs else None,
                    }
                    if not row["lengths_match_max_tokens"]:
                        row["aggregate"]["comparability_note"] = (
                            "missing runs, early stop or unequal output lengths; decode_tps "
                            "medians are NOT directly comparable to complete-length cells")
                    record["cells"].append(row)
                    (out / "sweep.json").write_text(json.dumps(record, indent=2))
                    brief = {k: row[k] for k in ("id", "status", "complete_runs",
                                                 "lengths_match_max_tokens") if k in row}
                    if row.get("aggregate", {}).get("decode_tps_median") is not None:
                        brief["decode_tps_median"] = row["aggregate"]["decode_tps_median"]
                    print(json.dumps(brief), flush=True)
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out / "sweep.json").write_text(json.dumps(record, indent=2))


if __name__ == "__main__":
    if "--worker-config" in sys.argv:
        _worker_json()
    else:
        main()
