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

Active development. Benchmark orchestration, routing and context primitives are implemented; native integration and the demo are in progress. **No measured speedup is claimed yet.** The runtime is installed on the Latitude; downloads and device benchmarking are underway. Results will include model hashes, configurations, failures and timing definitions.

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
