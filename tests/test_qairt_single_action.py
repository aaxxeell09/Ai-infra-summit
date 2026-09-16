"""Synthetic streaming tests; no QAIRT model or hardware results."""
import ctypes
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_layout import _make_runtime
from test_backend_identity import qairt_bundle
from turbo.native import NativeModel, NativeRuntime, _ToolCallStop
from eval.secretary_adapter import SecretaryAdapter
from eval.run_secretary_eval import run_uninstrumented

CALL = b'<tool_call>{"name":"list_files","arguments":{}}</tool_call>'


@pytest.mark.parametrize('split', range(1, len(b'</tool_call>')))
def test_stop_marker_split_across_callbacks(split):
    stop = _ToolCallStop()
    marker = stop.marker
    assert stop.feed(b'<tool_call>{}</tool') is True
    # Independent split test with arbitrary prefix, including UTF-8 split bytes.
    stop = _ToolCallStop()
    assert stop.feed(b'\xc3') is True
    assert stop.feed(b'\xa9' + marker[:split]) is True
    assert stop.feed(marker[split:]) is False
    assert stop.hit
    assert stop.feed(b'ignored-by-cancellation') is False
    assert stop.callbacks_after_stop == 1


def model(tmp_path, enabled, chunks, ignore_callback=False):
    qairt_bundle(tmp_path)
    NativeRuntime._shared.clear()
    runtime, lib = _make_runtime()
    def generate(handle, in_p, out_p):
        gin = lib._deref(in_p)
        lib.stop_count = gin.config.contents.stop_count
        lib.has_callback = bool(gin.on_token)
        emitted = b''
        count = 0
        stopped = False
        for chunk in chunks:
            # Match official QAIRT pipeline: append native text BEFORE callback.
            emitted += chunk
            count += 1
            if gin.on_token and not gin.on_token(chunk, None):
                stopped = True
                if not ignore_callback: break
        lib.holder = ctypes.create_string_buffer(emitted)
        out = lib._deref(out_p)
        out.full_text = ctypes.cast(lib.holder, ctypes.c_void_p).value
        out.profile_data.generated_tokens = count
        out.profile_data.stop_reason = b'user' if stopped else b'eos'
        return 0
    lib.geniex_llm_generate = generate
    return NativeModel(runtime, tmp_path, backend='qairt_npu', stop_after_tool_call=enabled), runtime, lib


def test_candidate_stops_generation_and_keeps_native_closing_tag(tmp_path):
    m, runtime, lib = model(tmp_path, True, [CALL[:-5], CALL[-5:], CALL])
    seen=[]
    with m:
        result=m.chat([{'role':'user','content':'synthetic'}],on_token=lambda piece: seen.append(piece))
    runtime.close()
    assert result['text'] == CALL.decode()
    assert result['profile']['generated_tokens'] == 2
    assert result['profile']['stop_reason'] == 'user'
    assert result['generation_control']['delimiter_seen'] is True
    assert result['generation_control']['native_text_modified'] is False
    assert ''.join(seen) == CALL.decode()
    assert lib.stop_count == 0  # the QAIRT ABI rejects native stop lists


def test_default_has_no_callback_and_keeps_multiple_calls(tmp_path):
    m,runtime,lib=model(tmp_path,False,[CALL,CALL])
    with m: result=m.chat([{'role':'user','content':'synthetic'}])
    runtime.close()
    assert not lib.has_callback
    assert result['text']==(CALL+CALL).decode()
    assert result['profile']['generated_tokens']==2
    assert result['generation_control']['delimiter_seen'] is False


def test_same_chunk_extra_action_is_never_trimmed_or_forgiven(tmp_path):
    m,runtime,_=model(tmp_path,True,[CALL+CALL])
    with m: result=m.chat([{'role':'user','content':'synthetic'}])
    runtime.close()
    assert result['text']==(CALL+CALL).decode()
    codec=SecretaryAdapter.from_files([])
    with pytest.raises(ValueError, match='exactly one'):
        codec.decode(result['text'],snapshot_digest=codec.digest)


def test_ignored_cancellation_remains_visible(tmp_path):
    m,runtime,_=model(tmp_path,True,[CALL,CALL],ignore_callback=True)
    with m: result=m.chat([{'role':'user','content':'synthetic'}])
    runtime.close()
    assert result['text']==(CALL+CALL).decode()
    assert result['generation_control']['callbacks_after_stop_request']==1


def test_missing_marker_does_not_invent_closure(tmp_path):
    m,runtime,_=model(tmp_path,True,[b'<tool_call>{'])
    with m: result=m.chat([{'role':'user','content':'synthetic'}])
    runtime.close()
    assert result['text']=='<tool_call>{'
    assert not result['generation_control']['delimiter_seen']


@pytest.mark.parametrize('value', ['true', 1, None])
def test_option_requires_boolean(value):
    with pytest.raises(ValueError,match='boolean'):
        NativeModel(None,'synthetic.gguf',stop_after_tool_call=value)


def test_enabled_option_rejects_non_qairt():
    with pytest.raises(ValueError,match='QAIRT'):
        NativeModel(None,'synthetic.gguf',stop_after_tool_call=True)


def test_runner_passes_candidate_setting_without_altering_generation(monkeypatch):
    import eval.run_secretary_eval as runner
    captured={}
    class Runtime:
        def __init__(self,*args): pass
        def close(self): pass
    class Model:
        def __init__(self,*args,**kwargs): captured.update(kwargs)
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def provenance(self): return {}
        def chat(self,*args,**kwargs): captured['chat']=kwargs; return {'text':CALL.decode()}
    monkeypatch.setattr(runner,'execute',lambda *args: [])
    run_uninstrumented({'sdk_dir':'unused','model_path':'unused','stop_after_tool_call':True},
                       {'model_label':'test'},[],SecretaryAdapter.from_files([]),Runtime,Model)
    assert captured['stop_after_tool_call'] is True
    assert captured['chat']['temperature']==0
    assert captured['chat']['reset'] is True
    assert captured['chat']['max_tokens']==128


@pytest.mark.parametrize('prefix', [
    b'<tool_call>{"name":"clarify","arguments":{"question":"literal </tool_call>',
    b'<tool_call>not-json</tool_call>',
])
def test_literal_marker_diagnostic_does_not_claim_valid_action(tmp_path, prefix):
    m, runtime, _ = model(tmp_path, True, [prefix, b' trailing completion'])
    with m:
        result = m.chat([{'role': 'user', 'content': 'synthetic'}])
    runtime.close()
    assert result['text'] == prefix.decode()
    assert result['generation_control']['delimiter_seen'] is True
    assert result['generation_control']['native_text_modified'] is False
    codec = SecretaryAdapter.from_files([])
    with pytest.raises((ValueError, json.JSONDecodeError)):
        codec.decode(result['text'], snapshot_digest=codec.digest)
