# Three-person ownership

One owner per workstream. Cross-stream changes go through the integrator; each owner delivers a concrete acceptance check.

| Owner | Owns | Does not own | Deliverable |
| --- | --- | --- | --- |
| Device and performance | Runtime/model variants, tuner search space, reproducible measurements, NPU dispatch, power and memory telemetry | Semantic task scoring or pitch claims | Raw results, verified backend evidence and recommended configuration |
| Tasks and correctness | Secretary workloads, held-out prompts, exact action/filesystem checks, routing quality gates | Runtime speed measurements or slide design | A reproducible quality suite showing which speed gains preserve correct behavior |
| Product and submission | Tuner interaction, charts, demo sequence/video, pitch, slides and submission requirements | Changing benchmark results or grading criteria | A working three-minute demonstration with traceable claims |

The coding agent integrates code, runs checks, maintains the research trail and pushes small working commits. Human review focuses on three questions: are measurements real, are actions correct, and does the demo make the result clear?

## Immediate handoffs

- Device owner: ask Qualcomm for the supported way to prove Hexagon dispatch and obtain power telemetry on X1E-80-100; confirm which compiled QNN text-model bundles are available. Keep input/output workload and power state fixed during comparisons.
- Quality owner: prepare held-out file-operation requests with similar filenames, negation, missing information and required clarification. Write expected tool calls before seeing model output.
- Product owner: confirm the exact judging/submission requirements, rehearse the tuner-first pitch, and capture the real device plus the resulting chart/config. Keep secretary/tool examples as a concrete workload, not a second product.

Pitch: “Getting a model onto a Snapdragon is easy; getting it fast is guesswork. This removes the guesswork.”
