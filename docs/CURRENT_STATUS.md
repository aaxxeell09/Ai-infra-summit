# Current project status

Snapshot: **2026-09-16**, inspected TurboLab source **`c866c48f0d12219d8cf38187c71769623143c0c8`**. This documentation update runs no inference. [TurboLab readiness](TURBOLAB_READINESS.md) separates implementation, target evidence and remaining gates.

## Evidence and qualification

- **Directly inspected:** source and committed result summaries listed below. Their measurement commits are historical; they are not measurements of the current checkout.
- **Owner-confirmed target state:** `local/experiments/` contains EXP-001 through EXP-026, `local/energy-probe-300s.json` exists, and SSH access has been restored. These target files have not been independently read or resealed in this documentation worktree. Do not substitute the older six-archive Mac copy for the target inventory.
- **Owner-reported current canary:** real QAIRT, eight cases, **6/8 correct**, **1 invalid output**, **13.835 s wall time**, **528.41 ms median generation-only latency**. It is **`DIAGNOSTIC_CANARY`**, outside qualified experiment archives, not a 35-case evaluation or promotion result. The generation median is not recorded task latency, cold end-to-end latency, or the wall duration divided by eight.
- **Owner-reported portable validation:** approximately **1,106 tests**, with OS-dependent counts. This is not a new test run by this documentation task and does not validate ARM64/Hexagon execution.

`completed_qualified` in a tracker record describes its measurement/provenance checks. It does **not** mean product quality approved, energy commissioned, or a winning model. `historical_diagnostic` retains evidence without promoting its qualification. EXP IDs are local to their archive root: the six trials named EXP-001…006 in the QAIRT repeat publication are not automatically the same records as the target root's EXP-001…026.

## Platform and frozen benchmark

The documented target is a Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB, Windows ARM64, GenieX 0.6.1 / QAIRT 2.45. These hardware/runtime details were not freshly read from the target during this documentation update.

Secretary v2 remains **35 development / 15 heldout / 50 full milestone** cases. Existing datasets, expected actions, fixture bytes, results and evaluator semantics are unchanged. Published full-suite results can inform aggregate status; heldout cases must not guide tuning. Source/evaluator fingerprint differences remain reasons to decline comparison, not reasons to rewrite old hashes.

## QAIRT control and stopping evidence

The initial [development control](../eval/results/candidate_qairt-stop-control-dev-v1.json) and [stop candidate](../eval/results/candidate_qairt-stop-candidate-dev-v1.json), measured at `728c6a2`, recorded **14/35 versus 21/35 correct**, with **16 versus 2 invalid outputs**. The corresponding full milestone recorded **20/50 versus 29/50 correct**, with **17 versus 4 invalid outputs**. These historical comparisons to the old official reference remain `NOT_COMPARABLE`.

The later [three-block development campaign](../eval/results/qairt-repeats-0700.md), at `a8c3707`, used control/stop, stop/control, control/stop order:

| Treatment | Correct / attempts | Invalid / attempts | Mean of three recorded task medians |
|---|---:|---:|---:|
| Control | 45/105 | 41/105 | 628.295 ms |
| Stop | 58/105 | 10/105 | 564.787 ms |

These are three repetitions of **35 unique prompts**, not 105 independent prompts. Every trial scored **0/9 on clarification**. The stop treatment reduced the observed trailing-output problem, but neither treatment meets the frozen invalid-output ceiling. The table's statistic is a mean of trial medians, not a pooled median. It does not establish a native decode speedup or an overall winner. Full-process SYS energy remains **diagnostic/uncommissioned**.

## Model evidence already in the repository

All medians below are **recorded task latency** at each report's evaluator boundary, not current TurboLab canary generation latency or user-facing cold E2E. Different models, splits and measurement commits prevent treating this table as a controlled ranking.

| Deployment / split | Correct / total | Invalid / total | Median recorded task ms | Status and source |
|---|---:|---:|---:|---|
| Qwen3-1.7B CPU, full | 34/50 | 4/50 | 1,592.538 | Historical gate `FAIL`; [result](../eval/results/candidate_qwen17-cpu-t10-v2.json) |
| Qwen3-4B CPU, development | 25/35 | 2/35 | 4,799.700 | Historical `NOT_COMPARABLE`; [result](../eval/results/candidate_qwen4b-cpu10-dev-v1.json) |
| Qwen3-4B CPU, full | 37/50 | 2/50 | 3,487.006 | Historical `NOT_COMPARABLE`; [result](../eval/results/candidate_qwen4b-cpu10-v2.json) |
| Qwen3-8B CPU, development | 27/35 | 1/35 | 9,377.869 | Measured diagnostic; [KPI](../eval/results/large-model-dev-1100/qwen8b-cpu10-dev-1100-kpi.json) |
| Qwen3-8B CPU, full | 38/50 | 2/50 | 12,946.677 | No quality PASS; [milestone](../eval/results/qwen8b-full-1200/README.md) |
| GPT-OSS-20B CPU, development | 0/35 | 35/35 | 7,744.813 | Recorded generation, failed action contract; [KPI](../eval/results/large-model-dev-1100/gptoss20b-cpu10-dev-1100-kpi.json) |

Thus the older “download/runtime validation pending” descriptions for these larger deployments are no longer a complete status. The evidence establishes those particular attempts, not universal model/backend support. GPT-OSS J/correct is **undefined with zero successes**. Larger-model full-process energy is diagnostic and must not be used for qualified energy comparisons.

Earlier [QAIRT](../benchmarks/results/qairt-mcp-loop-01/README.md) and [4B](../benchmarks/results/qwen4b-mcp-loop-0800/README.md) tuner→apply→MCP loops completed on the target. Both invoice tasks failed in each smoke: working integration is not successful Secretary task execution.

## Current TurboLab implementation

### Subsequent owner-reported target observations

The owner supplied the following measurements from **one target session** after
the initial status snapshot. Raw files, exact measurement source SHA and artifact
hashes have not been inspected here. These are diagnostic reports, not constants
for the scheduler and not qualified experiment results.

| Category | Reported value | Boundary |
|---|---:|---|
| S1 | 8.467 s | Wall time |
| S2, eight cases | 13.835 s | `hardware_seconds` reported by the canary |
| S3, eighteen cases | 18.636 s | `hardware_seconds` reported by the canary |
| S3, eighteen cases | 22.856 s | Outer wall time |
| Development, 35 cases | 64.354 s | Outer wall time |
| OpenAI API probe | 3.154 s | Reported API probe latency |
| Anthropic API probes | 1.829 s; 1.191 s | Two separate reported probe latencies |

The later S2 field name clarifies the earlier “wall time” description above;
it is not evidence of S2 outer-process wall time. API numbers establish reported
successful probes, not durable credentials, quotas or future latency guarantees.

The owner also ran five identical-prompt calls on the same QAIRT `NativeModel`
instance with `reset=True`, official Qwen3-0.6B, GenieX 0.6.1 and QAIRT 2.45.
Reported outputs were `hello`, `Hello.`, `HELLO`, `hello`, `hello`:
**exact byte-identical output was false**. This demonstrates output variation in
that observed run; semantic correctness was not assessed. Logged fields were
`temperature=0`, `top_p=1`, `top_k=0`, `seed=-1`. Their pre/post-adapter logging
boundary still needs verification. Zero is a fallback sentinel in the pinned
[QAIRT sampler adapter](qairt-sampling.md), so this is not proof of greedy
sampling. Explicit sampler controls remain Lane C research.

A separate ten-minute pilot failed at its first S1 with
`TypeError: 'NoneType' object is not callable`: the executor forwarded
`runner=None` over the probe's default callable. The owner then found no
`session.json`. At the inspected base, startup runner selection and durable
session recovery are therefore blockers. Separate fix branches must be reviewed
and target-validated before claiming this pilot works.

At `c866c48`, [the implemented workflow](turbolab.md) separates S0 static admission, S1 startup generation, S2/S3 diagnostic canaries, and S4/S5 tracked full-development evaluations. Sealed S4/S5 archives are re-read through the observation adapter. The real proposer/critic call sites, bounded search and archive ingestion are present in source; mock/dry-run evidence does not prove live external API success.

The current QAIRT search contract exposes `max_tokens` and `stop_after_tool_call`; unsupported sampler/grammar/prompt changes remain separate research proposals. No parallel API or commissioning branch is claimed merged by this snapshot.

## Access, energy and next step

SSH restoration is owner-confirmed. A read-only connection check in this documentation session reached the target and matched its existing host key; the saved authentication key was rejected with `Permission denied`. No SSH settings were changed and no inference was attempted. The session therefore lacks accepted authentication for reading the 26 archives and probe; it does not establish that SSH is unavailable to the team. Exact target archive mapping and probe cadence remain unverified here.

A 300-second probe's existence or observed update cadence does **not** certify counter hardware resolution. No commissioned energy comparison, qualified efficient mode, owner-approved product thresholds, or complete current TurboLab S1→S5 campaign is established here. The next actions and exact gates are in [TurboLab readiness](TURBOLAB_READINESS.md#next_5_actions).
