# TurboLab integration review — e4b30e1

Scope: read-only Flash review, followed by owner inspection of the exact commit.
No branch changes, merge, inference or benchmark run. Source references below
refer to the teammate branch, not the current main checkout.

## 1. Resume cannot restore its budget

[autotune.py:269](https://github.com/aaxxeell09/Ai-infra-summit/blob/e4b30e1/scripts/autotune.py#L269)
passes `{'elapsed_s': ...}` into `Budget.restore`, which requires a schema version
and `elapsed_seconds`. Owner reproduced `ValueError: Unsupported budget snapshot
schema: None` using the exact budget module with an injected clock; its correctly
shaped snapshot round-trip succeeds. Resume therefore fails before scheduling.
Use the existing snapshot contract and cover the actual resume entrypoint.

## 2. Real experiment outcomes and measurements are not ingested

[scheduler.py:271–277](https://github.com/aaxxeell09/Ai-infra-summit/blob/e4b30e1/turbo/optimizer/scheduler.py#L271)
returns `outcome='completed'` and `net_cases=None` for every archive returned by
the tracker. The tracker also returns a path after failed or timed-out runs;
status and qualification are in the archive. Thus session bookkeeping calls
failures completed, and the executor supplies no measured rows for selection.
Read and validate the immutable archive's status, qualification and result before
constructing observations; preserve failures and never infer missing metrics.

The worker additionally claimed failed runs could be promoted. That consequence
is **not established**: `promote_best` holds when development case deltas are
missing. S5's unconditional survival remains worth testing, but the confirmed
finding is incorrect outcome bookkeeping and absent measurement ingestion, not
a demonstrated false winner.

## 3. Admission estimates do not enforce the session deadline

[scheduler.py:160–170](https://github.com/aaxxeell09/Ai-infra-summit/blob/e4b30e1/turbo/optimizer/scheduler.py#L160)
checks a candidate estimate against remaining time, then invokes the executor
without the remaining budget. The executor uses the independent CLI timeout
(default 600 seconds). A short estimate can admit a much longer job near cutoff;
the budget is checked again only after it returns. Pass an absolute deadline or
remaining allowance through execution, accounting explicitly for setup/cleanup.
Test with an injected clock and a bounded stub, without stressing hardware.

The queue claim is process-local and the tracker lock is per archive root.
Different roots do not establish device-wide exclusion. Keep one external
hardware owner until a device-scoped lock is implemented and tested.

## Integration decision

Hold integration of this branch pending these fixes and focused tests. The
existing narrow invoice demo and recorded evidence are unaffected. No frozen
benchmark or quality threshold changes are proposed.
