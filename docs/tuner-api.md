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

**QAIRT context is compiled into the bundle.** The captured official
`benchmark.c` forces its runtime `n_ctx` to zero. Each QAIRT variant therefore
requires exactly one registered compiled context and a bundle directory; every
other context is rejected. Register a distinct variant/path per compiled
context. `-c` is preserved in the command for reproducibility but does not
select or recompile a QAIRT context. Its report's `params.n_ctx=0` is retained.

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
were verified offline; no native hardware validation or new network experiments
were performed.

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
row. This runner leaves memory/energy unavailable rather than inventing them.
Energy capture from the parent telemetry layer is deliberately not integrated
in this correction. Setting `energy_channel` alone does not enable it, and an
`efficient` sweep consequently returns no recommendation.

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
