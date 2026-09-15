import json
import tempfile
import unittest
from pathlib import Path

from turbo.catalog import filter_models, load_catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_real_catalog_is_valid(self):
        self.assertTrue(self.catalog["models"])
        for e in self.catalog["models"]:
            self.assertIn(e["kind"], {"instruction", "base", "multimodal"})
            self.assertIn(e["state"], {"downloaded", "downloading", "candidate", "rejected"})
            for status in e["backend_support"].values():
                self.assertIn(status, {"unverified", "supported", "unsupported"})
                self.assertNotEqual(status, "supported",
                                    "no hardware claim allowed until measured")

    def test_total_bytes_matches_pinned_files(self):
        for e in self.catalog["models"]:
            total = sum(f["bytes"] for f in e["source"]["files"] if f.get("bytes"))
            self.assertEqual(total, e["total_bytes"], e["id"])

    def test_multimodal_gguf_has_model_projector_pair(self):
        vl = next(e for e in self.catalog["models"]
                  if e["id"] == "qwen3-vl-4b-instruct-q4_0")
        self.assertTrue(vl["requires_projector"])
        self.assertEqual(len(vl["source"]["files"]), 2)

    def test_granite_architecture_is_verified_hybrid(self):
        g = next(e for e in self.catalog["models"]
                 if e["architecture"].startswith("granite"))
        self.assertEqual(g["architecture"], "granitehybrid")

    def test_filtering_by_state_and_kind(self):
        downloaded = filter_models(self.catalog, state="downloaded")
        self.assertEqual({e["id"] for e in downloaded}, {"qwen3-0.6b-q4_0",
                         "qwen3-1.7b-q4_0", "smollm2-360m-instruct-q8_0"})
        mm = filter_models(self.catalog, kind="multimodal")
        self.assertEqual({e["id"] for e in mm},
                         {"qwen3-vl-4b-instruct-q4_0", "qwen3-vl-4b-instruct-qairt"})

    def test_backend_filter_matches_only_listed_entries(self):
        rows = filter_models(self.catalog, backend="geniex-qairt@0.6.1")
        self.assertEqual([e["id"] for e in rows], ["qwen3-vl-4b-instruct-qairt"])
        rows = filter_models(self.catalog, backend="geniex-llama_cpp@0.6.1")
        self.assertNotIn("qwen3-vl-4b-instruct-qairt",
                         [e["id"] for e in rows])

    def test_invalid_entries_rejected(self):
        bad = {"models": [{"id": "x", "kind": "nonsense"}]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(p)


if __name__ == "__main__":
    unittest.main()
