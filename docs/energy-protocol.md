# Secretary task-energy protocol

## Objective and inspection

Minimize **gross SYS joules per correct task**, subject to acceptable accuracy, bounded task latency and the existing invalid-output/move/clarification gates. Raw tokens/s is secondary. No new hardware measurement has been executed to prepare this protocol.

| Capability before this change | Status | Reused implementation / missing part |
| --- | --- | --- |
| Cumulative energy meter | EXISTING | Windows PDH `EnergyMeter`, picowatt-hour conversion in `energy_delta` |
| Warm-task boundaries | MISSING | Existing measurements covered an entire evaluation process |
| Platform / runtime idle | MISSING | Counter API existed, repeatable idle windows did not |
| Energy metadata | PARTIAL | Historical telemetry sidecars and per-channel joules; no task lifecycle |
| J/task and J/correct task | MISSING | Existing tuner ranked tokens/J |
| Power conditions | PARTIAL | AC/battery existed; active scheme and battery saver added read-only |
| Warmup | EXISTING | Legacy Secretary has one uncounted development request |
| Decision table / automatic aggregation | PARTIAL | Existing scorer/quality comparison and tuner Pareto ranking reused; task-energy decision reporting added |

No second meter, alternative scoring, new tool definitions or backend optimizations are introduced. The existing runner gains **opt-in** `--energy-protocol` instrumentation. Without it, the one-warmup protocol stays available. The new energy protocol has its own signature and cannot be merged with old full-process energy records.

## Exact lifecycle boundaries

| Scope | Start | End | Excluded |
| --- | --- | --- | --- |
| `warm_task` — primary | After disposable workspace/golden audit setup, immediately before request message preparation | After native completion, deterministic validation/parsing and the actual file tool returns; invalid/model-error attempts also end here | Download, installation, model load, warmups, fixture copying, golden tool execution, final snapshot comparison, report writing |
| `inference` — diagnostic | Immediately before `geniex_llm_generate` | Immediately after that native call returns | Prompt templating, sampler setup, parsing, file tools |
| `cold_load` — separate | Immediately before runtime/model constructors | Loaded model is ready for the first request | Dataset/hash setup, subsequent graph warmups |
| Platform idle | Runtime not yet loaded, no requests | End of each fixed counter window | Any inference |
| Runtime idle | Model loaded and warmups complete, no requests | End of each fixed counter window | Any inference |

Warm-task energy uses the existing parsing/scoring helper, so its small deterministic expected-answer checks and row bookkeeping are inside the boundary. Golden filesystem execution and audit comparisons are outside. This is a local Secretary benchmark measurement, **not** browser/network/UI end-to-end energy. No retries or routing are added; all failures count. If a future retry is introduced it must remain inside the same task interval and require a protocol review.

Counter reads have overhead. The nested inference readings occur inside the warm task interval, uniformly on all backends; inference energy is a subset, never added to task energy. `warm_task_latency_ms` records the task body; meter `duration_s` is the corresponding counter-sampling interval. Their small acquisition-boundary difference remains visible. The legacy `task_latency_ms` also includes audit work and is not used for the primary decision-table latency. Native profile times remain as reported, in microseconds; `timings` uses seconds. Native `timings.total` brackets the generation call inside the observer, excluding the two PDH reads.

## Definitions

For N attempted tasks, C correct tasks and valid gross SYS energy E_i for every attempt:

- **Gross task energy:** `(SYS_after − SYS_before) × 3.6e-9` joules, from cumulative picowatt-hours.
- **J/task:** `sum(E_i) / N`.
- **J/correct task:** `sum(E_i) / C`. Energy consumed by failed attempts remains in the numerator. C=0 means unavailable/undefined, never zero.
- **Platform idle power:** mean of repeated `platform_idle` energy/window measurements with no loaded runtime.
- **Runtime idle power:** mean of repeated `runtime_idle` energy/window measurements with a loaded, warmed model.
- **Net active energy:** `E_i − runtime_idle_W × measured_interval_s`, a secondary diagnostic. If idle is unstable or the result is negative, net energy is null with a reason. Gross energy remains recorded.

Do not report incomplete-energy totals as whole-suite efficiency. One missing/stale/reset/error/too-short task observation makes whole-suite energy eligibility unavailable. Keep the attempts and their failure information.

SYS is the Windows meter's channel name: it is not proof of wall-socket, battery-only or NPU-only energy. CPU/GPU channels are diagnostics; do not add overlapping rails or subtract CPU rails from SYS to infer Hexagon watts. NPU-only energy is unavailable without a verified dedicated rail.

## Commission the counter before running tasks

**Wait for explicit confirmation that the download is complete before running any command in this section or starting the benchmark.** This preparation did not execute them.

A later counter-only probe, in the intended benchmark environment:

```powershell
python -m turbo.telemetry --probe-seconds 60 --sample-interval 0.25 --output local/counter-probe.json
```

This records raw observations and observed update gaps. Polling gaps do not prove the hardware counter's resolution. Inspect for stale steps, resets, error flags and whether gaps depend on polling. Repeat at an appropriate sampling interval if needed. Retain the probe artifact, its hash and observation details in `counter_resolution_evidence`. Do not simply copy the poll interval into `counter_resolution_s`.

Copy `configs/energy-protocol.example.json` to `local/energy-protocol.json`. Its null fields intentionally prevent execution until filled from observations. Declare a conservative observed counter interval, an idle window at least ten times that interval, and a justified `idle_max_cv` (coefficient of variation = standard deviation / mean). A 30–60 s idle window is a candidate starting range, **not an already validated duration**. Three windows are required for each idle condition. Use the same completed protocol file for all three backends.

Warm-task/inference intervals shorter than two declared counter intervals remain unavailable. Two intervals are only a minimum resolution screen, not a precision guarantee; report quantization uncertainty, and do not select a winner if the meter is too coarse for the tasks. No extrapolated or zero-filled per-task energy is supplied. A coarse meter requires a separately designed block-measurement protocol or better instrumentation, not relabeling full-process energy.

## Warmup, power and ordering

- Energy-template warmup: **three non-evaluation requests**, common prompts, normal tool schema and output limit, reset between calls, no model reload within a suite. Warmup energy is recorded separately. Legacy one-request correctness runs remain a different protocol. First graph initialization can remain in warmup rather than cold-load energy; both are reported.
- Initial comparison: one fixed power source (template AC) and one unchanged Windows power mode. The code reads active scheme, AC/battery, battery percentage and battery-saver status; it never changes the plan.
- The active scheme is not necessarily the Settings power-mode overlay. Record the observed mode in the protocol; automatic overlay detection is unavailable. Keep it unchanged and report that manual observation. Beginning/ready/end snapshots do not detect every transient change.
- Keep display brightness/state, network state and background activity matched. `background_contamination=false` is an operator observation, not an automatic proof. Record machine identity and these conditions. No invented temperature or automatic background-activity measurement is provided.
- Prespecify sequential blocks: block 1 CPU→HTP→QAIRT; block 2 HTP→QAIRT→CPU; block 3 QAIRT→CPU→HTP. Record `--run-order` and unique candidate names/output directories. Do not run simultaneous models. No fixed long cooldown is imposed; unstable idle requires investigation and a recorded stabilization decision.
- Reject comparisons with power changes, unknown required power state, changed source/runtime binaries, mismatched lifecycle/warmup/protocol signatures, missing task energy or unstable idle. Keep all raw failed trials. Do not silently select the best block; report repetitions and variability. Current table consumes one prespecified matched block, not a significance test or confidence-interval claim.

## Future execution commands

First run the existing QAIRT smoke test after the download completes and its path is known. Use the same verified SDK and same pinned clean source commit for all variants. Use the prepared `local/llama-cpu-secretary.json`, `local/llama-htp-secretary.json`, `local/qairt-secretary.json` unchanged. CPU/HTP use the same GGUF hash; QAIRT's different precision must be disclosed.

```powershell
python eval/run_secretary_eval.py --dataset all --candidate-name cpu-energy-block1 --config local/llama-cpu-secretary.json --energy-protocol local/energy-protocol.json --run-order 1 --output-dir local/energy/block1
python eval/run_secretary_eval.py --dataset all --candidate-name htp-energy-block1 --config local/llama-htp-secretary.json --energy-protocol local/energy-protocol.json --run-order 2 --output-dir local/energy/block1
python eval/run_secretary_eval.py --dataset all --candidate-name qairt-energy-block1 --config local/qairt-secretary.json --energy-protocol local/energy-protocol.json --run-order 3 --output-dir local/energy/block1
```

For readiness use `--dataset dev` with distinct names first. Runtime/model failures are real failures; no mock fallback exists. Do not infer a hardware timeout from `max_tokens`: native loading/generation is synchronous and has no added wall-clock watchdog here.

The default historical reference is intentionally incompatible. A new clean energy-protocol reference requires explicit Henry approval through the existing baseline workflow in a **new directory**, never overwriting `eval/results/baseline.json`. Supply its path with `--baseline` once available. Changing thresholds, mode names or baseline JSON cannot manufacture a PASS.

## Results and decision artifact

Existing Secretary schema/scoring fields remain. Each instrumented row adds:

```text
energy: {scope: warm_task, channel: SYS, gross_energy_j, duration_s,
         avg_power_w, net_energy_j, idle_power_w_used, unavailable_reason,
         raw_before, raw_after}
warm_task_latency_ms
inference_energy: {same interval fields, scope: inference} or null
```

`task_success`, `profile` (TTFT, prompt/decode times, tokens/s, counts), invalid output and clarification fields are reused. Backend/runtime/requested/resolved device provenance remains available. Top-level `energy_measurement` stores lifecycle intervals, both idle estimates, power snapshots, process peak RAM, protocol signature, SDK hashes, run order and invalidation reasons. Whole-process peak RAM includes loading and audit, not just inference.

The suite summary includes counts, accuracy, total/mean/median/p95 task energy, J/correct task, mean/median/p95 warm latency, invalid output, clarification and critical move failures. p95 needs at least 20 samples. Missing fields stay unavailable. Tokens/J is secondary: no total-runtime token numerator is invented, and legacy uncounted warmup tokens are not divided into full-process energy. When both the generated-token count and inference interval energy are available, `inference_energy.tokens_per_joule` records their matched-scope ratio; it is never a selection objective.

Create or update the table after measurements using the three **instrumented JSON reports**, not historical telemetry sidecars:

```powershell
python eval/decision_table.py --cpu local/energy/block1/candidate_cpu-energy-block1.json --htp local/energy/block1/candidate_htp-energy-block1.json --qairt local/energy/block1/candidate_qairt-energy-block1.json --baseline local/energy-reference/baseline.json --policy local/decision-policy.json --output docs/decision-matrix.md
```

Copy `eval/decision_policy.json` to `local/decision-policy.json`, then designate minimum accuracy and maximum warm-task latency plus its statistic before selection. Defaults are null and intentionally produce no eligible winner. Existing `eval/quality_policy.json` remains unchanged and supplies invalid-output/move/clarification protections. Selection minimizes J/correct task only after those gates and the accuracy/latency limits pass. FAST/EFFICIENT remain conditional recommendations; BALANCED requires a stated trade-off, never assumes a backend identity.

With no inputs, `python eval/decision_table.py` regenerates the honest empty table and JSON companion. All three primary rows remain NOT_MEASURED until corresponding measurements exist; historical numbers are not imported into them. No mode or winning backend is assigned by this preparation.

## Offline validation

The 50 frozen golden cases, their expectations, the fixture and tool schema hashes are unchanged. Synthetic tests establish matching correctness with instrumentation enabled, golden setup outside the interval, actual execution inside it, load/warmup/idle ordering, native generation bracketing, failed-attempt energy accounting, raw counter consistency, missing/zero-correct handling, and refusal to select on incomplete/incompatible evidence. No synthetic readings appear as measured results.

The development suite reports 278 passing tests and 13 passing subtests, one skip. Four known upstream issues remain: the held-out scan detects prompts in committed evaluation audit reports, and three MCP integration tests need an absent developer-local model. They were reported by the full suite, then excluded from the offline verification rerun. External Claude/Fable review is unavailable on this Mac; bounded independent code review checked the instrumentation. No target-device command was executed.
