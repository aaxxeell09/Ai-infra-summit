# Three primary KPIs

## SUCCESS

`100 × correct tasks / all attempted benchmark tasks`. Always show numerator/denominator and split: dev35, heldout15, full50. Correctness is the unchanged frozen v2 result flag, not JSON validity.21/35 correct plus2 invalid does not imply33/35 correct. A process failure without complete rows is incomplete evidence, never a successful zero-task trial.

## MEDIAN TASK LATENCY

Use the median of recorded **task** timing, with its exact boundary. `median_e2e_ms` is a storage field, not permission to call all timers true user E2E. Display `MEDIAN_TASK` and a scope:

- warm_task_v1 excludes fixture preparation, model load and final filesystem audit;
- task_latency_ms in the uninstrumented frozen evaluator includes fixture setup/golden execution and final audit;
- inference-only latency_ms is a secondary diagnostic and cannot fill absent task latency.

For historical inference-only reports: primary task latency is UNAVAILABLE; retain inference median separately. See timing-boundaries.md. P95 nearest-rank requires at least20 cases; repeated-block variability is a different statistic.

## GROSS SYS J/CORRECT

`gross SYS energy for the whole explicitly scoped block / correct tasks in that same block`. Incorrect tasks stay in energy numerator. Missing/stale/reset/unvalidated energy stays unavailable; zero correct tasks => null. Never total only successful-task energy. Cold full-process and warmed block boundaries cannot be pooled.

Raw-consistent energy derivation is not commissioning or product qualification. Counter update cadence, power conditions and enough duration must be established. SYS is a meter channel, not NPU-only or wall power. No translation from token reduction to energy saved without measurement.

## Qualification

Clean reproducible measurement ≠ Secretary quality-gate PASS ≠ comparable energy ≠ winning backend. Each status is separate. Thresholds remain owner decisions. All generated summaries must avoid a single weighted score.
