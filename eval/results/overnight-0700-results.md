# Completed recovery measurements — 07:00 UTC checkpoint

These are preserved observations from the Latitude, not accepted product modes.
The historical-reference gate remains **NOT_COMPARABLE** because evaluator
fingerprints differ. No baseline, golden case, expected answer or scoring rule
was changed. Previously queued manifests are historical planning snapshots;
the completed JSON reports contain the actual source, configuration and results.

## Full 50-case observations

| Configuration | Correct | Invalid | Clarify correct | Mean inference ms | Median inference ms | p95 inference ms |
|---|---:|---:|---:|---:|---:|---:|
| 4B Q4_0 CPU10 | 37/50 (74%) | 2/50 | 2/13 | 5,940.103 | 3,430.061 | 26,837.233 |
| QAIRT 0.6B control | 20/50 (40%) | 17/50 | 0/13 | 810.762 | 524.575 | 1,965.833 |
| QAIRT 0.6B first-call stop | 29/50 (58%) | 4/50 | 1/13 | 518.686 | 496.162 | 699.029 |

All three exceed the frozen 2% invalid-output ceiling. 4B completed all eight
move cases, but clarification remains unreliable. Its median recorded complete
task interval was 3,487.006 ms; inference timing above excludes fixture execution
and is not cold user-facing latency. No held-out case-level failure analysis was
used to choose the next experiment.

4B used clean `16d13138a61fd3f0e4bcbe5ae6bcb2271fb1b843`. QAIRT control and stop
used clean `728c6a2ad72917a8173f88cf647360bb83269c0a`, identical model bundle and
SDK configuration, changing only `stop_after_tool_call`. Raw result, Markdown
and full-process telemetry companions are stored together under `eval/results/`.
The windowless recovery completed after the original console jobs were interrupted.

## What stopping actually did

The candidate's native callback saw the closing delimiter in 47/50 full cases;
all 47 reported native stop reason `user`, with zero callbacks after the stop
request. The remaining three ended at EOS. Every record retains
`native_text_modified=false`. Generated tokens fell from 2,199 to 1,109 for the
50 measured cases, excluding warmup. This supports shorter generation, not a
claim of faster native decode throughput or stricter semantic correctness.

Mean inference time was 36.0% lower in this single control-then-candidate
observation. Median inference time was only 5.4% lower. Order was not balanced
and sampling was not established as deterministic. Repeatability and causal
effect size remain unverified; a new balanced development campaign is queued.

The development observations were 14/35 control versus 21/35 stop, with invalid
outputs 16/35 versus 2/35 and mean inference 862.656 versus 514.269 ms. Both had
0/9 clarification success. The stop mechanism addresses trailing generation;
it does not resolve missing information, ambiguity or wrong intended actions.

## Energy and archive boundaries

Full-process SYS energy was 11,748.700 J for the 4B run (321.991 s), 870.534 J for
QAIRT control (56.669 s), and 876.819 J for QAIRT stop (43.362 s). The stop run
did **not** use less gross SYS energy in this observation. These blocks include
loading, hashing, warmup, scoring and serialization. They are diagnostic,
uncommissioned measurements; do not use them to select an efficient mode.
Tokens/J remains unavailable because warmup token counts are missing.

All five completed reports were imported through `scripts/experiment_tracker.py
backfill-known`, preserving the original bytes and telemetry. The five archive
seals verified successfully. They are `historical_diagnostic`; importing them
does not upgrade provenance or establish a quality PASS. Archive IDs are local
to this worktree's ignored `local/experiments/` ledger.

## Next isolated run

The merged repository passed 675 tests and 17 subtests. Clean source
`a8c3707741d7bf4e48479bf26fa28a87c46c3f49` is installed in a separate Windows
checkout. Its existing campaign planner binds private configuration snapshots
and orders three development blocks per treatment: control/stop, stop/control,
control/stop. Every attempt runs through the immutable experiment tracker with
a 300-second child limit, preserving failures. Energy is retained as diagnostic
without inventing a counter-resolution guarantee. No further full-suite run is
part of this repeatability campaign.
