import json
import tempfile
import unittest
from pathlib import Path

from turbo.context import ContextStore
from turbo.policy import Profile, choose


class PolicyTests(unittest.TestCase):
    def test_fastest_respects_quality_and_context(self):
        profiles = [Profile("tiny", "a", "cpu", 4, 160, 800, quality_tier=0, evidence="a.json"),
                    Profile("big", "b", "npu", 0, 80, 1500, quality_tier=1, evidence="b.json")]
        self.assertEqual(choose(profiles, prompt_tokens=500)["selected"]["name"], "tiny")
        self.assertEqual(choose(profiles, prompt_tokens=500, required_tier=1)["selected"]["name"], "big")
        with self.assertRaises(ValueError):
            choose(profiles, prompt_tokens=5000)

    def test_reuse_changes_latency_selection_only_when_resident(self):
        profiles = [Profile("tiny", "a", "cpu", 4, 160, 200, evidence="a.json"),
                    Profile("big", "b", "npu", 0, 80, 200, evidence="b.json")]
        kwargs = dict(prompt_tokens=3000, reusable_tokens={"big": 2900}, objective="latency")
        self.assertEqual(choose(profiles, **kwargs)["selected"]["name"], "tiny")
        self.assertEqual(choose(profiles, resident={"big"}, **kwargs)["selected"]["name"], "big")


class ContextTests(unittest.TestCase):
    def test_projection_preserves_raw_and_marks_loss(self):
        raw = json.dumps([{"path": "do-not-delete-2026.txt", "bytes": 123, "verbose": "x"*2000}])
        with tempfile.TemporaryDirectory() as d:
            store = ContextStore(Path(d))
            result = store.compact(raw, fields=["path", "bytes"])
            self.assertTrue(result["lossy"])
            self.assertEqual(store.get(result["raw_ref"]), raw)
            self.assertIn("do-not-delete-2026.txt", result["output"])
            self.assertGreater(result["saved_chars"], 0)
            with self.assertRaises(ValueError):
                store.get("../escape")

    def test_small_outputs_are_not_expanded(self):
        with tempfile.TemporaryDirectory() as d:
            result = ContextStore(Path(d)).compact('{"n":3}')
            self.assertFalse(result["applied"])
            self.assertEqual(result["saved_chars"], 0)


if __name__ == "__main__":
    unittest.main()
