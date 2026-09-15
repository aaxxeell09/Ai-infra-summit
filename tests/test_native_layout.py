'''Layout, version-policy and (mock) call-flow tests for turbo.native.

No native SDK is required: every ctypes interaction runs against a fake
library object, so the suite runs anywhere, including macOS.
'''

from __future__ import annotations

import ctypes
import json
import threading
import unittest
from ctypes import c_char_p, c_int32, c_void_p
from pathlib import Path
from unittest import mock

from turbo import native
from turbo.native import (
    PINNED_VERSION,
    NativeError,
    NativeModel,
    NativeRuntime,
    PinnedVersionMismatch,
    geniex_LlmCreateInput,
    geniex_ModelConfig,
    geniex_ProfileData,
    geniex_ToolCall,
)


class StructLayoutTests(unittest.TestCase):
    '''Pin the 64-bit ABI: sizes and offsets must match geniex.h @ v0.6.1.'''

    def test_pointer_is_8_bytes(self):
        self.assertEqual(ctypes.sizeof(c_void_p), 8)

    def test_toolcall_layout(self):
        self.assertEqual(ctypes.sizeof(geniex_ToolCall), 24)
        self.assertEqual(geniex_ToolCall.id.offset, 0)
        self.assertEqual(geniex_ToolCall.name.offset, 8)
        self.assertEqual(geniex_ToolCall.arguments.offset, 16)

    def test_profile_layout(self):
        p = geniex_ProfileData
        self.assertEqual(ctypes.sizeof(p), 88)
        self.assertEqual(p.decoding_speed.offset, 56)
        self.assertEqual(p.draft_n_total.offset, 64)
        self.assertEqual(p.stop_reason.offset, 80)

    def test_modelconfig_layout(self):
        c = geniex_ModelConfig
        self.assertEqual(ctypes.sizeof(c), 80)
        self.assertEqual(c.n_ctx.offset, 0)
        self.assertEqual(c.n_gpu_layers.offset, 24)
        self.assertEqual(c.chat_template_path.offset, 32)
        self.assertEqual(c.spec_type.offset, 48)
        self.assertEqual(c.spec_p_min.offset, 72)

    def test_createinput_layout(self):
        s = geniex_LlmCreateInput
        self.assertEqual(ctypes.sizeof(s), 112)
        self.assertEqual(s.model_path.offset, 0)
        self.assertEqual(s.tokenizer_path.offset, 8)
        self.assertEqual(s.config.offset, 16)
        self.assertEqual(s.plugin_id.offset, 16 + ctypes.sizeof(geniex_ModelConfig))
        self.assertEqual(s.device_id.offset, 104)

    def test_struct_size_guard_active(self):
        self.assertTrue(native._struct_sizes_ok())


class _FakeLib:
    '''Stands in for ctypes.CDLL; records calls and returns canned values.'''

    @staticmethod
    def _deref(x):
        # byref() yields a CArgObject wrapping the instance in _obj; a real
        # POINTER has .contents. Support both so the fake mirrors argtypes.
        if hasattr(x, 'contents'):
            return x.contents
        return getattr(x, '_obj', x)

    def __init__(self, version=b'0.6.1', resolve=('HTP0', -1, None)):
        self.calls = []
        self._resolve = resolve
        self.geniex_init = self._mk('init', ret=0)
        self.geniex_deinit = self._mk('deinit', ret=0)
        self.geniex_version = self._mk('version', ret=version)
        self.geniex_free = self._mk('free', ret=None)
        self.geniex_get_error_message = self._mk('errmsg', ret=b'fake failure')
        self.geniex_resolve_device = self._mk_resolve()
        self.geniex_llm_create = self._mk_create()
        self.geniex_llm_destroy = self._mk('llm_destroy', ret=0)
        self.geniex_llm_reset = self._mk('llm_reset', ret=0)
        self.geniex_llm_apply_chat_template = self._mk_template()
        self.geniex_llm_generate = self._mk_generate()

    def _mk(self, name, ret):
        def f(*args):
            self.calls.append((name,) + args)
            return ret
        return f

    def _mk_resolve(self):
        def f(in_p, out_p):
            self.calls.append(('resolve', in_p, out_p))
            dev, ngl, warn = self._resolve
            holder = ctypes.create_string_buffer(dev.encode())
            self._dev_holder = holder
            out = self._deref(out_p)
            out.device_id = ctypes.cast(holder, c_void_p).value
            out.ngl = ngl
            return 0
        return f

    def _mk_create(self):
        def f(in_p, out_p):
            self.calls.append(('llm_create', in_p, out_p))
            self.captured_create_input = self._deref(in_p)
            self._deref(out_p).value = 0xDEADBEEF
            return 0
        return f

    def _mk_template(self):
        def f(handle, in_p, out_p):
            self.calls.append(('template', handle, in_p, out_p))
            self.captured_template_input = self._deref(in_p)
            buf = ctypes.create_string_buffer(b'<prompt>')
            self._tmpl_holder = buf
            self._deref(out_p).formatted_text = ctypes.cast(buf, c_void_p).value
            return 0
        return f

    def _mk_generate(self):
        def f(handle, in_p, out_p):
            self.calls.append(('generate', handle, in_p, out_p))
            gin = self._deref(in_p)
            self.captured_generate_input = gin
            if gin.on_token:
                self.callback_result = bool(gin.on_token(b'Hi', None))
            buf = ctypes.create_string_buffer(b'Hello world')
            self._text_holder = buf
            out = self._deref(out_p)
            out.full_text = ctypes.cast(buf, c_void_p).value
            p = out.profile_data
            p.ttft = 1234
            p.media_time = 0
            p.prompt_time = 2000
            p.decode_time = 8000
            p.prompt_tokens = 4
            p.generated_tokens = 2
            p.prefill_speed = 2.0
            p.decoding_speed = 250.0
            p.stop_reason = b'eos'
            return 0
        return f


def _make_runtime(version=b'0.6.1'):
    lib = _FakeLib(version)
    with mock.patch.object(native.Path, 'is_file', return_value=True), \
            mock.patch.object(native.ctypes, 'CDLL', return_value=lib), \
            mock.patch.object(native, '_preload_siblings'):
        rt = object.__new__(NativeRuntime)
        rt.sdk_dir = Path('/fake/sdk')
        rt._dll_dir_tokens = []
        rt._lib = None
        rt._models = []
        rt._lifecycle_lock = threading.Lock()
        rt._deinited = False
        rt._load_and_init()
        rt._ready = True
    return rt, lib


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        NativeRuntime._shared.clear()

    def test_version_checked_before_init(self):
        rt, lib = _make_runtime(b'0.6.1')
        order = [c[0] for c in lib.calls]
        self.assertLess(order.index('version'), order.index('init'))
        self.assertIn(('init',), lib.calls)

    def test_version_mismatch_rejected_before_init(self):
        with self.assertRaises(PinnedVersionMismatch) as cm:
            _make_runtime(b'0.7.0')
        self.assertEqual(cm.exception.reported, '0.7.0')
        self.assertEqual(cm.exception.code, -990001)

    def test_v_prefix_accepted(self):
        _make_runtime(b'v0.6.1')  # must not raise

    def test_error_code_and_message(self):
        rt, _ = _make_runtime()
        with self.assertRaises(NativeError) as cm:
            rt._check(-5)
        self.assertEqual(cm.exception.code, -5)
        self.assertEqual(cm.exception.message, 'fake failure')

    def test_resolve_device_frees_with_original_pointer(self):
        rt, lib = _make_runtime()
        dev, ngl, warn = rt.resolve_device('llama_cpp', 'npu')
        self.assertEqual(dev, 'HTP0')
        self.assertEqual(ngl, -1)
        frees = [c[1].value for c in lib.calls if c[0] == 'free']
        self.assertEqual(len(frees), 1)
        self.assertEqual(frees[0], ctypes.cast(lib._dev_holder, c_void_p).value)

    def test_close_deinit_when_no_models(self):
        rt, lib = _make_runtime()
        rt.close()
        self.assertIn(('deinit',), lib.calls)

    def test_close_rejects_open_models(self):
        rt, lib = _make_runtime()
        m = NativeModel(rt, '/fake/model.gguf', device='npu')
        try:
            with self.assertRaises(RuntimeError):
                rt.close()
        finally:
            m.close()
        rt.close()
        self.assertIn(('deinit',), lib.calls)


class ModelFlowTests(unittest.TestCase):
    def setUp(self):
        NativeRuntime._shared.clear()

    def _model(self, **kw):
        rt, lib = _make_runtime()
        m = NativeModel(rt, '/fake/model.gguf', device='npu', context=2048, threads=4, **kw)
        return m, lib

    def test_create_uses_resolved_device_and_config(self):
        m, lib = self._model()
        try:
            creates = [c for c in lib.calls if c[0] == 'llm_create']
            self.assertEqual(len(creates), 1)
            cin = lib._deref(creates[0][1])
            self.assertEqual(cin.plugin_id, b'llama_cpp')
            self.assertEqual(cin.device_id, b'HTP0')
            self.assertEqual(cin.config.n_ctx, 2048)
            self.assertEqual(cin.config.n_threads, 4)
            self.assertIsNone(cin.config.spec_type)  # default spec_type disables
        finally:
            m.close()

    def test_chat_flow_and_result_shape(self):
        m, lib = self._model()
        try:
            seen = []
            result = m.chat(
                [
                    {'role': 'system', 'content': 'be brief'},
                    {'role': 'user', 'content': 'hello'},
                ],
                on_token=seen.append,
            )
            self.assertEqual(result['text'], 'Hello world')
            self.assertEqual(seen, ['Hi'])
            self.assertTrue(lib.callback_result)
            prof = result['profile']
            self.assertEqual(prof['decoding_speed'], 250.0)
            self.assertEqual(prof['prefill_speed'], 2.0)
            self.assertEqual(prof['ttft'], 1234)
            self.assertEqual(prof['generated_tokens'], 2)
            self.assertEqual(prof['prompt_tokens'], 4)
            self.assertEqual(prof['stop_reason'], 'eos')
            self.assertEqual(result['backend'], 'geniex')
            self.assertEqual(result['device'], 'HTP0')
            self.assertEqual(result['version'], '0.6.1')
            self.assertIn('ttft', result['timings'])
            self.assertIn('total', result['timings'])
            self.assertIn('threads', result['config'])
            json.dumps(result)  # full dict must be JSON-serializable
            gin = lib.captured_generate_input
            self.assertEqual(gin.prompt_utf8, b'<prompt>')
            self.assertIsNotNone(gin.on_token)
            frees = [c[1].value for c in lib.calls if c[0] == 'free']
            self.assertIn(ctypes.cast(lib._text_holder, c_void_p).value, frees)
            self.assertIn(ctypes.cast(lib._tmpl_holder, c_void_p).value, frees)
        finally:
            m.close()

    def test_grammar_passed_in_sampler(self):
        m, lib = self._model()
        try:
            m.chat([{'role': 'user', 'content': 'x'}], grammar='root ::= "ok"')
            sampler = lib.captured_generate_input.config.contents.sampler_config.contents
            self.assertEqual(sampler.grammar_string, b'root ::= "ok"')
            m.chat([{'role': 'user', 'content': 'x'}])
            sampler2 = lib.captured_generate_input.config.contents.sampler_config.contents
            self.assertIsNone(sampler2.grammar_string)
        finally:
            m.close()

    def test_tool_calls_structural(self):
        m, lib = self._model()
        try:
            messages = [
                {'role': 'user', 'content': 'weather?'},
                {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [
                        {'id': 'call_1', 'function': {'name': 'get_weather', 'arguments': '{"city": "SF"}'}}
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'name': 'get_weather', 'content': 'sunny'},
            ]
            m.chat(messages)
            tin = lib.captured_template_input
            self.assertEqual(tin.message_count, 3)
            self.assertEqual(tin.enable_thinking, False)
            assistant = tin.messages[1]
            self.assertEqual(assistant.tool_call_count, 1)
            tc = assistant.tool_calls[0]
            self.assertEqual(tc.id, b'call_1')
            self.assertEqual(tc.name, b'get_weather')
            self.assertEqual(tc.arguments, b'{"city": "SF"}')
            tool_msg = tin.messages[2]
            self.assertEqual(tool_msg.tool_call_id, b'call_1')
            self.assertEqual(tool_msg.tool_name, b'get_weather')
            self.assertIsNone(tin.tools)
        finally:
            m.close()

    def test_reset_flag_calls_llm_reset(self):
        m, lib = self._model()
        try:
            m.chat([{'role': 'user', 'content': 'x'}], reset=True)
            m.chat([{'role': 'user', 'content': 'y'}], reset=False)
            resets = [c for c in lib.calls if c[0] == 'llm_reset']
            self.assertEqual(len(resets), 1)
        finally:
            m.close()

    def test_close_destroys_and_chat_after_close_rejected(self):
        m, lib = self._model()
        m.close()
        self.assertIn('llm_destroy', [c[0] for c in lib.calls])
        with self.assertRaises(NativeError):
            m.chat([{'role': 'user', 'content': 'x'}])


class VersionPolicyTests(unittest.TestCase):
    def test_matrix(self):
        ok = ['0.6.1', 'v0.6.1', 'V0.6.1', '0.6.1-rc0', 'geniex 0.6.1 (build 7)']
        bad = ['0.6.0', '0.6.2', '0.7.0', '0.6.10', '1.0.0', '']
        for v in ok:
            self.assertTrue(native._version_matches(v), v)
        for v in bad:
            self.assertFalse(native._version_matches(v), v)


if __name__ == '__main__':
    unittest.main()
