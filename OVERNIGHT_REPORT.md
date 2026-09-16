# Overnight engineering report

## 1. Executive summary

Implemented and exercised immutable experiment tracking, copied six historical measurements, generated primary-KPI/error reports, fixed audit infrastructure risks, added cross-platform CI and repeated-campaign planning, and built isolated optimization diagnostics. No new hardware measurement or overall backend winner is claimed. Original benchmark/result bytes remain unchanged.

This report records tested engineering, not a claim that model quality, token throughput or energy efficiency improved tonight. No new model was downloaded. The saved SSH route timed out twice; hardware-dependent phases remained blocked while independent engineering continued.

## 2. Starting commit

`e9c0c3f2dbc94833ea2ae30ae3ca61a1337e7b82`. The initial audit checkout was282b040 and was fast-forwarded before implementation. Open frontend PR1 was inspected and preserved.

## 3. Ending commit

Engineering checkpoint at report generation: `0b1e2c597a0197d35f7383f29c15889442f9dee4`. The final documentation commit is necessarily later; `local/overnight-report.json` records the exact final HEAD after checkpoint creation. Use `git log -1` to identify the commit containing this report.

## 4. Commits created

- `905fc23` — Fix native buffer ownership and exact context recovery
- `7e899b2` — Make validation portable and pin historical leakage evidence
- `0a297ae` — Preserve private JSON and raw measurement provenance
- `2487e88` — Add read-only QAIRT artifact evidence inspector
- `8db69f1` — Validate imported evidence and protect decision reports
- `1f07363` — Label microbenchmark modes as exploratory recommendations
- `99591e8` — Archive every experiment with immutable evidence and primary KPIs
- `16c5824` — Plan balanced dev campaigns and characterize frozen parser risks
- `fc8987b` — Reject tuner recommendations when measured inputs drift
- `b3f8329` — Report verified experiment tradeoffs and dev-only failure evidence
- `ef917b5` — Capture bounded host versions and make CI text encoding explicit
- `bcfd1c7` — Add isolated action proposal and static prefix diagnostics
- `19f99ee` — Bound GGUF metadata reads before allocating untrusted lengths
- `ef0052c` — Bind campaign configuration hashes to one captured snapshot
- `0b1e2c5` — Close tracker JSON ambiguity and relative execution path gaps

## 5. Test status before

At the synchronized starting revision: **387 passed, 1 skipped, 1 failed, 3 errors, 13 subtests passed**. One historical archive leakage failure and three private-model MCP setup errors were real failures, not hidden.

## 6. Test status after

Final local validation: **674 passed, 1 skipped, 17 subtests passed** in23.75seconds. Frontend: **28 passed**, syntax checks pass. First hosted CI passed macOS but found Linux GGUF allocation and Windows default-encoding issues; both received concrete fixes. Cross-platform result must be read from the final appendix, not assumed from local success.

## 7. Experiment tracking system

`scripts/experiment_tracker.py` supports run/backfill/backfill-known/ledger/verify. Every attempt has a unique OS-locked EXP directory, manifest, captured config/command, hypotheses/change/control, source state/diff, results/logs, KPIs and SHA256 inventory. Duplicate imports return the original archive. Sealed archives reject mutation through tracker APIs; later external edits are detected by verification. Filesystem permissions are not a tamper-proof storage appliance.

Qualified measurement requires clean source, matching captured evaluator/application/model/config identities, fixed case IDs/hashes, complete reports and stable pre/post artifacts. Qualification does not mean product quality approval. Dirty runs require explicit diagnostic mode. Bounded child execution retains failures and partial evidence. Optional software version capture is bounded and never fabricates missing versions.

## 8. Historical runs backfilled

Six archives EXP-001..006, copied from available `eval/results` source reports with matching companions. Original bytes remain on disk. Re-running backfill kept six identities; every archive seal verified. Historical commands/versions not recorded remain unknown. Local raw files for the specifically requested current CPU/HTP/QAIRT-stop dev runs and energy-probe-300s were unavailable. Owner-supplied approximate values were not inserted as measurements.

## 9. Primary KPI table

| Archive | Correct/total | Success % | Median task ms | Gross SYS J/correct | Qualification |
|---|---:|---:|---:|---:|---|
| EXP-001_baseline | 30/50 | 60.000 | 1205.338 | unavailable | historical; unavailable |
| EXP-002_candidate_cpu-t10-v2 | 33/50 | 66.000 | 919.031 | unavailable | historical; unavailable |
| EXP-003_candidate_greedy-topk1-cpu-v2 | 29/50 | 58.000 | 889.072 | unavailable | historical; unavailable |
| EXP-004_candidate_qairt-native-06-v1 | 23/50 | 46.000 | 589.565 | 33.075 | historical; diagnostic_uncommissioned |
| EXP-005_candidate_qwen17-cpu-t10-v2 | 34/50 | 68.000 | 1592.538 | unavailable | historical; unavailable |
| EXP-006_candidate_qwen4b-cpu10-dev-v1 | 25/35 | 71.429 | 4799.700 | 403.577 | historical; diagnostic_uncommissioned |


These historical rows are not a controlled comparable campaign. First five use50 full cases; the last uses35 development cases. Table latency is the recorded evaluator task boundary, not cold user-facing E2E. The two energy values are DERIVED from historical full-process SYS blocks and explicitly **diagnostic_uncommissioned**; they cannot select a winner or qualify energy deltas.

## 10. New hardware experiments

**Zero.** No Snapdragon inference, counter commissioning, power-setting change or model download. Two bounded read-only SSH attempts timed out. Six-run QAIRT control/stop offline plan prepared locally; model/SDK paths are empty placeholders, so it is not executable until filled and regenerated.

## 11. Energy methodology

Gross SYS block joules include all attempts, including incorrect tasks. J/correct divides this total by correct tasks. Zero correct or incomplete/failed denominators produce null, never0. Full-process energy includes loading/warmup/evaluator overhead and is not relabeled warm-task energy. Raw PDH source/status/type and host timestamps are retained. Observed update gaps are not certified hardware resolution. Declared and observed power modes remain distinct.

## 12. QAIRT findings

Literal generation-time stop remains opt-in and does not rewrite final native output. Tests characterize delimiter splits, literal markers inside strings, malformed actions and cancellation limits. Official flat bundles remain supported; nested shard roots are rejected. Artifact inspector records only observed fields; unknown quantization stays unknown. Requesting NPU does not prove exclusive operator dispatch. QAIRT-stop repeatability needs the actual hardware and original dev evidence.

## 13. Correctness findings

The available Qwen4B development archive has25/35 correct,10 failures and9/9 failed clarification cases. This is historical Qwen4B evidence, not QAIRT-stop evidence. Frozen malformed-extra-call behavior and the prompt's multi-call wording are characterized without changing parser/scoring. Standalone exact-command proposals abstain conservatively, execute nothing and are disabled by default; they have synthetic test evidence only.

## 14. Latency findings

No new speedup measured. Inference latency, recorded task latency, warm-task latency and full-process duration have different boundaries. Reports preserve their scopes and avoid calling inference-only latency E2E. Static prefix has407 instruction bytes+606 inventory bytes; tokenizer-specific counts and safe prefix reuse remain unknown.

## 15. Energy findings

Two historical full-process blocks allow diagnostic J/correct derivation; commissioning/comparable treatment evidence is insufficient. New summary/campaign tools exclude those values from qualified Pareto groups, energy deltas and pooled energy statistics. No overall winner is selected.

## 16. Error taxonomy

Diagnostic labels distinguish invalid format from valid-but-wrong actions, wrong tool/arguments/no-action, clarify, execution, filesystem, timeout and runtime errors. Categories may overlap and are not a replacement scorer. Dev-only reports retain raw output/arguments/tokens/stop evidence locally. Heldout/mixed/unknown splits are refused for case-level optimization reports.

## 17. Repeatability

Planner binds one captured config byte snapshot, checks a single intended field change, targets at least three blocks per treatment and rotates positions. Exact plan/config hashes are verified before use. Statistics retain all attempts and disclose missing/incompatible evidence; no best-run selection or significance claim. Actual repeated hardware blocks remain unperformed.

## 18. Fixed audit issues

- A05: exclusive decision outputs with input/companion collision checks.
- A08: post-sweep input/runtime verification blocks ranking and later export after drift/deadline failure.
- A10/A11: honest declared power and retained raw counter timing/status evidence.
- A14: exact ties produce no unique winner.
- A18: strict BOM-safe private JSON.
- A19/A20/A26: native free-on-error, flat QAIRT root validation, exact context bytes with hash checking.
- A24/A25: hermetic model stubs and portable CI.
- A30/A31: imported identity consistency and untracked runtime override rejection.
- Additional CI discovery: bounded GGUF metadata reads and portable temporary-file handling.

## 19. Remaining audit issues

| Finding | Disposition |
|---|---|
| A01/A06 | Frozen parser/prompt inconsistency characterized; versioned owner decision. |
| A02/A04 | Tracker adds strict clean/source checks; historical frozen evaluator/gate unchanged. |
| A03/A32 | Exploratory mode labels added; sampler/application equivalence and Secretary product policy not established. |
| A07 | Actual sampler evidence retained; deterministic decoding not asserted. |
| A09 | Boundaries documented; existing timer semantics unchanged. |
| A12 | Import evidence strengthened; this is not hardware certification or proof against forged raw evidence. |
| A13 | Planner/statistics implemented; required hardware repetitions not yet collected. |
| A15 | Measurement/generator/reference labels separated; official reference policy remains pending. |
| A16 | Exact historical archive pins distinguish exposure; heldout secrecy is not restored. |
| A17 | Canonical new inventories/UTF-8 CI added; legacy hashes not rewritten or declared portable. |
| A21 | Literal stop limitations characterized; no strict syntax-aware native stop claim. |
| A22 | Filesystem race diagnosed; no risky frozen executor rewrite. |
| A23 | Tracker bounds the child process; in-process native per-case timeout remains unproven. |
| A27 | Historical abstractions retained; no broad cleanup or migration. |
| A28 | CURRENT_STATUS and explicit historical labels added. |
| A29 | Frontend preview remains distinct; collaborator design/PR untouched. |

## 20. Hardware-blocked items

Target access, original current dev/probe artifacts, actual artifact inventory, PDH commissioning, stable power/thermal observations, native smoke test, QAIRT stop repetitions, long-block energy campaign and fresh three-backend comparison. Offline/unit results do not substitute for these.

## 21. Owner decisions required

See `OWNER_DECISIONS_REQUIRED.md`: product success/latency thresholds, BALANCED policy, versioned parser/prompt/schema/router contract, reference approval and heldout exposure policy. No owner-dependent choice was silently made; unrelated work continued.

## 22. Exact next 10 actions

1. Restore authenticated Snapdragon access and inspect existing scheduled jobs before claiming exclusive use.
2. Locate and copy the original CPU/HTP/QAIRT baseline/repeat/stop dev files and 300-second probe; backfill without rewriting originals.
3. Inspect actual GGUF, QAIRT bundle and SDK with the artifact inspector; retain canonical and legacy identities.
4. Fill private model/SDK paths, regenerate and verify the offline QAIRT control/stop campaign plan.
5. Commit any approved setup changes and establish a clean checkout; verify UTF-8 execution and frozen hashes on Windows.
6. Commission gross SYS block measurement with raw PDH/source timestamps, idle repeats, stable power and sufficiently long duration.
7. Run at least three interleaved dev control/stop blocks through the tracker, preserving every failed or timed-out attempt.
8. Generate verified campaign statistics and dev-only failure deltas; do not pool uncommissioned energy or infer a causal gain from one run.
9. Obtain owner-defined success/latency thresholds and approval for any versioned prompt/parser/schema/router experiment.
10. Only after a chosen development milestone, perform the separately authorized full validation and fresh comparable CPU/HTP/QAIRT campaign.

## 23. Files changed

The commit list provides independent checkpoints. Paths changed at report generation:

- `.github/workflows/portable-validation.yml`
- `AGENTS.md`
- `OWNER_DECISIONS_REQUIRED.md`
- `docs/agent-operating-context.md`
- `docs/energy-boundaries.md`
- `docs/experiment-protocol.md`
- `docs/kpi-definitions.md`
- `docs/overnight-engineering-log.md`
- `docs/prefix-context-evidence.md`
- `docs/provenance-infrastructure-changes.md`
- `docs/qairt-artifact.md`
- `docs/secretary-proposal-candidate.md`
- `docs/secretary-vnext-diagnostics.md`
- `docs/timing-boundaries.md`
- `eval/compare_backends.py`
- `eval/decision_table.py`
- `eval/energy_measurement.py`
- `eval/leakage_audit.py`
- `eval/report_validation.py`
- `eval/run_secretary_eval.py`
- `scripts/analyze_experiment_campaign.py`
- `scripts/analyze_experiment_errors.py`
- `scripts/compare_experiment_cases.py`
- `scripts/experiment_tracker.py`
- `scripts/inspect_model_artifact.py`
- `scripts/inspect_secretary_prefix.py`
- `scripts/plan_experiment_campaign.py`
- `scripts/propose_secretary_action.py`
- `scripts/render_experiment_summary.py`
- `tests/test_artifact_inspection.py`
- `tests/test_campaign_plan.py`
- `tests/test_compare_backends.py`
- `tests/test_context_integrity.py`
- `tests/test_decision_table.py`
- `tests/test_energy_evidence_capture.py`
- `tests/test_eval_golden.py`
- `tests/test_experiment_analysis.py`
- `tests/test_experiment_hardening.py`
- `tests/test_experiment_tracker.py`
- `tests/test_json_io.py`
- `tests/test_leakage_audit.py`
- `tests/test_mcp_server.py`
- `tests/test_native_safety.py`
- `tests/test_porting.py`
- `tests/test_prefix_inspection.py`
- `tests/test_qairt_single_action.py`
- `tests/test_report_validation.py`
- `tests/test_secretary_proposal.py`
- `tests/test_secretary_vnext_diagnostics.py`
- `tests/test_service.py`
- `tests/test_tuning.py`
- `turbo/campaign_plan.py`
- `turbo/context.py`
- `turbo/experiment_analysis.py`
- `turbo/experiments.py`
- `turbo/json_io.py`
- `turbo/native.py`
- `turbo/porting.py`
- `turbo/secretary_proposal.py`
- `turbo/service.py`
- `turbo/telemetry.py`
- `turbo/tuning.py`


This report and `docs/CURRENT_STATUS.md` are final documentation additions. Machine-readable final file inventory is recorded locally.

## 24. Files explicitly not touched

128 captured frozen/historical file hashes verified unchanged: datasets, benchmark manifest, fixture inventory/tree, historical eval/benchmark results, benchmark tasks and frozen semantic evaluation dependencies. No edits to `eval/scoring.py`, `eval/secretary_adapter.py`, `eval/validate_dataset.py`, `eval/quality_policy.json` or `turbo/secretary.py`. `service.parse_calls` unchanged. Runner edits are private JSON reads and additive sampler provenance, documented as a changed evaluator fingerprint. No frontend design files modified.

## 25. Reproduction commands

Run from the repository with a Python environment containing pytest. Use `python -X utf8` on Windows. Existing outputs are exclusive: choose a new report name when repeating.

```sh
python -m pytest tests -q -p no:cacheprovider
python -X utf8 eval/validate_dataset.py
python -X utf8 eval/leakage_audit.py
npm --prefix frontend run check
npm --prefix frontend test
python scripts/experiment_tracker.py backfill-known
python scripts/experiment_tracker.py ledger
python scripts/experiment_tracker.py verify local/experiments/EXP-001_baseline
python scripts/render_experiment_summary.py --output local/summary-new.md
python scripts/analyze_experiment_campaign.py --output local/campaign-new.md
python scripts/analyze_experiment_errors.py local/experiments/EXP-006_candidate_qwen4b-cpu10-dev-v1 --output local/errors-new.md
python scripts/inspect_secretary_prefix.py --output local/prefix-new.json
python scripts/plan_experiment_campaign.py --verify local/overnight/qairt-stop-offline-plan.json
```

For actual inference, first fill private model/SDK configuration and establish clean/exclusive hardware conditions, then use the tracker `run` command documented in `docs/experiment-protocol.md`. Never bypass tracking for an official measurement.

## Final validation appendix

- 128 frozen/historical files unchanged; all six archive seals verified again.
- 674 Python tests and17 subtests pass; one existing integration test is skipped because its separate parent service checkout is unavailable. Frontend28 tests and syntax pass.
- Hosted CI at `19f99ee` passes Linux, Windows and macOS: [portable validation](https://github.com/aaxxeell09/Ai-infra-summit/actions/runs/35064495754). Final code commit `0b1e2c5` also passes all three systems: [final code validation](https://github.com/aaxxeell09/Ai-infra-summit/actions/runs/35064799039).
- Audit A01–A32 disposition reviewed; repository TODO/FIXME/NOT_IMPLEMENTED search produced no additional actionable code items. Final review's JSON/path gaps were fixed, not deferred. Remaining hardware/versioned-semantic/product-policy items are explicit.

Final source check: `service.parse_calls` AST is identical to the starting revision. The documentation checkpoint adds no runtime changes.
