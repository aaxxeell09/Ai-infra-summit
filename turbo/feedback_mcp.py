"""Opt-in stdio MCP wrapper for the fixture-only feedback diagnostic.

Exposes exactly one tool, local_feedback_diagnostic, over line-delimited
JSON-RPC 2.0 (same framing as turbo/mcp_server.py). Every call runs the
committed scripts/run_secretary_feedback.py in a fresh subprocess with
--enable-candidate --constrain-tools and a unique output directory; no shell.
Call-time arguments are limited to a public demo task_id and a model id from
the startup allowlist; paths, prompts and workspace are never accepted here.
This is a bounded diagnostic transport, not a production service, and it makes
no quality claim: existing_demo_verification is returned verbatim.

Hardware exclusivity is external to this process: the operator must stop the
gateway and any other model jobs before starting the server.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_secretary_feedback.py"
TIMEOUT_S = 180
STDERR_TAIL_CHARS = 4000
SERVER_INFO = {"name": "turbo-feedback-mcp", "version": "0.1.0"}
PROTOCOL_VERSION = "2025-06-18"

TOOLS = [{
    "name": "local_feedback_diagnostic",
    "description": (
        "Run one opt-in fixture-only feedback diagnostic against the local "
        "model via scripts/run_secretary_feedback.py. task_id selects a "
        "public demo fixture; model_id must be on the server startup "
        "allowlist. Requires exclusive hardware: stop the gateway and all "
        "other model jobs first. Returns the raw diagnostic record including "
        "existing_demo_verification verbatim; it makes no quality claim."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string",
                        "description": "Public demo fixture id; not golden v2."},
            "model_id": {"type": "string",
                         "description": "Model name from the server startup allowlist."},
        },
        "required": ["task_id", "model_id"],
        "additionalProperties": False,
    },
}]


class FeedbackMCPServer:
    def __init__(self, models, output_root, stdin=None, stdout=None, runner=None):
        self.models = dict(models)
        self.output_root = Path(output_root)
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.runner = runner or subprocess.run
        self.initialized = False
        self._lock = threading.Lock()

    # ---- wire helpers (same framing as turbo/mcp_server.py) ------------
    def _write(self, payload):
        self.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.stdout.flush()

    def respond(self, id, result):
        self._write({"jsonrpc": "2.0", "id": id, "result": result})

    def respond_error(self, id, code, message):
        self._write({"jsonrpc": "2.0", "id": id,
                     "error": {"code": code, "message": message}})

    def dispatch(self, msg):
        if not isinstance(msg, dict):
            return
        method = msg.get("method")
        if method is None or "id" not in msg:
            return
        id = msg.get("id")
        if method == "initialize":
            if self.initialized:
                return self.respond_error(id, -32600, "server already initialized")
            self.initialized = True
            requested = (msg.get("params") or {}).get("protocolVersion")
            return self.respond(id, {
                "protocolVersion": requested if requested == PROTOCOL_VERSION else PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        if method == "notifications/initialized":
            return
        if method == "ping":
            return self.respond(id, {})
        if method == "tools/list":
            return self.respond(id, {"tools": TOOLS})
        if method == "tools/call":
            return self.handle_tools_call(id, msg.get("params"))
        self.respond_error(id, -32601, "method not found: %s" % method)

    def serve_forever(self):
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self.respond_error(None, -32700, "parse error: line is not valid JSON")
                continue
            self.dispatch(msg)

    # ---- tool ----------------------------------------------------------
    def handle_tools_call(self, id, params):
        if not self.initialized:
            return self.respond_error(id, -32002, "server not initialized")
        params = params if isinstance(params, dict) else {}
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return self.respond_error(id, -32602, "params.arguments must be an object")
        try:
            result = self._tool_diagnostic(args)
        except ValueError as exc:
            result = {"error": str(exc), "isError": True}
        self.respond(id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "structuredContent": result,
            "isError": bool(result.get("isError")),
        })

    def _tool_diagnostic(self, args):
        unexpected = sorted(set(args) - {"task_id", "model_id"})
        if unexpected:
            raise ValueError("unexpected arguments: %s" % ", ".join(unexpected))
        task_id = args.get("task_id")
        model_id = args.get("model_id")
        config = self.models.get(model_id)
        if config is None:
            raise ValueError(
                "unknown model_id %r; allowlist: %s" % (model_id, ", ".join(sorted(self.models))))
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id must be a nonempty string")
        # The script re-validates the task id and owns prompt/workspace
        # handling; this check keeps unknown ids from creating an output
        # directory at all.
        sys.path.insert(0, str(ROOT))
        from turbo.secretary import load_tasks
        if task_id not in {t["id"] for t in load_tasks()}:
            raise ValueError("unknown demo task_id %r" % task_id)
        if self._lock.locked():
            raise ValueError("another diagnostic is already running; one at a time")
        with self._lock:
            return self._run_diagnostic(model_id, config, task_id)

    def _run_diagnostic(self, model_id, config, task_id):
        self.output_root.mkdir(parents=True, exist_ok=True)
        out_dir = self.output_root / (
            "feedback-mcp-%s-%s" % (time.strftime("%Y%m%dT%H%M%S"), uuid.uuid4().hex[:8]))
        argv = [sys.executable, str(SCRIPT),
                "--enable-candidate", "--constrain-tools",
                "--config", str(Path(config).resolve()),
                "--task-id", task_id,
                "--output", str(out_dir)]
        result = {"task_id": task_id, "model_id": model_id, "output_dir": str(out_dir)}
        try:
            proc = self.runner(argv, cwd=str(ROOT), timeout=TIMEOUT_S,
                               capture_output=True, text=True)
        except subprocess.TimeoutExpired as exc:
            result.update({"timed_out": True, "timeout_s": TIMEOUT_S,
                           "error": "diagnostic exceeded %ds; partial artifacts preserved" % TIMEOUT_S,
                           "stderr_tail": (exc.stderr or "")[-STDERR_TAIL_CHARS:],
                           "isError": True})
            return result
        result["returncode"] = proc.returncode
        result["stdout_tail"] = (proc.stdout or "")[-STDERR_TAIL_CHARS:]
        result["stderr_tail"] = (proc.stderr or "")[-STDERR_TAIL_CHARS:]
        report_path = out_dir / "diagnostic.json"
        if report_path.is_file():
            result["report"] = json.loads(report_path.read_text(encoding="utf-8"))
            report = result["report"]
            result["existing_demo_verification"] = report.get("existing_demo_verification")
            result["completed"] = report.get("completed")
            result["identity"] = {k: report.get(k) for k in
                                  ("version", "git_commit", "model_sha256", "sdk_identity",
                                   "grammar_enabled", "grammar_canary",
                                   "diagnostic_elapsed_s", "timing_scope")}
        else:
            result["error"] = "diagnostic wrote no diagnostic.json; see stderr_tail"
            result["isError"] = True
        if proc.returncode != 0:
            result["isError"] = True
        return result


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enable-candidate", action="store_true",
                   help="Required; without it the server refuses to start")
    p.add_argument("--model", action="append", default=[], metavar="NAME=PATH",
                   help="Startup allowlist entry mapping a model id to an "
                        "existing config path; repeatable")
    p.add_argument("--output-root", required=True, type=Path,
                   help="Directory that receives one unique subdirectory per run")
    args = p.parse_args(argv)
    if not args.enable_candidate:
        p.error("Explicit --enable-candidate required; default service remains unchanged")
    models = {}
    for entry in args.model:
        name, sep, path = entry.partition("=")
        if not sep or not name or not path:
            p.error("--model must be NAME=PATH")
        if not Path(path).is_file():
            p.error("config path does not exist: %s" % path)
        models[name] = path
    if not models:
        p.error("at least one --model NAME=PATH allowlist entry is required")
    args.models = models
    return args


def main(argv=None):
    args = parse_args(argv)
    FeedbackMCPServer(args.models, args.output_root).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
