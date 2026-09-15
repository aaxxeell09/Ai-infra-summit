# Build queue and ownership

Last updated: September 15, 2026. Check this file, `AGENTS.md`, open PRs and remote changes before starting a workstream. Commit and push small working milestones often.

## P0 — prove the central benefit on the Latitude

Owner: main integration agent. Independent review: `review/benchmark-energy` worktree.

- [x] Install native ARM64 GenieX benchmark on the actual Latitude.
- [x] Download and SHA-256 verify Qwen3-0.6B Q4_0 on both computers.
- [x] Screen CPU thread counts, GPU, NPU and hybrid on identical weights.
- [x] Publish raw screening results, exact commands, model/runtime hashes, memory and energy-counter evidence.
- [x] Run five alternating default-CPU versus selected-CPU pairs with 15 repetitions per trial.
- [x] Audit and publish confirmation results; disclose substantial run-to-run variation and unresolved power/thermal effects.
- [x] Run a separate default automatic-dispatch versus tuned comparison. Source inspection says GenieX v0.6.1 defaults to NPU; verify it on-device. Keep the stronger default-CPU baseline visible.
- [x] Capture operation-level Hexagon dispatch evidence in a diagnostic run separated from clean timing.
- [x] Record power state around every trial; identify reset/stale/missing telemetry and preserve failures.
- [x] Export a recommended configuration with evidence and scope, not an unsupported universal speedup claim.

Acceptance: reproducible same-model measurements of prefill/decode tok/s, TTFT, memory and correctly scoped measured energy. Report tokens/J over an explicitly defined interval. Keep raw per-run distributions.

## P1 — ship the tuner

Owner: worker in `feat/tuner-engine`; integration: main agent.

- [ ] Configurable registry of model variants, runtime/plugin, backend, context and thread candidates.
- [ ] Capability-aware search: reject invalid QNN/QAIRT device/context combinations; require a matching multimodal workload.
- [ ] Serial isolated trial execution with progress, bounded timeouts, logs and failed candidates retained.
- [ ] Objective selection for decode, prefill and latency; quality/context constraints remain explicit.
- [ ] Batch/microbatch tuning through the native SDK. Do not invent native benchmark flags that are unavailable.
- [ ] API contract for live chart, measurement status and exportable configuration.
- [ ] Integrate teammates' frontend PRs and perform end-to-end checks against actual laptop results.

Acceptance: select a registered model, run a valid device sweep, inspect charts and download a usable recommended configuration.

## P1 — model and architecture coverage

Owner: worker in `feat/model-catalog`; hardware execution: main agent.

- [x] Qwen3-0.6B dense text model: actual CPU/GPU/NPU/hybrid inference verified.
- [ ] Finish Qwen3-1.7B Q4_0 download, verify checksum and benchmark.
- [ ] Finish Qwen3-4B-Instruct-2507 Q4_0 download, verify checksum and benchmark.
- [ ] Add a very small instruction model from another family; identify exact model/quantization and license.
- [ ] Add an IBM Granite or Mamba-family candidate; verify actual architecture and installed-runtime support rather than assuming support from its name.
- [ ] Add a multimodal candidate with matching projector or compiled bundle and a fixed image workload.
- [ ] Compare compatible QNN/QAIRT and llama.cpp variants with quantization/model differences disclosed.
- [ ] Record per-backend success, fallback and failure. A family listed in the catalog is not a claim of hardware validation.

Acceptance: catalog contains verified provenance and compatibility status; each claimed supported path completes real inference and produces accepted measurements. No weights in Git.

## P1 — agent workload and quality

Owner: main agent. Initial worker implementation available for integration.

- [x] Streaming benchmark client with correct partial-line SSE handling and provider token counts.
- [x] Native SDK adapter and ABI/layout tests implemented; hardware smoke test passed on the Latitude.
- [x] Disposable secretary fixture and bounded file tools implemented.
- [ ] Review tool validation, symlink handling and task gold labels; fix inconsistent/missing fixture references.
- [ ] Run held-out structured-tool requests on actual local models; score names, arguments and final state.
- [ ] Compare verbose tool calls with snapshot-bound compact ToolWire actions and optional constrained grammar.
- [ ] Calibrate model routing with measured quality tiers and account for retry/fallback/loading time.
- [ ] Test prefix reuse, deterministic context reduction, Caveman-style prose brevity and RTK-style tool-output reduction separately.
- [ ] Evaluate local learned compression only if its own runtime plus recovery/cache costs are measured.

Acceptance: faster tasks still satisfy exact constraints. Valid JSON alone does not count as correctness.

## P2 — deeper portable optimizations

- [ ] Speculation ablations: n-gram variants, acceptance rates and real tool/copy workloads.
- [ ] Explore draft-model speculation and supported architecture-specific optimizations; retain only measured wins.
- [ ] Test context-length and prefill microbatch effects without silently reducing required usable context.
- [ ] Inspect KV cache opportunities and source-level CPU/GPU/NPU changes where practical.
- [ ] Compare with an independently tuned upstream runtime before claiming superiority over open source generally.
- [ ] Investigate original combinations without claiming established upstream techniques as novel inventions.

## Product, demo and submission

Owner: human teammates (frontend design, demo and submission); agent supplies backend data, API documentation and requested artifact support.

- [ ] Tuner-first interface: prefill, decode, TTFT, dispatch evidence, memory, power/energy and recommendation.
- [ ] Keep prototype UI separate from teammate design work; review open PRs before every push.
- [ ] Demo story and live recording on actual hardware.
- [ ] Demo PowerPoint with accepted measurements, reproducible chart and precise limitations.
- [ ] Confirm current judging/submission requirements and rehearse a three-minute presentation.

Pitch: “Getting a model onto a Snapdragon is easy; getting it fast is guesswork. This removes the guesswork.”

## Review and operational work

- [x] Project instructions record autonomous development, frequent commits/pushes and division of work.
- [x] Latitude keep-awake task runs for a bounded 12 hours without permanent power-plan changes.
- [ ] Fable 5.1 review through Claude Code on `henry.qin@algosoup.ai` when the saved login is restored. Account currently reports unauthenticated; no silent fallback.
- [ ] Continue higher-level adversarial review and integrate useful findings.
- [ ] Check PRs and remote changes before pushing; preserve collaborators' files and branches.

## Feature ledger from the full conversation

These are retained requirements; a new tuner direction does not silently remove them. Delivery order is evidence first, integrated tuner next, then workload/context improvements with their own ablations.

| Requested capability | Implementation / next evidence | Owner |
| --- | --- | --- |
| Automatic model/device tuning | Registered quantization/runtime/context/thread/batch candidates; export a measured recommendation | Tuner worktree + integrator |
| Raw speed beyond a stock install | Same-weights default-auto and strong CPU baselines; independently tuned upstream comparison before broader claims | Integrator |
| Small and large local model routing | Hardware profiles plus task-quality eligibility, resident-model/loading/prefix costs | Integrator |
| Local secretary and structured tool use | File fixture, exact action/state evaluator, clarification/negation tests | Integrator |
| Agentic coding harness integration | Document and smoke-test an actual supported OpenAI client/harness; identify unsupported streaming/tools explicitly | Integrator |
| Agent swarms | Measure concurrent-request/model contention and throughput before enabling; retain sequential low-latency mode | Integrator |
| Prefill optimization | Context/prompt buckets, separate batch threads and microbatch sweeps | Tuner + integrator |
| KV cache and prefix reuse | Stable system/schema prefix; cold versus warm experiment; avoid compression invalidating earlier cache | Context + integrator |
| Parsec-like context reduction fully local | Deterministic projection/retrieval first; optional local learned scorer with measured overhead | Context worktree |
| Local LLMLingua-style alternative | Verify checkpoint/runtime/ARM64 compatibility; measure quality and compressor cost rather than assuming a win | Catalog/context + integrator |
| RTK-style tool-output reduction | Explicit eligible outputs, preserved exit/error information and exact raw recovery | Context worktree |
| Caveman-style efficiency | Optional concise prose budgets; preserve JSON, code, paths, numbers and required detail | Context worktree |
| Compact tool/action representation | Snapshot-bound ToolWire, optional grammar, same semantic task checks and actual generated-token counts | Integrator |
| Portable architecture/kernel optimizations | Speculation first; investigate runtime-supported kernels/SSM/multimodal paths with dispatch proof | Integrator + catalog |
| Original contribution | Measured combination of calibration, routing and compact local actions; compare prior art without claiming invention prematurely | Integrator |
| Broad model families | Qwen sizes, a second tiny dense family, Granite/Mamba candidate, multimodal and compatible QNN bundles | Catalog worktree |
| High-level/adversarial reviews | Independent measurement audit; Fable through selected Claude Code account when login works | Review worktree + integrator |
| Demo deck and actual E2E demonstration | Teammate frontend/design; agent data/API/deck support; actual laptop execution and reproducible charts | Humans + integrator |
| Frequent GitHub commits and PR awareness | Inspect open PRs/remotes before pushes, small working commits, isolated worker branches | Everyone |

Superseded by explicit user pivot: workshop safety camera, Arduino sensor/actuator orchestration and inspection-station UI. Preserve their archive without spending the current inference-tuner critical path on them.

## High-value additions under consideration

These extend the requested tuner; they do not precede the P0 evidence milestone.

- [ ] **Fast / efficient / balanced objectives:** compute a speed–energy Pareto frontier from comparable measured trials, then recommend within explicit latency, memory and quality constraints.
- [ ] **Sustained-performance mode:** report early versus late throughput, variability and slow-tail behavior; avoid choosing a configuration solely from a short burst. Investigate observed baseline dips without inventing a thermal cause.
- [ ] **Dispatch/fallback detective:** retain runtime coercion warnings and operation-level device evidence; distinguish requested placement, resolved device and observed execution.
- [ ] **Workload replay:** replay local secretary/coding traces with fixed fixtures, controlled cache state and exact output checks.
- [ ] **Attribution dashboard:** ablate runtime tuning, model routing, prefix cache, context reduction, concise output and compact actions independently.
- [ ] **Portable evidence bundle:** export model/runtime hashes, device/power state, complete config, raw measurements, failures, quality scores and reproduction commands.
- [ ] **Profile invalidation:** rerun calibration when the model, quantization, runtime, driver or relevant device configuration changes.
- [ ] **Search-budget control:** quick screening versus longer confirmation, with elapsed-time budget and explicit incomplete/unsupported trials.

## Added September 15: agent control, ports and kernels

- [ ] Agent-facing MCP: local model/status tools, bounded local worker calls, explicit fast/efficient/balanced mode selection and tuning requests. Owner: `feat/agent-interface`.
- [ ] Model import/preflight: distinguish directly loadable GGUF, conversions, architecture support and chipset/context-specific QAIRT compilation. Owner: `feat/kernel-ports`.
- [ ] Kernel research: compare MLX portability, ARM CPU kernels, Adreno and Hexagon paths against the installed release; require real hardware wins before adoption. Owner: `feat/kernel-ports`.
- [ ] Speculative decoding: actual supported n-gram screening, then compatible draft models with acceptance and output-correctness checks. Owner: integrator.
