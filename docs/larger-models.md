# Larger models on the Latitude

The requested coverage extends to 20–25B models. The registry contains pinned
artifacts, not a promise that each model runs on the installed backend.

| Candidate | Weights | Role to test | Status |
| --- | --- | --- | --- |
| Qwen3-4B-Instruct-2507 Q4_0 | 2.376 GB | Instruction-focused secretary | Download in progress |
| Qwen3-8B Q4_K_M | 5.028 GB | Larger dense model, same broad family | Pinned; download/runtime validation pending |
| gpt-oss-20b MXFP4 | 12.110 GB | Local planner and difficult tool requests | Pinned; download/runtime validation pending |

Sizes are exact artifact bytes expressed as decimal GB. SHA-256 values and
repository revisions are in [the catalog](../configs/model-catalog.json).
Qwen3-8B Q4_0 is absent from the pinned Unsloth repository; the selected Q4_K_M
artifact needs its own backend checks. It is not interchangeable with the
Q4_0 weights used in our existing measurements.

The [gpt-oss model card](https://huggingface.co/openai/gpt-oss-20b) describes
21B total parameters with 3.6B active per token. All weights still need storage
and runtime memory. It requires Harmony formatting. The
[ggml-org conversion](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF)
is a candidate for the installed GenieX llama.cpp plugin; upstream support
does not prove that our packaged version supports its kernels or tool parser.
For [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), separate thinking and
non-thinking configurations and count reasoning tokens in task latency.

## Admission and measurements

1. Download the pinned file and verify its full SHA-256 before registration
   in the live service. Keep weights outside Git.
2. Check free RAM and storage. Start at context 2048 and short outputs with one
   resident model. Measure load time, process peak memory and paging before
   expanding context or keeping a helper model resident.
3. Probe CPU first, then supported GPU/NPU paths. Preserve loader errors and
   requested/resolved dispatch. A candidate that cannot load remains unsupported
   for that specific runtime/configuration.
4. Verify plain generation, the required chat template and structured tool
   output. Grammar validity alone does not establish the right action.
5. Screen prefill, decode, TTFT, task latency, memory and matched-interval SYS
   energy. Model substitutions are separate from same-weights tuning gains.
6. Commit a serious candidate and run the unchanged frozen correctness suite.
   Do not use held-out answers to tune the parser or prompt. Preserve the
   official reference and the existing quality gate.

## Large-to-small routing

First compare each model alone on a task category. Route narrow tasks to a
smaller model only when measured quality permits it; keep difficult requests
with the larger model or escalate after an explicit validation failure.
Measure planner time, model swaps, loading, worker generation, validation and
fallback together. Concurrent residency and simultaneous requests are later
experiments, since both consume the same 32 GB RAM and memory bandwidth.

The current service chooses a measured configuration by mode. The separate
quality-aware router still needs service integration; this document does not
claim that large-to-small delegation is working yet.
