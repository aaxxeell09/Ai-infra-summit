# Small-versus-large model routing (bounded helper)

`turbo/router.py` is a pure planning and execution helper for routing a
request between a small and a larger local model. It has no hardware access
and no HTTP; the agent/harness caller passes requests and executes the valid
final action itself.

## Interface

- `plan_route(profiles, requirements) -> dict` ranks measured profiles for
  one request and returns a plan plus trace. Planning alone performs no calls
  (validated by `tests/test_router.py`).
- `run_with_fallback(plan, invoke, validate, attempts=2) -> dict` executes
  the plan serially (concurrency 1). `invoke(profile, requirements)` performs
  one inference call; `validate(output, requirements)` checks the structured
  final action. Escalation to the larger model happens only when the small
  model's output fails validation (invalid structured output / preflight
  failure). No execution side effects occur before validation succeeds, and
  no gold answers are ever passed to online validation.

## Profiles and requirements

Profiles (`ModelProfile`) must carry the actual model/runtime identity with
weights hash, measured prefill/decode/load rates and context, plus a
task-quality rate with evidence (measured on held-out tasks of the given task
kind). The service Engine completion path supplies these from the model
registry and benchmark recommendations; a tier or parameter count alone never
implies quality ("larger = smart" is rejected unless calibrated).

Requirements (`Requirements`) carry `task_kind`, the tokenized context and
output budget, an optional objective `quality_minimum` and the routing
objective (`latency`, `decode`, `efficient`). Models whose measured
quality is unavailable or below the minimum are excluded outright; the router
never infers quality from size. A model without calibration is never
auto-accepted unless the request opts in via `allow_uncalibrated`; a manual
`manual_model` bootstrap route is permitted and labeled
`manual-uncalibrated` in the trace.

## Selection rule

Among eligible profiles the router prefers the fastest small model whose
measured quality is within `quality_band` (default 0.05) of the best
eligible quality; larger models beyond the band are held strictly as
fallback. Objective `decode` ranks by decode rate, others by predicted
wall time `context/prefill_tps + output/decode_tps + load_s`.

## Accounting and disclosure

The run result counts every attempt with its measured `elapsed_s` and the
actual `total_s` wall time, including retries. Plan `estimated_s` values
are disclosed as predictions and never merged into measured totals. The trace
records model, why, status and validation per attempt, and the result with
the total. Missing, stale or unmeasured values mean unavailable, never zero,
matching the measurement rules in `AGENTS.md`.

## Frozen benchmark boundary

This helper does not touch `turbo/bench.py`, `turbo/policy.py`, evaluation
files or benchmark data; the Axel-frozen benchmark protocol is unchanged. The
service Engine may call this helper but keeps its own completion and registry
code.
