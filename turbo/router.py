"""Bounded small-versus-large model router (pure planning/execution helper).

Profiles must carry measured prefill/decode/load rates, the model/runtime
identity with weights hash and a task-quality rate with evidence. Parameter
count or tier alone never implies quality: "larger=smart" is rejected unless a
profile is calibrated. Bootstrap/manual routing of an uncalibrated model is
permitted but always disclosed and never auto-selected without explicit
opt-in. Pure planning: no hardware access, no HTTP, no side effects.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable

OBJECTIVES = ("latency", "decode", "efficient")


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    runtime: str
    weights_hash: str
    prefill_tps: float
    decode_tps: float
    load_s: float
    context: int
    quality_rate: float | None = None
    quality_evidence: str = ""
    calibrated: bool = False
    larger: bool = False


@dataclass(frozen=True)
class Requirements:
    task_kind: str
    context_tokens: int
    output_tokens: int = 128
    quality_minimum: float | None = None
    objective: str = "latency"
    allow_uncalibrated: bool = False
    manual_model: str | None = None
    quality_band: float = 0.05


def _measurement_gap(p: ModelProfile) -> str | None:
    if not p.model or not p.runtime or not p.weights_hash:
        return "missing model/runtime/weights hash"
    if p.prefill_tps <= 0 or p.decode_tps <= 0 or p.load_s < 0:
        return "missing measured prefill/decode/load"
    return None


def plan_route(profiles: Iterable[ModelProfile], req: Requirements) -> dict:
    """Rank measured profiles for one request; returns a plan, never a call."""
    if req.objective not in OBJECTIVES:
        raise ValueError("objective must be latency, decode or efficient")
    if req.context_tokens < 0 or req.output_tokens < 1:
        raise ValueError("invalid context/token budget")
    if not 0 <= req.quality_band <= 1:
        raise ValueError("quality_band must be within 0..1")
    need = req.context_tokens + req.output_tokens
    candidates, rejected = [], []
    for p in profiles:
        reason = _measurement_gap(p)
        if not reason and p.context < need:
            reason = "context budget exceeded"
        if not reason and req.quality_minimum is not None:
            if p.quality_rate is None or not p.quality_evidence:
                reason = "task-quality rate/evidence unavailable"
            elif p.quality_rate < req.quality_minimum:
                reason = "measured quality below requirement"
        if not reason and not p.calibrated and not req.allow_uncalibrated:
            reason = "uncalibrated; opt-in required"
        if reason:
            rejected.append({"name": p.name, "reason": reason})
        else:
            candidates.append(p)
    selected, trace = None, []
    if candidates:
        qrates = [p.quality_rate for p in candidates if p.quality_rate is not None]
        best_q = max(qrates) if qrates else None

        def est_s(p):
            return (req.context_tokens / p.prefill_tps
                    + req.output_tokens / p.decode_tps + p.load_s)

        def rank(p):
            similar = best_q is None or (p.quality_rate is not None
                                         and p.quality_rate >= best_q - req.quality_band)
            size = 0 if (similar and not p.larger) else (1 if similar else 2)
            speed = -p.decode_tps if req.objective == "decode" else est_s(p)
            return (size, speed, p.name)

        ordered = sorted(candidates, key=rank)
        selected = ordered[0]
        for p in ordered:
            size = rank(p)[0]
            why = ("fastest similar-quality small model" if size == 0 else
                   "similar-quality larger model held for fallback" if size == 1 else
                   "larger model held for fallback (quality band)")
            trace.append({"model": p.name, "why": why, "status": "planned",
                          "estimated_s": est_s(p), "estimate_only": True})
    if req.manual_model:
        trace.insert(0, {"model": req.manual_model, "why": "explicit manual/bootstrap route",
                         "status": "manual-uncalibrated", "estimated_s": None})
    return {"selected": selected, "candidates": [p.name for p in candidates],
            "rejected": rejected, "manual_model": req.manual_model,
            "_profiles": candidates,
            "requirements": req, "objective": req.objective, "trace": trace,
            "uncalibrated_disclosed": selected is None or not selected.calibrated,
            "status": "ok" if selected else "no_route"}


def run_with_fallback(plan: dict, invoke: Callable, validate: Callable,
                      attempts: int = 2) -> dict:
    """Execute a plan serially (concurrency 1), escalating only on invalid output.

    invoke(profile_or_None, requirements) performs exactly one inference call;
    validate(output, requirements) checks the structured final action using the
    request only, never a gold answer. Each attempt is timed on a wall clock;
    plan estimated_s values stay disclosed as predictions.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    req = plan["requirements"]
    by_name = {p.name: p for p in plan.get("_profiles", [])}
    ordered = ([("manual", plan["manual_model"])] if plan.get("manual_model") else [])
    ordered += [("candidate", name) for name in plan.get("candidates", [])]
    planned = {t["model"]: t for t in plan.get("trace", [])}
    trace, result, total, n = [], None, 0.0, 0
    for kind, name in ordered[:attempts]:
        n += 1
        info = planned.get(name, {})
        if kind == "manual":
            info = {"why": "explicit manual/bootstrap route", "status": "manual-uncalibrated"}
        start = time.perf_counter()
        output = invoke(by_name.get(name) if kind == "candidate" else None, req)
        elapsed = time.perf_counter() - start
        total += elapsed
        ok, note = validate(output, req)
        trace.append({"model": name, "why": info.get("why", "candidate"),
                      "status": info.get("status", "executed"),
                      "validation": "valid" if ok else "invalid",
                      "note": note, "elapsed_s": elapsed})
        if ok:
            result = output
            break
    return {"status": "ok" if result is not None else "failed",
            "result": result, "attempts": n, "total_s": total, "trace": trace,
            "predicted_order": [t["model"] for t in plan.get("trace", [])],
            "disclosure": "elapsed_s measured per attempt; plan estimated_s are predictions"}
