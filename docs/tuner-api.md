# Tuner engine public API

turbo/tuning.py is the bounded tuner core. Stdlib only, no network and no
hardware required for planning or tests. It plans a search space, constructs
exact official-bench commands, runs them serially and ranks results.

## Data classes

Variant.from_dict(dict) - model registry entry. Required fields: id, path,
architecture, quantization, plugin (llama_cpp or qairt), kind (llm or vlm).
Optional: tokenizer_path, mmproj_path, compiled_contexts, requiredimage.

SearchSpace.from_dict(dict) - devices, threads, contexts, prompt/gen token
counts, warmup, repeats. The batch and ubatch fields exist but raise
TuningError when set: the current official bench binary supports only
-t -c -p -n, so no batch flag is ever fabricated.

## Functions

    from turbo.tuning import (
        Variant, SearchSpace, Cell, TuningError,
        plan_cells, build_command, rank_results, run_tuning, export_recommended,
    )

plan_cells(variants, space) -> list[Cell]
    Enumerates every (variant, device, threads, context) combination. Invalid
    combinations keep an unsupported_reason so they stay visible instead of
    being dropped or coerced: qairt on cpu/gpu, context outside registered
    compiled_contexts, and VLM variants without an image workload.

build_command(bench_exe, variant, cell, space, image_path=None, prompt_file=None) -> list[str]
    The exact official-bench invocation. Raises TuningError for batch/ubatch
    requests or unsupported cells. VLM runs add --vlm --mmproj-path <path>
    --image <path> plus --prompt-file when a prompt file is supplied.

rank_results(results, objective, constraints=None, variability_penalty=0.0) -> list[dict]
    objective is decode, prefill, balanced (harmonic mean of decode and
    prefill), fast (max decode) or efficient (tokens/J when present, decode
    otherwise). Only completed cells with at least one full-length run are
    ranked; missing metrics make a cell ineligible rather than scoring zero.
    variability_penalty in [0,1] discounts the score by the cell's
    variability_ratio (std/mean of run decode tps) when present. Each ranked
    row gains rank, score, objective and a provisional flag (true unless the
    cell recorded 3+ repeats). No thermal or power-state cause is ever
    inferred from variability.

pareto_frontier(results, axes=("decode_tps", "prefill_tps")) -> list[dict]
    Cells not dominated on the given axes (higher is better). Missing metrics
    make a cell ineligible. Sorted by the first axis descending.

run_tuning(bench_exe, variants, space, output_dir, objective,
image_path=None, prompt_file=None, timeout_s=240, progress=None) -> dict
    Serial sweep with a unique per-cell output JSON under output_dir,
    timeout_s per subprocess, and a progress(done, total) callback after
    every cell. Returns schema_version, objective, cells_planned, cells_run,
    results, ranking, pareto_frontier, recommended, energy_comparability and
    standing caveats.

## Energy comparability

SearchSpace accepts an optional energy_channel name (for example SYS) that a
caller-side meter fills into per-cell tokens_per_joule. tokens/J is valid
only for the same workload (same prompt/gen tokens) on the same model
quantization and architecture, measured over the full trial interval
including model load. run_tuning reports energy_comparability across cells
and states a violation rather than silently comparing across workloads.

export_recommended(record, path) -> dict
    Writes the recommended config JSON: model variant id, plugin, sha256
    checksum, tuned device/threads/context, and scope (objective, gen_tokens,
    provisional).

## HTTP embedding and model identity

run_tuning is a plain callable and blocks until the sweep finishes or the
budget expires, so wrap it in any HTTP handler thread. The parent service
owns routing and supervision; this module owns planning, command
construction, execution and ranking. Model identity is preserved per cell:
each result row stores the variant id and the model sha256, and rankings
never compare across different weights.
