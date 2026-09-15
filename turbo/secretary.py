"""Local secretary fixture and tool validation. Stdlib only; no inference, no UI.

The parent server seeds a fixture per run (create_fixture), offers TOOLS to the
model, parses <tool_call>{name,arguments}</tool_call>, and calls execute_tool.
All filesystem access is confined to the sandbox root by realpath checks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_FILES: dict[str, str] = {
    'README.md': '# Desk notes\n\nWelcome to the secretary sandbox.\n',
    'notes/2026-09-standup.md': '# September standup\n\n- ship NPU decode bench\n- book demo room\n',
    'notes/parking-lot.md': '# Parking lot\n\nIdeas not scheduled this quarter.\n',
    'notes/ideas.md': '# Ideas\n\nRainbow tables for eval dashboards.\n',
    'docs/expense-policy.md': '# Expense policy\n\nMeals over 75 USD need a receipt.\n',
    'docs/onboarding.md': '# Onboarding\n\nDay one checklist for new hires.\n',
    'docs/vendor-contacts.md': '# Vendor contacts\n\nHexagon tools desk: tools@example.com\n',
    'invoices/2026/INV-0142.pdf': 'fake pdf bytes',
    'invoices/2026/INV-0157.pdf': 'fake pdf bytes',
    'drafts/q3-summary.md': '# Q3 summary draft\n\nDevice benchmark results are under review.\n',
    'drafts/hexagon-invoice.md': '# Demo invoice HX-0926\n\nVendor: Hexagon\nAmount: 120 USD\n',
    'todo.txt': 'reply to Dana\nfile expense report\nwater the plant\n',
}

def _safe_resolve(root: Path, relative: str) -> Path:
    """Resolve a sandbox-relative path, refusing escapes via .. or symlinks."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError("path escapes the sandbox: " + relative)
    return candidate


def create_fixture(root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Seed the sandbox with the standard file set. Returns [{path, bytes}]."""
    root_path = Path(root)
    if root_path.exists() and any(root_path.iterdir()):
        raise FileExistsError("fixture root exists and is not empty: " + str(root))
    inventory = []
    for rel, content in _FILES.items():
        target = _safe_resolve(root_path, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        target.write_bytes(data)
        inventory.append({"path": rel, "bytes": len(data)})
    return inventory


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "result": None, "error": message}


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "result": result, "error": None}


def execute_tool(root: str | os.PathLike[str], name: str,
                 args: dict[str, Any]) -> dict[str, Any]:
    """Run one tool inside the sandbox. Never raises; see module docstring."""
    root_path = Path(root)
    try:
        if not isinstance(args, dict):
            return _err("arguments must be an object")
        allowed = {"list_files": set(), "read_file": {"path"},
                   "search_files": {"query"}, "move_file": {"path", "destination"},
                   "clarify": {"question"}}
        if name in allowed and set(args) - allowed[name]:
            return _err("unexpected arguments")
        if name == "list_files":
            files = sorted(
                p.relative_to(root_path).as_posix()
                for p in root_path.rglob("*") if p.is_file() and not p.is_symlink()
                and p.resolve().is_relative_to(root_path.resolve())
            )
            return _ok({"files": files})

        if name == "read_file":
            rel = args.get("path")
            if not isinstance(rel, str) or not rel:
                return _err("path must be a non-empty string")
            target = _safe_resolve(root_path, rel)
            if not target.is_file():
                return _err("file not found: " + rel)
            return _ok({"path": rel,
                        "content": target.read_text(encoding="utf-8",
                                                    errors="replace")})

        if name == "search_files":
            query = args.get("query")
            if not isinstance(query, str) or not query:
                return _err("query must be a non-empty string")
            matches = []
            needle = query.lower()
            for path in sorted(root_path.rglob("*")):
                if (not path.is_file() or path.is_symlink()
                    or not path.resolve().is_relative_to(root_path.resolve())
                    or path.suffix.lower() in {".pdf"}):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                rel = path.relative_to(root_path).as_posix()
                for number, line in enumerate(text.splitlines(), start=1):
                    if needle in line.lower():
                        matches.append({"path": rel, "line_number": number,
                                        "line": line})
            return _ok({"matches": matches})

        if name == "move_file":
            rel = args.get("path")
            dest = args.get("destination")
            if not isinstance(rel, str) or not rel:
                return _err("path must be a non-empty string")
            if not isinstance(dest, str) or not dest:
                return _err("destination must be a non-empty string")
            source = _safe_resolve(root_path, rel)
            target = _safe_resolve(root_path, dest)
            if not source.is_file():
                return _err("file not found: " + rel)
            if target.exists():
                return _err("destination already exists: " + dest)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            return _ok({"path": rel, "destination": dest})

        if name == "clarify":
            question = args.get("question")
            if not isinstance(question, str) or not question:
                return _err("question must be a non-empty string")
            return _ok({"question": question})

        return _err("unknown tool: " + str(name))
    except (ValueError, OSError) as exc:
        return _err(str(exc))


TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List every file in the workspace, sorted.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "exact workspace-relative path including every parent folder"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "Case-insensitive substring search across text files.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "move_file",
        "description": "Move a file. Both path and destination must be complete workspace-relative filenames, including parent folders and file extension. destination is a filename, never only a directory. Refuses overwrite or escape.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "destination": {"type": "string"},
        }, "required": ["path", "destination"]},
    }},
    {"type": "function", "function": {
        "name": "clarify",
        "description": "Ask the user a clarifying question when the request is "
                       "genuinely ambiguous.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"},
        }, "required": ["question"]},
    }},
]

_TASKS_PATH = Path(__file__).resolve().parent.parent / "benchmarks" / "secretary_tasks.json"


def load_tasks(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Load secretary evaluation tasks from the benchmark JSON."""
    source = Path(path) if path else _TASKS_PATH
    tasks = json.loads(source.read_text(encoding="utf-8"))
    for task in tasks:
        for key in ("id", "prompt", "difficulty", "expected_calls", "scoring"):
            if key not in task:
                raise ValueError("task missing %r: %s" % (key, task.get("id")))
    return tasks


def snapshot(root):
    """Exact relative paths and content digests for final-state verification."""
    import hashlib
    root = Path(root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and p.resolve().is_relative_to(root.resolve())}


def grade_task(task, calls, results, root):
    """Grade exact intent and complete final state; never sent to the model."""
    import tempfile
    expected = task['expected_calls']
    if task['scoring'] == 'name_only':
        calls_ok = [c['name'] for c in calls] == [c['name'] for c in expected]
    else:
        calls_ok = calls == expected
    with tempfile.TemporaryDirectory() as folder:
        create_fixture(folder)
        for c in expected:
            if c['name'] != 'clarify':
                gold = execute_tool(folder, c['name'], c['arguments'])
                if not gold['ok']:
                    raise ValueError('Invalid gold fixture: ' + gold['error'])
        state_ok = snapshot(root) == snapshot(folder)
    execution_ok = len(results) == len(calls) and all(r['ok'] for r in results)
    return {'passed': calls_ok and state_ok and execution_ok,
            'calls_match': calls_ok, 'final_state_match': state_ok,
            'execution_ok': execution_ok, 'task_id': task['id']}
