"""n_batch plumbing through NativeModel, reusing the fake-lib harness."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_layout import ModelFlowTests  # noqa: E402


class NBatchPlumbingTests(ModelFlowTests):
    """Inherit the full fake-lib model flow; add n_batch coverage."""

    def test_n_batch_default_zero_and_explicit_value_reach_abi(self):
        m, lib = self._model()  # default: 0 (SDK default per params.cpp)
        try:
            self.assertEqual(lib.captured_create_input.config.n_batch, 0)
        finally:
            m.close()
        m2, lib2 = self._model(n_batch=1024, ubatch=256, threads_batch=4)
        try:
            cfg = lib2.captured_create_input.config
            self.assertEqual(cfg.n_batch, 1024)
            self.assertEqual(cfg.n_ubatch, 256)
            self.assertEqual(cfg.n_threads_batch, 4)
        finally:
            m2.close()

    def test_n_batch_in_reported_config(self):
        m, _ = self._model(n_batch=2048)
        try:
            self.assertEqual(m.config["n_batch"], 2048)
        finally:
            m.close()


if __name__ == "__main__":
    unittest.main()
