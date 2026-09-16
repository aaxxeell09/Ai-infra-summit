# TurboLab readiness

Snapshot: **2026-09-16**. Inspected implementation: **`c866c48f0d12219d8cf38187c71769623143c0c8`**. Evidence provenance and measured historical aggregates are detailed in [CURRENT_STATUS](CURRENT_STATUS.md). This update performs no inference and changes no frozen evidence.

## READY

- TurboLab source has bounded backend-aware search, static admission, stage-specific execution, proposer/critic call sites and sealed-archive ingestion. See [implementation and contracts](turbolab.md).
- S1 is a startup/liveness probe. S2/S3 are diagnostic canaries, explicitly not qualified promotion evidence. S4/S5 use the tracker and the full 35-case development split. Generated candidates, hardware attempts and qualified experiments remain different counters.
- Development-only search and the separate explicitly requested frozen final milestone path are present. Neither diagnostics nor search may tune on heldout cases.
- The current supported QAIRT experiment controls are `max_tokens` and `stop_after_tool_call`. A proposed sampler, grammar, prompt, parser or executor change is not silently part of that contract.
- Portable tests are owner-reported at approximately **1,106**, with OS-dependent counts. That count is not a new measurement or a claim of target execution. This docs-only change has its own file/link and frozen-byte checks.

“Ready” here means the inspected software path is available. It does not mean that every stage, API provider, quality gate or energy condition has been validated on the current target/source combination. No parallel API/commissioning branch is asserted merged.

## VALIDATED_ON_TARGET

### Committed historical evidence, directly inspected

- QAIRT control/stop **three repetitions per treatment**, 35 development cases each, measured at `a8c3707`: control **45/105 correct, 41/105 invalid**; stop **58/105 correct, 10/105 invalid**. Every trial has **0/9 clarification success**. [Campaign evidence](../eval/results/qairt-repeats-0700.md) records balanced order and artifact checks. Its measurement qualification is not product approval or energy qualification.
- Separate committed model evaluations exist for **1.7B, 4B, 8B and GPT-OSS-20B**. The [status table](CURRENT_STATUS.md#model-evidence-already-in-the-repository) preserves split sizes and timing boundaries. In particular 8B reached **27/35 development** and **38/50 full**, while GPT-OSS-20B recorded **0/35 development with 35 invalid outputs**. Successful loading/generation is not tool-contract success.
- Earlier QAIRT and 4B tuner/apply/MCP lifecycle smokes completed; their invoice task checks failed. These are historical integration observations, not proof of a successful current TurboLab campaign.

### Current target state reported by the owner

- Target archives **EXP-001…EXP-026** and **`local/energy-probe-300s.json`** exist; SSH access is restored. The 26 individual manifests and probe observations have not yet been directly inspected from this worktree. A read-only check reached the target and matched the existing host key, but the saved key was rejected with `Permission denied`; no SSH settings were changed. IDs must be qualified by archive root; do not map older campaign-local IDs to this set by name alone.
- A real QAIRT **eight-case** canary at the current TurboLab checkpoint reportedly completed: **6/8 correct**, **1 invalid**, **13.835 seconds wall time**, **528.41 ms median generation-only latency**. Its status is **`DIAGNOSTIC_CANARY`**, outside qualified experiment archives. It establishes a reported diagnostic run, not S4/S5 completion, a promotion, or an E2E/task-latency result.

Owner confirmations are identified as such rather than presented as newly inspected raw artifacts. No model inference was launched for this readiness update.

Subsequent owner reports add S1/S2/S3/dev35 and API timing samples, plus a
five-repeat same-process QAIRT test whose outputs were not byte-identical.
[Exact values and timing boundaries](CURRENT_STATUS.md#subsequent-owner-reported-target-observations)
are retained as single-session diagnostics. None are hardcoded scheduler costs.

## NOT_YET_VALIDATED

- Read-only reconciliation of the target's 26 sealed archives: exact source/model/SDK identities, statuses, dataset scope, retained failures, control relationships and integrity results. The local six-archive historical Mac copy is not a substitute.
- A complete current-source TurboLab session through startup, diagnostic canaries, tracked development evaluation and confirming repeats, with stage boundaries and actual costs validated against sealed evidence.
- Independently inspected provider probe records and their source/model/authentication identities. Successful OpenAI and Anthropic timings are now owner-reported; sustained availability and failures still need validation.
- Current target's effective sampler, cancellation behavior, dispatch evidence and thermal/background stability. Older target observations do not automatically validate changed source. `dispatch_verified=false` is absence of that proof, not evidence that no NPU work occurred.
- Energy commissioning. Probe duration and counter update gaps are observations, not certified hardware resolution. Diagnostic full-process SYS joules cannot be substituted for warm-task energy or promoted to comparable energy by setting a flag.
- Quality acceptance and the product's success/latency thresholds. Recorded invalid rates and clarification failures remain visible; no prompt/parser/scorer relaxation or new golden answer is authorized by these results.

## BLOCKED

- **Base-commit pilot and recovery:** the owner observed first-S1 `runner=None` failure and a missing `session.json` at `c866c48`. The separate runner/persistence fix must pass portable recovery tests and a target retry before a ten-minute pilot or 120-minute session is considered ready.

- **Qualified efficiency ranking:** no commissioned, compatible energy campaign is established in the evidence reviewed here. No overall winner or qualified EFFICIENT/BALANCED recommendation follows.
- **Current target archive verification from this Mac:** network reachability and the known host key were observed, but this session's saved authentication key was rejected. An accepted authorized credential is needed to read the target archive/probe evidence. SSH restoration remains owner-confirmed; the device is not declared globally inaccessible.
- **Product promotion:** explicit owner decisions on product thresholds and BALANCED policy remain necessary. Passing archive provenance checks alone cannot approve the Secretary.
- **Unsupported QAIRT research controls:** sampler/grammar/prompt changes need a separately reviewed, versioned contract and hardware validation before becoming admissible experiments. Other branches' work is not treated as already integrated.

## NEXT_5_ACTIONS

1. **Resolve this session's authorized authentication read-only.** The host was reachable but rejected the saved key. Once authenticated, record target source SHA and sanitized archive inventory, without starting another hardware job. Verify EXP-001…026 seals and identify incomplete/failed attempts; keep private addresses and raw logs under ignored `local/`.
2. **Bind current diagnostic evidence.** Read the eight-case canary record and 300-second probe. Preserve the canary's `DIAGNOSTIC_CANARY` label, exact timing names and split; report probe duration/update observations without inventing counter resolution. Reconcile owner-reported numbers with those artifacts.
3. **Complete the commissioning review separately.** Inspect raw SYS counters, scope, power conditions, runtime identity and idle/thermal evidence. Keep energy diagnostic until the required checks pass; do not assume pending commissioning code is merged.
4. **Validate one bounded current-source development workflow.** After confirming one hardware owner and no competing job, commit the exact control/candidate inputs and use TurboLab's existing tracked S4/S5 path. Preserve every attempt and balanced repeat order. Use only supported controls; canaries cannot substitute for the full 35-case gates.
5. **Review a qualified summary before promotion.** Compare only matching source/dataset/case/protocol identities and explicit latency boundaries. Keep historical and diagnostic results separate, include failed-task energy, and obtain product policy decisions. A heldout milestone is a separate explicit final action, never feedback for another search round.
