"""Model coverage catalog: stdlib-only loader, validation and offline filtering.

The catalog is a planning artifact. Loading and filtering never starts an
inference call, downloads a model or touches the device. Backend support is
"unverified" until the named runtime version is measured on the target laptop;
NPU support additionally requires dispatch diagnostics, so filtering never
selects an NPU-only entry on its own.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REQUIRED_KEYS = {"id", "kind", "architecture", "license", "total_bytes",
                 "requires_projector", "state", "source", "backend_support"}
VALID_KINDS = {"instruction", "base", "multimodal"}
VALID_STATES = {"downloaded", "downloading", "candidate", "rejected"}
DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "configs" / "model-catalog.json"


def load_catalog(path: str | Path = DEFAULT_CATALOG) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    validate(catalog)
    return catalog


def validate(catalog: dict) -> None:
    if not isinstance(catalog.get("models"), list) or not catalog["models"]:
        raise ValueError("catalog must contain a non-empty models list")
    if not 1 <= len(catalog["models"]) <= 8:
        raise ValueError("catalog must hold 1..8 entries")
    ids = set()
    for entry in catalog["models"]:
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            raise ValueError(f"{entry.get('id', '?')}: missing keys {sorted(missing)}")
        if entry["id"] in ids:
            raise ValueError(f"duplicate id {entry['id']}")
        ids.add(entry["id"])
        if entry["kind"] not in VALID_KINDS:
            raise ValueError(f"{entry['id']}: kind must be one of {sorted(VALID_KINDS)}")
        if entry["state"] not in VALID_STATES:
            raise ValueError(f"{entry['id']}: state must be one of {sorted(VALID_STATES)}")
        if not isinstance(entry["total_bytes"], int) or entry["total_bytes"] <= 0:
            raise ValueError(f"{entry['id']}: total_bytes must be a positive integer")
        files = entry["source"].get("files") or []
        if not files:
            raise ValueError(f"{entry['id']}: source.files must list the pinned artifact(s)")
        if entry["requires_projector"] and len(files) < 2 and not entry["id"].endswith("-qairt"):
            raise ValueError(f"{entry['id']}: multimodal GGUF needs model+projector files")
        declared = sum(f["bytes"] for f in files if isinstance(f.get("bytes"), int))
        if declared and declared != entry["total_bytes"]:
            raise ValueError(f"{entry['id']}: total_bytes != sum of file sizes")
        for runtime, status in entry["backend_support"].items():
            if status not in {"unverified", "supported", "unsupported"}:
                raise ValueError(f"{entry['id']}: bad backend status {status!r} for {runtime}")


def filter_models(catalog: dict, state: str | None = None, kind: str | None = None,
                  backend: str | None = None) -> list[dict]:
    """Return catalog entries matching state/kind and an optional backend key.

    Offline planning only: a listed backend means planned-for-device, never
    measured. "supported" is rejected at validation time until a runtime is
    measured on the target laptop, so filtering can never certify hardware.
    """
    out = []
    for entry in catalog["models"]:
        if state and entry["state"] != state:
            continue
        if kind and entry["kind"] != kind:
            continue
        if backend and backend not in entry["backend_support"]:
            continue
        if backend and entry["backend_support"].get(backend) == "unsupported":
            continue
        out.append(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List catalog models (offline; no network, no inference).")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--state", choices=sorted(VALID_STATES))
    parser.add_argument("--kind", choices=sorted(VALID_KINDS))
    parser.add_argument("--backend", help="runtime key such as geniex-llama_cpp@0.6.1")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    rows = filter_models(load_catalog(args.catalog), state=args.state,
                         kind=args.kind, backend=args.backend)
    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        for e in rows:
            projector = " +projector" if e["requires_projector"] else ""
            print(f"{e['id']:42s} {e['kind']:10s} {e['architecture']:14s} "
                  f"{e['total_bytes'] / 1e6:8.1f} MB {e['state']}{projector}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
