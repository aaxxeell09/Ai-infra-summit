"""Synthetic ABI tests only; no model, SDK, target or inference is used."""
import ctypes
import json
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_layout import _make_runtime
from test_backend_identity import qairt_bundle
from turbo.native import NativeRuntime, NativeModel
from turbo import qairt_sampler_diagnostic as diagnostic

REQUEST = {'temperature':.8,'top_p':1.,'top_k':1,'seed':42}


@pytest.mark.parametrize('field,value', [('temperature',0),('temperature',-1),('temperature',float('nan')),
    ('temperature',1e-100),('temperature',3),('top_p',0),('top_p',1.1),('top_k',0),('top_k',True),
    ('top_k',2**31),('seed',0),('seed',-1),('seed',2**31)])
def test_sentinels_out_of_range_and_ambiguous_types_refused(field,value):
    with pytest.raises(ValueError): diagnostic.encode_sampler(dict(REQUEST,**{field:value}))


def test_unknown_controls_refused():
    with pytest.raises(ValueError): diagnostic.encode_sampler(dict(REQUEST,min_p=.1))


def test_readback_absence_refuses_before_native_model_load(monkeypatch):
    monkeypatch.setattr(NativeModel,'__init__',lambda *a,**k: pytest.fail('Model load attempted'))
    with pytest.raises(diagnostic.SamplerVerificationError,match='readback'):
        diagnostic.LaneCQairtSamplerModel(None,'not-loaded',requested_sampling=REQUEST,backend='qairt_npu')


def fake_model(tmp_path, monkeypatch, *, mismatch=False, outputs=None):
    qairt_bundle(tmp_path)
    NativeRuntime._shared.clear()
    runtime, lib = _make_runtime()
    submitted=[]
    class SyntheticReadback:
        evidence_origin='synthetic_test'
        def read_effective_sampler_after_generation(self, handle):
            return dict(submitted[-1],top_k=40) if mismatch else submitted[-1]
    monkeypatch.setattr(diagnostic,'TRUSTED_READBACK_ADAPTERS',(SyntheticReadback,))
    original=lib.geniex_llm_generate
    def generate(handle, inp, out):
        sampler=lib._deref(inp).config.contents.sampler_config.contents
        submitted.append(diagnostic.sampler_values(sampler))
        code=original(handle,inp,out)
        if outputs is not None:
            lib.text_holder=ctypes.create_string_buffer(outputs[len(submitted)-1].encode())
            lib._deref(out).full_text=ctypes.cast(lib.text_holder,ctypes.c_void_p).value
        return code
    lib.geniex_llm_generate=generate
    model=diagnostic.LaneCQairtSamplerModel(runtime,tmp_path,requested_sampling=REQUEST,
        readback=SyntheticReadback(),backend='qairt_npu')
    return model,runtime,lib,submitted


def test_all_controls_reach_public_abi_and_five_resets_are_preserved(tmp_path,monkeypatch):
    model,runtime,lib,submitted=fake_model(tmp_path,monkeypatch,outputs=['hello']*5)
    with model:
        result=diagnostic.five_repeat_diagnostic(model,'fixed prompt')
    runtime.close()
    expected=diagnostic.sampler_values(diagnostic.encode_sampler(REQUEST))
    assert submitted==[expected]*5
    assert len([call for call in lib.calls if call[0]=='llm_reset'])==5
    assert result['all_identical_utf8_bytes'] is True
    assert result['semantic_correctness'] is None and not result['qualified']
    assert all(row['sampling']['effective_native'] is None for row in result['rows'])
    assert all(row['sampling']['verification']=='synthetic_contract_only' for row in result['rows'])


def test_mismatched_readback_fails_before_output_is_accepted(tmp_path,monkeypatch):
    model,runtime,lib,submitted=fake_model(tmp_path,monkeypatch,mismatch=True)
    original=model.runtime
    with model:
        result=diagnostic.five_repeat_diagnostic(model,'fixed prompt')
        assert model.runtime is original
    runtime.close()
    assert len(submitted)==1
    assert result['completed_repeats']==0 and result['all_identical_utf8_bytes'] is None
    assert 'differs' in result['rows'][0]['reason']
    assert 'text' not in result['rows'][0]
    assert result['attempted_repeats']==1
    assert result['rows'][0]['sampling']['requested']==REQUEST
    assert result['rows'][0]['sampling']['synthetic_effective']['top_k']==40
    assert result['rows'][0]['sampling']['effective_native'] is None


def test_case_and_punctuation_are_not_normalized_for_determinism(tmp_path,monkeypatch):
    model,runtime,lib,submitted=fake_model(tmp_path,monkeypatch,outputs=['hello','Hello.','HELLO','hello','hello'])
    with model:
        result=diagnostic.five_repeat_diagnostic(model,'fixed prompt')
    runtime.close()
    assert result['all_identical_utf8_bytes'] is False
    assert result['semantic_correctness'] is None


def test_frozen_default_sampler_still_reaches_abi_unchanged(tmp_path):
    qairt_bundle(tmp_path); NativeRuntime._shared.clear()
    runtime,lib=_make_runtime(); seen=[]; original=lib.geniex_llm_generate
    def generate(handle,inp,out):
        seen.append(diagnostic.sampler_values(lib._deref(inp).config.contents.sampler_config.contents))
        return original(handle,inp,out)
    lib.geniex_llm_generate=generate
    with NativeModel(runtime,tmp_path,backend='qairt_npu') as model:
        model.chat([{'role':'user','content':'synthetic'}])
    runtime.close()
    assert seen==[{'temperature':0.,'top_p':1.,'top_k':0,'seed':-1}]


def test_cli_writes_blocked_evidence_without_native_load(tmp_path,monkeypatch,capsys):
    from scripts import qairt_sampler_diagnostic as cli
    monkeypatch.setattr(cli,'LOCAL_OUTPUT_ROOT',tmp_path/'local')
    monkeypatch.setattr(NativeRuntime,'__init__',lambda *a,**k: pytest.fail('SDK load attempted'))
    config=tmp_path/'config.json';config.write_text(json.dumps({'backend':'qairt_npu','plugin':'qairt','device':'npu'}))
    output=tmp_path/'local/report.json'
    args=['--config',str(config),'--temperature','.8','--top-p','1','--top-k','1','--seed','42','--output',str(output)]
    assert cli.main(args)==3
    report=json.loads(output.read_text())
    assert report['effective_native'] is None and report['abi_submitted'] is None
    assert report['completed_repeats']==0 and report['all_identical_utf8_bytes'] is None
    assert 'no inference attempted' in capsys.readouterr().out
    with pytest.raises(SystemExit): cli.main(args)


@pytest.mark.parametrize('failure_kind', ['native_error','readback_error'])
def test_runtime_failures_retain_sampling_evidence_and_release_output(tmp_path,monkeypatch,failure_kind):
    model,runtime,lib,submitted=fake_model(tmp_path,monkeypatch)
    original_runtime=model.runtime
    if failure_kind=='native_error':
        original_generate=lib.geniex_llm_generate
        def failing_generate(*args):
            original_generate(*args)  # Native failure can still allocate its output.
            return -200101
        lib.geniex_llm_generate=failing_generate
        expected_error='NativeError'
    else:
        def failing_readback(handle):
            raise RuntimeError('readback unavailable')
        monkeypatch.setattr(model._readback,'read_effective_sampler_after_generation',failing_readback)
        expected_error='RuntimeError'
    with model:
        frees_before=len([call for call in lib.calls if call[0]=='free'])
        report=diagnostic.five_repeat_diagnostic(model,'fixed prompt')
        assert model.runtime is original_runtime
        assert len([call for call in lib.calls if call[0]=='free'])==frees_before+2
    runtime.close()
    row=report['rows'][0]
    assert row['error']==expected_error
    assert row['sampling']['requested']==REQUEST
    assert row['sampling']['abi_submitted']==submitted[0]
    assert row['sampling']['effective_native'] is None
    assert row['sampling']['synthetic_effective'] is None
    assert row['sampling']['verification']=='unavailable_after_runtime_error'
    assert report['attempted_repeats']==1 and report['completed_repeats']==0
    assert report['all_identical_utf8_bytes'] is None


def test_readback_exception_object_is_not_replaced(tmp_path,monkeypatch):
    model,runtime,lib,submitted=fake_model(tmp_path,monkeypatch)
    original_error=RuntimeError('original failure')
    def fail(handle): raise original_error
    monkeypatch.setattr(model._readback,'read_effective_sampler_after_generation',fail)
    with model:
        with pytest.raises(RuntimeError) as caught:
            model.chat([{'role':'user','content':'fixed prompt'}])
    runtime.close()
    assert caught.value is original_error
    assert caught.value.sampling_evidence['requested']==REQUEST
