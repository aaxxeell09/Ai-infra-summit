# Immutable experiment protocol v1

Primary displays are success (correct/all attempted), recorded median task latency with exact scope, and gross SYS joules/all-correct-task count. No scalar score or automatic product winner. Development has35 cases, held-out15, full milestone50. Do not use held-out failures to tune.

## Commands

From repository root, after committing code:

```sh
python scripts/experiment_tracker.py backfill-known
python scripts/experiment_tracker.py run --name qairt-stop-repeat-1 --dataset dev --config local/qairt-single-action.json --change "Repeat unchanged stop candidate" --hypothesis "Check repeatability" --control "$CONTROL_EXP_ID"
python scripts/experiment_tracker.py ledger
python scripts/experiment_tracker.py verify local/experiments/EXP-001_example
```

`--root` precedes the subcommand. A missing control denotes a baseline/diagnostic, never causal attribution. `--diagnostic-dirty` explicitly permits dirty diagnostics; they cannot become clean qualified measurements. `--dataset all` is a deliberate milestone, not a search loop. Never guess an existing control ID: inspect the ledger and set `CONTROL_EXP_ID` to the verified matching control before using the example.

Each unique directory starts incomplete before child execution. It captures config bytes, exact argv, command/reproduce text, hypothesis/change/control, git commit/status/diff, environment, raw stdout/stderr, result/telemetry when available, KPI JSON/text and SHA256 inventory. Completed archives are sealed; verification detects edits/additions/deletions. Hashes detect accidental tampering, not cryptographic signer identity. Filesystem administrators can still modify files; consumers must verify. Interrupted archives remain incomplete and IDs are not reused. Ledgers are rebuildable indexes; raw archive evidence is authoritative.

Qualification means reproducible clean measurement provenance, **not** a product quality PASS or energetic winner. A report can execute with evaluator exit2 (quality FAIL/NOT_COMPARABLE) and remain a valid preserved observation. Runtime/process failures and timeouts are distinct. Unknown fields remain null. Current code changes to runner infrastructure change its hash; no claim of provenance identity with old runs.

## Energy and repeated blocks

Optional `--capture-full-process-energy --counter-resolution 1` records a **complete child process** block. Supply a resolution only from recorded commissioning evidence;1 is illustrative CLI syntax, not an inferred hardware guarantee. This boundary includes validation, hashing, model load, warmup, all cases, fixture work and serialization. It is not warm-task energy. Counter-derived energy is diagnostic until commissioning/power/repetition evidence is validated. Preserve raw counters even on failure; a partial/missing result cannot establish completed-suite J/correct.

A future warm-suite block must bracket after model load/warmup and before/after the same entire repeated workload, with a versioned scope. Do not repurpose legacy per-task readings or silently change frozen runner timing. Approximate 1second update gaps make ~0.5second task attribution suspect; long blocks are preferable. Gross is primary; idle-subtracted net is diagnostic.

Target three independent blocks per treatment, balanced order, e.g. CPU/HTP/QAIRT, QAIRT/HTP/CPU, CPU/QAIRT/HTP. Record campaign/treatment, control, single changed variable, block index/order/time/duration/power/idle/thermal evidence. Keep every attempt, show N/mean/median/stddev/CV/min/max. No best-run selection or unsupported significance claim. Same case IDs/hashes, evaluator/protocol/scope and relevant runtime/power facts are necessary for comparison. Different quantizations are deployment treatments, not pure hardware speedups.

## Historical imports

`backfill` copies, never moves or changes sources. Original bytes and companions remain available. Idempotency is by captured evidence fingerprints, not filename alone. Historical dirty/unknown provenance stays diagnostic. Metadata is OBSERVED_LOG, statistics DERIVED, missing fields UNKNOWN. Reproduction commands are copied only if recorded; otherwise NOT_RECORDED. Current machine facts must never fill old gaps.

Failure categories are diagnostic projections of existing flags, can overlap, and do not rescore output. Correct vs invalid are not complements:21/35 correct and2 invalid also means12 well-formed but incorrect tasks. Frozen evaluator defects require owner-approved versioning, not post-hoc cleanup.

## Windows text environment

Use `python -X utf8` (or `PYTHONUTF8=1`) for frozen validation and tooling on Windows. The frozen validator retains platform-default reads; legacy Windows code pages otherwise misdecode UTF-8 inventory names. CI sets UTF-8 explicitly without changing fixture bytes, filenames, inventory or validator semantics. Tracker child commands already use `-X utf8`.
