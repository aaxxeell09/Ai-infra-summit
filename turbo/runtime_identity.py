"""Fingerprint the packaged benchmark and native SDK, including nested HTP libs.

This describes files on disk, not a driver/OS attestation. Services retain the
identity captured before loading the SDK and require restart after disk drift.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import threading
import time

_cache = {}
_lock = threading.Lock()


def sdk_root(exe):
    parent = Path(exe).resolve().parent
    return parent.parent if parent.name.lower() == "bin" else parent


def _native(path):
    name = path.name.lower()
    return name.endswith((".dll", ".so", ".dylib")) or ".so." in name


def _entries(exe, root):
    if not exe.is_file() or not root.is_dir():
        raise ValueError("Missing benchmark executable or SDK directory")
    if not any((d / name).is_file() for d in (root / "lib", root)
               for name in ("geniex.dll", "libgeniex.so", "libgeniex.dylib")):
        raise ValueError("Missing packaged GenieX bridge")
    entries = {"benchmark/" + exe.name: exe}
    def fail(error):
        raise error
    # Traverse with an explicit error callback; unreadable subtrees must never
    # silently disappear from an otherwise valid identity.
    for directory, dirs, files in os.walk(root, onerror=fail, followlinks=False):
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise ValueError("SDK directory symlinks require an explicit manifest")
        for name in files:
            path = Path(directory) / name
            if _native(path):
                if not path.resolve().is_relative_to(root):
                    raise ValueError("Native library escapes SDK directory")
                entries["sdk/" + path.relative_to(root).as_posix()] = path
    return dict(sorted(entries.items()))


def _signature(entries):
    return tuple((key, str(path.resolve()), path.stat().st_size,
                  path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                 for key, path in entries.items())


def runtime_identity(exe, sdk_dir=None, *, deadline=float("inf"), use_cache=False):
    if not exe:
        raise ValueError("Missing benchmark executable")
    exe = Path(exe).resolve()
    root = Path(sdk_dir).resolve() if sdk_dir else sdk_root(exe)
    # The installed plugin supports an external runtime override. A packaged
    # SDK hash cannot bind that override, so require a separately measured run.
    if os.environ.get("GENIEX_QAIRT_LIB"):
        raise ValueError("External QAIRT library override is not bound by this SDK manifest")
    entries = _entries(exe, root)
    signature = _signature(entries)
    key = (str(exe), str(root), signature)
    if use_cache:
        with _lock:
            if key in _cache:
                return copy.deepcopy(_cache[key])
    files = {}
    for name, path in entries.items():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Runtime fingerprint exceeded tuning budget")
                digest.update(block)
        files[name] = digest.hexdigest()
    if signature != _signature(_entries(exe, root)):
        raise ValueError("Native SDK changed while being fingerprinted")
    digest = hashlib.sha256()
    for name, value in files.items():
        digest.update(name.encode() + b"\0" + bytes.fromhex(value))
    result = dict(schema_version="turbo.runtime.v1", sha256=digest.hexdigest(),
                  files=files, scope="benchmark executable and SDK native libraries; excludes OS/driver")
    if use_cache:
        with _lock:
            # Keep one version per SDK instead of accumulating stale snapshots.
            for old in list(_cache):
                if old[:2] == key[:2]:
                    del _cache[old]
            _cache[key] = copy.deepcopy(result)
    return result


def binding_matches(expected, actual):
    return (isinstance(expected, dict) and isinstance(actual, dict)
            and expected.get("schema_version") == "turbo.runtime.v1"
            and bool(expected.get("files")) and expected == actual)
