# Three-person ownership

One owner per workstream. Cross-stream changes go through the integrator; each owner delivers a concrete acceptance check.

| Owner | Owns | Does not own | Deliverable |
| --- | --- | --- | --- |
| Device and performance | Runtime/model variants, tuner search space, reproducible measurements, NPU dispatch, power and memory telemetry | Semantic task scoring or pitch claims | Raw results, verified backend evidence and recommended configuration |
| Tasks and correctness | Secretary workloads, held-out prompts, exact action/filesystem checks, routing quality gates | Runtime speed measurements or slide design | A reproducible quality suite showing which speed gains preserve correct behavior |
| Product and submission | Tuner interaction, charts, demo sequence/video, pitch, slides and submission requirements | Changing benchmark results or grading criteria | A working three-minute demonstration with traceable claims |

Henry/Codex owns native integration, device rehearsal and performance evidence. Axel owns the frozen correctness benchmark, tracking system and optimization-loop work. Ilan owns the frontend visual design; Codex integrates the live provider while preserving that design. Presentation artifacts are built from measured evidence and reviewed with the team. Human review focuses on three questions: are measurements real, are actions correct, and does the demo make the result clear?

## Immediate handoffs

- Device owner: ask Qualcomm for the supported way to prove Hexagon dispatch and obtain power telemetry on X1E-80-100; confirm which compiled QNN text-model bundles are available. Keep input/output workload and power state fixed during comparisons.
- Quality owner: prepare held-out file-operation requests with similar filenames, negation, missing information and required clarification. Write expected tool calls before seeing model output.
- Product owner: confirm the exact judging/submission requirements, rehearse the tuner-first pitch, and capture the real device plus the resulting chart/config. Keep secretary/tool examples as a concrete workload, not a second product.

Pitch: “Getting a model onto a Snapdragon is easy; getting it fast is guesswork. This removes the guesswork.”

## September 16 integration checkpoint

- Ilan's frontend PR at `204a9fb` is merged. The live provider at `86eb559`
  connects its existing screens to the Latitude; the verified browser result is
  under `benchmarks/results/live-ui-1720/`.
- The v5 deck uses the frontend's blue-and-white palette. The primary demo is the
  live CPU answer comparison, followed by recorded MCP and QAIRT evidence.
- Axel's `389c2e8` pilot-recovery work fixes the resume snapshot and `runner=None`
  startup defect. `d4e6743` commissioning work supplies measured stage-cost
  estimates. These are sibling branches, not one merged deployment. Later
  registry/research/canary branches require their own integration review.
- The reviewed loop still uses estimated admission against a session budget;
  this is not a hard per-execution remaining-time deadline. Do not describe an
  arbitrary five-minute budget as guaranteed wall-clock termination. Preserve
  uncertain jobs and reconcile them before resuming.
- A teammate QAIRT pilot was observed on the Latitude and left uninterrupted.
  The demo gateway was started only after its processes exited. Keep one native
  hardware owner; stop/reconcile the gateway before a new autonomous loop session.
