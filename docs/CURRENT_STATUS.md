# Current project status

Snapshot: 2026-09-16 UTC, engineering checkpoint `bcfd1c7`. See `OVERNIGHT_REPORT.md` and the engineering log for subsequent commits and final validation.

## Platform and benchmark

Target configuration documented by the project: Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB, Windows ARM64, GenieX 0.6.1, QAIRT 2.45. **Not re-observed on hardware during this sprint.**

Frozen Secretary v2: **35 development / 15 heldout / 50 full milestone** cases. Never interpret a 35-case result as a 50-case result. Frozen prompt/parser/scoring/fixtures remain unchanged. Infrastructure runner and application source hashes changed; fresh runs are required for identical-provenance comparisons with current code.

## Evidence available locally

Six original measured reports were copied to sealed EXP-001 through EXP-006. All are labeled historical diagnostics, retaining original clean/dirty state. No new inference measurement has been performed.

| Historical archive | Correct / total | Success | Median recorded task ms | Gross SYS J/correct |
|---|---:|---:|---:|---:|
| EXP-001 reference | 30/50 | 60.00% | 1205.338 | unavailable |
| EXP-002 CPU t10 | 33/50 | 66.00% | 919.031 | unavailable |
| EXP-003 CPU greedy candidate | 29/50 | 58.00% | 889.072 | unavailable |
| EXP-004 QAIRT native | 23/50 | 46.00% | 589.565 | 33.075 diagnostic |
| EXP-005 Qwen1.7B CPU | 34/50 | 68.00% | 1592.538 | unavailable |
| EXP-006 Qwen4B CPU development | 25/35 | 71.43% | 4799.700 | 403.577 diagnostic |

These rows are **not a comparable campaign**. Different datasets, model weights, commits and provenance remain explicit. Recorded task latency excludes user-interface/network/cold-load time; diagnostic energy includes the complete evaluator process. The two energy figures are uncommissioned and cannot qualify energy deltas, Pareto selection or an overall winner.

The requested current CPU/HTP/QAIRT-stop development raw files and 300-second probe were not found in this checkout. Owner-supplied approximate figures are not substituted into measured archives. The previously generated local three-backend comparison is a derived historical report, not a replacement for missing original current runs.

## What is validated now

- Portable experiment allocation, immutable archive verification, retained failures, repeatable historical import, strict provenance and primary KPI reporting.
- Native error cleanup, context byte preservation, flat QAIRT shard validation, report output protection, identity/energy import consistency and tuner artifact drift detection.
- Final code checkpoint0b1e2c5: local674 tests and17 subtests pass (one existing unavailable parent-checkout integration test skipped), frontend28 tests pass, and hosted Linux/Windows/macOS CI passes.
- Development-only error analysis for EXP-006 shows ten failures, including all nine clarification cases. This does not establish QAIRT-stop behavior or a causal diagnosis.

## Not yet validated / blocked

Snapdragon SSH access through the saved route times out. Model/SDK bytes, fresh dispatch logs, PDH commissioning, thermal conditions, stop repeatability and controlled block-energy comparisons require target access. No large model downloaded. No hosted x64 CI run can validate ARM64 Hexagon execution.

The standalone deterministic action proposal is disabled by default, executes nothing, and has only synthetic test evidence. Prefix caching is unproven. Product quality/latency thresholds and BALANCED policy remain owner decisions.

## Next controlled experiment

Once hardware access and exclusive ownership are established, verify model/runtime inputs and commissioning, then use the tracker for a clean development-only QAIRT control versus `stop_after_tool_call=true` campaign. Change only that flag, target at least three balanced blocks per treatment, preserve all failures and all raw counters, and report success / task latency / scoped J per correct task. Do not tune on heldout or alter frozen semantics.
