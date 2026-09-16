"""One-command bounded live demo for the t13 invoice fixture.

Spawns a real 'python -Xutf8 -m turbo.feedback_mcp' child (stdio,
newline-delimited JSON-RPC), drives initialize / tools/list / tools/call
against the public demo fixture t13 with the startup model allowlist entry
qwen4b=<config>, and prints one concise JSON summary. The inner diagnostic
runs the real local model; no fake inference is used here.

Independence: the single correct file move is re-checked from the raw
initial/final workspace snapshots in the report, not from the model's own
grade. The demo makes no quality claim: quality_qualified is always false
and public-fixture diagnostics are never frozen secretary-eval-v2 quality
PASS. No rescoring or repair is attempted; the physical outcome and the
exact-call grade are reported separately.

Exit codes: 0 only when transport completed without runtime failure; 1 on
preflight, transport, watchdog-timeout or runtime failure. A zero exit
never means quality passed.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_S = 240
MODEL_ID = "qwen4b"
TASK_ID = "t13"
PROTOCOL_VERSION = "2025-06-18"
TOOL_NAME = "local_feedback_diagnostic"
EXPECTED_SOURCE = "drafts/hexagon-invoice.md"
EXPECTED_DESTINATION = "invoices/2026/hexagon-invoice.md"
SOURCE = ("scripts/demo_invoice_mcp.py spawned a real 'python -Xutf8 -m "
          "turbo.feedback_mcp' subprocess over stdio newline-delimited "
          "JSON-RPC; the inner diagnostic ran scripts/run_secretary_feedback.py "
          "with the real local qwen4b model; no fake inference")
SCOPE = ("Public demo fixture diagnostic; not frozen secretary-eval-v2 "
         "quality PASS; no rescoring or repair; physical outcome and exact "
         "call grade are reported separately")
Popen = subprocess.Popen


def _preflight(config_path, output_path):
    """Validate config and clean Git source before any output is created."""
    errors = []
    commit = None
    if not config_path.is_file():
        errors.append("config not found: %s" % config_path)
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                errors.append("config must be a JSON object")
            else:
                for key in ("sdk_dir", "model_path"):
                    value = config.get(key)
                    if not isinstance(value, str) or not value:
                        errors.append("config missing string key: %s" % key)
        except ValueError as exc:
            errors.append("config is not valid JSON: %s" % exc)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append("git unavailable under %s: %s" % (ROOT, exc))
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(ROOT), text=True)
        if status.strip():
            errors.append("Git source must be clean before creating output; "
                          "commit or stash local changes")
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append("git status unavailable: %s" % exc)
    if output_path.exists():
        errors.append("output path already exists; refusing to overwrite: %s"
                      % output_path)
    return errors, commit


def _terminate_tree(proc):
    """Terminate only the process tree this script spawned."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait(timeout=5)


def _build_requests():
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                    "clientInfo": {"name": "demo-invoice-cli",
                                   "version": "0.1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": TOOL_NAME,
                    "arguments": {"task_id": TASK_ID,
                                  "model_id": MODEL_ID}}},
    ]


def _run_server(config_path, output_path, timeout_s):
    argv = [sys.executable, "-Xutf8", "-m", "turbo.feedback_mcp",
            "--enable-candidate",
            "--model", "%s=%s" % (MODEL_ID, config_path),
            "--output-root", str(output_path / "mcp-runs")]
    kwargs = {"cwd": str(ROOT), "stdin": subprocess.PIPE,
              "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if sys.platform == "win32":
        kwargs["creationflags"] = (subprocess.CREATE_NO_WINDOW |
                                   subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = Popen(argv, **kwargs)
    except OSError as exc:
        return {"timed_out": False, "spawn_error": str(exc),
                "returncode": None, "stdout": "", "stderr": ""}
    payload = "".join(
        json.dumps(request, ensure_ascii=False) + "\n"
        for request in _build_requests()).encode("utf-8")
    try:
        out, err = proc.communicate(input=payload, timeout=timeout_s)
        return {"timed_out": False, "returncode": proc.returncode,
                "stdout": out.decode("utf-8", errors="replace"),
                "stderr": err.decode("utf-8", errors="replace")}
    except subprocess.TimeoutExpired as exc:
        _terminate_tree(proc)
        out = exc.stdout if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        return {"timed_out": True, "returncode": None,
                "stdout": out, "stderr": err}


def _parse_replies(raw_stdout):
    frames, parse_errors = [], []
    for line in raw_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            frames.append(json.loads(line))
        except ValueError as exc:
            parse_errors.append("malformed reply line: %s" % exc)
    by_id = {}
    for frame in frames:
        if isinstance(frame, dict) and isinstance(frame.get("id"), int):
            by_id[frame["id"]] = frame
    return frames, by_id, parse_errors


def _check_move(initial, final):
    """Re-check the exact single move from raw workspace snapshots."""
    result = {"expected_source": EXPECTED_SOURCE,
              "expected_destination": EXPECTED_DESTINATION,
              "initial_snapshot": initial, "final_snapshot": final,
              "verified": False}
    if not isinstance(initial, dict) or not isinstance(final, dict):
        result["reason"] = "initial/final workspace snapshots missing from report"
        return result
    removed = {k: v for k, v in initial.items() if k not in final}
    added = {k: v for k, v in final.items() if k not in initial}
    modified = sorted(k for k in initial
                      if k in final and initial[k] != final[k])
    src_hash = initial.get(EXPECTED_SOURCE)
    dst_hash = final.get(EXPECTED_DESTINATION)
    result["removed"] = removed
    result["added"] = added
    result["modified"] = modified
    if (removed == {EXPECTED_SOURCE: src_hash}
            and added == {EXPECTED_DESTINATION: dst_hash}
            and not modified and src_hash is not None
            and src_hash == dst_hash):
        result["verified"] = True
        result["sha256"] = dst_hash
    else:
        result["reason"] = ("workspace change is not exactly "
                            + EXPECTED_SOURCE + " -> " + EXPECTED_DESTINATION
                            + " with identical bytes")
    return result


def _extract(sc):
    report = sc.get("report") if isinstance(sc.get("report"), dict) else {}
    loop = report.get("loop") if isinstance(report.get("loop"), dict) else {}
    identity = (sc.get("identity")
                if isinstance(sc.get("identity"), dict) else {})
    verification = sc.get("existing_demo_verification")
    timing = {
        "loop": {"elapsed_s": loop.get("elapsed_s"),
                 "timing_scope": loop.get("timing_scope")},
        "diagnostic": {"elapsed_s": identity.get("diagnostic_elapsed_s"),
                       "timing_scope": report.get("timing_scope")},
    }
    return verification, timing, loop, report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path,
                        help="Native model config path passed to the "
                             "startup allowlist entry qwen4b=<config>")
    parser.add_argument("--output", required=True, type=Path,
                        help="New (ignored local/) directory; never "
                             "overwritten")
    parser.add_argument("--enable-candidate", action="store_true",
                        help="Required; the demo refuses to run otherwise")
    args = parser.parse_args(argv)
    if not args.enable_candidate:
        parser.error("Explicit --enable-candidate required; default service "
                     "remains unchanged")
    return args


def main(argv=None):
    args = parse_args(argv)
    output_path = args.output.resolve()
    summary = {"schema": "demo_invoice_mcp.summary/1",
               "task_id": TASK_ID, "model_id": MODEL_ID,
               "source": SOURCE, "scope": SCOPE,
               "quality_qualified": False,
               "transport_completed": False,
               "existing_demo_verification": None,
               "ok": False}
    errors, commit = _preflight(args.config, output_path)
    summary["git_commit"] = commit
    if errors:
        summary["errors"] = errors
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1
    output_path.mkdir(parents=True, exist_ok=False)
    run = _run_server(args.config, output_path, TIMEOUT_S)
    (output_path / "mcp-stdout.txt").write_text(
        run["stdout"], encoding="utf-8")
    (output_path / "mcp-stderr.txt").write_text(
        run["stderr"], encoding="utf-8")
    frames, by_id, parse_errors = _parse_replies(run["stdout"])
    (output_path / "parsed-replies.json").write_text(
        json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")
    errors.extend(parse_errors)
    if run.get("spawn_error"):
        errors.append("failed to spawn turbo.feedback_mcp: %s"
                      % run["spawn_error"])
    elif run["timed_out"]:
        errors.append("external process exceeded the %ds watchdog; the "
                      "owned process tree was terminated" % TIMEOUT_S)
    elif run["returncode"] != 0:
        errors.append("turbo.feedback_mcp exited %s; see mcp-stderr.txt"
                      % run["returncode"])
    init = by_id.get(1)
    tools = by_id.get(3)
    call = by_id.get(4)
    if init is None or "result" not in init:
        errors.append("initialize response missing or malformed")
    if tools is None or "result" not in tools:
        errors.append("tools/list response missing or malformed")
    else:
        names = [t.get("name") for t in tools["result"].get("tools", [])]
        if TOOL_NAME not in names:
            errors.append("tools/list did not advertise %s" % TOOL_NAME)
    transport_completed = (not errors and init is not None
                           and tools is not None
                           and call is not None and "result" in call)
    if transport_completed:
        sc = call["result"].get("structuredContent")
        if not isinstance(sc, dict):
            errors.append("tools/call reply has no structured diagnostic "
                          "content")
        else:
            if call["result"].get("isError") or sc.get("isError"):
                errors.append("tools/call returned a structured error: %s"
                              % (sc.get("error") or "isError flag set"))
            if sc.get("completed") is not True:
                errors.append("diagnostic reported completed=false")
            verification, timing, loop, _report = _extract(sc)
            summary["existing_demo_verification"] = verification
            summary["timing"] = timing
            summary["file_move"] = _check_move(
                loop.get("initial_snapshot"), loop.get("final_snapshot"))
            summary["inner_output_dir"] = sc.get("output_dir")
    summary["transport_completed"] = transport_completed
    summary["ok"] = not errors
    summary["result_path"] = str(output_path)
    if errors:
        summary["errors"] = errors
    (output_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
