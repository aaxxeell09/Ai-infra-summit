"""Bounded tuner engine: plan, run and rank official-bench cells.

Stdlib only. Emits only flags the official llama-bench supports
(-t -c -p -n). Batch/ubatch are planned capability, never fabricated.
"""
from __future__ import annotations

import hashlib, json, subprocess, time
from dataclasses import dataclass
from pathlib import Path


class TuningError(ValueError):
    """Raised for invalid configs or unsupported combinations."""


@dataclass(frozen=True)
class Variant:
    id: str
    path: str
    architecture: str
    quantization: str
    plugin: str  # "llama_cpp" | "qairt"
    kind: str  # "llm" | "vlm"
    tokenizer_path: str | None = None
    mmproj_path: str | None = None
    compiled_contexts: tuple[str, ...] | list[str] | None = None
    requiredimage: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Variant":
        try:
            return cls(
                id=data["id"], path=data["path"],
                architecture=data["architecture"],
                quantization=data["quantization"],
                plugin=data["plugin"], kind=data["kind"],
                tokenizer_path=data.get("tokenizer_path"),
                mmproj_path=data.get("mmproj_path"),
                compiled_contexts=data.get("compiled_contexts"),
                requiredimage=bool(data.get("requiredimage", False)),
            )
        except KeyError as exc:
            raise TuningError(f"variant missing required field {exc}") from exc


@dataclass(frozen=True)
class SearchSpace:
    devices: tuple[str, ...] = ("cpu",)
    threads: tuple[int, ...] = (4,)
    contexts: tuple[int, ...] = (4096,)
    prompt_tokens: int = 512
    gen_tokens: int = 128
    warmup: int = 0
    repeats: int = 1
    batch: int | None = None
    ubatch: int | None = None
    # Optional energy channel name (e.g. "SYS") for caller-side tokens/J.
    energy_channel: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SearchSpace":
        return cls(
            devices=tuple(data.get("devices", ["cpu"])),
            threads=tuple(data.get("threads", [4])),
            contexts=tuple(data.get("contexts", [4096])),
            prompt_tokens=data.get("prompt_tokens", 512),
            gen_tokens=data.get("gen_tokens", 128),
            warmup=data.get("warmup", 0),
            repeats=data.get("repeats", 1),
            batch=data.get("batch"),
            ubatch=data.get("ubatch"),
            energy_channel=data.get("energy_channel"),
        )


@dataclass(frozen=True)
class Cell:
    variant_id: str
    device: str
    threads: int
    context: int
    kind: str
    plugin: str
    unsupported_reason: str | None = None


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def plan_cells(variants: list[Variant], space: SearchSpace) -> list[Cell]:
    """Enumerate cells; invalid combos carry unsupported_reason."""
    cells: list[Cell] = []
    for v in variants:
        for device in space.devices:
            base_reason = None
            if v.plugin == "qairt" and device in ("cpu", "gpu"):
                base_reason = f"qairt does not support device={device}; would require coercion"
            elif v.kind == "vlm" and not v.requiredimage:
                base_reason = "VLM requires an image workload (requiredimage=true)"
            for threads in space.threads:
                for context in space.contexts:
                    reason = base_reason
                    if (
                        reason is None and v.compiled_contexts
                        and str(context) not in [str(c) for c in v.compiled_contexts]
                    ):
                        reason = (
                            f"requested context {context} not in "
                            f"compiled_contexts {list(v.compiled_contexts)}"
                        )
                    cells.append(Cell(
                        variant_id=v.id, device=device, threads=threads,
                        context=context, kind=v.kind, plugin=v.plugin,
                        unsupported_reason=reason,
                    ))
    return cells


def build_command(
    bench_exe: str, variant: Variant, cell: Cell, space: SearchSpace,
    image_path: str | None = None, prompt_file: str | None = None,
) -> list[str]:
    """Exact official bench invocation; TuningError on batch/ubatch or
    unsupported cells."""
    if space.batch is not None or space.ubatch is not None:
        raise TuningError(
            "batch/ubatch tuning is planned but not supported by the current "
            "official bench binary; refusing to emit an unsupported flag"
        )
    if cell.unsupported_reason:
        raise TuningError(f"cell {cell} unsupported: {cell.unsupported_reason}")
    if cell.kind == "vlm":
        if not image_path:
            raise TuningError("VLM cell requires image_path")
        if not variant.mmproj_path:
            raise TuningError("VLM variant requires mmproj_path")
    cmd = [str(bench_exe), "--plugin", variant.plugin, "--device", cell.device,
           "-m", str(variant.path), "-c", str(cell.context),
           "-p", str(space.prompt_tokens), "-n", str(space.gen_tokens),
           "-t", str(cell.threads)]
    if variant.plugin == "llama_cpp":
        cmd += ["--warmup", str(space.warmup), "-r", str(space.repeats),
                "--temperature", "0", "--seed", "42"]
    if cell.kind == "vlm":
        cmd += ["--vlm", "--mmproj-path", str(variant.mmproj_path),
                "--image", str(image_path)]
        if prompt_file:
            cmd += ["--prompt-file", str(prompt_file)]
    return cmd


def _parse_result_json(data: dict, gen_tokens: int) -> dict:
    """Metrics from one bench JSON; None when no full-length run."""
    runs = data.get("runs") or []
    full = [r for r in runs if r.get("gen_tokens") == gen_tokens]
    agg = data.get("agg") or {}
    return {
        "complete_length_runs": len(full),
        "prefill_tps": agg.get("prefill_tps") if full else None,
        "decode_tps": (agg.get("decode_tps") or agg.get("generation_tps")) if full else None,
        "device_id": data.get("device_id"),
    }


def rank_results(
    results: list[dict], objective: str = "decode",
    constraints: dict | None = None,
    variability_penalty: float = 0.0,
) -> list[dict]:
    """Rank successful full-length cells only.

    objective: decode | prefill | balanced (harmonic mean) | fast (max
    decode) | efficient (tokens/J when present, decode otherwise). Missing
    metrics make a cell ineligible, never zero. variability_penalty in [0,1]
    discounts by variability_ratio (std/mean of run decode tps) when present.
    provisional=True unless the cell recorded 3+ repeats. No thermal cause
    is inferred.
    """
    if objective not in ("decode", "prefill", "balanced", "fast", "efficient"):
        raise TuningError(f"unknown objective {objective!r}")
    constraints = constraints or {}
    scored: list[tuple[float, dict]] = []
    for r in results:
        if r.get("status") != "completed":
            continue
        if (r.get("complete_length_runs") or 0) < 1:
            continue
        d, p = r.get("decode_tps"), r.get("prefill_tps")
        if objective == "balanced":
            score = (2 / (1 / d + 1 / p)) if (d and p) else None
        elif objective == "fast":
            score = d
        elif objective == "efficient":
            e = r.get("tokens_per_joule")
            score = e if e is not None else d
        else:
            score = r.get({"decode": "decode_tps", "prefill": "prefill_tps"}[objective])
        if score is None or score <= 0:
            continue
        vr = r.get("variability_ratio")
        score = score * (1 - variability_penalty * min(vr, 1.0)) if (
            variability_penalty > 0 and vr is not None) else score
        passed = all(
            r.get(f) is not None and (r.get(f) >= b if op == "min" else r.get(f) <= b)
            for f, op, b in constraints.get("rules", [])
        )
        if passed:
            scored.append((score, r))
    scored.sort(key=lambda pair: -pair[0])
    out = []
    for i, (score, r) in enumerate(scored):
        row = dict(r)
        row.update(rank=i + 1, objective=objective, score=score,
                   provisional=(r.get("repeats", 1) or 0) < 3)
        out.append(row)
    return out


def pareto_frontier(
    results: list[dict],
    axes: tuple[str, ...] = ("decode_tps", "prefill_tps"),
) -> list[dict]:
    """Cells not dominated on the axes (higher is better); missing metrics
    are ineligible. Sorted by the first axis descending."""
    eligible = [
        r for r in results
        if r.get("status") == "completed"
        and all(r.get(a) is not None for a in axes)
    ]
    frontier = [
        r for r in eligible
        if not any(
            other is not r and all(other[a] >= r[a] for a in axes)
            and any(other[a] > r[a] for a in axes)
            for other in eligible
        )
    ]
    return sorted(frontier, key=lambda r: -r[axes[0]])


def _energy_comparable(rows: list[dict]) -> str | None:
    """Energy rows share workload and model identity, else a reason."""
    if len(rows) < 2:
        return None
    for k in ("gen_tokens", "prompt_tokens", "quantization", "architecture"):
        if len({r.get(k) for r in rows}) > 1:
            return f"not comparable: differing {k} across energy rows"
    return None


def run_tuning(
    bench_exe: str, variants: list[Variant], space: SearchSpace,
    output_dir: str, objective: str = "decode",
    image_path: str | None = None, prompt_file: str | None = None,
    timeout_s: int = 240, progress=None,
) -> dict:
    """Serial bounded sweep; progress(done, total) after every cell."""
    if space.batch is not None or space.ubatch is not None:
        raise TuningError(
            "batch/ubatch tuning is planned but unsupported by the official bench; "
            "capability recorded, no run emitted"
        )
    cells = plan_cells(variants, space)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for i, cell in enumerate(cells):
        variant = next(v for v in variants if v.id == cell.variant_id)
        row: dict = {
            "variant_id": cell.variant_id, "device": cell.device,
            "threads": cell.threads, "context": cell.context,
            "kind": cell.kind, "plugin": cell.plugin,
            "repeats": space.repeats, "gen_tokens": space.gen_tokens,
            "model_sha256": _sha256(variant.path) if Path(variant.path).is_file() else None,
        }
        if cell.unsupported_reason:
            row.update(status="unsupported", reason=cell.unsupported_reason)
            results.append(row)
            if progress:
                progress(i + 1, len(cells))
            continue
        cmd = build_command(bench_exe, variant, cell, space, image_path, prompt_file)
        target = out / f"{cell.variant_id}-{cell.device}-t{cell.threads}-c{cell.context}.json"
        row["command"] = cmd
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
            row["exit_code"] = proc.returncode
            if proc.returncode != 0 or not target.exists():
                row.update(status="failed", stderr=proc.stderr[-2000:])
            else:
                data = json.loads(target.read_text(encoding="utf-8-sig"))
                row.update(status="completed",
                           **_parse_result_json(data, space.gen_tokens))
        except subprocess.TimeoutExpired:
            row.update(status="timeout", exit_code=None)
        except (OSError, json.JSONDecodeError) as exc:
            row.update(status="failed", error=str(exc))
        results.append(row)
        if progress:
            progress(i + 1, len(cells))
    ranked = rank_results(results, objective=objective)
    frontier = pareto_frontier(results)
    energy_rows = [r for r in results if r.get("tokens_per_joule") is not None]
    return {
        "schema_version": "turbo.tuning.v1",
        "objective": objective,
        "cells_planned": len(cells),
        "cells_run": sum(1 for r in results if r.get("status") == "completed"),
        "results": results,
        "ranking": ranked,
        "pareto_frontier": frontier,
        "recommended": ranked[0] if ranked else None,
        "energy_comparability": _energy_comparable(energy_rows),
        "caveats": [
            "batch/ubatch: planned capability, current official bench lacks flags; not measured",
            "provisional rankings need paired confirm runs before headline claims",
            "tokens/J compares only same workload + same model quantization over the full trial interval",
        ],
    }


def export_recommended(record: dict, path: str) -> dict:
    """Recommended config JSON: full model identity and scope."""
    rec = record.get("recommended")
    if not rec:
        raise TuningError("no successful cell to recommend")
    config = {
        "schema_version": "turbo.recommended.v1",
        "model": {
            "variant_id": rec["variant_id"], "plugin": rec["plugin"],
            "sha256": rec.get("model_sha256"),
        },
        "tuning": {
            "device": rec["device"], "threads": rec["threads"],
            "context": rec["context"],
        },
        "scope": {
            "objective": record["objective"],
            "gen_tokens": rec.get("gen_tokens"),
            "provisional": rec.get("provisional", True),
        },
    }
    Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config
