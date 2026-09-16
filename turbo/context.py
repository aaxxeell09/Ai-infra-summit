"""Auditable, local context reduction with exact raw-data recovery.

Only explicit tool outputs are reduced. System instructions, schemas and user
messages are never passed to this module by the gateway. Character counts are
not token counts. Projection and previews are lossy and labeled as such.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class ContextStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, text: str) -> str:
        raw = text.encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()
        target = self.root / (key + ".txt")
        if not target.exists():
            target.write_bytes(raw)
        elif target.read_bytes() != raw:
            raise ValueError("context reference integrity mismatch")
        return key

    def get(self, key: str) -> str:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid context reference")
        raw = (self.root / (key + ".txt")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise ValueError("context reference integrity mismatch")
        return raw.decode("utf-8")

    def compact(self, text: str, *, fields: list[str] | None = None,
                preview_chars: int | None = None) -> dict:
        start = time.perf_counter()
        key = self.put(text)
        value, removed, mode = text, 0, "unchanged"
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            value = parsed
            mode = "json_minify"
            if fields is not None:
                allowed = set(fields)
                def project(row):
                    nonlocal removed
                    if not isinstance(row, dict):
                        return row
                    removed += len(set(row) - allowed)
                    return {k: v for k, v in row.items() if k in allowed}
                value = [project(row) for row in parsed] if isinstance(parsed, list) else project(parsed)
                mode = "field_projection"
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        truncated = preview_chars is not None and len(value) > preview_chars
        if truncated:
            if preview_chars < 1:
                raise ValueError("preview budget must be positive")
            value = value[:preview_chars]
            mode += "+preview"
        lossy = bool(removed or truncated)
        envelope = {"text": value, "raw_ref": key, "lossy": lossy}
        # A small output can become larger after adding recovery metadata.
        encoded = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
        use_compact = len(encoded) < len(text)
        output = encoded if use_compact else text
        return {"output": output, "raw_ref": key, "applied": use_compact,
                "lossy": lossy if use_compact else False, "mode": mode,
                "removed_fields": removed if use_compact else 0,
                "input_chars": len(text), "output_chars": len(output),
                "saved_chars": len(text) - len(output),
                "elapsed_s": time.perf_counter() - start}
