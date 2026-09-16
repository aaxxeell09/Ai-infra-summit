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
