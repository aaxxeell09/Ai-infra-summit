# QAIRT first-call stopping: three development repetitions per treatment

All six sequential trials completed on the Latitude at clean commit
`a8c3707741d7bf4e48479bf26fa28a87c46c3f49`. The tracker verified complete case
sets, clean source and unchanged model/SDK artifacts before and after every run.
Archive seals verified again after retrieval. `completed_qualified` describes
measurement provenance; **none of these trials establishes product approval**.

Each trial used the same 35 development cases. The order was control/stop,
stop/control, control/stop. These are 105 attempts per treatment on 35 unique
prompts, not 105 independent prompts. No held-out cases were run in this campaign.
The sole configuration change was `stop_after_tool_call` false versus true.

| Block | Treatment | Correct / 35 | Invalid / 35 | Mean inference ms | Median recorded task ms |
|---|---|---:|---:|---:|---:|
| 1 | Control | 15 | 15 | 798.612 | 609.498 |
| 1 | Stop | 20 | 3 | 518.007 | 567.624 |
| 2 | Stop | 18 | 3 | 520.708 | 562.883 |
| 2 | Control | 14 | 14 | 874.682 | 676.044 |
| 3 | Control | 16 | 12 | 692.747 | 599.342 |
| 3 | Stop | 20 | 4 | 511.507 | 563.854 |

Across the equal-sized trials, success was 45/105 (42.86%) for control and
58/105 (55.24%) for stop. Invalid outputs were 41/105 (39.05%) versus 10/105
(9.52%). Every trial had **0/9 clarification success**. Stopping improves the
observed trailing-generation problem but leaves substantial semantic failures.
All trials exceed the frozen 2% invalid-output ceiling, and the historical
reference remains NOT_COMPARABLE under its evaluator-fingerprint check.

Mean inference latency across trials was 788.680 ms versus 516.741 ms, a 34.48%
observed reduction. The mean of the three recorded task medians was 628.295 ms
versus 564.787 ms, a 10.11% reduction. These are distinct aggregates and timing
boundaries; neither is cold user-facing end-to-end latency. Sample standard
deviations of the task medians were 41.663 and 2.504 ms respectively. With three
blocks, no statistical significance or universal speedup is claimed. This is
generation-length control, not evidence of increased native decode tokens/s.

Gross SYS measurements remain **diagnostic/uncommissioned**. Counter resolution
was not guessed. The campaign analyzer correctly declines to pool energy or
select an efficient mode. All energy from failed actions is retained in each
block; no successful-case-only denominator hides failed work.

## Evidence and reproduction

- `qairt-repeats-0700_campaign.json`: existing analyzer's complete derived report;
  no overall winner, no integrity failures, two groups with three trials each.
- `qairt-repeats-0700/candidate_EXP-001.json` through `candidate_EXP-006.json`
  and their Markdown companions:
  unchanged runner output. EXP order matches the six table rows above. IDs are
  scoped to this campaign directory; telemetry companions preserve raw counters
  and scope.
- `qairt-repeats-0700_artifact-identity.json`: common canonical model and SDK
  manifests, verified stable across all six attempts. This canonical model hash
  scheme differs from the legacy bundle hash; do not equate the two strings.
- Original sealed EXP archives remain in ignored private storage. Their
  `manifest.json`, exact commands, config snapshots and raw logs are retained.

Use the existing planner to bind the two private configs and rotate three
development blocks, then execute each planned run through
`scripts/experiment_tracker.py run --dataset dev --timeout 300
--capture-full-process-energy`. The candidate config differs only by
`stop_after_tool_call: true`. Preserve every attempt and use the actual first
control EXP ID with `--control`; do not assume an ID in a populated ledger.
The artifact paths are private; all remaining configuration is in the reports.

## Restored gateway

The restored service at the same source commit completed actual inference via
`llama_cpp_htp`, resolving automatic placement to HTP0. It returned `2 + 3 = 5`
to a request for only the number. Arithmetic is correct, but the exact-format
constraint was not followed. `dispatch_verified` remains false; backend identity
does not prove exclusive operator placement. The redacted response is preserved
as `benchmarks/results/gateway-smoke-0800.json`.

Next is a separate two-round 4B tuner/apply/MCP/invoice integration smoke. This
does not qualify the Secretary model, replace v2, or change any golden data.
