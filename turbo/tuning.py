"""Offline GenieX schema-4 tuner. Rankings are scoped, provisional screenings."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


class TuningError(ValueError):
    """Invalid request or unsupported benchmark capability."""


@dataclass(frozen=True)
class Variant:
    id: str
    path: str
    architecture: str
    quantization: str
    plugin: str
    kind: str
    tokenizer_path: str | None = None
    mmproj_path: str | None = None
    compiled_contexts: tuple[int, ...] | None = None
    requiredimage: bool = False

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


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
    energy_channel: str | None = None
    temperature: float = 0
    seed: int = 42

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass(frozen=True)
class Cell:
    variant_id: str
    device: str
    threads: int
    context: int
    kind: str
    plugin: str
    unsupported_reason: str | None = None


def _positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def _invalid_constant(value):
    raise TuningError(f"nonfinite native JSON: {value}")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _sha256(path, deadline=float("inf")):
    path = Path(path)
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    if not files:
        raise TuningError(f"empty artifact: {path}")
    digest = hashlib.sha256()
    for file in files:
        if path.is_dir():
            digest.update(str(file.relative_to(path)).encode() + b"\0")
        inner = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                if time.monotonic() >= deadline:
                    raise TimeoutError("total tuning budget exhausted while hashing")
                inner.update(block)
        digest.update(inner.digest())
    return digest.hexdigest() if path.is_dir() else inner.hexdigest()


def plan_cells(variants, space, max_cells=256):
    """Retain unsupported combinations; cap the Cartesian product before allocation."""
    if len({v.id for v in variants}) != len(variants):
        raise TuningError("duplicate variant ids")
    axes = (variants, space.devices, space.threads, space.contexts)
    if not all(axes) or math.prod(map(len, axes)) > max_cells:
        raise TuningError("empty search or max_cells exceeded")
    nums = (*space.threads, *space.contexts, space.prompt_tokens, space.gen_tokens,
            space.warmup, space.repeats, space.seed)
    if any(type(n) is not int or n < 0 for n in nums) or not all(
            n > 0 for n in (*space.contexts, space.prompt_tokens, space.gen_tokens, space.repeats)):
        raise TuningError("invalid numeric search axis")
    if not math.isfinite(space.temperature) or space.temperature < 0:
        raise TuningError("invalid temperature")
    cells = []
    for v, device, threads, context in itertools.product(*axes):
        reason = None
        if v.plugin not in ("llama_cpp", "qairt") or v.kind not in ("llm", "vlm"):
            reason = "unsupported plugin or model kind"
        elif space.batch is not None or space.ubatch is not None:
            reason = "batch/ubatch unsupported; planned SDK capability"
        elif device not in ("cpu", "gpu", "npu", "hybrid"):
            reason = "unsupported device; automatic coercion is not tuning"
        elif v.plugin == "qairt" and device != "npu":
            reason = "qairt requires npu; device coercion rejected"
        elif v.plugin == "qairt" and len(v.compiled_contexts or ()) != 1:
            reason = "qairt needs one compiled context per bundle; -c cannot select it"
        elif v.compiled_contexts is not None and str(context) not in map(str, v.compiled_contexts):
            reason = "unsupported compiled context"
        elif context < space.prompt_tokens + space.gen_tokens:
            reason = "context smaller than requested token budget"
        cells.append(Cell(v.id, device, threads, context, v.kind, v.plugin, reason))
    return cells


def build_command(bench_exe, variant, cell, space, image_path=None, prompt_file=None,
                  output_json=None, cell_id=None):
    """Verified options.c flags; local artifacts only, never model-manager ids."""
    matching = [c for c in plan_cells([variant], space) if c == cell]
    if not matching or cell.unsupported_reason:
        raise TuningError(cell.unsupported_reason or "cell does not match registered axes")
    vlm = variant.kind == "vlm"
    if (vlm or variant.requiredimage) and (not image_path or not prompt_file):
        raise TuningError("image workload requires image_path and prompt_file")
    if image_path and not vlm:
        raise TuningError("image workload requires kind=vlm")
    if vlm and variant.plugin == "llama_cpp" and not variant.mmproj_path:
        raise TuningError("llama_cpp VLM requires mmproj_path")
    if not vlm and variant.mmproj_path:
        raise TuningError("mmproj switches the native benchmark to VLM")
    if variant.plugin == "qairt" and (not Path(variant.path).is_dir() or not prompt_file):
        raise TuningError("qairt requires a local compiled bundle and prompt_file")
    paths = [bench_exe, variant.path, variant.tokenizer_path, variant.mmproj_path,
             image_path, prompt_file]
    for path in filter(None, paths):
        if not Path(path).exists():
            raise TuningError(f"missing local artifact: {path}")
    cmd = [str(Path(bench_exe).resolve()), "--plugin", variant.plugin, "--device", cell.device,
           "-m", str(Path(variant.path).resolve()), "-c", str(cell.context),
           "-p", str(space.prompt_tokens), "-n", str(space.gen_tokens), "-t", str(cell.threads),
           "-r", str(space.repeats), "--warmup", str(space.warmup),
           "--temperature", str(space.temperature), "--seed", str(space.seed)]
    if vlm:
        cmd += ["--vlm"]
    for flag, path in (("--tokenizer-path", variant.tokenizer_path),
                       ("--mmproj-path", variant.mmproj_path), ("--image", image_path),
                       ("--prompt-file", prompt_file), ("--output-json", output_json)):
        if path:
            cmd += [flag, str(Path(path).resolve())]
    if cell_id:
        cmd += ["--cell-id", str(cell_id)]
    return cmd


def _parse_result_json(data, gen_tokens, repeats=1):
    if not isinstance(data, dict) or str(data.get("schema_version")) != "4":
        raise TuningError("expected native benchmark schema_version=4")
    runs, agg = data.get("runs"), data.get("agg")
    if (not isinstance(runs, list) or not all(isinstance(r, dict) for r in runs)
            or not isinstance(agg, dict) or not isinstance(data.get("params"), dict)):
        raise TuningError("malformed native runs/agg")
    complete = sum(r.get("gen_tokens") == gen_tokens and r.get("stop_reason") == "length" for r in runs)
    metrics = {}
    for key in ("decode_tps", "prefill_tps", "ttft_ms"):
        entry = agg.get(key)
        value = entry.get("median") if isinstance(entry, dict) else None
        metrics[key] = value if _positive(value) else None
    times = [(r.get("prompt_time_us"), r.get("decode_time_us")) for r in runs]
    metrics["latency_s"] = (statistics.median((sum(pair) + r["media_us"]) / 1e6 for pair, r in zip(times, runs))
                           if times and all(_positive(x) for pair in times for x in pair)
                           and all(type(r.get("media_us")) in (int, float) and
                                   math.isfinite(r["media_us"]) and r["media_us"] >= 0 for r in runs) else None)
    values = [r.get("decode_tps") for r in runs]
    variability = (statistics.stdev(values) / statistics.mean(values)
                   if len(values) > 1 and all(map(_positive, values)) else None)
    return dict(metrics, runs=runs, complete_length_runs=complete, run_count=len(runs),
                full_length=len(runs) == complete == repeats, device_id=data.get("device_id"),
                reported_params=data.get("params"), variability_ratio=variability)


_GROUP_FIELDS = ("variant_id", "model_sha256", "architecture", "quantization", "plugin",
                 "kind", "artifact_sha256", "workload_id", "power_state", "power_scope",
                 "runtime_sha256")


def _group(row, energy=False):
    if any(row.get(k) is None for k in _GROUP_FIELDS):
        return None
    scope = {k: row[k] for k in _GROUP_FIELDS}
    if energy:
        scope.update(energy_scope=row.get("energy_scope"), energy_channel=row.get("energy_channel"))
    return _digest(scope)


def _eligible(row):
    n = row.get("repeats")
    return (row.get("status") == "completed" and type(n) is int and n > 0
            and _positive(row.get("gen_tokens")) and _positive(row.get("prompt_tokens"))
            and row.get("full_length") is True and row.get("run_count") == n
            and row.get("complete_length_runs") == n and _group(row) is not None)


def _efficiency(row):
    if (row.get("energy_valid") is True and row.get("energy_scope") == "full_process_trial"
            and row.get("energy_channel") and row.get("warmup") == 0
            and row.get("power_state") in ("ac", "battery")
            and _positive(row.get("energy_j")) and _positive(row.get("energy_duration_s"))):
        return row["repeats"] * row["gen_tokens"] / row["energy_j"]
    return None


def rank_results(results, objective="decode", constraints=None, variability_penalty=0.0):
    """Flat list of separate groups; rank restarts at 1 in each group."""
    if objective not in ("decode", "prefill", "balanced", "fast", "efficient"):
        raise TuningError("unknown objective")
    if not 0 <= variability_penalty <= 1:
        raise TuningError("variability_penalty must be in [0,1]")
    rules = (constraints or {}).get("rules", [])
    if any(op not in ("min", "max") or not _positive(bound) for _, op, bound in rules):
        raise TuningError("invalid constraint rule")
    groups = {}
    for row in results:
        if not _eligible(row):
            continue
        d, p = row.get("decode_tps"), row.get("prefill_tps")
        score = _efficiency(row) if objective == "efficient" else p if objective == "prefill" else d
        if objective == "balanced":
            score = 1 / row["latency_s"] if _positive(row.get("latency_s")) else None
        if not _positive(score) or any(not _positive(row.get(f)) or
                (row[f] < b if op == "min" else row[f] > b) for f, op, b in rules):
            continue
        vr = row.get("variability_ratio")
        if variability_penalty and (type(vr) not in (int, float) or not math.isfinite(vr) or vr < 0):
            continue
        if variability_penalty:
            score /= 1 + variability_penalty * vr
        gid = _group(row, objective == "efficient")
        groups.setdefault(gid, []).append(dict(row, score=score, objective=objective,
            tokens_per_joule=_efficiency(row), group_id=gid, provisional=True, requires_paired_confirmation=True))
    return [dict(row, rank=i + 1) for rows in groups.values()
            for i, row in enumerate(sorted(rows, key=lambda r: -r["score"]))]


def pareto_frontier(results, axes=("decode_tps", "prefill_tps")):
    if not axes:
        raise TuningError("empty Pareto axes")
    rows = [dict(r, tokens_per_joule=_efficiency(r)) for r in results if _eligible(r)]
    rows = [r for r in rows if all(_positive(r.get(a)) for a in axes)]
    return [r for r in rows if not any(_group(o, "tokens_per_joule" in axes) ==
        _group(r, "tokens_per_joule" in axes) and all(o[a] >= r[a] for a in axes)
        and any(o[a] > r[a] for a in axes) for o in rows)]


def _measured_trial(cmd, cwd, stream, timeout, warmup):
    from .telemetry import EnergyMeter, ProcessMemory, energy_delta, power_state as read_power
    meter = EnergyMeter()
    power_before = read_power()
    before = meter.sample()
    proc = memory = peak = None
    expired = False
    try:
        start = time.monotonic()
        proc = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, cwd=cwd)
        memory = ProcessMemory(proc.pid)
        while proc.poll() is None:
            sample = memory.sample()
            if sample and (peak is None or sample['peak_working_set_mb'] > peak['peak_working_set_mb']):
                peak = sample
            if time.monotonic() - start >= timeout:
                expired = True
                proc.kill()
                proc.wait()
                break
            time.sleep(0.05)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        after = meter.sample()
        meter.close()
        if memory:
            memory.close()
    power_after = read_power()
    energy = energy_delta(before, after, None)
    channel = energy['channels'].get('SYS', {})
    power = power_before.get('ac_line_status', 'unavailable')
    if power != power_after.get('ac_line_status'):
        power = 'changed'
    return proc.returncode, dict(
        **(peak or {}), power_state_start=power_before, power_state_end=power_after,
        power_state=power, power_scope='measured', energy=energy,
        energy_before=before, energy_after=after,
        energy_j=channel.get('energy_j'), energy_duration_s=after['monotonic_s']-before['monotonic_s'],
        energy_scope='full_process_trial', energy_channel='SYS',
        energy_valid=bool(channel) and warmup == 0 and not expired,
        energy_reason='full process interval including load, prefill and decode; warmup excluded from efficiency eligibility',
        timed_out=expired)


def run_tuning(bench_exe, variants, space, output_dir, objective="decode", image_path=None,
               prompt_file=None, timeout_s=240, progress=None, *, budget_s=600,
               constraints=None, power_state="unavailable", variability_penalty=0.0):
    """Serial subprocesses, new directory only, incremental evidence, two time bounds."""
    if not _positive(timeout_s) or not _positive(budget_s):
        raise TuningError("positive finite timeout_s and budget_s required")
    rank_results([], objective, constraints, variability_penalty)
    cells = plan_cells(variants, space)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    deadline, cache = time.monotonic() + budget_s, {}
    record = dict(schema_version="turbo.tuning.v2", objective=objective, constraints=constraints,
                  variability_penalty=variability_penalty, results=[], cells_planned=len(cells))
    def save():
        temp = out / "record.tmp"
        temp.write_text(json.dumps(record, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(out / "record.json")
    def fingerprint(path):
        path = str(Path(path).resolve())
        if path not in cache:
            cache[path] = _sha256(path, deadline)
        return cache[path]
    save()
    for i, cell in enumerate(cells):
        variant = next(v for v in variants if v.id == cell.variant_id)
        trial = out / f"trial-{i:04d}"
        trial.mkdir(exist_ok=False)
        target, log = trial / "result.json", trial / "bench.log"
        log.touch()
        model = asdict(variant)
        for key in ("path", "tokenizer_path", "mmproj_path"):
            if model[key]:
                model[key] = str(Path(model[key]).resolve())
        row = dict(asdict(cell), repeats=space.repeats, gen_tokens=space.gen_tokens,
            prompt_tokens=space.prompt_tokens, warmup=space.warmup, model=model,
            architecture=variant.architecture, quantization=variant.quantization,
            power_state=power_state, power_scope=str(out) if power_state == "unavailable" else "declared",
            result_path=str(target), log_path=str(log), status="pending", tokens_per_joule=None,
            energy_valid=False, energy_reason="unavailable: runner does not capture energy")
        record["results"].append(row)
        try:
            if cell.unsupported_reason:
                row.update(status="unsupported", error=cell.unsupported_reason)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("total tuning budget exhausted")
            cmd = build_command(bench_exe, variant, cell, space, image_path, prompt_file, target, trial.name)
            artifacts = {key: fingerprint(path) for key, path in
                (("model", variant.path), ("tokenizer", variant.tokenizer_path), ("mmproj", variant.mmproj_path)) if path}
            workload = dict(asdict(space), image_path=str(Path(image_path).resolve()) if image_path else None,
                            prompt_file=str(Path(prompt_file).resolve()) if prompt_file else None,
                            image_sha256=fingerprint(image_path) if image_path else None,
                            prompt_sha256=fingerprint(prompt_file) if prompt_file else None)
            for key in ("devices", "threads", "contexts", "batch", "ubatch", "energy_channel"):
                workload.pop(key)
            row.update(command=cmd, artifact_sha256=artifacts, model_sha256=artifacts["model"],
                runtime_sha256=fingerprint(bench_exe), workload=workload, workload_id=_digest(workload), status="running")
            row["group_id"] = _group(row)
            save()
            remaining = min(timeout_s, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("total tuning budget exhausted")
            with log.open("w", encoding="utf-8") as stream:
                exit_code, telemetry = _measured_trial(cmd, Path(bench_exe).resolve().parent, stream, remaining, space.warmup)
            row.update(telemetry, exit_code=exit_code)
            row['group_id'] = _group(row)
            if row['timed_out']:
                raise TimeoutError('native benchmark exceeded cell deadline')
            data = json.loads(target.read_text(encoding="utf-8-sig"), parse_constant=_invalid_constant)
            row.update(_parse_result_json(data, space.gen_tokens, space.repeats))
            params = data.get("params") or {}
            expected = dict(repetitions=space.repeats, n_gen=space.gen_tokens, warmup=space.warmup,
                temperature=space.temperature, seed=space.seed, n_threads=cell.threads,
                n_ctx=0 if variant.plugin == "qairt" else cell.context, n_prompt=space.prompt_tokens)
            if data.get("plugin") != variant.plugin or data.get("device") != cell.device or any(
                    params.get(k) != value for k, value in expected.items()):
                raise TuningError("native report does not match requested cell")
            model, reported = Path(variant.path).resolve(), Path(data.get("model_path", "")).resolve()
            if (reported != model and (not model.is_dir() or model not in reported.parents)
                    or data.get("cell_id") != trial.name):
                raise TuningError("native report has mismatched model path or trial id")
            row["status"] = "failed" if exit_code else "completed" if row["full_length"] else "partial"
            row['tokens_per_joule'] = _efficiency(row) if row['full_length'] else None
            data['telemetry'] = {k: row.get(k) for k in ('peak_working_set_mb', 'energy_j', 'energy_channel', 'energy_scope', 'tokens_per_joule', 'energy')}
            target.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
        except (subprocess.TimeoutExpired, TimeoutError) as exc:
            row.update(status="timeout", error=str(exc))
        except (OSError, ValueError, TypeError) as exc:
            row.update(status="failed", error=str(exc))
        finally:
            save()
            if progress:
                progress(i + 1, len(cells))
    ranked = rank_results(record["results"], objective, constraints, variability_penalty)
    recommendations = {r["group_id"]: r for r in ranked if r["rank"] == 1}
    record.update(ranking=ranked, pareto_frontier=pareto_frontier(record["results"]),
        recommendations=recommendations, recommended=next(iter(recommendations.values()))
        if len(recommendations) == 1 and len({_group(r) for r in record["results"]}) == 1 else None,
        cells_run=sum("exit_code" in r for r in record["results"]), output_dir=str(out))
    try:
        record["recommendation"] = recommendation_record(record)
        recpath = out / "recommended.json"
        recpath.write_text(json.dumps(record["recommendation"], indent=2, allow_nan=False), encoding="utf-8")
        record["recommendation_path"] = str(recpath)
    except TuningError as exc:
        record.update(recommendation=None, recommendation_path=None, recommendation_error=str(exc))
    save()
    return record


def recommendation_record(record, group_id=None):
    """Parent Engine.modes/apply contract; explicit group selection, no static profiles."""
    groups = {_group(r) for r in record["results"]}
    if group_id is None:
        if len(groups) != 1 or None in groups:
            raise TuningError("select one model/workload/power group for service modes")
        group_id = next(iter(groups))
    rows = [r for r in record["results"] if _group(r) == group_id and _eligible(r)]
    if not rows:
        raise TuningError("no eligible measurements for service modes")
    first = rows[0]
    model = first["model"]
    if (first["plugin"] != "llama_cpp" or first["kind"] != "llm"
            or model.get("tokenizer_path") or model.get("mmproj_path")):
        raise TuningError("current parent apply supports llama_cpp LLM without artifact overrides only")
    modes, unavailable = {}, {}
    for mode in ("fast", "efficient", "balanced"):
        ranked = rank_results(rows, mode, record.get("constraints"), record.get("variability_penalty", 0))
        if not ranked or len({r["group_id"] for r in ranked}) != 1:
            unavailable[mode] = "missing eligible metrics or incomparable energy channels"
            continue
        r = ranked[0]
        metrics = {k: r.get(k) for k in ("decode_tps", "prefill_tps", "latency_s", "tokens_per_joule")}
        metrics.update(median_decode_tps=r["decode_tps"], median_ttft_ms=r["ttft_ms"],
                       median_peak_mib=r.get("peak_working_set_mb"))
        modes[mode] = dict(device=r["device"], threads=r["threads"], context=r["context"],
            metrics=metrics, evidence=r["result_path"], command=r["command"],
            provisional=True, requires_paired_confirmation=True)
    if not modes:
        raise TuningError("no eligible modes under the requested constraints")
    return dict(schema_version="turbo.recommended.v2", model_id=first["variant_id"],
        model_sha256=first["model_sha256"], model=model, plugin=first["plugin"],
        artifact_sha256=first["artifact_sha256"], runtime_sha256=first["runtime_sha256"],
        scope=dict(group_id=group_id, workload=first["workload"], power_state=first["power_state"],
            power_scope=first["power_scope"], quality_calibrated=False, cold_kv=True,
            evidence=str(Path(record["output_dir"]) / "record.json"),
            provisional=True, requires_paired_confirmation=True),
        modes=modes, unavailable_modes=unavailable)


def export_recommended(record, path, group_id=None):
    rec = record.get("recommendations", {}).get(group_id) if group_id else record.get("recommended")
    if not rec or not _eligible(rec):
        raise TuningError("no eligible recommendation; select a group for multiple models/workloads")
    config = dict(schema_version="turbo.recommended.v2", model=rec["model"],
        model_sha256=rec["model_sha256"], artifact_sha256=rec["artifact_sha256"],
        plugin=rec["plugin"], device=rec["device"], threads=rec["threads"], context=rec["context"],
        scope={k: rec[k] for k in ("group_id", "workload", "power_state", "power_scope", "runtime_sha256", "objective")},
        provisional=True, requires_paired_confirmation=True)
    Path(path).write_text(json.dumps(config, indent=2, allow_nan=False), encoding="utf-8")
    return config
