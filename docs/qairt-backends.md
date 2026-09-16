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
