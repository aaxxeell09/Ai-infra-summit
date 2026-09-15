"""Tests for turbo.porting offline preflight."""
import struct
import tempfile
import unittest
from pathlib import Path

from turbo.porting import GGUFError, preflight, read_gguf_arch


def gguf_bytes(arch=None, version=3):
    kv = []
    if arch is not None:
        key = b"general.architecture"
        kv.append(struct.pack("<Q", len(key)) + key
                  + struct.pack("<I", 8) + struct.pack("<Q", len(arch)) + arch.encode())
    return (b"GGUF" + struct.pack("<IQQ", version, 0, len(kv))
            + b"".join(kv))


class GGUFHeaderTests(unittest.TestCase):
    def test_reads_arch(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes("qwen3"))
            f.flush()
            self.assertEqual(read_gguf_arch(Path(f.name)), "qwen3")

    def test_missing_arch_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes())
            f.flush()
            self.assertIsNone(read_gguf_arch(Path(f.name)))

    def test_bad_magic_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(b"SAFE")
            f.flush()
            with self.assertRaises(GGUFError):
                read_gguf_arch(Path(f.name))

    def test_truncated_integer_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(b"GGUF\x03")
            f.flush()
            with self.assertRaises(GGUFError):
                read_gguf_arch(Path(f.name))

    def test_truncated_string_raises(self):
        body = struct.pack("<Q", 20) + b"short"
        blob = b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<I", 8) + body
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(blob)
            f.flush()
            with self.assertRaises(GGUFError):
                read_gguf_arch(Path(f.name))


class PreflightTests(unittest.TestCase):
    def test_mlx_unsupported_with_evidence(self):
        out = preflight({"format": "mlx"})
        self.assertEqual(out["status"], "unsupported")
        self.assertIn("mlx-platform", out["evidence"])

    def test_huggingface_needs_conversion_no_auto_claim(self):
        out = preflight({"format": "huggingface"})
        self.assertEqual(out["status"], "needs-conversion")
        self.assertTrue(all("convert" not in c or c.startswith(("python", "#"))
                            for c in out["suggested_commands"]))

    def test_gguf_without_capability_evidence_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes("llama"))
            f.flush()
            out = preflight({"format": "gguf"}, f.name)
        self.assertEqual(out["status"], "unknown")
        self.assertIn("no capability evidence", out["reason"])

    def test_gguf_with_capability_evidence_ready(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes("llama"))
            f.flush()
            out = preflight({"format": "gguf"}, f.name,
                            {"llama": "measured load on X1E-80-100"})
        self.assertEqual(out["status"], "ready")

    def test_manifest_arch_mismatch_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes("qwen3"))
            f.flush()
            out = preflight({"format": "gguf", "architecture": "llama"}, f.name)
        self.assertEqual(out["status"], "unknown")
        self.assertIn("mismatch", out["reason"])

    def test_malformed_gguf_unknown_not_crash(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(b"GGUFgarbage")
            f.flush()
            out = preflight({"format": "gguf"}, f.name)
        self.assertEqual(out["status"], "unknown")
        self.assertTrue(any("parse failed" in n for n in out["notes"]))

    def test_large_gguf_notes_session_limit(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            f.write(gguf_bytes("llama"))
            f.truncate(3_600_000_000)  # sparse, no 3.6GB allocation
            f.flush()
            out = preflight({"format": "gguf"}, f.name)
        self.assertTrue(any("3.5 GB" in n for n in out["notes"]))

    def test_qairt_bundle_shape_does_not_prove_runtime_support(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "geniex.json").write_text('{"chipset": "SM8750"}')
            Path(d, "model.serialized").write_bytes(b"x")
            out = preflight({"format": "qairt", "chipset": "sm8750"}, d)
        self.assertEqual(out["status"], "unknown")

    def test_qairt_chipset_mismatch_needs_compile(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "geniex.json").write_text('{"chipset": "SM8850"}')
            Path(d, "model.serialized").write_bytes(b"x")
            out = preflight({"format": "qairt", "chipset": "SM8750"}, d)
        self.assertEqual(out["status"], "needs-compile")

    def test_qairt_missing_shards_needs_compile(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "geniex.json").write_text("{}")
            out = preflight({"format": "qairt"}, d)
        self.assertEqual(out["status"], "needs-compile")

    def test_qairt_missing_geniex_json_needs_compile(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "model.serialized").write_bytes(b"x")
            out = preflight({"format": "qairt"}, d)
        self.assertEqual(out["status"], "needs-compile")

    def test_unknown_format(self):
        self.assertEqual(preflight({"format": "onnx"})["status"], "unknown")

    def test_qairt_speculation_flag_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "geniex.json").write_text("{}")
            Path(d, "m.bin").write_bytes(b"x")
            out = preflight({"format": "qairt", "speculation": True}, d)
        self.assertTrue(any("ignored" in n for n in out["notes"]))


if __name__ == "__main__":
    unittest.main()
