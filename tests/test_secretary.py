"""Tests for turbo.secretary: fixture, tools, sandbox escapes, task integrity."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from turbo.secretary import TOOLS, create_fixture, execute_tool, load_tasks


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sandbox"
        self.root.mkdir()
        self.inventory = create_fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inventory_lists_all_files(self):
        self.assertEqual(len(self.inventory), 12)
        paths = [entry["path"] for entry in self.inventory]
        self.assertIn("todo.txt", paths)
        self.assertIn("invoices/2026/INV-0142.pdf", paths)
        self.assertTrue(all("bytes" in entry for entry in self.inventory))

    def test_all_seeded_files_exist(self):
        for entry in self.inventory:
            self.assertTrue((self.root / entry["path"]).is_file(),
                            entry["path"])

    def test_refuses_nonempty_root(self):
        with self.assertRaises(FileExistsError):
            create_fixture(self.root)


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sandbox"
        self.root.mkdir()
        create_fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, name, args):
        return execute_tool(self.root, name, args)

    def test_list_files_sorted(self):
        res = self.run_tool("list_files", {})
        self.assertTrue(res["ok"])
        files = res["result"]["files"]
        self.assertEqual(files, sorted(files))
        self.assertEqual(len(files), 12)

    def test_read_file_utf8(self):
        res = self.run_tool("read_file", {"path": "todo.txt"})
        self.assertTrue(res["ok"])
        self.assertIn("reply to Dana", res["result"]["content"])

    def test_read_file_missing(self):
        res = self.run_tool("read_file", {"path": "nope.md"})
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["error"])

    def test_search_files_case_insensitive(self):
        res = self.run_tool("search_files", {"query": "RECEIPT"})
        self.assertTrue(res["ok"])
        matches = res["result"]["matches"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["path"], "docs/expense-policy.md")
        self.assertEqual(matches[0]["line_number"], 3)

    def test_search_files_skips_pdf(self):
        res = self.run_tool("search_files", {"query": "pdf"})
        self.assertTrue(res["ok"])
        self.assertEqual(res["result"]["matches"], [])

    def test_move_file_success(self):
        res = self.run_tool("move_file", {
            "path": "notes/ideas.md", "destination": "ideas.md"})
        self.assertTrue(res["ok"])
        self.assertFalse((self.root / "notes/ideas.md").exists())
        self.assertTrue((self.root / "ideas.md").is_file())

    def test_move_file_refuses_overwrite(self):
        res = self.run_tool("move_file", {
            "path": "notes/ideas.md", "destination": "todo.txt"})
        self.assertFalse(res["ok"])
        self.assertIn("already exists", res["error"])
        self.assertTrue((self.root / "notes/ideas.md").is_file())

    def test_move_file_missing_source(self):
        res = self.run_tool("move_file", {
            "path": "ghost.md", "destination": "x.md"})
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["error"])

    def test_clarify_echo(self):
        res = self.run_tool("clarify", {"question": "Which file?"})
        self.assertTrue(res["ok"])
        self.assertEqual(res["result"]["question"], "Which file?")

    def test_unknown_tool(self):
        res = self.run_tool("rm_rf", {})
        self.assertFalse(res["ok"])
        self.assertIn("unknown tool", res["error"])

    def test_bad_args(self):
        res = self.run_tool("read_file", {})
        self.assertFalse(res["ok"])
        self.assertIn("path must be", res["error"])


class SandboxEscapeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sandbox"
        self.root.mkdir()
        create_fixture(self.root)
        self.outside = Path(self.tmp.name) / "outside.txt"
        self.outside.write_text("outside", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_path_traversal_blocked(self):
        res = execute_tool(self.root, "read_file",
                           {"path": "../outside.txt"})
        self.assertFalse(res["ok"])
        self.assertIn("escapes", res["error"])

    def test_move_traversal_blocked(self):
        res = execute_tool(self.root, "move_file",
                           {"path": "todo.txt", "destination": "../evil.txt"})
        self.assertFalse(res["ok"])
        self.assertFalse(self.outside.with_name("evil.txt").exists())

    def test_read_symlink_escape_blocked(self):
        link = self.root / "innocent.txt"
        os.symlink(self.outside, link)
        res = execute_tool(self.root, "read_file", {"path": "innocent.txt"})
        self.assertFalse(res["ok"])
        self.assertIn("escapes", res["error"])

    def test_move_destination_symlink_escape_blocked(self):
        link_dir = self.root / "linkdir"
        os.symlink(self.tmp.name, link_dir)
        res = execute_tool(self.root, "move_file",
                           {"path": "todo.txt",
                            "destination": "linkdir/stealed.txt"})
        self.assertFalse(res["ok"])
        self.assertIn("escapes", res["error"])
        self.assertTrue((self.root / "todo.txt").is_file())

    def test_deep_traversal_blocked(self):
        res = execute_tool(self.root, "read_file",
                           {"path": "notes/../../outside.txt"})
        self.assertFalse(res["ok"])


class TasksTest(unittest.TestCase):
    def test_tasks_load_and_shape(self):
        tasks = load_tasks()
        self.assertEqual(len(tasks), 13)
        for task in tasks:
            for key in ("id", "prompt", "difficulty", "expected_calls",
                        "scoring", "negatives"):
                self.assertIn(key, task, task["id"])
            self.assertTrue(task["prompt"].strip())
            for call in task["expected_calls"]:
                self.assertIn(call["name"],
                              {t["function"]["name"] for t in TOOLS},
                              task["id"])
                self.assertIsInstance(call["arguments"], dict)

    def test_task_ids_unique(self):
        ids = [t["id"] for t in load_tasks()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_difficulty_mix(self):
        tasks = load_tasks()
        diffs = {t["difficulty"] for t in tasks}
        self.assertIn("simple", diffs)
        self.assertIn("clarify", diffs)
        self.assertIn("multi_step", diffs)
        self.assertEqual(sum(t["difficulty"] == "clarify" for t in tasks), 2)
        self.assertEqual(sum(t["difficulty"] == "multi_step" for t in tasks), 2)

    def test_tools_schema_shape(self):
        names = {t["function"]["name"] for t in TOOLS}
        self.assertEqual(names, {"list_files", "read_file", "search_files",
                                 "move_file", "clarify"})
        for tool in TOOLS:
            self.assertEqual(tool["type"], "function")
            self.assertEqual(tool["function"]["parameters"]["type"], "object")
        self.assertTrue(json.dumps(TOOLS))  # serializable


if __name__ == "__main__":
    unittest.main()
