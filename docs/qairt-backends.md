# Three Secretary runtime identities

## Inspection before this change

Inspected clean `main` at `1066632` after fast-forwarding the local checkout. NativeRuntime and NativeModel already loaded both plugins, resolved devices through the SDK and autodetected QAIRT directories containing `geniex.json`. The tuner already admitted QAIRT variants with one compiled context and rejected CPU coercion. The porting preflight already checked bundle shape. Model paths and plugins were already configurable. There was no need for another backend class.

Missing pieces were explicit named identities, additive native result provenance and directory-artifact hashing in the Secretary runner. The committed baseline and candidates are real historical results and remain untouched. Thinking is already disabled in the native chat template (`enable_thinking=False`).

## Configuration

| `backend` | Existing plugin | Requested device | Artifact |
| --- | --- | --- | --- |
| `llama_cpp_cpu` | `llama_cpp` | `cpu` | GGUF file |
| `llama_cpp_htp` | `llama_cpp` | `npu` (also accepts explicit `HTP0`) | GGUF file |
| `qairt_npu` | `qairt` | `npu` | Local directory containing `geniex.json` and the downloaded compiled model files |

`backend` is optional on NativeModel. Old plugin/device calls retain their defaults. Contradictory explicit settings are rejected, as is a known CPU/GPU resolution for an explicitly requested NPU backend. Bundle shape is not proof of compatibility or completed download; the SDK must successfully load it.

Copy `configs/qairt-secretary.example.json` to an ignored private file, e.g. `local/qairt-secretary.json`. Fill `sdk_dir` with the existing native SDK directory and `model_path` with the actual downloaded bundle directory containing `geniex.json`. No machine path is embedded in source. The native binding expects a resolved local artifact, not a model-hub name or archive. Empty paths fail with `QAIRT model not configured` before loading the SDK.

QAIRT compiled context comes from the artifact. A requested generic `context` value does not select another compiled graph or prove its effective context. Do not alter sampling, prompts or context as part of this backend comparison.

## Smallest smoke test

After download completion, verify the local bundle and use the same Python environment as the native Secretary:

```powershell
python scripts/backend_smoke.py --config local/qairt-secretary.json
```

This loads the existing NativeModel, requests 16 output tokens and prints real output/profile/provenance. It does not download anything or run the full benchmark. Then confirm prompt dependence with a second bounded prompt:

```powershell
python scripts/backend_smoke.py --config local/qairt-secretary.json --prompt "Reply with the single word goodbye."
```

Check text, plugin and resolver information; retain SDK errors/warnings. Separate on-device evidence is still needed to establish actual Hexagon dispatch and absence of fallback. Do not run concurrent inference during a benchmark. The token limit bounds generation length, not wall-clock loading time.

Only after successful smoke tests:

```powershell
python eval/run_secretary_eval.py --dataset dev --candidate-name qairt-npu-dev --config local/qairt-secretary.json --output-dir local/qairt-eval
```

Use `--dataset all` and a fresh candidate name for a serious full run. The model's precision may differ from the GGUF; compare deployment variants and disclose this, rather than attributing all differences to the runtime.

## Metadata and compatibility

Legacy `backend: geniex`, `device`, `version` and `config` remain available. Native results add `backend_id`, `runtime`, `requested_device`, `resolved_device`, resolution warning, `model_artifact_type`, `model_path_or_id`, `geniex_version`, `qairt_version` and `dispatch_verified`. Resolver information is not utilization telemetry. QAIRT version and effective compiled context remain null until discovered; no version or dispatch result is invented. GenieX version is the binding's pinned version, not an independent binary version probe.

The runner stores native provenance under `inference_backend` and per-case backend/device fields. QAIRT directory fingerprints reuse `turbo.tuning._sha256`, including all bundle files. Its relative-path representation is platform dependent; compare hashes from the same Windows environment. Secretary reports replace the private artifact path with its basename while retaining artifact hashes; smoke output is a local diagnostic and retains the configured path. Readiness, precision and chipset/context compatibility require the actual artifact and runtime.

**Frozen evaluator guard:** the runner's hash changes with this adapter/provenance integration. Existing scoring therefore correctly returns `NOT_COMPARABLE` versus the historical frozen baseline. This change does not weaken that guard, rewrite the baseline, change golden answers or redefine any score. Before claiming an official quality gate against the historical baseline, the evaluation owner must approve how to handle the runner provenance difference. The three variants can be measured with this same runner; historical records remain immutable. A nonzero exit after writing a candidate report can mean NOT_COMPARABLE, not failed inference.

## Validation and remaining evidence

Backend selection, conflict rejection, QAIRT ABI plumbing and additive metadata are tested using the existing fake SDK harness. These tests do not prove QAIRT inference. No device execution or completed download has been verified from this checkout; the SSH alias documented in `docs/remote-access.md` is not installed in this Mac session.

The existing leakage test currently reports held-out prompts in committed baseline/candidate audit reports introduced upstream after `ccd1e00`. These are evaluation reports, not tuning examples. The detector and frozen methodology are deliberately unchanged here; its failure is reported, not suppressed.

Validation on the development Mac: 245 tests and 5 subtests passed, 1 skipped; the four known upstream failures above were deselected in the focused rerun. Full-suite invocation retained and reported those failures. External Claude/Fable review was unavailable because the Claude executable is absent; a bounded independent code review checked this change.

## Prepared comparison set (same runner)

Configuration preparation inspected clean `main` at `c759d930c7dc0b71080b5f6a177f1433c68c7826`. The QAIRT example already existed; the two llama.cpp examples below complete the set. No inference code or benchmark methodology changed during preparation.

| Variant | Tracked template | Private run configuration | Evidence |
| --- | --- | --- | --- |
| CPU | `configs/llama-cpu-secretary.example.json` | `local/llama-cpu-secretary.json` | `eval/results/candidate_cpu-t10-v2.json` |
| HTP | `configs/llama-htp-secretary.example.json` | `local/llama-htp-secretary.json` | `eval/results/baseline.json`, resolved HTP0 on 50/50 cases |
| QAIRT | `configs/qairt-secretary.example.json` (reused) | `local/qairt-secretary.json` | Existing backend template; actual bundle pending |

CPU preserves the recorded tuned candidate: `threads=10`, `threads_batch=0`, `ubatch=0`, `n_batch=0`, `context=4096`, `max_tokens=128`, `plugin=llama_cpp`, `spec_type=none`, `draft_tokens=8`, `grammar=false`. Zero batch threads requests the SDK default; it is not a measured effective prefill thread count. This historical CPU candidate failed the quality gate; using its settings does not make it an accepted winner.

HTP preserves the reference's numeric settings (`threads=0`, all batch settings zero, context 4096, output 128, no speculation/grammar). Its sole intentional selection change is historical `device=auto` → explicit `device=npu`, with `backend=llama_cpp_htp`. Verify that the SDK still resolves HTP0. Do not claim the old run explicitly requested NPU.

Both GGUF paths must point to the SAME Qwen3-0.6B Q4_0 file. Recorded SHA-256: `33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb`. QAIRT uses its separately identified official Qwen3-0.6B artifact; disclose its precision/context after inspecting the download. No QAIRT quantization or effective compiled context is assumed here. Its omitted native settings retain current defaults, and `max_tokens=128` matches the other two.

### Prepare paths on the Latitude

Run from the repository root. Preserve existing private files:

```powershell
New-Item -ItemType Directory -Force local | Out-Null
foreach ($name in @('llama-cpu-secretary', 'llama-htp-secretary', 'qairt-secretary')) {
    if (!(Test-Path "local/$name.json")) {
        Copy-Item "configs/$name.example.json" "local/$name.json"
    }
}
```

Fill `sdk_dir` with the same verified native SDK directory in all three. Fill the two GGUF `model_path` values identically; leave QAIRT blank until the real completed directory containing `geniex.json` is known. Edit JSON as UTF-8 without a BOM. Record actual current conditions in `hardware_note` (this optional field can also be added to QAIRT), without copying historical assertions that power mode has already been verified. `local/` is ignored by Git. Empty templates are preparation files, not runnable configurations.

### Exact commands

These commands are prepared only; do not execute them while the active download or another inference workload would interfere. After synchronizing the preparation commit, pin **one clean commit** for the entire set, and do not pull or edit source between runs. Record `git rev-parse HEAD`. Use the same SDK binaries, generation protocol, environment and recorded power mode, and run sequentially. Use new output names/directories for repetitions; existing results are never overwritten.

Development runs (35 cases each):

```powershell
python eval/run_secretary_eval.py --dataset dev --candidate-name llama-cpu-current-dev --config local/llama-cpu-secretary.json --output-dir local/three-backends/dev
python eval/run_secretary_eval.py --dataset dev --candidate-name llama-htp-current-dev --config local/llama-htp-secretary.json --output-dir local/three-backends/dev
```

When the QAIRT download finishes, verify the completed artifact, fill its path, and run the smallest smoke test first:

```powershell
python scripts/backend_smoke.py --config local/qairt-secretary.json
python scripts/backend_smoke.py --config local/qairt-secretary.json --prompt "Reply with the single word goodbye."
```

Check for genuine prompt-dependent output and `runtime=qairt`, the resolved device, errors/warnings and model fingerprint. Resolver metadata alone still does not establish hardware utilization. Only after successful smoke:

```powershell
python eval/run_secretary_eval.py --dataset dev --candidate-name qairt-npu-current-dev --config local/qairt-secretary.json --output-dir local/three-backends/dev
```

Serious full runs (50 cases each; same commit as each other):

```powershell
python eval/run_secretary_eval.py --dataset all --candidate-name llama-cpu-current-all --config local/llama-cpu-secretary.json --output-dir local/three-backends/all
python eval/run_secretary_eval.py --dataset all --candidate-name llama-htp-current-all --config local/llama-htp-secretary.json --output-dir local/three-backends/all
python eval/run_secretary_eval.py --dataset all --candidate-name qairt-npu-current-all --config local/qairt-secretary.json --output-dir local/three-backends/all
```

All three use identical golden cases, schema, scoring, fixture, system prompt and current runner. Different model/runtime implementations can have different tokenizers or sampling behavior; matching requested settings is not proof of identical effective sampling. The existing llama.cpp zero-temperature SDK caveat remains in force; do not add a greedy optimization to this set.

**Comparison status:** these commands intentionally create candidate records and retain the runner's default historical baseline. Its hash mismatch produces `NOT_COMPARABLE` (exit 2) even if inference and report writing complete. Never interpret exit 2 alone as failed inference or ignore other errors. The three new records can be compared descriptively on their common methodology; the current comparison CLI does not treat a candidate file as an approved baseline. A formal PASS/FAIL needs a separately designated, Henry-approved current-runner reference in a NEW output directory using the existing `--freeze-baseline` / `--baseline-approval` workflow. No approval or new reference is manufactured here, and `eval/results/baseline.json` stays immutable. Once that new reference exists, supply it with `--baseline` for candidate runs/comparisons. This is a reference-designation requirement, not permission to weaken the guard.

### Energy and latency metadata: existing capability and gaps

Objective: minimize **joules per correct task** while satisfying accuracy requirements and a predefined maximum end-to-end task latency. The maximum latency value and whether it applies to every task, p95 or another statistic have not yet been designated; no new threshold or gate is introduced by this preparation.

- `hardware_note` can associate recorded power mode/source/background conditions with a run. It does not measure them. `turbo.telemetry.power_state()` reports AC/battery state, not the Windows power plan.
- Existing `turbo.telemetry.EnergyMeter`, `energy_delta` and `ProcessMemory` support Windows counter deltas and memory. Historical `*_telemetry.json` sidecars demonstrate per-channel joules, average watts, before/after samples, timing scope and process memory.
- The Secretary runner itself does **not** invoke that collection or accept energy/power-mode flags. The commands above alone will not produce new energy sidecars. The device operator must reuse the existing measurement harness or separately associate a telemetry sidecar with the exact run ID, result/config/commit hashes and shared timing boundaries. A reusable Secretary energy-wrapper CLI is not present in this checkout; it is not built in this task.
- Use the same measured channel, e.g. `SYS`, for all variants. `SYS` is a meter channel, not a claim of wall-socket or NPU-only energy. Do not add overlapping channel totals. Missing counters remain unavailable, not zero.
- For total matched run energy E, N evaluated tasks and C correct tasks: **J/task = E/N**, **J/correct task = E/C**. Include energy spent on failures. For C=0, J/correct task is undefined (or explicitly infinite), never zero. Label these as amortized full-run values if E includes initialization, warmup, fixture/scoring and serialization, as historical sidecars do. The runner does not automatically compute these derived fields.
- Tokens/J requires a token count covering the SAME energy interval. Historical sidecars leave it null because warmup tokens are missing; summing measured-case tokens does not repair that mismatch. Preserve this limitation.
- `latency_ms` measures completion/templating; `task_latency_ms` additionally includes deterministic scoring, fixture copying and tool execution. Neither includes model initialization/warmup. They are benchmark timing boundaries, not full UI/network response time. Record the intended latency threshold against the appropriate boundary.
- Native profiles already record TTFT, prompt/decode times, speeds and token counts; reports include accuracy, invalid outputs and clarification metrics. Memory and power remain associated telemetry, not new tuning knobs.

No energy value, device path, artifact completion or new benchmark result is inferred by these templates.

Preparation validation: all three templates parse, use runner-supported keys and resolve to the intended identities; CPU/HTP values match committed evidence. Missing QAIRT artifact is rejected. Configuration-only QAIRT resolution was tested with a temporary marker, without loading the SDK. The 30 existing backend/native/telemetry tests pass, frozen benchmark validation passes, and local copies are Git-ignored. No inference ran.
