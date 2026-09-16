"""Synthetic instrumentation tests: no SDK, power meter or hardware execution."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys

import pytest
from eval.run_secretary_eval import execute
from eval.secretary_adapter import SecretaryAdapter
from eval.scoring import load_dataset
from eval.energy_measurement import validate_protocol

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'eval/fixtures/secretary_workspace'


class SyntheticSession:
    def __init__(self): self.events=[]; self.last_inference=None
    @contextmanager
    def measure(self, scope):
        self.events.append(('start',scope))
        result={'scope':scope,'channel':'SYS','gross_energy_j':2.,'duration_s':1.,
                'avg_power_w':2.,'net_energy_j':None}
        try: yield result
        finally: self.events.append(('end',scope))


def test_all_golden_results_identical_with_energy_enabled():
    cases=load_dataset([ROOT/'eval/datasets/secretary_dev.json',ROOT/'eval/datasets/secretary_heldout.json'])
    codec=SecretaryAdapter.from_files(json.loads((ROOT/'eval/fixtures/files.json').read_text()))
    for case in cases:
        args=case['expected']['arguments'] or ({'question':'Which item?'} if case['expected']['tool']=='clarify' else {})
        def complete(messages): return {'text':json.dumps({'name':case['expected']['tool'],'arguments':args})}
        plain=execute([case],codec,complete,FIXTURE)[0]
        measured=execute([case],codec,complete,FIXTURE,SyntheticSession())[0]
        assert plain['task_success'] is True
        for key in ('task_success','tool','arguments','failure_reasons','execution_ok','final_state_match'):
            assert measured.get(key)==plain.get(key), (case['id'],key)
        assert measured['energy']['gross_energy_j']==2.


def test_golden_execution_outside_task_and_actual_inside(monkeypatch):
    import eval.secretary_adapter as adapter
    session=SyntheticSession()
    original=adapter.execute_tool
    def wrapped(*args):
        session.events.append(('tool',args[1]))
        return original(*args)
    monkeypatch.setattr(adapter,'execute_tool',wrapped)
    case=load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
    codec=SecretaryAdapter.from_files(json.loads((ROOT/'eval/fixtures/files.json').read_text()))
    def complete(messages):
        session.events.append(('model','call'))
        return {'text':json.dumps({'name':case['expected']['tool'],'arguments':case['expected']['arguments']})}
    execute([case],codec,complete,FIXTURE,session)
    assert session.events == [('tool',case['expected']['tool']),('start','warm_task'),
                              ('model','call'),('tool',case['expected']['tool']),('end','warm_task')]


@pytest.mark.parametrize('text', ['not JSON', '{"name":"list_files","name":"read_file","arguments":{}}'])
def test_invalid_output_keeps_failed_energy_without_tool_execution(text):
    case=load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
    codec=SecretaryAdapter.from_files(json.loads((ROOT/'eval/fixtures/files.json').read_text()))
    row=execute([case],codec,lambda _: {'text':text},FIXTURE,SyntheticSession())[0]
    assert not row['task_success'] and row['invalid_output']
    assert row['energy']['gross_energy_j']==2.
    assert 'execution_ok' not in row


def test_model_failure_is_still_an_energy_attempt():
    case=load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
    codec=SecretaryAdapter.from_files([])
    def fail(_): raise TimeoutError('synthetic')
    row=execute([case],codec,fail,FIXTURE,SyntheticSession())[0]
    assert row['failure_reasons']==['TIMEOUT']
    assert row['energy']['gross_energy_j']==2.


def test_generation_observer_brackets_sdk_call_without_changing_sampling():
    sys.path.insert(0,str(ROOT/'tests'))
    from test_native_layout import _make_runtime
    from turbo.native import NativeModel, NativeRuntime
    NativeRuntime._shared.clear()
    runtime,lib=_make_runtime()
    session=SyntheticSession()
    generate=lib.geniex_llm_generate
    def wrapped(*args):
        session.events.append(('generate','native'))
        return generate(*args)
    lib.geniex_llm_generate=wrapped
    with NativeModel(runtime,'/synthetic/model.gguf',generation_observer=session) as model:
        result=model.chat([{'role':'user','content':'synthetic test'}])
        assert result['sampling']['sdk_top_k']==0
    runtime.close()
    assert session.events==[('start','inference'),('generate','native'),('end','inference')]


def test_uncommissioned_protocol_rejected_before_meter():
    with pytest.raises(ValueError): validate_protocol({'channel':'SYS','counter_resolution_s':None})


def test_lifecycle_separates_load_warmup_idle_and_tasks(monkeypatch, tmp_path):
    import eval.energy_measurement as lifecycle
    protocol={'channel':'SYS','counter_resolution_s':.1,'counter_resolution_evidence':'synthetic test only',
              'idle_window_s':10,'idle_repeats':3,'idle_max_cv':.1,'warmup_count':3,'power_source':'ac',
              'power_mode':'synthetic-mode','hardware_note':'synthetic-machine',
              'display_network_conditions':'synthetic','background_contamination':False}
    real_validate=lifecycle.EnergySession.validate_protocol
    class Session(SyntheticSession):
        validate_protocol=staticmethod(real_validate)
        def __init__(self, protocol): super().__init__(); sessions.append(self)
        def close(self): self.events.append(('close','meter'))
        def measure_idle(self, kind):
            self.events.append(('idle',kind)); return {'stable':True,'mean_power_w':1.}
    sessions=[]
    class Memory:
        def __init__(self,*args): pass
        def sample(self): return {'peak_working_set_mb':10}
        def close(self): pass
    class Runtime:
        def __init__(self,*args): sessions[0].events.append(('load','runtime'))
        def close(self): pass
    class Model:
        def __init__(self,*args,**kwargs): sessions[0].events.append(('load','model'))
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def provenance(self): return {'backend_id':'llama_cpp_cpu'}
        def chat(self,*args,**kwargs):
            sessions[0].events.append(('request','model'))
            return {'text':'{"name":"clarify","arguments":{"question":"Which file?"}}'}
    monkeypatch.setattr(lifecycle, 'EnergySession', Session)
    monkeypatch.setattr(lifecycle, 'ProcessMemory', Memory)
    monkeypatch.setattr(lifecycle.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(lifecycle, 'power_snapshot', lambda:{'ac_line_status':'ac','active_scheme_guid':'test',
                         'battery_saver':False,'battery_percent':90})
    (tmp_path/'geniex.dll').write_bytes(b'synthetic, never loaded')
    case=load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[0]
    metadata={'model_label':'test.gguf','energy_instrumentation_sha256':{'test':'hash'}}
    result=lifecycle.measured_run({'sdk_dir':str(tmp_path),'model_path':'test.gguf'},metadata,[case],
                         SecretaryAdapter.from_files([]),execute,FIXTURE,protocol,1,Runtime,Model)
    assert len(result)==1 and result[0]['energy']['gross_energy_j']==2.
    evidence=metadata['energy_measurement']
    assert evidence['valid'] and len(evidence['warmups'])==3
    assert evidence['cold_load']['scope']=='cold_load'
    assert list(evidence['signature']['runtime_files_sha256'])==['geniex.dll']
    events=sessions[0].events
    assert events.index(('idle','platform')) < events.index(('load','runtime'))
    assert events.index(('idle','runtime')) < events.index(('start','warm_task'))
    assert events.count(('request','model'))==4
