# Build queue and ownership

Last updated: September 16, 2026. Check this file, `AGENTS.md`, open PRs and remote changes before starting a workstream. Commit and push small working milestones often.

## Immediate demo priority — September 16 morning

The next deliverable is **local inference tuning with verified agent actions**.
See [the three-minute runbook](docs/narrow-demo-runbook.md) and
[the four-slide deck](demo/local-turbo-narrow-demo-v3.pptx). Broader backlog below
is preserved; it is not evidence that unfinished features are demo-ready.

- [x] Verify the 4B public invoice fixture through real MCP, including content and surrounding file hashes. Existing exact-call grade still fails; see `benchmarks/results/feedback-mcp-1300/`.
- [x] Publish balanced repeated QAIRT output-stopping evidence: 34.48% lower mean inference latency, caused by shorter generation. No native tokens/s, energy or quality-gate win.
- [x] Publish and visually inspect a concise, evidence-scoped PowerPoint and presenter runbook.
- [x] Integrate and locally test the bounded one-command presenter CLI, including recorded-payload verification and malformed-reply failures.
- [ ] Verify the new presenter entrypoint in a successful hardware rehearsal. Its underlying MCP path already has recorded evidence.
- [x] Retrieve the already completed `Qualcomm-Bound-MCP-1400` result and independently verify both selected configurations and actual copied final files. Exact-call grades remain false; see `benchmarks/results/bound-feedback-mcp-1400/`.
- [ ] Restore reliable access and the live gateway. Retrieval briefly succeeded, but a later SSH read failed; the gateway task was disabled with no port 8083 listener at cutoff.
- [ ] Replace the teammate frontend's preview finale with a verified live provider; preserve its design ownership and label recorded fallback explicitly.
- [ ] Review teammate TurboLab branch `claude/beautiful-mayer-gslb35` at `33de023` before integration. It is not yet a validated demo dependency.

All broader quality gates remain unpassed. At 09:00 Pacific, stop starting
experiments and leave the scheduled final handoff.

## Current execution order — Qualcomm feedback

The native QAIRT comparison now leads engineering work; see [the gated roadmap](docs/qairt-roadmap.md). Earlier queues below remain backlog, not simultaneous priorities.

- [x] Verify Tailscale unattended connection and fresh SSH through the private overlay.
- [x] Verify fresh Tailscale SSH after Mac changes networks and supervised tunnel recovery.
- [ ] Finish graphical desktop authentication (Microsoft-backed Windows account).
- [x] Confirm installed GenieX catalog lists Qwen3-0.6B QAIRT for X Elite and QAIRT 2.45 is installed.
- [x] Finish official QAIRT artifact download/import; record local ZIP hash, W4A16 precision and compiled contexts.
- [x] Prove prompt-dependent QAIRT inference with loaded HTP v73 runtime and two compiled shards.
- [ ] Capture per-graph execution selection; keep this distinct from generic dispatch/utilization claims.
- [x] Register distinct QAIRT, llama.cpp CPU and llama.cpp HTP identities; native QAIRT load/generation and full evaluation now recorded.
- [x] Run clean QAIRT development (14/35) and unchanged full 50-case candidate (23/50); publish failures, runtime hashes and full-process telemetry. No grammar/context/router changes. Historical comparison is NOT_COMPARABLE because evaluator provenance changed.
- [ ] Publish three-path correctness/latency/energy comparison and choose modes only from evidence.
- [ ] Finish exact hash-bound tune/apply/task/MCP and real frontend/controller demonstration.
- [ ] Pick one supported QAIRT tuning experiment after its baseline works; then return to reliability, larger models and context/prefix work.

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
- [x] Finish Qwen3-1.7B Q4_0 download, verify checksum and benchmark (10 real backend/thread cells; publication review pending).
- [x] Finish Qwen3-4B-Instruct-2507 Q4_0 download, verify checksum and benchmark. Full result 37/50; quality gate unpassed. See `eval/results/candidate_qwen4b-cpu10-v2.md`.
- [x] Download/checksum and exercise 8B and 20B models. 8B full result 38/50; 20B development 0/35 from incompatible output format. Native generation is not Secretary eligibility; see `eval/results/qwen8b-full-1200/` and `eval/results/large-model-dev-1100/`.
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
- [x] Freeze user-confirmed untuned reference on all 50 v2 cases: 60% task success, 0/13 clarification, 1209.531 ms mean inference; exact intent/action/final-state scoring. Candidate comparisons next.
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

Superseded: workshop safety camera and inspection-station UI. The user subsequently reintroduced UNO Q as a functional physical mode controller and a separate optional local inference device. Its adapters are integrated; real SmolLM2-360M CPU inference is recorded in `benchmarks/results/uno-q-smoke-01/`. Exact-output failures prevent Secretary admission. Physical controller acknowledgement remains unverified.

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

- [x] Agent-facing MCP tools implemented and integrated. Actual mode application and invoice inference exercised on the Latitude; both invoice tasks failed semantic checks. Evidence: `benchmarks/results/integration-01/`. Accepted task-quality demonstration remains open.
- [ ] Model import/preflight: distinguish directly loadable GGUF, conversions, architecture support and chipset/context-specific QAIRT compilation. Owner: `feat/kernel-ports`.
- [ ] Kernel research: compare MLX portability, ARM CPU kernels, Adreno and Hexagon paths against the installed release; require real hardware wins before adoption. Owner: `feat/kernel-ports`.
- [ ] Speculative decoding: actual supported n-gram screening, then compatible draft models with acceptance and output-correctness checks. Owner: integrator.

## Current integration acceptance

Tune → export measured mode → apply native runtime settings → run a secretary fixture → verify calls and final state → repeat via MCP. The 0.6B model currently fails the invoice semantic task; do not call the full flow successful until repaired or a better model passes.

Axel's authoritative **secretary-eval-v2** arrived in `ccd1e00` and is frozen. It executes the actual production tool in an isolated fixture and checks final state, with 35 development and 15 held-out cases. Henry confirmed an explicitly untuned reference after historical-original provenance could not be established. The official 50-case baseline is committed under `eval/results/`; prior v1 diagnostics remain quarantined.

- [ ] Inference router: measured small/large profiles, quality eligibility and explicit escalation on invalid actions, with retries and model-load cost included.
- [ ] Extensible model registration across supported runtime architectures; unsupported models receive a precise conversion/compilation/kernel requirement.
- [ ] Optional lightweight Pi client integration after the local service + MCP demo passes; no extra harness dependencies on the critical path.

Latest correctness coordination: **v2 frozen; confirmed baseline measured** at `ccd1e00`, results commit `6ac2aef`. Preserve this reference; evaluate CPU/10 as the first serious candidate. Do not modify golden data. Gate: ≤3 percentage-point accuracy drop and no critical move/clarify regression. Serious candidate and evaluation handoffs belong under `eval/results/` with commit/config/command.

## Active isolated Codex work

Separate CLI Codex processes using GLM-5.3-Flash successfully run in isolated worktrees. The native session cap and provider request-rate limits still apply to their respective routes; no unlimited-capacity claim. Current scopes: integration correctness review, saved performance-evidence audit, constrained-tool grammar experiment, and UNO Q adapter hardening. Only the parent owns hardware inference during official evaluations.

## Latest live integration and model queue

- [x] Run the HTTP tuner on the Latitude and export measured CPU/NPU configurations.
- [x] Apply both configurations through actual stdio MCP and execute invoice requests; preserve both failures.
- [ ] Correct the failed invoice behavior and pass the unchanged quality gate.
- [ ] Complete pinned Qwen3-8B Q4_K_M and gpt-oss-20b MXFP4 downloads queued on the Latitude; checksum, memory, runtime and tool-parser checks precede admission.
- [x] Finish and checksum Qwen3-4B-Instruct-2507 Q4_0 download on Mac.
- [ ] Transfer the verified 4B model to Latitude, then prioritize its secretary evaluation.


## Latest checkpoint: QAIRT loop and SDK binding

- [x] Publish full native QAIRT 50-case result and runtime components (`8192409`).
- [x] Fix compiled-shard/context tuner ABI and run a real two-repeat Latitude cell (`718140c`).
- [x] Implement SDK-library-bound recommendations, QAIRT mode apply, and repeated MCP/HTTP/native-loop smoke harness (`efd5100`).
- [x] Run the two-round QAIRT integration harness after access returned, on clean `16d1313`; tune/apply/inference/MCP succeeds, both invoice checks fail.
- [ ] Restore normal service after isolated tests; it is currently intentionally stopped.
- [ ] Coordinate evaluator hash migration and archived-report leakage scan with Axel. No golden benchmark changes made.
- [ ] Qualify a reliable Secretary model before enabling accepted product modes. Current speed/efficiency recommendations remain provisional, quality uncalibrated.
