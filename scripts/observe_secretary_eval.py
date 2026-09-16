"""Observe the existing frozen evaluator; never supply prompts or score answers.

Energy covers the complete child process, not only warm inference. Native
logs stay in the chosen output directory and need review before publication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from turbo.telemetry import EnergyMeter, ProcessMemory, energy_delta, power_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_name")
    parser.add_argument("dataset", choices=("dev", "all"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    os.chdir(ROOT)
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        parser.error("Run from a clean source checkout; private config/output should be ignored")
    if not args.candidate_name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.candidate_name):
        parser.error("Candidate name must contain only letters, numbers, hyphens or underscores")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if (out / f"candidate_{args.candidate_name}.json").exists():
        parser.error("Candidate result already exists; use a new name")
    command = [sys.executable, "-X", "utf8", "eval/run_secretary_eval.py",
               "--dataset", args.dataset, "--candidate-name", args.candidate_name,
               "--config", args.config, "--output-dir", args.output_dir]
    meter = EnergyMeter()
    power_before, before = power_snapshot(), meter.sample()
    peak = private = samples = 0
    timed_out = False
    try:
        with (out / f"{args.candidate_name}.log").open("xb") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            memory = ProcessMemory(child.pid)
            start = time.monotonic()
            try:
                while child.poll() is None:
                    sample = memory.sample()
                    if sample:
                        peak = max(peak, sample["peak_working_set_mb"])
                        private = max(private, sample["private_mb"])
                        samples += 1
                    if time.monotonic() - start > 600:
                        child.kill()
                        child.wait()
                        timed_out = True
                        break
                    time.sleep(.05)
            finally:
                memory.close()
                if child.poll() is None:
                    child.kill()
                    child.wait()
        after, power_after = meter.sample(), power_snapshot()
    finally:
        meter.close()
    record = dict(candidate_name=args.candidate_name, exit_code=child.returncode,
        timed_out=timed_out, energy=energy_delta(before, after),
        raw_before=before, raw_after=after, power_before=power_before, power_after=power_after,
        peak_working_set_mib=peak or None, sampled_peak_private_mib=private or None,
        memory_samples=samples,
        scope="Complete evaluator child process: validation, hashes, model load, one uncounted warmup, cases, fixture execution and scoring, output serialization. Not inference-only or warm-task energy.",
        tokens_per_joule=None,
        tokens_per_joule_unavailable_reason="Untimed warmup token counts are not in the runner report.",
        command=[Path(command[0]).name, *command[1:]], supervisor_source=Path(__file__).name)
    (out / f"{args.candidate_name}-telemetry.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"candidate": args.candidate_name, "exit_code": child.returncode,
                      "timed_out": timed_out, "duration_s": record["energy"]["duration_s"]}))
    return 124 if timed_out else child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
