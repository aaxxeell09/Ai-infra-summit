"""Message-level context optimization on top of ContextStore.

Only policy-selected tool results are transformed. System, user and assistant
messages are never modified. Every applied reduction keeps a SHA-256 raw_ref
into the store for exact recovery. Lossy modes are labeled. All accounting is
in characters; tokens are never inferred.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

RECOVERY_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "context_recover",
        "description": (
            "Return the exact original text behind a compacted tool result. "
            "raw_ref comes from the result envelope."
        ),
        "parameters": {
            "type": "object",
            "properties": {"raw_ref": {"type": "string"}},
            "required": ["raw_ref"],
        },
    },
}

RTK_STYLE_LABEL = "context-pipeline/command-output"
PATH_KEYS = {"path", "file", "filepath", "name", "id"}
NEGATION_RE = re.compile(r"(^|_)(not|negat\w*|invert\w*|exclud\w*)($|_)")


@dataclass
class Policy:
    """Explicit opt-in configuration. Defaults change nothing."""

    tools: frozenset[str] = frozenset()
    call_map: dict[str, dict] = field(default_factory=dict)
    fields: dict[str, list[str]] = field(default_factory=dict)
    preview_opt_in: bool = False
    preview_chars: int | None = None
    rtk_label: bool = False
    compressor: Callable[[str, str], str] | None = None
    # Cost precheck only: inputs longer than a non-negative budget skip the
    # hook. There is NO timeout promise; the hook must return on its own.
    cost_budget_chars: int | None = None


def caveman_prose_instruction() -> str:
    """Opt-in instruction so the model compresses its own generated prose.

    Excludes JSON, code and exact-value fields. Never applied to user prompts.
    """
    return (
        "Compress only your own generated prose: short clauses, plain words, "
        "no filler. Keep all JSON, code, numbers, paths, ids and negations "
        "verbatim. Do not restate the user prompt."
    )


def stable_prefix_fingerprint(messages: list[dict]) -> str:
    """SHA-256 of history up to the first tool result, for KV-prefix reuse."""
    prefix = []
    for msg in messages:
        if msg.get("role") == "tool":
            break
        prefix.append(msg)
    blob = json.dumps(prefix, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _project_row(row: dict, allowed: set[str]) -> tuple[dict, int]:
    kept, removed = {}, 0
    for key, value in row.items():
        keep = (
            key in allowed
            or key in PATH_KEYS
            or bool(NEGATION_RE.search(key))
            or (isinstance(value, (int, float)) and not isinstance(value, bool))
        )
        if keep:
            kept[key] = value
        else:
            removed += 1
    return kept, removed


def project_search(text: str, fields: list[str]) -> tuple[str, int, bool]:
    """Deterministic JSON projection for list-of-object search shapes."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return text, 0, False
    if not (
        isinstance(parsed, list)
        and parsed
        and all(isinstance(row, dict) for row in parsed)
    ):
        return text, 0, False
    allowed = set(fields)
    rows, removed = [], 0
    for row in parsed:
        kept, n = _project_row(row, allowed)
        rows.append(kept)
        removed += n
    if not removed:
        return text, 0, False
    return (
        json.dumps(rows, separators=(",", ":"), ensure_ascii=False),
        removed,
        True,
    )


def _envelope(store, raw_ref: str, text: str, mode: str, lossy: bool) -> str:
    raw = {
        "text": text,
        "raw_ref": raw_ref,
        "lossy": lossy,
        "mode": mode,
        "recover": "context_recover",
    }
    return json.dumps(raw, separators=(",", ":"), ensure_ascii=False)


def _transform(content: str, name: str, cfg: dict, policy: Policy, store):
    start = time.perf_counter()
    applied = lossy = False
    mode = ""
    text = content
    raw_ref = store.put(content)  # exact original, always recoverable
    fields = cfg.get("fields") or policy.fields.get(name)
    if fields is not None:
        projected, removed, ok = project_search(content, fields)
        if ok:
            text = projected
            mode, lossy, applied = "field_projection", True, True
    hook = policy.compressor
    if hook is not None:
        budget = policy.cost_budget_chars
        if budget is None or (budget >= 0 and len(text) <= budget):
            try:
                text = hook(text, name)
                mode = mode + "+compressor" if mode else "compressor"
                lossy = applied = True
            except Exception:
                pass  # fallback: keep pre-hook text; record stays truthful
    elif policy.preview_opt_in and policy.preview_chars:
        text = text[: policy.preview_chars]
        mode = mode + "+preview" if mode else "preview"
        lossy = applied = True
    if policy.rtk_label and "exit_code" in cfg:
        label = "[" + RTK_STYLE_LABEL + " exit=" + str(cfg["exit_code"]) + "]"
        text = label + "\n" + text  # exit code and failure text preserved
        mode += "+rtk_label"
        lossy = applied = True
    record = {
        "tool": name,
        "mode": mode or "unchanged",
        "lossy": lossy,
        "saved_chars": 0,
        "applied": False,
        "elapsed_s": time.perf_counter() - start,
    }
    if not applied:
        return content, record
    out = _envelope(store, raw_ref, text, mode, lossy)
    saved = len(content) - len(out)
    if saved <= 0:
        # Small data: envelope would not pay off; report no change.
        record["mode"] = "unchanged"
        record["lossy"] = False
        return content, record
    record.update(
        raw_ref=raw_ref,
        saved_chars=saved,
        applied=True,
        elapsed_s=time.perf_counter() - start,
    )
    return out, record


def optimize_messages(messages: list[dict], store, policy: Policy) -> dict:
    """Return a new message list plus per-result records; inputs are not mutated.

    Non-tool messages keep their original object references. Tool messages not
    selected by policy keep their content byte-for-byte. Recovery schema and
    executor are opt-in helpers; nothing is appended to caller arrays.
    """
    call_names = {}
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            if call.get("id") and fn.get("name"):
                call_names[call["id"]] = fn["name"]
    out, records = [], []
    for msg in messages:
        if msg.get("role") != "tool":
            out.append(msg)
            continue
        cid = msg.get("tool_call_id")
        name = call_names.get(cid, msg.get("name") or "")
        if (name not in policy.tools and cid not in policy.call_map) or not isinstance(
            msg.get("content"), str
        ):
            out.append(msg)
            continue
        new_content, record = _transform(
            msg["content"], name, policy.call_map.get(cid, {}), policy, store
        )
        record["tool_call_id"] = cid
        records.append(record)
        out.append({**msg, "content": new_content} if record["applied"] else msg)
    return {
        "messages": out,
        "records": records,
        "prefix_fingerprint": stable_prefix_fingerprint(out),
    }


def execute_recovery(store, call: dict) -> dict:
    """Opt-in executor for RECOVERY_TOOL_SCHEMA. Never auto-registered."""
    if call.get("name") != RECOVERY_TOOL_SCHEMA["function"]["name"]:
        return {"ok": False, "error": "unknown tool"}
    args = call.get("arguments", "{}")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return {"ok": False, "error": "invalid arguments"}
    try:
        return {"ok": True, "text": store.get(args["raw_ref"])}
    except (KeyError, ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


def break_even(input_tokens_saved, prefill_usd_per_mtok, overhead_usd, prefix_loss_usd) -> float:
    """Net USD saved. Rejects unmeasured or negative token counts.

    input_tokens_saved must come from a real tokenizer measurement; this
    helper never derives tokens from characters.
    """
    values = (input_tokens_saved, prefill_usd_per_mtok, overhead_usd, prefix_loss_usd)
    if any(v is None for v in values):
        raise ValueError("unmeasured input: pass tokenizer-measured tokens and costs")
    if any(v < 0 for v in values):
        raise ValueError("negative values are not meaningful here")
    return input_tokens_saved / 1e6 * prefill_usd_per_mtok - overhead_usd - prefix_loss_usd