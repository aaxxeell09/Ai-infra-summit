"""Tests for turbo.porting offline preflight."""
import struct
from contextlib import contextmanager
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


@contextmanager
def temporary_gguf(data, sparse_size=None):
    # Close the writer before reopening on Windows (NamedTemporaryFile denies it).
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'model.gguf'
        path.write_bytes(data)
        if sparse_size is not None:
            with path.open('r+b') as stream:
                stream.truncate(sparse_size)
        yield path


class GGUFHeaderTests(unittest.TestCase):
    def test_reads_arch(self):
        with temporary_gguf(gguf_bytes("qwen3")) as path:
            self.assertEqual(read_gguf_arch(path), "qwen3")

    def test_missing_arch_returns_none(self):
        with temporary_gguf(gguf_bytes()) as path:
            self.assertIsNone(read_gguf_arch(path))

    def test_bad_magic_raises(self):
        with temporary_gguf(b"SAFE") as path:
            with self.assertRaises(GGUFError):
                read_gguf_arch(path)

    def test_truncated_integer_raises(self):
        with temporary_gguf(b"GGUF\x03") as path:
            with self.assertRaises(GGUFError):
                read_gguf_arch(path)

    def test_truncated_string_raises(self):
        body = struct.pack("<Q", 20) + b"short"
        blob = b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<I", 8) + body
        with temporary_gguf(blob) as path:
            with self.assertRaises(GGUFError):
                read_gguf_arch(path)


class GGUFResourceBoundsTests(unittest.TestCase):
    @staticmethod
    def metadata(value_type, payload, *, include_arch=False):
        key = b'other'
        entry = struct.pack('<Q', len(key)) + key + struct.pack('<I', value_type) + payload
        if include_arch:
            # Strip the header from a separate valid architecture record.
            entry += gguf_bytes('qwen3')[24:]
        return b'GGUF' + struct.pack('<IQQ', 3, 0, 2 if include_arch else 1) + entry

    def assert_malformed(self, blob):
        with temporary_gguf(blob) as path:
            with self.assertRaises(GGUFError):
                read_gguf_arch(path)

    def test_max_uint64_key_length_never_allocates(self):
        blob = b'GGUF' + struct.pack('<IQQ', 3, 0, 1) + struct.pack('<Q', 2**64-1) + b'padding'
        self.assert_malformed(blob)

    def test_max_uint64_string_value_length_never_allocates(self):
        self.assert_malformed(self.metadata(8, struct.pack('<Q', 2**64-1)))

    def test_scalar_read_cannot_silently_pass_eof(self):
        self.assert_malformed(self.metadata(12, b'x'))

    def test_scalar_array_length_checked_before_skip(self):
        self.assert_malformed(self.metadata(9, struct.pack('<IQ', 12, 2**64-1)))

    def test_string_array_count_checked_before_iteration(self):
        self.assert_malformed(self.metadata(9, struct.pack('<IQ', 8, 2**64-1)))

    def test_unknown_array_type_rejected_even_when_empty(self):
        self.assert_malformed(self.metadata(9, struct.pack('<IQ', 12345, 0)))

    def test_nested_array_depth_is_bounded(self):
        nested = struct.pack('<IQ', 0, 0)
        for _ in range(32):
            nested = struct.pack('<IQ', 9, 1) + nested
        self.assert_malformed(self.metadata(9, nested))

    def test_skips_valid_arrays_and_strings_before_architecture(self):
        payloads = [(0, b'1'), (8, struct.pack('<Q', 3)+b'abc'),
                    (9, struct.pack('<IQ', 4, 3)+struct.pack('<III', 1, 2, 3)),
                    (9, struct.pack('<IQ', 8, 2)+struct.pack('<Q', 1)+b'a'+struct.pack('<Q', 2)+b'bc')]
        for value_type, payload in payloads:
            with self.subTest(value_type=value_type, payload=payload):
                with temporary_gguf(self.metadata(value_type, payload, include_arch=True)) as path:
                    self.assertEqual(read_gguf_arch(path), 'qwen3')

    def test_key_allocation_budget_also_applies_to_large_present_data(self):
        from turbo.porting import _MAX_READ_STRING_BYTES
        count = _MAX_READ_STRING_BYTES + 1
        blob = b'GGUF'+struct.pack('<IQQ', 3, 0, 1)+struct.pack('<Q', count)+b'x'*count+struct.pack('<IB', 0, 0)
        self.assert_malformed(blob)

    def test_huge_metadata_count_rejected_without_loop(self):
        self.assert_malformed(b'GGUF'+struct.pack('<IQQ', 3, 0, 2**64-1))


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
        with temporary_gguf(gguf_bytes("llama")) as path:
            out = preflight({"format": "gguf"}, str(path))
        self.assertEqual(out["status"], "unknown")
        self.assertIn("no capability evidence", out["reason"])

    def test_gguf_with_capability_evidence_ready(self):
        with temporary_gguf(gguf_bytes("llama")) as path:
            out = preflight({"format": "gguf"}, str(path),
                            {"llama": "measured load on X1E-80-100"})
        self.assertEqual(out["status"], "ready")

    def test_manifest_arch_mismatch_unknown(self):
        with temporary_gguf(gguf_bytes("qwen3")) as path:
            out = preflight({"format": "gguf", "architecture": "llama"}, str(path))
        self.assertEqual(out["status"], "unknown")
        self.assertIn("mismatch", out["reason"])

    def test_malformed_gguf_unknown_not_crash(self):
        with temporary_gguf(b"GGUFgarbage") as path:
            out = preflight({"format": "gguf"}, str(path))
        self.assertEqual(out["status"], "unknown")
        self.assertTrue(any("parse failed" in n for n in out["notes"]))

    def test_large_gguf_notes_session_limit(self):
        with temporary_gguf(gguf_bytes("llama"), sparse_size=3_600_000_000) as path:
            out = preflight({"format": "gguf"}, str(path))
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
