"""Offline porting preflight for GenieX model artifacts.

Classifies a user-supplied manifest and optional model path as ready,
needs-conversion, needs-compile, unsupported or unknown, citing evidence ids
from EVIDENCE. No network access, no execution, and no embedded architecture
support map: runtime support for a GGUF architecture is only claimed when the
caller supplies capability evidence from a local measurement. Suggested
commands are returned as data strings and never run here.

See docs/kernel-and-porting.md for the sources behind each evidence id.
"""
from __future__ import annotations

from pathlib import Path

READY, NEEDS_CONVERSION, NEEDS_COMPILE = "ready", "needs-conversion", "needs-compile"
UNSUPPORTED, UNKNOWN = "unsupported", "unknown"

HTP_SESSION_BYTES = 3_500_000_000  # ~3.5 GB per Hexagon session (developer.md)

EVIDENCE = {
    "geniex-runtimes": "llama_cpp runs GGUF (CPU, Adreno OpenCL, Hexagon HTP); "
    "qairt runs compiled QAIRT shards NPU-only; runtimes are not interchangeable.",
    "qairt-bundle": "A QAIRT bundle needs geniex.json plus compiled shards; the "
    "compiled context is chipset-bound at generation time.",
    "htp-quant": "HTP prefers Q4_0/Q8_0 (Q4_K_M tensors fall back to CPU); "
    "ggml-hexagon repacks Q4_0, Q8_0 and MXFP4 into non-host buffers at load.",
    "htp-session-limit": "One Hexagon session maps ~3.5 GB; larger models need a "
    "multi-device layer split.",
    "mlx-platform": "MLX provides Apple Metal and Linux CUDA/CPU builds; no verified Snapdragon Windows "
    "ARM64 backend exists.",
    "spec-llamacpp-only": "Speculative decoding is a llama_cpp-plugin feature, "
    "ignored by qairt; draft-* types need a draft GGUF, ngram-* self-speculate.",
}


class GGUFError(ValueError):
    """Raised when a GGUF header or metadata section is malformed."""


_SCALARS = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def read_gguf_arch(path: Path) -> str | None:
    """Return general.architecture from GGUF metadata, or None if absent."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        if fh.read(4) != b"GGUF":
            raise GGUFError("bad magic")
        version = _uint(fh, 4)
        if version not in (2, 3):
            raise GGUFError(f"unsupported GGUF version {version}")
        _uint(fh, 8)  # tensor count (unused for metadata scan)
        for _ in range(_uint(fh, 8)):
            key = _string(fh)
            vtype = _uint(fh, 4)
            if vtype == 8 and key.decode("utf-8", "replace") == "general.architecture":
                return _string(fh).decode("utf-8", "replace")
            _skip_value(fh, vtype)
            if fh.tell() > size:
                raise GGUFError("metadata exceeds file size")
    return None


def _uint(fh, n: int) -> int:
    data = fh.read(n)
    if len(data) != n:
        raise GGUFError("truncated integer")
    return int.from_bytes(data, "little")


def _string(fh) -> bytes:
    length = _uint(fh, 8)
    data = fh.read(length)
    if len(data) != length:
        raise GGUFError("truncated string")
    return data


def _skip_value(fh, vtype: int) -> None:
    if vtype == 8:
        _string(fh)
    elif vtype == 9:  # array: element type, count, elements
        etype, count = _uint(fh, 4), _uint(fh, 8)
        for _ in range(count):
            _skip_value(fh, etype)
    elif vtype not in _SCALARS:
        raise GGUFError(f"unknown metadata type {vtype}")
    else:
        fh.read(_SCALARS[vtype])


def preflight(manifest: dict, model_path: str | None = None,
              capabilities: dict | None = None) -> dict:
    """Classify one local artifact. See module docstring for the contract."""
    caps = capabilities or {}
    fmt = str(manifest.get("format", "")).strip().lower()
    notes: list[str] = []
    if manifest.get("speculation") and fmt in ("qairt", "qai-hub", "genie-bundle"):
        notes.append("speculation requested but ignored: qairt plugin does not "
                     "support it")
    if fmt in ("mlx", "mlx-lm"):
        return _result(UNSUPPORTED, "MLX has Apple Metal and Linux CUDA/CPU backends; we have verified "
                       "no supported Snapdragon Windows ARM64 backend", ["mlx-platform"], notes)
    if fmt in ("huggingface", "hf", "safetensors"):
        return _result(NEEDS_CONVERSION,
                       "HF weights are not a GenieX runtime input; convert to "
                       "GGUF (llama.cpp) or compile via AI Hub for QAIRT. GGUF "
                       "conversion does not by itself verify runtime arch support",
                       ["geniex-runtimes"],
                       notes, ["python convert_hf_to_gguf.py <model-dir> --outfile model.gguf",
                        "# then re-run preflight with format=gguf"])
    if fmt in ("qairt", "qai-hub", "genie-bundle"):
        return _preflight_qairt(manifest, model_path, notes)
    if fmt == "gguf" or (model_path and model_path.endswith(".gguf")):
        return _preflight_gguf(manifest, model_path, caps, notes)
    notes.append(f"unrecognized manifest format {fmt!r}")
    return _result(UNKNOWN, "cannot classify without a recognized format "
                   "(gguf, huggingface, qairt, mlx)", [], notes)


def _preflight_qairt(manifest, model_path, notes):
    bundle = manifest.get("bundle") or model_path
    if not bundle:
        return _result(NEEDS_COMPILE, "QAIRT bundle path not supplied",
                       ["qairt-bundle"], notes)
    p = Path(bundle)
    if not p.is_dir():
        return _result(NEEDS_COMPILE, f"bundle directory missing: {p}",
                       ["qairt-bundle"], notes)
    if not (p / "geniex.json").is_file():
        return _result(NEEDS_COMPILE, "QAIRT bundle lacks geniex.json",
                       ["qairt-bundle"], notes,
                       ["# obtain a chipset-matched bundle from Qualcomm AI Hub"])
    shards = [f for f in p.iterdir() if f.suffix in (".bin", ".serialized")]
    if not shards:
        return _result(NEEDS_COMPILE, "QAIRT bundle has no compiled shard files",
                       ["qairt-bundle"], notes)
    want = manifest.get("chipset")
    if want:
        meta = (p / "geniex.json").read_text(errors="replace")
        if want.lower() not in meta.lower():
            return _result(NEEDS_COMPILE,
                           f"bundle context does not reference chipset {want}; "
                           "compiled context is chipset-bound", ["qairt-bundle"], notes)
    return _result(UNKNOWN, "QAIRT bundle shape found; compiled chipset/context compatibility still requires runtime evidence",
                   ["qairt-bundle"], notes)


def _preflight_gguf(manifest, model_path, caps, notes):
    path = model_path or manifest.get("model")
    if not path:
        return _result(UNKNOWN, "no GGUF path supplied", [], notes)
    p = Path(path)
    try:
        arch = read_gguf_arch(p)
    except (GGUFError, OSError, OverflowError) as err:
        notes.append(f"gguf parse failed: {err}")
        return _result(UNKNOWN, f"GGUF file unreadable or malformed: {p}", [], notes)
    declared = manifest.get("architecture")
    if declared and arch is not None and declared != arch:
        return _result(UNKNOWN,
                       f"artifact mismatch: manifest declares architecture "
                       f"{declared!r} but GGUF metadata says {arch!r}", [], notes)
    if arch is None:
        notes.append("GGUF metadata lacks general.architecture")
        return _result(UNKNOWN, "no architecture recorded in GGUF metadata", [], notes)
    if p.stat().st_size > HTP_SESSION_BYTES:
        notes.append("model exceeds one ~3.5 GB Hexagon session; needs multi-device "
                     "layer split (e.g. --device HTP0,HTP1,HTP2,HTP3)")
    if str(manifest.get("quantization", "")).lower() in ("q4_k_m", "q5_k_m", "q6_k"):
        notes.append("quantization has HTP CPU-fallback tensors; Q4_0/Q8_0 give a "
                     "clean NPU run")
    if arch in caps:
        return _result(READY, f"architecture {arch!r} has supplied capability "
                       f"evidence: {caps[arch]}", [], notes)
    notes.append("this module embeds no architecture support map; supply a "
                 "capabilities mapping measured on the target runtime")
    return _result(UNKNOWN, f"no capability evidence for architecture {arch!r}",
                   [], notes)


def _result(status, reason, evidence_ids, notes, commands=None):
    return {"status": status, "reason": reason, "evidence": evidence_ids,
            "evidence_claims": {e: EVIDENCE[e] for e in evidence_ids},
            "notes": notes, "suggested_commands": commands or []}
