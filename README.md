# Local Turbo

Fast, private tool-using AI on a Snapdragon X Elite laptop. We are rebuilding around measured inference throughput, local model routing and auditable context reduction.

**Hardware:** Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB RAM, Adreno X1-85, Windows ARM64. Inference runs locally through Qualcomm GenieX. The earlier camera/Arduino prototype is preserved in Git history and `archive/inspection-station`.

## What we are building

- Native benchmark sweeps comparing CPU thread counts, GPU, NPU and hybrid execution on identical weights.
- A calibrated router selecting a local model/configuration subject to context and tool-quality requirements.
- A local secretary performing structured file operations in a disposable workspace.
- Context reduction preserving stable instructions and keeping original tool results recoverable locally.
- An OpenAI-compatible adapter and dashboard showing measured speed, TTFT, tool correctness and routing decisions.

## Current status

Active development with real Latitude results. A same-model CPU confirmation measured 88.65 versus 75.86 aggregate decode tok/s across 9,600 generated tokens per configuration (+16.9% in this run), with intermittent slowdowns in both legs and essentially unchanged pooled energy efficiency. Full distributions and limitations are in [the results report](benchmarks/results/README.md). Native SDK inference and actual Hexagon operation dispatch have also been verified. Broader model coverage, context optimizations and the integrated tuner are in progress.

## Run tests

Python 3.11+; the core project uses the standard library.

```sh
python -m unittest discover -s tests -v
```

## Benchmark on the Latitude

Download the official GenieX v0.6.1 ARM64 benchmark release and a compatible GGUF. From native Windows ARM64 Python:

```powershell
python scripts/sweep.py --exe C:/tools/geniex-bench/bin/geniex-bench.exe --model C:/models/Qwen3-0.6B-Q4_0.gguf --output local/bench-screen
```

Each cell preserves native timings, arguments, exit status and logs. See [benchmark protocol](docs/benchmark-protocol.md).

## Evidence boundaries

Tokens per second, fewer generated tokens and faster completed tasks are separate metrics. Existing prefix caching and speculative decoding belong to their upstream implementations. Our experimental contribution is a portable measured policy combining model, device and context choices; novelty and speedup remain hypotheses until tested.

[SSH setup](docs/ssh.md) uses placeholders. Credentials, device addresses, models and private logs stay out of Git.

## Correctness benchmark

The [Secretary evaluation protocol](docs/secretary-evaluation.md) provides a versioned golden dataset (secretary-eval-v2), 35 development and 15 held-out single-action cases, 30 synthetic fixture files, deterministic scoring, difficulty/category audits and configurable quality gates. Official baseline freezing requires Henry-confirmed configuration and a clean commit. The evaluator uses the actual Secretary tools and executor on isolated synthetic workspaces; it checks intent, execution and final state for one action, not the full routed multi-step workflow. The historical reference is explicitly **not measured** until the real Latitude run is completed.

```sh
python eval/validate_dataset.py --check-leakage
```

See the protocol for the real SDK/model configuration, baseline freeze and one-command candidate evaluation. No runtime tuning or product UI is changed by this evaluation work.
