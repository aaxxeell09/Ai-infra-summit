# Kernel ports and model porting: support map and measured roadmap

Research date: 2026-09-15. Scope: GenieX model ports (GGUF via llama.cpp, QAIRT compiled bundles) and kernel-level optimization on Snapdragon X Elite X1E-80-100, Windows ARM64. Every support claim below cites a primary source or is marked unverified. turbo/porting.py implements offline preflight over these artifact classes; it embeds no architecture support map and requires measured capability evidence before reporting a GGUF architecture ready.

## Artifact classes: what GenieX actually consumes

Three classes are distinct and never interchangeable:

1. **GGUF (llama.cpp plugin).** Covers *supported* architectures: llama.cpp documents per-architecture support in [docs/build.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md) and the model list in [models/README](https://github.com/ggml-org/llama.cpp/blob/master/models/README.md). The authoritative per-revision list is the architecture table in [gguf-py/gguf/constants.py](https://github.com/ggml-org/llama.cpp/blob/master/gguf-py/gguf/constants.py). Converting HF safetensors with the convert_hf_to_gguf script produces a GGUF file but does not create runtime support: an unsupported architecture fails at model load. GenieX itself advertises community GGUF from Hugging Face with per-arch support following llama.cpp ([aihub.qualcomm.com/geniex](https://aihub.qualcomm.com/geniex)).
2. **Converted HF weights (via GGUF or other routes).** Conversion is a format change only. Verify with a measured load on the target runtime before calling the model portable.
3. **QAIRT / AI Hub compiled bundles.** Models exported and compiled chipset- and context-bound via Qualcomm AI Hub, shipped as shard files plus geniex.json ([example bundle](https://huggingface.co/yichqian/geniex-qairt-models/blob/main/granite4_micro/geniex.json)). The compiled context is bound at generation time; requesting CPU or GPU on a QAIRT model is coerced to NPU with a warning (pinned run.md, QAIRT section).

MLX is absent on purpose: MLX is an Apple-silicon array framework over Metal ([ml-explore/mlx](https://github.com/ml-explore/mlx), [mlx-framework.org](https://mlx-framework.org/)); there is no MLX backend for Snapdragon Windows ARM64. "MLX on Snapdragon" is not a port target; the analogy target is llama.cpp GGML kernels on Adreno/Hexagon.

## Kernel reality on the X1E-80-100

- **ARM CPU.** GGML CPU kernels dispatch at runtime on ARMv8.2+ features (dotprod, i8mm) and use quantized kernels; Apple's [KleidiAI integration](https://github.com/ggml-org/llama.cpp/blob/master/docs/kleidiAI.md) accelerates some quantized matmuls. Measured, not assumed, on this laptop.
- **Adreno GPU.** llama.cpp has an OpenCL backend targeting Adreno ([Qualcomm blog](https://www.qualcomm.com/developer/blog/2024/11/introducing-new-opn-cl-gpu-backend-llama-cpp-for-qualcomm-adreno-gpu)). GenieX exposes it as the gpu alias (GPUOpenCL) on Windows ARM64 (pinned run.md, compute-unit aliases).
- **Hexagon NPU (ggml-hexagon).** The backend repacks Q4_0, Q8_0 and MXFP4 into non-host buffers at load; other quants fall back to CPU ([developer.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/developer.md)). One Hexagon session maps about 3.5 GB, so larger models need a multi-device layer split (device list HTP0,HTP1,HTP2,HTP3). GenieX pins quant guidance: Q4_K_M is suboptimal on HTP; Q4_0 gives a clean NPU run (pinned run.md). Windows requires signed DSP libraries (test signing plus cert import).
- **Unsupported architecture kernels.** A GGUF of an architecture absent from llama.cpp's revision list fails at load; this is not fixable by conversion, only by upstream support or a compiled QAIRT bundle if AI Hub exports the model. Never claim automatic conversion.

## Speculative decoding: supported types vs draft-model support

Pinned geniex.h documents the llama_cpp plugin spec types: draft models (draft-mtp, draft-eagle3, draft-simple, each needing spec_draft_model) and self-speculative n-gram types (ngram-simple, ngram-map-k, ngram-map-k4v, ngram-mod, ngram-cache, no draft model needed). The qairt plugin ignores speculation entirely. Draft-model speculation needs a draft GGUF the runtime can load on the same backend; MTP and EAGLE3 head support is architecture- and runtime-revision-bound. Record draft_n_total / draft_n_accepted from profile data to prove acceptance rather than assume it.

## Our own optimization hypotheses (measure before claiming)

Credit: compact tool representations and cache-aware routing have prior art (SGLang); the combination below is ours to measure.

| Hypothesis | Why | Risk | Primary metric |
| --- | --- | --- | --- |
| **Repack-aware quantization routing**: preflight a GGUF's quant against HTP repack classes before NPU runs; route K-quants to CPU/OpenCL without a failed load | Saves a wasted load plus fallback run per K-quant model | Misroutes a quant HTP handles after a backend update | Failed-load rate, end-to-end tokens/J |
| **Acceptance-gated speculation routing**: enable speculation only when measured acceptance clears a threshold on the current task; fall back to plain decode otherwise | N-gram speculation can silently lose to verification overhead on novel text | Threshold overfits to the secretary fixture | tokens/s on live prompts, not a fixed fixture |
| **ToolWire-style compact actions** (existing project experiment): integer-symbol tool calls bound to a file-inventory digest | Fewer decoded tokens per action | Schema prefill cost, intent errors | Time to validated action, exact-action accuracy |

## Prioritized measured experiments

1. **Backend sweep on Qwen3-1.7B Q4_0 GGUF**: CPU vs GPU vs NPU vs hybrid, paired same-weights trials, thread sweep first. Baseline for all claims.
2. **HTP quant comparison**: Q4_0 vs Q8_0 vs Q4_K_M on the same model; confirm the CPU-fallback penalty the docs predict. Feeds repack-aware routing.
3. **N-gram speculation on structured-file prompts** vs plain decode, with acceptance telemetry; only scale to draft-model types after n-gram shows net gain.
4. **Large-model split**: a >3.5 GB GGUF via an HTP0-3 layer split, verifying the documented session limit and measuring split overhead.
5. **QAIRT bundle comparison**: an AI Hub-compiled Qwen3 vs the GGUF on the same prompts, NPU-only, with dispatch evidence per AGENTS.md.

Each experiment needs paired trials, warmup policy, power state, model hash, binary version, exact command, and acceptance/quality metrics per docs/benchmark-protocol.md.

## Source inventory

- Pinned local capture: /Users/user/Documents/Qualcomm/Ai-infra-summit/local/geniex-research/ (run.md runtime/compute-unit/QAIRT behavior, geniex.h speculative types and profile data, hexagon.md build/env vars, bench.md benchmark CI, device.cpp, params.cpp, threadpool.cpp, run.c, options.c).
- Upstream llama.cpp: [Hexagon developer docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/developer.md), [Snapdragon README](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md), [gguf constants](https://github.com/ggml-org/llama.cpp/blob/master/gguf-py/gguf/constants.py), [KleidiAI](https://github.com/ggml-org/llama.cpp/blob/master/docs/kleidiAI.md).
- GenieX: [GitHub repo](https://github.com/qualcomm/GenieX), [AI Hub page](https://aihub.qualcomm.com/geniex), [QAIRT bundle example](https://huggingface.co/yichqian/geniex-qairt-models/blob/main/granite4_micro/geniex.json).
- MLX: [ml-explore/mlx](https://github.com/ml-explore/mlx), [mlx-framework.org](https://mlx-framework.org/) - Apple silicon only.

## Caveats

- Upstream llama.cpp moves fast; re-verify arch support and HTP quant classes against the pinned revision actually installed on the laptop.
- A "ready" verdict from porting.py means the artifact is shaped for the requested runtime and evidenced for the architecture; it does not replace a measured load.
- The session limit (about 3.5 GB) and repack classes come from upstream docs at the cited revision; a different backend build can change both.

