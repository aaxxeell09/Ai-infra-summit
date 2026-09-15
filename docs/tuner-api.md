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

rank_results(results, objective, constraints=None) -> list[dict]
    objective is decode, prefill or balanced (harmonic mean of decode and
    prefill). Only completed cells with at least one full-length run are
    ranked; missing metrics exclude a cell rather than scoring zero. Each
    ranked row gains rank, score, objective and a provisional flag (true
    unless the cell recorded 3+ repeats).

run_tuning(bench_exe, variants, space, output_dir, objective,
image_path=None, prompt_file=None, timeout_s=240, progress=None) -> dict
    Serial sweep with a unique per-cell output JSON under output_dir,
    timeout_s per subprocess, and a progress(done, total) callback after
    every cell. Returns schema_version, objective, cells_planned, cells_run,
    results, ranking, recommended and standing caveats.

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
