"""Hardware-calibrated routing. Estimates are never presented as measurements."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class Profile:
    name: str
    model: str
    device: str
    threads: int
    decode_tps: float
    prefill_tps: float
    context: int = 4096
    load_s: float = 0
    quality_tier: int = 0
    evidence: str = ""


def choose(profiles: Iterable[Profile], *, prompt_tokens: int,
           output_tokens: int = 128, required_tier: int = 0,
           resident: set[str] | None = None,
           reusable_tokens: dict[str, int] | None = None,
           objective: str = "decode") -> dict:
    """Rank measured profiles, with quality/context eligibility as hard limits.

    Caller must supply tokenizer counts for token-accurate estimates. A caller
    using character estimates must disclose that separately. A tier is an
    application calibration label, not a universal model capability claim.
    """
    if objective not in {"decode", "latency"}:
        raise ValueError("objective must be decode or latency")
    if prompt_tokens < 0 or output_tokens < 1:
        raise ValueError("invalid token budget")
    resident, reusable_tokens = resident or set(), reusable_tokens or {}
    candidates, rejected = [], []
    for p in profiles:
        reason = None
        if p.quality_tier < required_tier:
            reason = "quality tier below requirement"
        elif p.context < prompt_tokens + output_tokens:
            reason = "context budget exceeded"
        elif p.decode_tps <= 0 or p.prefill_tps <= 0 or not p.evidence:
            reason = "missing measured profile"
        if reason:
            rejected.append({"name": p.name, "reason": reason})
            continue
        reuse = min(prompt_tokens, max(0, reusable_tokens.get(p.name, 0))) if p.name in resident else 0
        estimate = ((prompt_tokens - reuse) / p.prefill_tps + output_tokens / p.decode_tps
                    + (0 if p.name in resident else p.load_s))
        candidates.append({**asdict(p), "estimated_s": estimate, "reusable_tokens": reuse})
    if not candidates:
        raise ValueError("No measured profile meets the context and quality requirements")
    candidates.sort(key=(lambda p: (-p["decode_tps"], p["estimated_s"], p["name"]))
                    if objective == "decode" else (lambda p: (p["estimated_s"], p["name"])))
    return {"selected": candidates[0], "objective": objective, "candidates": candidates,
            "rejected": rejected, "estimate_only": True}
