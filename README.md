# Local Turbo

Private tool-using AI on a Snapdragon X Elite laptop. Our primary objective is to minimize **energy per correct Secretary task**, subject to acceptable accuracy and task latency. Throughput remains a secondary diagnostic.

**Hardware:** Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB RAM, Adreno X1-85, Windows ARM64. Inference runs locally through Qualcomm GenieX. The earlier camera/Arduino prototype is preserved in Git history and `archive/inspection-station`.

## What we are building

- Native benchmark sweeps comparing CPU thread counts, GPU, NPU and hybrid execution on identical weights.
- A calibrated router selecting a local model/configuration subject to context and tool-quality requirements.
- A local secretary performing structured file operations in a disposable workspace.
- Context reduction preserving stable instructions and keeping original tool results recoverable locally.
- An OpenAI-compatible adapter and dashboard showing measured speed, TTFT, tool correctness and routing decisions.

## Current status

Native QAIRT now has a complete [50-case result](eval/results/candidate_qairt-native-06-v1.md): **23/50 (46%)**, 34% invalid outputs, mean inference **786 ms**. It is not qualified. The historical comparison correctly remains `NOT_COMPARABLE` after the evaluator provenance changed. A [QAIRT tuner cell](benchmarks/results/qairt-tuner-smoke-01/README.md) also ran on the Latitude. The [repeated QAIRT MCP loop](benchmarks/results/qairt-mcp-loop-01/README.md) now works on the Latitude with SDK hash binding. Both invoice tasks still fail correctness.

The [task-energy protocol](docs/energy-protocol.md) and optional per-task instrumentation are prepared for CPU, llama.cpp HTP and QAIRT. The [decision matrix](docs/decision-matrix.md) remains unmeasured: no new hardware energy run or winning backend is claimed.

Actual Latitude measurements show **2.67× aggregate decode throughput** for CPU/10 versus default auto/NPU on the same 0.6B weights. The stronger CPU-default comparison measured +16.9% aggregate but only +3.2% median individual-run throughput, with substantial variability. See [results and limits](benchmarks/results/README.md).

The live HTTP tuner now exports CPU/NPU configurations that are applied through actual MCP and native inference. A simple file task passed; the invoice task failed in both modes. [Integration evidence](benchmarks/results/integration-01/README.md) retains those failures. All serious correctness candidates still fail the frozen quality gate. The teammate frontend below remains a recorded-results and scripted-answer preview; its live bridge and quality-aware model routing are not connected yet. [GOAL.md](GOAL.md) records the full acceptance criteria.

## Local demo interface

The three-screen frontend previews the target machine, compares the recorded Latitude screening results, and previews default-versus-Local-Turbo answers with separate speed and routing views. It does not yet run live inference or apply configurations to the device.

```sh
cd frontend
npm run dev
```

Open `http://127.0.0.1:4173`. Node.js 20+ is required; no package installation is needed. See [frontend setup and backend integration](frontend/README.md) and the [versioned UX specification](frontend/ux-spec.json).

## Core tests

Python 3.11+; the core project uses the standard library.

```sh
python -m pytest tests -q
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

The [Secretary evaluation protocol](docs/secretary-evaluation.md) provides a versioned golden dataset (secretary-eval-v2), 35 development and 15 held-out single-action cases, 30 synthetic fixture files, deterministic scoring, difficulty/category audits and configurable quality gates. Official baseline freezing requires Henry-confirmed configuration and a clean commit. The evaluator uses the actual Secretary tools and executor on isolated synthetic workspaces; it checks intent, execution and final state for one action, not the full routed multi-step workflow. The confirmed untuned reference is now [measured on the Latitude](eval/results/baseline.md): **30/50 tasks correct (60%)**, mean inference latency **1209.531 ms**, median **1147.561 ms**, p95 **1500.174 ms**, and **0/13 clarification cases correct**. It uses Qwen3-0.6B Q4_0, GenieX 0.6.1 auto placement resolved to HTP0, at application/evaluator commit `ccd1e00`. Henry designated this reference after historical pre-optimization provenance could not be established. Preserve the frozen benchmark and reference; candidates must pass the documented quality gate.

```sh
python eval/validate_dataset.py --check-leakage
```

See the protocol for the real SDK/model configuration, baseline freeze and one-command candidate evaluation. No runtime tuning or product UI is changed by this evaluation work.
