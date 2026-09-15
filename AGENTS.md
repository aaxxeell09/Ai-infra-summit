# Local Turbo — project instructions

## Objective and current scope

Build an automatic local inference tuner for the Dell Latitude 7455 with Snapdragon X Elite X1E-80-100, 32 GB RAM, Adreno X1-85 and Windows ARM64.

The product takes a locally available model and finds a good configuration for the device through actual measurements. Compare supported runtime/backend, thread, context and batch settings; extend to registered quantization variants and compatible QNN/QAIRT bundles. Output a chart, an exportable recommended configuration and the evidence behind the recommendation.

Pitch: “Getting a model onto a Snapdragon is easy; getting it fast is guesswork. This removes the guesswork.”

A local secretary that performs structured file operations is the demonstration workload and quality check. The former camera/workshop/Arduino inspection product is superseded. Its code is preserved on `archive/inspection-station`; do not restore that scope without a user request. The UNO Q and Modulinos are available hardware, but are not required for the inference tuner.

## User preferences and standing authority

- Work autonomously and carry development through implementation, tests, real-device measurements, documentation and demo artifacts. Make routine reversible decisions without repeatedly asking permission.
- **Commit and push to GitHub frequently.** Make small coherent checkpoints after a working change or meaningful verified milestone. Do not leave hours of completed work only in the working tree. The user explicitly authorized commits and pushes to `aaxxeell09/Ai-infra-summit` using GitHub account `Qin2Qin`.
- Check current work before committing; preserve other contributors' edits. Run relevant checks and inspect the staged diff. Never commit credentials, private connection details, model weights or raw private captures.
- Refactor aggressively when evidence shows the design is wrong. Preserve useful work in Git, and explain material changes briefly.
- Optimize for speed of execution and credible evidence. Prefer implementation and experiments over repeatedly expanding plans.
- Keep updates concise, grammatical and specific. Provide a meaningful update during sustained work, roughly every minute. State measured results and limitations directly; avoid hype and invented speed claims.
- Suggest improvements to the idea, targets and demo as evidence develops. Challenge assumptions, including the claim that NPU must be fastest.
- Ask only for genuinely missing information, a new consequential action outside existing authority, or hardware/account access that cannot be restored autonomously. Continue independent work while awaiting an answer.

## Ownership

The coding agent owns both workstreams 1 and 2:

1. **Device and performance:** runtime/model variants, tuner search space, reproducible benchmarks, dispatch evidence, energy and memory telemetry, configuration recommendations.
2. **Tasks and correctness:** secretary fixtures, held-out prompts, exact tool/action checks, routing quality gates, regression evaluation.

Human collaborators can own workstream 3: product presentation, live demo/video, pitch, slides and submission requirements. The coding agent still supplies an integrated UI and requested PowerPoint/demo artifacts. See `docs/team.md` for boundaries and handoffs.

## Measurement requirements

Run headline benchmarks on the actual Latitude, with native ARM64 binaries. Mac timings are not a substitute.

Report separately:

- Prefill tokens/s and decode tokens/s.
- Time to first token and total completion/task time.
- Requested backend, resolved device and evidence of actual CPU/GPU/NPU execution.
- Memory footprint, with the metric and scope stated.
- Measured power and energy efficiency where telemetry is available.
- Tool/action correctness, output length, retries, failures and fallback overhead.

Use the same model weights and quantization for a runtime-tuning speedup claim. Model routing and quantization are separate experiments. Preserve warmup policy, context/prompt/output lengths, random seed, power state, background workloads, model hashes, binary versions and exact commands. Screen candidates, then confirm promising settings with alternating paired trials. Keep failed configurations visible.

The Latitude exposes Windows Energy Meter counters including `SYS`, CPU clusters and GPU. On-device counter help identifies Energy as picowatt-hours, Time as milliseconds and Power as milliwatts. Verify availability/units when initializing telemetry. Use energy differences over a matched measurement interval. Label the measured channel; do not equate a rail, battery estimate and wall-socket power. Do not sum overlapping rails. Missing, stale or reset readings mean unavailable, not zero. Express `(tokens/s)/W` as tokens/J and state whether the interval includes loading, prefill, warmup and decode.

A requested `npu` flag, allocated NPU buffer or TOPS specification alone is not proof of active NPU computation. Capture execution/profile evidence where possible. Instrumentation can affect performance; separate diagnostic dispatch runs from clean timing runs.

Never count streaming chunks as tokens. Use runtime/provider token counts. Do not credit answer replay, shorter output or context compression as increased native decode tokens/s. A valid JSON response is not necessarily a correct action. Publish assumptions and provisional recommendations explicitly.

## Architecture and experiment rules

- Core inference, routing, context handling and tool execution must work offline after dependencies/models are installed. Do not silently add hosted scoring or cloud inference.
- Use Qualcomm GenieX and its native SDK where appropriate. Version-pin ABI bindings. Test CPU, GPU, NPU and hybrid rather than assuming a winner.
- QNN/QAIRT compiled bundles must be compatible with their architecture, chipset and compiled context. Never relabel a coerced NPU-only run as CPU.
- Preserve stable instruction/schema prefixes. Reduce eligible dynamic tool outputs with an auditable local raw-data recovery path. Projection/pruning is lossy unless proven otherwise.
- ToolWire is an experiment in compact typed actions bound to a file-inventory snapshot. Exact symbol expansion and schema/grammar checks do not establish semantic correctness; evaluate intent separately.
- The calibrated router may optimize decode throughput or estimated end-to-end latency subject to context and measured quality constraints. Mark estimates and uncalibrated bootstrap decisions clearly.
- Credit upstream features. Investigate portable optimizations and original combinations, but do not claim a feature is new merely because this project implements it.
- Agent swarms or simultaneous models can compete for memory bandwidth. Isolate benchmark trials and measure contention before adding concurrency.
- Keep file tools inside disposable demo fixtures with traversal, symlink and overwrite protections. Do not let model output execute arbitrary shell commands.

## Research and review

Use primary technical sources: official documentation, version-pinned source, model cards and research papers. Verify support against installed binaries; current upstream may differ. Store the useful research outline in `docs/research.md` and benchmark methodology in `docs/benchmark-protocol.md`.

Use bounded independent subagents for separable implementation and adversarial review. Prefer the configured economical GLM-5.3-Flash route when the exact model is available; give narrow context and disjoint file ownership. Do not duplicate delegated work. Verify decision-relevant findings and reconcile disagreements.

The user requests consequential review from Fable 5.1 through the real Claude Code harness. Use the user-selected saved identity `henry.qin@algosoup.ai` by email, not an assumed slot number. Do not default to slot 2. Follow the local `cost-aware-delegation` skill. If authentication is unavailable, report that accurately and continue other work. No silent account rotation, quota reset, paid fallback or direct extracted-token API calls.

Use the presentation skill for the requested demo deck, and visually verify every final slide. Base charts and claims on accepted measurements; label pending metrics rather than filling them with illustrative numbers.

## Repository hygiene and operation

- `local/` holds private machine configuration, SSH helpers, models, credentials-free raw working logs and temporary artifacts; it is ignored.
- `models/` and large model artifacts stay out of Git.
- Public SSH documentation uses placeholders. Never publish passwords, private keys, device addresses or account tokens.
- Preserve the user's power settings. A process-scoped keep-awake helper is authorized during development; it must release its request on exit and have a bounded lifetime.
- Use relevant tests and real-device smoke checks; do not substitute unit tests for hardware execution. Stop expanding tests once the current change is adequately verified.
- Keep README status and the public recommended configuration consistent with what actually works. A successful tool invocation is not proof that inference, telemetry or a benchmark succeeded.
