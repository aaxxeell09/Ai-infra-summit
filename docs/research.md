# Snapdragon inference: research and build outline

Research date: September 15, 2026. Target: Latitude 7455, X1E-80-100, 32 GB RAM, Windows ARM64. Statements below distinguish documented capabilities, implementation choices and experiments. Performance numbers must come from this laptop.

## Objective and product

A local secretary should turn a request into a correct file operation quickly, entirely on the laptop. Our primary engine metric is native decode tokens per second. We also measure time to first token, prefill, generated tokens, total task time and tool correctness. These metrics answer different questions: output compression can finish a task sooner without increasing decode throughput.

The product is an inference gateway with a calibration runner and an inspectable secretary demo. The gateway can be called by clients using its supported OpenAI chat-completion subset. Full compatibility with any particular coding harness must be tested; an OpenAI-shaped endpoint alone does not establish Claude Code or Codex integration.

## 1. Establish the strongest practical native baseline

GenieX supports GGUF inference through llama.cpp and compiled models through Qualcomm AI Engine Direct. The GGUF path is useful for a same-weights comparison across CPU, GPU, NPU and hybrid. Compiled QAIRT bundles are a separate comparison: requesting CPU does not create a meaningful CPU baseline for an NPU-only bundle. Q4_0 is the documented recommended GGUF precision for Hexagon. [GenieX local server documentation](https://github.com/qualcomm/GenieX/blob/v0.6.1/docs/en/run/cli/local-server.mdx), [device-resolution API](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/include/geniex.h).

Start with Qwen3-0.6B Q4_0 for fast iteration and Qwen3-1.7B Q4_0 as the larger local tier. These are candidates, not evidence of adequate tool accuracy. Use the model's own chat template, disable optional thinking consistently across comparisons, and grade generated actions. Model weights and quantization are pinned independently. [Qwen3-0.6B model card](https://huggingface.co/Qwen/Qwen3-0.6B), [Qwen3-1.7B model card](https://huggingface.co/Qwen/Qwen3-1.7B).

The native benchmark exposes generation threads, compute backend, context length, speculation, warmups and repetitions. It reports device-side timings and uses a fixed-length random-ID prefill by default. Random tokens measure engine throughput; they do not establish agent quality. Follow with real structured-tool prompts. [Version-pinned benchmark implementation](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/benchmark/run.c), [options](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/benchmark/options.c).

## 2. Tune what the installed runtime actually exposes

Sweep generation threads first, then compare CPU, GPU, NPU and hybrid. Memory bandwidth, scheduling and per-token launch overhead can matter more than advertised TOPS for small batch decoding. We make no assumption that the NPU wins decode. A backend may instead win prefill, energy or a larger workload; only measured evidence can decide.

The v0.6.1 llama.cpp adapter already applies device-specific batch settings, flash-attention choices and Windows thread-pool policy. Enabling an existing default is not a new optimization. The SDK exposes separate generation/batch thread counts and microbatch size, allowing targeted follow-up sweeps through our native adapter. [Configuration mapping](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/llama_cpp/src/params.cpp), [thread-pool policy](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/llama_cpp/src/threadpool.cpp).

Upstream Hexagon uses shared system memory; VTCM holds temporary/intermediate work. Large-model mapping and supported operations depend on the exact backend revision. The Windows route also has signed DSP library requirements. A custom kernel port therefore has a build, deployment and verification cost; do not change driver signing or security settings merely to chase an unmeasured idea. The supplied signed runtime is the first implementation path. [Hexagon backend](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md), [Windows requirements](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/windows.md).

## 3. Portable optimization experiments

| Experiment | Why it might help | What could make it lose | Acceptance evidence |
| --- | --- | --- | --- |
| Thread/microbatch calibration | Match CPU scheduling and prefill shape to this device | Extra threads saturate bandwidth or interfere with offload | Paired same-model native timings |
| N-gram speculative decoding | Repeated paths, JSON keys or copied text provide cheap draft tokens | Verification overhead and low acceptance | Accepted/total drafts, identical task quality, total time |
| Draft-model speculation | Tiny model proposes multiple target tokens | Two models compete for memory bandwidth | Target-model throughput and acceptance, full overhead included |
| Prefix reuse | Stable schemas and instructions avoid repeated prefill | Rewriting early history invalidates reuse | Cold/warm TTFT, actual fresh-token work |
| Compact tool representation | Fewer output tokens for the same action | Dictionary/schema increases prefill; model confuses symbols | Exact action equivalence and time to validated action |
| Local learned pruning | Shorter long tool outputs reduce prefill/KV demand | Scorer cost, lost facts, cache disruption | Compression time, task accuracy and recovery overhead |

GenieX already exposes several n-gram and draft strategies. Speculation can silently become ineffective when drafts are rejected; recording only the requested flag is insufficient. A repetitive workload is suitable for this experiment, but disclose its scope. [SDK model configuration](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/include/geniex.h), [upstream speculative implementation](https://github.com/ggml-org/llama.cpp/blob/master/common/speculative.cpp).

Do not port a CUDA serving framework wholesale to Windows ARM64 during the first build. Extract portable algorithms where the current runtime exposes the necessary primitives. KV paging, quantized KV, alternate attention kernels and MTP architecture support require runtime/model compatibility; they are not universal switches. Changing model architecture or quantization creates a different comparison and requires fresh correctness checks.

## 4. Original project experiment: ToolWire plus calibrated routing

ToolWire compiles a local file inventory into stable integer symbols. The model emits a compact typed action such as `{"r":3}`; a deterministic decoder expands it into the ordinary `read_file` call with the exact path. A snapshot digest binds symbols to the inventory, and the filesystem executor still rejects invalid paths and unsafe moves. Unknown symbols and stale snapshots cause failure rather than a guessed action.

A constrained grammar can enforce the wire format, but cannot establish that the chosen file matches the user's intent. That requires the same held-out action checks as verbose JSON. Compare normal tool JSON against ToolWire using the same model, backend and requests. Count the extra inventory prompt, schema overhead and all generated tokens.

The router ranks calibrated profiles under context and quality requirements. Decode mode maximizes measured tokens/s; latency mode estimates prefill plus decode plus loading. Cache reuse belongs in the latency calculation only when the matching state is actually resident. Route-quality tiers must come from task calibration rather than model size alone.

These are our implementation experiments, not a claim of first invention. Compact representations, constrained outputs and cache-aware scheduling have substantial prior art. SGLang explicitly combines structured program execution with prefix caching and optimized output constraints. Our proposed contribution is the measured combination on a single heterogeneous Qualcomm laptop. [SGLang paper](https://arxiv.org/abs/2312.07104), [SGLang implementation](https://github.com/sgl-project/sglang).

## 5. Local alternatives to hosted context scoring

Parsec describes a local proxy, but its standard scoring path sends chunks/features to a hosted API. That does not satisfy our offline core. Its vendor benchmark is useful as an experimental design reference, not evidence of a local Snapdragon speedup. [Parsec](https://getparsec.ai/), [published benchmark harness](https://github.com/daseinlabs/code-compression-bench).

Our dependency-free first path is JSON minification, explicit field projection, bounded previews and a local raw-text store. Projection and previews are lossy; their records must say so. Recovery references, exact paths and important constraints remain available. Tiny outputs bypass compression if metadata would make them larger. Apply reduction to eligible tool results, never silently to system instructions or user messages.

LLMLingua-2 is a credible learned alternative with public local checkpoints. Its token classifier can prune text without a hosted scoring call. Windows ARM64 dependency support and ONNX-export compatibility must be validated for the specific checkpoint; a Python package being pure Python does not make its dependencies architecture-independent. Third-party ONNX/JavaScript ports are candidates requiring equivalence tests. [Microsoft LLMLingua](https://github.com/microsoft/LLMLingua), [LLMLingua-2 paper](https://aclanthology.org/2024.findings-acl.57/), [small checkpoint](https://huggingface.co/microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank).

The approximate break-even condition is: compression time plus recovery and lost-cache cost must be less than the prefill/decode time saved. There is no guarantee of a win on a tiny model. Preserve stable system/schema prefixes and reduce new dynamic output. Even deterministic rewriting of an earlier prefix can invalidate cache alignment. [llama.cpp server cache controls](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Caveman-style brevity applies to optional prose, not paths, code, required explanations or tool schemas. RTK-style output filtering can reduce verbose command results, but raw output must remain recoverable. Neither technique is credited as a native decode speedup.

## 6. Demo and decision gates

1. Show the unplugged-from-cloud local server and the exact model/runtime identity.
2. Run default and tuned same-model inference with native counters visible.
3. Ask a real secretary request against disposable files; show the generated action and filesystem effect.
4. Compare verbose tool JSON and ToolWire; display native tokens/s, generated tokens, total time and correctness separately.
5. Show the router's chosen model and measured evidence, including rejected options.
6. Open the raw benchmark report and disclose failed backends and unproven ideas.

First ship a correct end-to-end path. Add an optimization only when its isolated experiment wins. Keep a working default configuration available. If the speedup disappears in confirmation, publish that result and change the policy rather than the numbers.
