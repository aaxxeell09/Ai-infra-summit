"""Native cleanup and QAIRT ABI preflight; fake library only."""
import ctypes
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_layout import _make_runtime
from turbo.native import NativeError, NativeModel, _qairt_bundle_input


@pytest.mark.parametrize('code', [0, -1])
def test_output_freed_once_on_success_and_native_error(code):
    runtime, lib = _make_runtime()
    model = NativeModel(runtime, '/fake/model.gguf')
    generate = lib.geniex_llm_generate
    def wrapped(*args):
        generate(*args)
        return code
    lib.geniex_llm_generate = wrapped
    try:
        if code:
            with pytest.raises(NativeError):
                model.chat([{'role': 'user', 'content': 'test'}])
        else:
            assert model.chat([{'role': 'user', 'content': 'test'}])['text'] == 'Hello world'
        pointer = ctypes.cast(lib._text_holder, ctypes.c_void_p).value
        assert [c[1].value for c in lib.calls if c[0] == 'free'].count(pointer) == 1
    finally:
        model.close()
        runtime.close()


def test_cleanup_failure_preserves_original_native_error():
    runtime, lib = _make_runtime()
    model = NativeModel(runtime, '/fake/model.gguf')
    generate = lib.geniex_llm_generate
    def wrapped(*args):
        generate(*args)
        return -1
    lib.geniex_llm_generate = wrapped
    free = runtime._free
    attempts = []
    def failing_free(pointer):
        # Let template cleanup succeed; only fail generated output cleanup.
        if hasattr(lib, '_text_holder'):
            attempts.append(pointer)
            raise RuntimeError('cleanup failure')
        return free(pointer)
    runtime._free = failing_free
    try:
        with pytest.raises(NativeError):
            model.chat([{'role': 'user', 'content': 'test'}])
        assert len(attempts) == 1
    finally:
        model.close()
        runtime.close()


def test_nested_first_shard_rejected_before_native_load(tmp_path):
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'weights.bin').write_bytes(b'fake')
    (tmp_path / 'genie_config.json').write_text(json.dumps({'dialog': {
        'context': {'size': 2048},
        'engine': {'model': {'binary': {'ctx-bins': ['nested/weights.bin']}}}}}))
    with pytest.raises(ValueError, match='directly inside the bundle root'):
        _qairt_bundle_input(str(tmp_path))
