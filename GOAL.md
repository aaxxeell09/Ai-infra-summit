# Local Turbo — project goal

Updated 2026-09-15. This file records the product goal and acceptance criteria. `todo.md` tracks execution; `AGENTS.md` records standing authority and working rules.

## Goal

Make a Snapdragon laptop a fast, private local AI workstation. Automatically measure compatible models and inference settings, recommend a configuration for the user's speed/efficiency preference, apply it to real inference, and complete useful agent tasks with verified results.

Pitch: **Getting a model onto a Snapdragon is easy; getting it fast is guesswork. This removes the guesswork.**

The product target is time and energy to a correct useful task, with native decode tokens/s as a component metric. Separately measure prefill throughput, time to first token and total useful task time. A faster incorrect action is not an accepted improvement. Fewer output tokens, context reduction and routing can improve task time without improving native decode speed; report these effects separately.

## Hardware and offline requirement

- Primary: Dell Latitude 7455, Snapdragon X Elite X1E80100, 32 GB RAM, Adreno X1-85, Windows ARM64.
- Optional edge node/controller: Arduino UNO Q ABX00162 with Modulino buttons, knob, buzzer, pixels and vibration modules as available. Register it as a separate device only after probing its actual capabilities. Linux ARM64 CPU inference is demonstrated with SmolLM2-360M Q8_0; the two diagnostic outputs failed exact formatting and do not establish Secretary eligibility. See `benchmarks/results/uno-q-smoke-01/`.
- Core operation must work without the internet after installation and model download. No hidden cloud inference or hosted scoring dependency.
- Credentials, addresses, connection details, model weights and raw private captures stay outside Git.

## What the user must be able to do

1. Select a locally available model and objective: fastest, most efficient or balanced.
2. Run a bounded tuner search over supported runtime/backend, quantization variants, context, decode/batch threads, batch and microbatch settings. See live progress, failures and comparable measured results.
3. Inspect a chart, explanation and recommended configuration. Export the complete configuration and evidence bundle.
4. Apply the exact selected configuration to the actual inference server. Verify model/runtime identity and effective settings; never silently substitute another configuration.
5. Complete a secretary task in a disposable local workspace, verify the action and final state, and report full task time.
6. Repeat through MCP: a larger agent chooses a mode, delegates a bounded task locally, and receives actual results, checks and metrics.
7. Use UNO Q buttons/knob to change the policy preference that selects and applies a measured configuration. Feedback reflects the acknowledged configuration. It must do more than change a visual indicator.

Demo: **Tune → choose speed or efficiency → run the same task → show the measured difference.**

## Model coverage and large-to-small delegation

Support an extensible model registry, not one hardcoded model or family. “Any model” means register, inspect and route through a compatible runtime or return a precise unsupported/conversion/compilation reason. Never claim every architecture executes on every backend.

- Tiny models for inexpensive narrow work; multiple families, including SmolLM and compatible Granite/Mamba-family candidates.
- Qwen3 0.6B and 1.7B, then 4B, 8B, approximately 14B and **20–25B-class quantized models** where verified runtime support, RAM and download/storage budget permit. Include an appropriate MoE candidate and record total versus active parameters separately. Account for weights, KV cache, runtime buffers and resident helper models in the 32 GB memory budget; measure serial loading/offload before keeping large and small models resident together. Larger experiments are wanted; parameter count alone does not establish quality.
- Multimodal models need matching projectors or compiled bundles and actual modality-specific tests.
- Compare GGUF/llama.cpp with compatible QAIRT compiled NPU models. Clearly disclose weight, quantization, architecture and runtime differences.
- A larger local model or external parent agent can plan/decompose work and delegate bounded tasks to smaller local workers through the router/MCP. The local implementation stays usable offline with a local parent model.
- Route using task type, context requirements, measured quality, latency/throughput, model residency/loading cost and energy where known. Escalate on explicit validation failure, not a guessed claim that larger is always better.
- Count parent planning, routing, loading, transfer, validation, retries and fallback in total task time. Do not hide those costs behind a fast small-model decode number.
- Model concurrency is an experiment: measure memory-bandwidth contention and throughput before claiming swarms are faster. Keep isolated single-request latency as a reference.

## Improve the inference stack, including GenieX

Using GenieX is the starting point, not the end of the project. Investigate changes around and within the runtime when there is a measurable opportunity.

- Automatic backend/configuration selection and persistent measured profiles; invalidate profiles when relevant model/runtime/device facts change.
- Prefill batching, microbatching, separate decode and batch thread settings, usable context and KV-cache footprint.
- Stable instruction/schema prefixes and explicitly measured cold-versus-warm prefix/KV reuse.
- Upstream speculative decoding, including n-gram and compatible draft-model methods. Record acceptance, output length, correctness and overhead; overshooting the requested output cap is not a fair fixed-length win.
- Structured tool-output constraints and compact typed-action experiments. Grammar validates form; it does not establish intent correctness.
- ARM CPU kernels, Adreno GPU and Hexagon/QAIRT paths; investigate portable techniques and architecture-specific kernels against the installed release. MLX-style ideas are research, not a claim that Apple kernels run on this laptop.
- Model import/preflight, conversion and QAIRT compilation helpers where supported. Report unsupported operators, artifacts and chipset/context requirements accurately.
- Prefer reviewable patches, documented upstream provenance/licenses and reproducible ablations. Do not call established upstream features novel. A broader “faster than open source” claim requires a fair independently tuned upstream comparison.

## Local context optimization

Implement Parsec-like benefits without requiring a hosted scoring API. Start with deterministic projection, retrieval and structured tool-output reduction; consider local learned scorers/compressors only when their own latency, memory and quality costs are measured.

Preserve system instructions, tool schemas, code, exact filenames/paths, numbers, errors and constraints. Keep original tool results locally recoverable by content hash. Label lossy projection/pruning. Measure compressor/recovery/cache-invalidation costs and exact task correctness. RTK-style reduction and concise prose are task-efficiency experiments, not native decode-speed improvements.

## Frozen correctness reference and ownership

Axel/Codex owns the golden benchmark, expectations, scoring and methodology. **`secretary-eval-v2` is frozen at `ccd1e00327fe5cabe875acec166e7d9831c1cfe0`: 35 development + 15 held-out cases, actual single-action fixture execution and final-state checks.** Do not modify it or tune on held-out answers without coordination.

Henry explicitly designated the untuned reference after a separate historical pre-optimization Secretary deployment could not be established. It uses Qwen3-0.6B Q4_0, GenieX 0.6.1 `llama_cpp`, auto placement, default threads/batching, context 4096, temperature 0, max 128 generated tokens, fresh KV per case, no grammar/speculation/routing. Full model/runtime hashes, clean application commit and exact execution instructions are under `eval/results/`. **Temperature zero was requested, but the tagged GenieX implementation substitutes sampling defaults for zeros; see `eval/results/baseline_sampling_note.md`.** Preserve this original behavior in the reference and test the greedy workaround as a separate candidate.

Verified reference: **30/50 tasks correct (60%)**, tool/action 70%, all-case arguments 82%, clarification **0/13**, mean inference 1209.531 ms, median 1147.561 ms, p95 1500.174 ms. It resolved to HTP0 and ran on AC power. Results committed in `6ac2aef`.

First same-weights candidate, CPU/10: **33/50 (66%)**, mean inference 853.287 ms (1.4175× observed latency ratio), median 853.103 ms, p95 986.358 ms. **Quality gate FAIL** because 8% invalid outputs exceeds the frozen 2% absolute limit. This is not an accepted optimization. Results committed in `3450c85`; the failed candidate remains visible.

Gate: at most 3 percentage points lost overall; no critical move/clarify regression; preserve the additional frozen policy checks and category audit. Small experiments do not each need a full correctness run. Every serious candidate must be committed, described and evaluated with the same benchmark.

Handoff fields: candidate name, application commit, change, expected benefit, model/weights hash, runtime/backend, full config, exact command and results under `eval/results/`.

Workflow: fixed baseline → experiment → serious candidate committed → metadata recorded → unchanged benchmark → speed/accuracy/category comparison → PASS/FAIL → next iteration. Never overwrite the baseline or weaken a gate to publish a win.

## Evidence and acceptance

For comparable trials retain model/runtime hashes, exact commands/configs, source commit and clean state, warmup/cache policy, output lengths, power state and competing workloads. Measure prefill/decode separately, TTFT, complete task time, memory and requested/resolved/observed dispatch. Instrumented diagnostic traces are separate from clean timing runs.

Use actual Windows Energy Meter units and matched intervals. SYS energy is a named meter channel, not wall-plug or NPU-only power. Tokens/J requires all generated tokens in the same interval, including warmups when present. Missing energy is unavailable, never zero. Do not sum overlapping rails.

Completion means the entire tuner → recommendation → applied runtime → correct secretary action → MCP flow works on the Latitude, with a reproducible measured improvement that passes the quality gate. The current 0.6B clarification failure prevents claiming a dependable secretary or completed product.

Greedy top-k workaround candidate (`41260c4`): **29/50 (58%)**, mean inference **823.220 ms**, median **845.590 ms**, p95 **933.759 ms**; gate **FAIL** for invalid output rate and a read-category regression. Correcting requested sampler semantics did not make the small model a reliable secretary. Keep it as an explicit experiment rather than silently promoting it.

## Working rules and delegation

- Work autonomously within the authorized scope. Keep the Latitude busy with useful queued measurements and downloads, but isolate official performance trials. A memory-bound workload need not show 100% CPU; do not add busywork that contaminates evidence.
- Commit and push small coherent milestones frequently. Fetch and check PRs before pushes; preserve teammate work. Human teammates own frontend/demo design; integrate their provider contract rather than redesigning it independently.
- Use isolated worktrees and bounded GLM-5.3-Flash workers. Separate Codex CLI processes are authorized and verified; they do not remove provider rate limits or create new allowance. Avoid overlapping write scopes and use one hardware owner.
- Independent adversarial review is required for measurement claims and integration. Use real Claude Code/Fable with the selected algosoup.ai account when authenticated; never silently rotate accounts or use a paid fallback.
- Keep claims honest and documentation current. Retain failures and uncertainties. The requested demo deck must be rendered and visually inspected, and its charts must come from accepted evidence.

## Immediate priorities

1. Secure unattended access before the Latitude is left at the venue. Fresh Tailscale SSH is verified after the Mac changed networks, and the local tunnel supervisor restarts successfully. Graphical desktop authentication still needs the Microsoft-backed Windows account credential. Keep the machine awake with a bounded process-scoped request.
2. **QAIRT artifact and first full evaluation are complete.** Official Qwen3-0.6B W4A16 loaded on HTP v73; full result is 23/50 (46%), mean inference 786.338 ms, 34% invalid outputs. Distinguish its compiled deployment from GGUF CPU/HTP. Preserve all failures and do not qualify the model from throughput alone.
3. Coordinate evaluator provenance with Axel before a formal comparison: the historical-reference guard correctly reports NOT_COMPARABLE. The questions, expected actions and scoring were preserved. Resolve the scanner's false positives on archived result reports with benchmark ownership.
4. Complete the hash-bound tuner → recommendation → exact apply → correct task → MCP loop. Wire teammate frontend to real sequential trials. Hardware policy changes must alter the same applied configuration and show acknowledged feedback.
5. Make Secretary reliable. Keep the measured CPU10 path; independently test production-schema grammar and conservative preconditions without changing golden answers. Coordinate any evaluation-adapter extension with Axel. The 1.7B result (34/50, 68%, 2839.033 ms mean, failed gate) does not establish a dependable larger-model solution.
6. After the first QAIRT comparison, select one exposed QAIRT tuning experiment from evidence. Then resume 4B/8B/20–25B quality/routing trials and isolated prefix/KV, batch, speculation and local context experiments. UNO Q now has a real SmolLM2-360M CPU run; its exact-output failures prevent task admission. Physical controller acknowledgement remains pending.

The supplied Henry V2 synthesis is research evidence. Its exact-runtime checks, output-validity findings, separate prefill-thread experiment and measurement cautions guide implementation. The subsequent explicit Qualcomm feedback makes the clean QAIRT comparison the immediate priority. See `docs/qairt-roadmap.md` for the execution gates.


Latest access state: offsite Tailscale SSH returned on the evening of September 15.
A fresh checkout pinned to `16d1313` completed two real QAIRT tune/apply/MCP cycles;
both invoice tasks failed. The verified 4B transfer is underway. Overnight work
is authorized through September 16 at 09:00 Pacific, with bounded jobs and cost
controls. See `docs/overnight-handoff.md` for the current checkpoint.
