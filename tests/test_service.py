import hashlib
import json
from pathlib import Path
from turbo.service import Engine
from turbo.secretary import create_fixture,execute_tool,grade_task,load_tasks
from turbo.runtime_identity import runtime_identity


def make_engine(tmp_path):
    model = tmp_path/'model.gguf'; model.write_bytes(b'test weights')
    rec = tmp_path/'rec.json'
    sdk = tmp_path/'sdk'; sdk.mkdir()
    exe = sdk/'bench.exe'; exe.write_bytes(b'benchmark')
    (sdk/'geniex.dll').write_bytes(b'native bridge')
    rec.write_text(json.dumps({'schema_version':'turbo.recommended.v2','plugin':'llama_cpp',
        'runtime_binding':runtime_identity(exe,sdk),
        'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'scope':{'evidence':'test','quality_calibrated':False},'modes':{'fast':{'device':'cpu','threads':10,'context':4096,'metrics':{'decode_tps':90,'tokens_per_joule':1.4}},'efficient':{'device':'npu','threads':0,'context':4096,'metrics':{'decode_tps':36,'tokens_per_joule':2.1,'energy_channel':'SYS','energy_scope':'full_process_trial'}}}}))
    return Engine({'models':{'small':{'path':str(model)}},'default':'small','recommendation_file':str(rec),'data_dir':str(tmp_path/'demo'), 'sdk_dir':str(sdk),'tuner':{'exe':str(exe)}})


def test_mode_switch_releases_old_model_and_applies_config(tmp_path):
    e=make_engine(tmp_path);e.apply('fast')
    class Old:
        closed=False
        def close(self):self.closed=True
    old=Old();e.loaded['small']=old
    r=e.apply('efficient')
    assert old.closed and not e.loaded
    assert r['config']=={'device':'npu','threads':0,'context':4096}


def test_wrong_weights_rejected(tmp_path):
    import pytest
    e=make_engine(tmp_path);Path(e.config['models']['small']['path']).write_bytes(b'other')
    with pytest.raises(ValueError,match='different model'):e.apply('fast')


def test_invoice_verified_by_calls_and_complete_state(tmp_path):
    create_fixture(tmp_path);task=next(t for t in load_tasks() if t['id']=='t13')
    c=task['expected_calls'][0];result=execute_tool(tmp_path,c['name'],c['arguments'])
    assert grade_task(task,[c],[result],tmp_path)['passed']
    (tmp_path/'todo.txt').write_text('unexpected side effect')
    assert not grade_task(task,[c],[result],tmp_path)['passed']


def test_secretary_propagates_applied_mode_and_verification(tmp_path):
    e=make_engine(tmp_path)
    def fake_completion(body,mode):
        e.apply(mode)
        call={'name':'move_file','arguments':json.dumps({'path':'drafts/hexagon-invoice.md','destination':'invoices/2026/hexagon-invoice.md'})}
        return {'tool_calls':[{'function':call}],'applied':e.applied,'profile':{}}
    e.completion=fake_completion
    r=e.secretary(mode='efficient',task_id='t13')
    assert r['passed'] and r['applied']['config']['device']=='npu'
    assert r['elapsed_s']>0


def test_search_does_not_follow_outside_symlink(tmp_path):
    root=tmp_path/'fixture';create_fixture(root)
    outside=tmp_path/'private.txt';outside.write_text('private-secret')
    (root/'leak.txt').symlink_to(outside)
    assert execute_tool(root,'search_files',{'query':'private-secret'})['result']['matches']==[]
    assert 'leak.txt' not in execute_tool(root,'list_files',{})['result']['files']
    assert not execute_tool(root,'read_file',None)['ok']


def test_tune_releases_models_without_reinitializing_windows_sdk(tmp_path, monkeypatch):
    import turbo.tuning as tuning
    e = make_engine(tmp_path)
    e.config['tuner'] = {'exe': 'unused-in-unit-test'}
    e.config['results_dir'] = str(tmp_path / 'results')
    class Runtime:
        def close(self):
            raise AssertionError('Native SDK must remain initialized between tune cycles')
    class Model:
        closed = False
        def close(self): self.closed = True
    runtime, model = Runtime(), Model()
    e.runtime = runtime
    e.loaded['small'] = model
    monkeypatch.setattr(tuning, 'run_tuning', lambda *args, **kwargs: {})
    e.start_tune({'search_space': {'devices':['cpu'], 'threads':[10], 'contexts':[4096]}})
    e.tuning_process.thread.join(timeout=2)
    assert not e.tuning_process.thread.is_alive()
    assert e.runtime is runtime and model.closed and not e.loaded


def test_sdk_drift_rejects_profile_and_retained_runtime(tmp_path):
    import pytest
    e = make_engine(tmp_path)
    e.apply('fast')
    original = e._current_runtime_binding()
    (Path(e.config['sdk_dir'])/'geniex.dll').write_bytes(b'updated bridge')
    with pytest.raises(ValueError, match='Runtime identity'):
        e.apply('fast')
    # Even a freshly tuned matching on-disk profile cannot replace DLLs that
    # remain resident in this Windows process.
    e.runtime_binding = original
    p = Path(e.config['recommendation_file']); rec = json.loads(p.read_text())
    rec['runtime_binding'] = e._current_runtime_binding(); p.write_text(json.dumps(rec))
    with pytest.raises(ValueError, match='restart the service'):
        e.apply('fast')


def test_efficient_mode_requires_scoped_measured_energy(tmp_path):
    import pytest
    e = make_engine(tmp_path)
    p = Path(e.config['recommendation_file']); rec = json.loads(p.read_text())
    rec['modes']['efficient']['metrics']['energy_channel'] = None
    p.write_text(json.dumps(rec))
    with pytest.raises(ValueError, match='measured tokens/J'):
        e.apply('efficient')


def test_qairt_bundle_apply_and_baseline_keep_compiled_context(tmp_path, monkeypatch):
    import pytest
    import turbo.native as native
    from turbo.tuning import _sha256
    e = make_engine(tmp_path)
    bundle = tmp_path/'bundle'; bundle.mkdir()
    (bundle/'weights.bin').write_bytes(b'compiled weights')
    (bundle/'genie_config.json').write_text(json.dumps({'dialog':{'context':{'size':2048},
        'engine':{'model':{'binary':{'ctx-bins':['weights.bin']}}}}}))
    e.config['models']['small'].update(path=str(bundle),plugin='qairt',compiled_contexts=[2048])
    p=Path(e.config['recommendation_file']); rec=json.loads(p.read_text())
    rec.update(model_sha256=_sha256(bundle),plugin='qairt')
    rec['modes']['fast'].update(device='npu',threads=0,context=2048)
    p.write_text(json.dumps(rec))
    assert e.apply('baseline')['config']=={'device':'npu','threads':0,'context':2048}
    assert e.apply('fast')['config']=={'device':'npu','threads':0,'context':2048}
    captured={}
    class FakeModel:
        def __init__(self, runtime, path, **kwargs): captured.update(kwargs)
    monkeypatch.setattr(native,'NativeRuntime',lambda _: object())
    monkeypatch.setattr(native,'NativeModel',FakeModel)
    e.load('small')
    assert captured['plugin']=='qairt' and captured['context']==2048 and captured['threads']==0
    (bundle/'weights.bin').write_bytes(b'replaced weights')
    with pytest.raises(ValueError,match='different model weights'): e.apply('fast')
