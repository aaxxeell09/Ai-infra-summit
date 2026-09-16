# Bounded tuner API (schema v2)

Public entry points: `Variant`, `SearchSpace`, `Cell`, `TuningError`,
`plan_cells`, `build_command`, `rank_results`, `pareto_frontier`, `run_tuning`
and `export_recommended` in `turbo.tuning`. Python 3.11+, standard library only.
The HTTP service should execute the blocking runner in its worker thread/process.

```python
from turbo.tuning import Variant, SearchSpace, run_tuning, export_recommended

variants = [Variant.from_dict(v) for v in config["variants"]]
space = SearchSpace.from_dict(config["search_space"])
record = run_tuning(
    bench_exe, variants, space, new_output_dir,
    objective=config["objective"],
    prompt_file=config.get("prompt_file"), image_path=config.get("image_path"),
    timeout_s=config.get("timeout_s", 240), budget_s=config.get("budget_s", 600),
    power_state=config.get("power_state", "unavailable"),
    constraints=config.get("constraints"),
    progress=lambda done, total: update_job(done, total),
)
if record["recommended"]:
    export_recommended(record, recommended_path)
```

`power_state` is a caller declaration for the measured session, not a power
measurement made by this module. Use `"unavailable"` unless it is known. Unknown
power states are scoped to the current output directory so separate sessions
cannot be pooled. A caller must split sessions when the power state changes.

## Registry, planning and native command

`Variant.from_dict(d)` takes required `id`, `path`, `architecture` (model
architecture), `quantization`, `plugin` (`llama_cpp`/`qairt`), and `kind`
(`llm`/`vlm`). Optional: `tokenizer_path`, `mmproj_path`, `compiled_contexts`
(integer context sizes) and `requiredimage`. Paths must be local artifacts.
No model-manager ids are sent to the benchmark.

`SearchSpace.from_dict(d)` accepts `devices`, `threads`, `contexts`,
`prompt_tokens`, `gen_tokens`, `warmup`, `repeats`, `temperature`, `seed`,
`batch`, `ubatch`, and reserved `energy_channel`.

`plan_cells(variants, space, max_cells=256)` validates axes and caps the
Cartesian product before allocating it. Unsupported combinations remain visible
as `Cell.unsupported_reason`. `batch`/`ubatch` are unsupported planned SDK
capabilities; no batch flags are emitted. QAIRT accepts only explicit NPU cells.

**QAIRT context is compiled into the bundle.** Register its maximum context
as one `compiled_contexts` entry; internal graph buckets such as 512/1024/4096
are selected by the runtime, not separate `-c` sweep values. The adapter reads
`genie_config.json`, verifies every declared shard, passes one shard as `-m`
and explicitly passes `-c 0`. A registration that disagrees with the artifact
is rejected. Only `device=npu` and `threads=0` are supported; llama.cpp thread
axes must not be represented as QAIRT optimizations.

`build_command(exe, variant, cell, space, image_path=None, prompt_file=None,
output_json=None, cell_id=None)` emits supported native flags:

- Both plugins receive `--plugin --device -m -t -c -p -n -r --warmup
  --temperature --seed`.
- A registered tokenizer is passed using `--tokenizer-path`.
- VLM requires image and prompt files and receives `--vlm --image --prompt-file`.
  `llama_cpp` also requires `--mmproj-path`. QAIRT VLM may use a self-contained
  bundle without a separate projector.
- QAIRT LLM also requires `--prompt-file`: the captured runner identifies QAIRT
  as rejecting random input ids. Prompt-file token counts, including QAIRT
  padding, come from the native report; requested `-p` is not a measured count.
- The runner always supplies `--output-json` with a unique trial target and
  `--cell-id`. Prompt files are wired for LLM as well as VLM.

Support was checked against the locally captured official GenieX `options.c`,
`benchmark.c`, and `run.c` in the parent's `local/geniex-research/`. The raw
schema-4 fixture is `benchmarks/results/screen-01/cpu-t0.json`. These changes
include real Latitude QAIRT command validation: two complete 32-token trials
through the compiled bundle after the shard/context fix. The screening cell
had no comparator and establishes no optimization gain. QAIRT prefill is
marked as runtime-reported prompt tokens / TTFT, potentially including compiled
padding, rather than an independent prefill measurement.

## Runner and failure handling

`run_tuning(exe, variants, space, output_dir, objective="decode",
image_path=None, prompt_file=None, timeout_s=240, progress=None, *,
budget_s=600, constraints=None, power_state="unavailable",
variability_penalty=0.0)`:

- Requires a new output directory (`exist_ok=False`), with numbered trial
  directories containing `bench.log` (stdout and stderr) and `result.json`.
  Existing directories fail before execution; old results cannot be reused.
- Runs serially, bounding each subprocess by the smaller of its timeout and
  the remaining total budget. Model/runtime/workload hashing is included in the
  budget and checks the deadline between chunks.
- Atomically writes `record.json` before execution and after each trial.
  Missing artifacts, build errors, bad JSON, exit failures, short output and
  timeouts remain visible. One bad trial does not abort the remaining cells.
  A failed progress callback propagates after evidence has been saved.
- Preserves per-run results and native reported parameters. Numeric metrics
  use `agg.<metric>.median`, never an aggregate object. Successful completion
  requires every requested measured repetition to finish at the requested
  token count with `stop_reason="length"` and matching native parameters,
  requested plugin/device, model path and trial id.
- SHA256 hashes individual files normally. Bundle directories use a sorted
  manifest digest of relative names (NUL-terminated) and each file's binary
  SHA256. Tokenizer/projector hashes are included separately. Artifacts must
  remain immutable throughout a sweep; fingerprints are cached within it.

`results` contains chart-ready per-cell rows, failures included. `ranking`
contains a flat list of **separate groups**; `rank` starts at 1 in each group.
`recommendations` maps each `group_id` to its scoped winner. `recommended` is
populated only when the entire sweep has exactly one comparison group.
`pareto_frontier` contains eligible non-dominated cells within those same groups.
No quality calibration or winner across different weights is inferred.

## Eligibility, objectives and export

Groups explicitly include variant id, model SHA256, model architecture,
quantization, plugin/kind, artifact SHA256s, workload fingerprint, power state
and its scope, and runtime SHA256. Workload fingerprints include prompt/image
content, requested lengths, repetitions, warmup, seed and temperature. Runtime
axes (threads/device/context) are excluded so they can be tuned within a group.

`rank_results(results, objective="decode", constraints=None,
variability_penalty=0.0)` requires `status="completed"`, all repeats full length,
and complete grouping metadata. Missing, nonfinite, nonnumeric or nonpositive
required metrics are ineligible.

- `decode` / `fast`: maximize median decode tokens/s.
- `prefill`: maximize median prefill tokens/s.
- `balanced`: minimize median native profile latency
  `(media_us + prompt_time_us + decode_time_us) / 1e6`. Its score is the reciprocal
  in 1/s; this includes encoding, prefill and decode, excluding model loading.
- `efficient`: maximize full-process generated tokens/J. **No decode fallback.**

Constraints use `{"rules": [["decode_tps", "min", 80],
["peak_working_set_mb", "max", 8000]]}`; missing constrained metrics exclude a
row. On Windows, the runner observes child-process peak working set and
Energy Meter SYS counter deltas, including process startup and model loading.
Efficient mode requires a valid full-process interval, known AC/battery state,
full-length outputs, and `warmup=0`. Missing or stale readings remain unavailable.

An external telemetry adapter may supply `energy_valid=true`, positive
`energy_j` and `energy_duration_s`, `energy_scope="full_process_trial"`, a
named `energy_channel`, known AC/battery state and `warmup=0` on otherwise
eligible rows. Efficiency is derived from full-length token counts divided by
measured joules. A bare `tokens_per_joule` field is insufficient. Missing,
stale/reset, partial-interval or warmup-unaccounted measurements must never be
marked valid. Energy comparisons also separate scope and channel; rails are
never summed or labeled as wall-socket energy.

Optional variability penalty divides the objective score by
`1 + penalty * variability_ratio`, with the ratio derived from per-run decode
standard deviation / mean. Requesting the penalty requires that diagnostic.
This is observed run variation, not evidence of a thermal cause.

`pareto_frontier(results, axes=("decode_tps", "prefill_tps"))` applies the same
full-length and identity eligibility, with higher-is-better axes. Including
`"tokens_per_joule"` requires the same valid energy evidence as `efficient`.

All recommendations are `provisional=true` and
`requires_paired_confirmation=true`, regardless of repetition count. Independent
repetitions do not establish paired confirmation.

`export_recommended(record, path, group_id=None)` writes the registered model
and artifact hashes, plugin, device, threads, context and complete workload,
power/runtime/objective scope. For multiple groups, the caller must choose
`group_id`; exporting a global recommendation raises `TuningError`.

## Parent service ingestion: exact modes contract

`run_tuning` now also returns:

- `recommendation`: a `turbo.recommended.v2` modes record (shape below), or
  `null` when an explicit group must be selected or the service cannot apply it.
- `recommendation_path`: absolute path to the newly written
  `<output_dir>/recommended.json`, or `null`.
- `recommendation_error`: reason when no service recommendation was produced.

The existing `recommended` field is the selected **trial row** for the requested
objective. It is different from `recommendation`, which is the parent's
apply-compatible modes record. `export_recommended` remains the complete generic
single-profile export for other adapters.

```python
record = run_tuning(...)  # completed job; parent owns locking/inference teardown
if record["recommendation_path"] is not None:
    engine.config["recommendation_file"] = record["recommendation_path"]
    engine.apply("fast", record["recommendation"]["model_id"])
```

Registry variant ids must match the parent's `config["models"]` keys.
The parent owns persisting its changed recommendation-file setting.
Nothing in this module edits or reloads the parent service automatically.

Exact modes-record fields (values below describe their types; `null` is JSON):

```text
{
  "schema_version": "turbo.recommended.v2",
  "model_id": string,
  "model_sha256": string,
  "model": Variant fields with absolute artifact paths,
  "plugin": "llama_cpp",
  "artifact_sha256": {"model": string, ...},
  "runtime_sha256": string,
  "scope": {
    "group_id": string,
    "workload": SearchSpace sampling fields + prompt/image paths and SHA256s,
    "power_state": string,
    "power_scope": string,
    "quality_calibrated": false,
    "cold_kv": true,
    "evidence": absolute path to record.json,
    "provisional": true,
    "requires_paired_confirmation": true
  },
  "modes": {
    "fast": {
      "device": string,
      "threads": integer,
      "context": integer,
      "metrics": {
        "decode_tps": number|null,
        "prefill_tps": number|null,
        "latency_s": number|null,
        "tokens_per_joule": number|null,
        "median_decode_tps": number|null,
        "median_ttft_ms": number|null,
        "median_peak_mib": number|null
      },
      "evidence": absolute path to the chosen trial result.json,
      "command": [string, ...],
      "provisional": true,
      "requires_paired_confirmation": true
    },
    "balanced": same shape, selected by measured native profile latency,
    "efficient": same shape, present only with valid comparable energy
  },
  "unavailable_modes": {omitted mode name: reason}
}
```

Each mode independently selects an eligible measured row from one group;
device/threads/context are copied exactly from that row. The current runner
normally emits `fast` and `balanced`; `efficient` is omitted without energy.
`balanced` here means measured profile latency as defined above, so the parent
does not substitute its legacy speed/energy interpolation.

`recommendation_record(record, group_id=None)` is also public. It builds this
record from completed measurements without launching anything. Use an explicit
group id for a multi-model sweep, or call it again after a parent telemetry
adapter attaches valid evidence to result rows. Multiple energy-channel groups
cannot produce one efficient winner.

The current parent's `Engine.load` only constructs `llama_cpp` LLMs without
tokenizer/projector overrides. This service-specific export therefore rejects
QAIRT/VLM/override profiles. Their measurements and generic scoped exports still
work; the parent must add the correct native load path before applying them.
This avoids claiming an incompatible model configuration was applied.

The local integration test imports the parent service read-only, calls its real
`Engine.apply`, and substitutes only `NativeRuntime`/`NativeModel` to inspect load
arguments. It asserts the new measured configuration and model SHA are honored,
and rejects absent efficient modes and another model's weights. The benchmark
side is an external fake CLI using the real schema-4 fixture. This is software
contract validation, not a claim of a new Latitude benchmark.


## Runtime binding and application

New recommendations include `runtime_binding`: SHA-256 of the benchmark executable
and native SDK libraries, recursively including QAIRT HTP libraries. Relative
manifest paths survive SDK relocation. The manifest excludes Windows, firmware
and drivers, which remain separate experiment provenance.

The tuner checks the SDK before and after measurements. The service verifies the
model or complete bundle hash, plugin and SDK binding before applying a mode.
Changed, missing or added libraries reject stale recommendations. A service with
an already loaded SDK also retains its original identity and requires restart
when disk bytes change; it cannot fix DLL residency by closing a model.
Legacy records without a runtime manifest require a fresh tune.

LLM recommendations support both `llama_cpp` and `qairt`. For QAIRT HTTP tuning,
register the bundle's compiled context and configure `tuner.prompt_file` locally.
This path supplies the same text workload to each selected backend. QAIRT modes
remain provisional and `quality_calibrated=false`; a working apply path does
not override the failed Secretary quality result.
