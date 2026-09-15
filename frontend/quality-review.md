# Demo UX quality review — 2026-09-15

Scope: three local screens, their copy and information hierarchy, task-provider boundary, and visible interaction behavior. The design-review checklist was applied to this existing in-progress UI. No public deployment, live hardware task execution or formal accessibility certification is claimed.

## Findings and changes

| Finding | Impact | Change |
| --- | --- | --- |
| The final step read like a disconnected canned file animation. | High | Added a compact model/configuration handoff, an explicit selected/applied state and a task provider that receives the chosen identity. |
| Fixed success copy could be mistaken for verified model output. | High | Result-driven live outcomes; preview explicitly says no model ran. Passing live status requires semantic/action/postcondition checks. |
| “Calibrate” implied a new benchmark would execute. | Medium | Navigation now says “Compare”; the first action opens recorded configurations. No fake calibration progress. |
| “Sweet spot” and “Make it do something” conveyed little about the task. | Medium | “Tune your model. For this machine.” → “Choose how it runs.” → “Your model. In action.” |
| Mode disclosures and evidence actions were duplicated. | Medium | One persistent mode badge; benchmark evidence in the footer and task evidence next to its outcome. |
| Raw action JSON competed with the visible file result. | Medium | Moved action details into a collapsed disclosure. The request and workspace are the two primary columns. |
| The empty folder promised a file would arrive even for clarification. | Medium | Neutral “No files in this folder” state. Clarification preserves the inventory. |
| Changing selection could leave an outcome from the old configuration. | High | Any metric/configuration change invalidates the prior task and restores its initial state. |
| Whole-screen entrance animation repeated during task updates. | Polish | Entrance only on navigation; result/file motion stays local and honors reduced-motion settings. |
| Small mobile scenario/selection buttons were difficult to use. | Medium | Scenario buttons are at least 44px high; selection CTAs are 48px and full-width at narrow sizes. |

## Quick wins completed

- Name actions after what actually happens: compare, preview, run on the device.
- Carry model and configuration into the final step without repeating chart metrics.
- Keep technical evidence expandable.
- Leave the final result visible; no automatic jump back to the opening screen.

## Verification

- Node syntax checks pass.
- 23 tests pass across recorded-data validation, ranking, export, isolated preview scenarios and the injected live provider.
- Live-provider tests use test doubles. They cover wrong model/settings, missing application acknowledgement, stale request/snapshot, invalid quality evidence, inconsistent file result, unscoped timings, device failure and abort. They are not hardware evidence.
- Browser: all three pages; metric-dependent selection (CPU 2 for first token, CPU 10 for generation); exact selection carried to task; previous outcome cleared after selection changes; successful example move and ambiguity; evidence dialog and responsive comparison controls.
- At 390px viewport width, comparison and task pages have no document horizontal overflow. Selection buttons measure 309×48px.
- Browser console: no errors observed during tested flows.

## Remaining integration work

The final live task still requires a backend bridge, exact setting application, disposable device fixtures, inference/execution and independent task checks. `task-contract.md` defines that handoff. The UI must not be presented as already running the model.

The additional read-only agent review checked the contract boundary. Requested Claude/Fable review was unavailable: the local Claude harness was logged out and the referenced cost-aware-delegation skill was absent. No such review is claimed.

The final adapter review also found and fixed canonical inventory comparison, ambiguous-task success validation and unsafe file-kind interpolation. Regression tests cover the first two; CSS class selection now uses a fixed allowlist.
