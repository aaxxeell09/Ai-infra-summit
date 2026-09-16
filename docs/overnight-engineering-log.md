# Overnight engineering log

## Start

- UTC start: 2026-09-16 (session began with local audit checkout282b040).
- Synchronized cleanly to starting revision `e9c0c3f2dbc94833ea2ae30ae3ca61a1337e7b82` after fetch/open-PR inspection. Frontend PR1 preserved, no redesign/merge.
- Frozen files and historical result bytes captured in ignored `local/overnight/frozen-start.json`.
- Broad baseline: **387 passed,1 skipped,1 failed,3 errors,13 subtests passed**. Failure: archive exposure scanner; errors: non-hermetic personal model path in MCP tests. No failures hidden.
- Independent scopes: native/context safety; decision/import/telemetry; hermetic tests/CI/report analysis. Root owns tracker/integration.
- All runtime experiments deferred until tracker is tested, code committed, historical evidence archived and exclusive hardware access verified.

## Phase A in progress

Immutable tracker and protocol implemented;22 initial tracker tests pass. Adversarial review found additional crash/concurrency/qualification edges; hardening before release. Owner-dependent items recorded separately. No new hardware measurements.

## Native/context safety checkpoint — 2026-09-16 UTC

- Fixed native output ownership on errors (A19), rejected nested QAIRT shard roots (A20), and preserved context bytes with digest validation (A26). Added literal-stop diagnostic coverage without changing parser semantics.
- Focused native/context tests: 82 passed. Integrated suite: **514 passed, 1 skipped, 13 subtests passed**.
- Hardware smoke test remains required; recorded SSH route timed out. Continuing portable work.
- Commit: recorded in the next checkpoint after commit creation.

## Portable validation checkpoint — 2026-09-16 UTC

- Native/context checkpoint committed as `905fc23`.
- MCP tests use synthetic models; historical leaked archives are exact-byte pinned while novel leakage fails. Frozen validator behavior remains unchanged. Added Linux/macOS/Windows CI.
- Focused MCP/leakage/golden: **46 passed**. Integrated suite: **514 passed, 1 skipped, 13 subtests passed**. Hosted Windows execution remains pending.

## JSON and raw telemetry checkpoint — 2026-09-16 UTC

- Portable validation committed as `7e899b2`.
- Added strict BOM-tolerant private JSON reads, additive per-case sampler capture, raw PDH metadata and declared/observed power separation; reject unbound QAIRT runtime override.
- Integrated validation: 514 passed, 1 skipped, 13 subtests passed. Runner file hash changes explicitly documented; no scoring/timing semantics changed.

## Artifact inventory checkpoint — 2026-09-16 UTC

- JSON/raw telemetry checkpoint: `0a297ae`.
- Added read-only canonical QAIRT artifact inspector: exact file hashes, explicit config evidence, unknown quantization retained, unsafe/missing references rejected.
- Artifact tests: 11 passed. No model download or hardware execution. Bundle inspection waits for actual model access.

## Report qualification checkpoint — 2026-09-16 UTC

- Artifact inspector committed as `2487e88`.
- Decision outputs cannot overwrite inputs or existing companions; exact ties expose co-winners. Imported identity/energy evidence validated, incomplete nested inputs fail closed, measurement/report/reference commits separated.
- Added four identity evidence states; requested placement never independently proves dispatch. Descriptive backend comparison remains energy-optional and selects no overall winner.
- Focused validation: **102 passed**.

## Product evidence contract checkpoint — 2026-09-16 UTC

- Report validation checkpoint: `8db69f1`.
- Added explicit exploratory versus Secretary-qualified mode metadata, without changing selection/inference settings or frontend design. Product BALANCED remains owner-dependent.
- Focused service/tuning suite: **56 passed, 1 skipped**. Application provenance change documented.

## Phase A/C — immutable tracker — 2026-09-16 UTC

- Mode evidence checkpoint: `1f07363`.
- Unique OS-locked EXP allocation, single-snapshot historical import, exclusive sealed inventories, retained failures/timeouts, source/model/config pre/post checks and explicit dirty diagnostics implemented. All attempts contribute block energy; incomplete denominators suppress J/correct.
- Tracker/hardening/report integration: **55 passed**. Required archive structure, crash-release locks, forged identities, Unicode/BOM, timeout cleanup and concurrency covered.
- Rules/protocol and pending owner decisions recorded. Proceeding immediately to historical import and reporting; no new hardware run.

## Phase B and campaign preparation — 2026-09-16 UTC

- Immutable tracker committed/pushed as `99591e8`. Six available historical reports copied to EXP-001..006, all seals verified. Re-import produced the same six archives. Missing requested CPU/HTP/QAIRT-stop dev and 300-second probe artifacts remain explicitly unavailable; no remembered numbers substituted.
- 128 frozen file hashes unchanged. Frontend syntax passes and all 28 frontend tests pass.
- Added development-only offline balanced campaign planner with config hash/drift and single-variable checks; 14 tests passed. Added nine synthetic parser/filesystem characterization tests without changing frozen semantics.
- Runtime experiments still blocked by inaccessible recorded SSH route. Continuing analysis/documentation and CI verification.

## Artifact stability checkpoint — 2026-09-16 UTC

- Campaign/diagnostics checkpoint: `16c5824`.
- Tuner now freshly verifies model/tokenizer/projector/image/prompt inputs after execution within its deadline; changed, deleted or unverifiable inputs cannot rank or export recommendations. Existing raw trials retained.
- Focused tuning tests: **57 passed, 1 skipped**, including five artifact mutations and deadline/deletion regressions.

## Phase F — reports and development errors — 2026-09-16 UTC

- Artifact stability checkpoint: `fc8987b`.
- Added sealed-archive summary, repeated campaign statistics, strict comparable case deltas and single-archive development-only error analysis. Diagnostic uncommissioned energy is excluded from qualified deltas/Pareto/pooling. No overall winner.
- Focused tracker/analysis: **47 passed**.
- First hosted CI at99591e8: macOS passes; Linux/Windows fail. Investigating actual logs; not declaring cross-platform completion.

## Portable CI diagnosis and machine evidence — 2026-09-16 UTC

- Reporting checkpoint: `b3f8329`; generated local SUMMARY, campaign and development-error reports. Only available development report has 25/35 correct and 9/9 failed clarify cases; this is Qwen4B historical evidence, not QAIRT-stop evidence.
- Windows failure traced to platform-default decoding of the frozen UTF-8 inventory: set execution UTF-8 explicitly, no frozen file edit. Linux failure is an unbounded GGUF metadata length allocation; fixing reader separately.
- Added bounded optional Git/Node/npm and machine/Python version capture; 45 tracker tests pass. Historical metadata remains untouched.
