"""Commissioning tests inject all execution; never construct NativeRuntime."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
from turbo.optimizer import commissioning as c
from turbo.experiments import archive_lock,write_json


def config(tmp_path):
    model=tmp_path/'model';model.mkdir();(model/'weights.bin').write_bytes(b'synthetic')
    sdk=tmp_path/'sdk';sdk.mkdir();(sdk/'library.dll').write_bytes(b'synthetic')
    path=tmp_path/'config.json';path.write_text(json.dumps({'backend':'qairt_npu','model_path':str(model),'sdk_dir':str(sdk)}))
    return path


def test_plan_has_unavailable_typed_metrics_and_no_native_import(tmp_path,monkeypatch):
    path=config(tmp_path)
    monkeypatch.setitem(sys.modules,'turbo.native',None)
    out=c.commission(path,output=tmp_path/'commissioning.json')
    assert out['attempts']==[] and out['energy_comparable'] is False
    for value in out['metrics'].values():
        assert value['value'] is None and value['source']=='unavailable'
        assert value['unit'] and value['timestamp'] and value['model_config_sha256']


def test_injected_runner_records_scopes_and_resume_does_not_repeat_success(tmp_path):
    path=config(tmp_path);calls=[]
    def runner(step,attempt,config_path):
        calls.append(step)
        return {'metrics':{name:True if c.METRICS[name][0]=='boolean' else 3.5 for name in c.STEPS[step]}}
    output=tmp_path/'commissioning.json';archives=tmp_path/'experiments'
    first=c.commission(path,output=output,runner=runner,archives=archives,inspect_artifacts=True)
    assert len(calls)==len(c.STEPS)
    original=[(Path(a['path'])/'result.json').read_bytes() for a in first['attempts']]
    c.commission(path,output=output,runner=runner,archives=archives,resume=True,inspect_artifacts=True)
    assert len(calls)==len(c.STEPS)
    assert original==[(Path(a['path'])/'result.json').read_bytes() for a in first['attempts']]
    assert c.load_costs(json.loads(path.read_text()),output)=={'S1':3.5,'S2':3.5,'S4':3.5,'S5':3.5}
    (tmp_path/'model'/'weights.bin').write_bytes(b'changed')
    assert c.load_costs(json.loads(path.read_text()),output)=={}


def test_failed_attempt_retained_and_retry_gets_new_directory(tmp_path):
    path=config(tmp_path);output=tmp_path/'commissioning.json'
    def fail(*args):raise subprocess.TimeoutExpired(['synthetic'],1)
    first=c.commission(path,output=output,runner=fail,steps=['s1'],archives=tmp_path/'exp')
    original=Path(first['attempts'][0]['path'])/'result.json';raw=original.read_bytes()
    second=c.commission(path,output=output,runner=lambda *a:{'metrics':{'s1_wall_s':4}},steps=['s1'],archives=tmp_path/'exp',resume=True)
    assert original.read_bytes()==raw and len(second['attempts'])==2
    assert second['metrics']['s1_wall_s']['value']==4


def test_interrupted_attempt_blocks_until_acknowledged(tmp_path):
    path=config(tmp_path);output=tmp_path/'commissioning.json'
    def crash(*args):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):c.commission(path,output=output,runner=crash,steps=['s1'],archives=tmp_path/'exp')
    with pytest.raises(RuntimeError,match='surviving child'):
        c.commission(path,output=output,runner=crash,steps=['s1'],archives=tmp_path/'exp',resume=True)
    final=c.commission(path,output=output,runner=lambda *a:{'metrics':{'s1_wall_s':1}},steps=['s1'],archives=tmp_path/'exp',resume=True,acknowledge_interrupted=True)
    assert len(final['attempts'])==2 and final['attempts'][0]['status']=='running'
    assert final['attempts'][1]['acknowledged_interrupted']


def test_shared_tracker_mutex_blocks_diagnostics_but_never_api(tmp_path):
    path=config(tmp_path);archives=tmp_path/'exp';calls=[]
    def runner(step,*args):calls.append(step);return {'metrics':{c.STEPS[step][0]:1}}
    with archive_lock(archives,'hardware-execution'):
        result=c.commission(path,output=tmp_path/'commissioning.json',runner=runner,steps=['s1','proposer_api'],archives=archives)
    assert calls==['proposer_api']
    assert result['attempts'][0]['status']=='failed'
    assert result['metrics']['s1_wall_s']['source']=='unavailable'


def test_missing_api_is_unavailable_and_no_subprocess(tmp_path,monkeypatch):
    monkeypatch.setattr(c,'child_command',lambda *a,**k:pytest.fail('Must not launch'))
    result=c.TargetRunner()('proposer_api',tmp_path,config(tmp_path))
    assert result['metrics']=={}


def test_real_routes_use_existing_probes_without_executing_them(tmp_path,monkeypatch):
    path=config(tmp_path);seen=[]
    monkeypatch.setattr(c,'child_command',lambda command,*a,**k:seen.append(command))
    runner=c.TargetRunner()
    assert 's1_wall_s' in runner('s1',tmp_path,path)['metrics']
    assert 's2_8_wall_s' in runner('s2',tmp_path,path)['metrics']
    assert seen[0][seen[0].index('--diagnostic-worker')+1]=='s1'
    assert seen[1][seen[1].index('--diagnostic-worker')+1]=='s2'
    assert all('heldout' not in str(command) for command in seen)


def test_invalid_metric_cannot_be_measured(tmp_path):
    path=config(tmp_path)
    result=c.commission(path,output=tmp_path/'commissioning.json',runner=lambda *a:{'metrics':{'s1_wall_s':float('nan')}},steps=['s1'],archives=tmp_path/'exp')
    assert result['attempts'][0]['status']=='failed' and result['metrics']['s1_wall_s']['value'] is None


def test_real_diagnostic_worker_owns_common_mutex_and_uses_existing_probe(tmp_path,monkeypatch):
    import runpy
    archives=tmp_path/'experiments';seen=[]
    def fake_probe(path,**kwargs):
        seen.append(path)
        with pytest.raises(TimeoutError):
            with archive_lock(archives,'hardware-execution',timeout=.01):pass
        return {}
    monkeypatch.setattr(runpy,'run_path',fake_probe)
    c.diagnostic_worker('s1',config(tmp_path),tmp_path/'out.json',archives=archives)
    assert seen==[str(c.ROOT/'scripts/backend_smoke.py')]


def test_plan_can_resume_into_artifact_bound_execution(tmp_path):
    path=config(tmp_path);out=tmp_path/'commissioning.json'
    c.commission(path,output=out)
    result=c.commission(path,output=out,resume=True,inspect_artifacts=True,steps=['s1'],
                        archives=tmp_path/'experiments',runner=lambda *a:{'metrics':{'s1_wall_s':1}})
    assert result['identity']['model_sha256'] and result['metrics']['s1_wall_s']['source']=='measured'


def test_scheduler_consumes_bound_stage_cost_without_claiming_candidate_measurement(tmp_path):
    import io
    from turbo.optimizer import scheduler, state, hardware_queue, budget, console
    path=config(tmp_path);out=tmp_path/'commissioning.json'
    c.commission(path,output=out,runner=lambda *a:{'metrics':{'s1_wall_s':7}},
                 steps=['s1'],archives=tmp_path/'experiments',inspect_artifacts=True)
    control=json.loads(path.read_text())
    session=state.new_session(backend='qairt_npu',split='development',budget_minutes=10,
                              control_name='control',control_config=control)
    engine=scheduler.Scheduler(session,backend='qairt_npu',budget=budget.Budget(10),
               queue=hardware_queue.HardwareQueue(),executor=lambda *a:pytest.fail('No execution'),
               console=console.Console(stream=io.StringIO()),commissioning_path=out)
    value,label=engine.estimated_cost({'config':control},'S1')
    assert value==7 and 'candidate estimate' in label
    assert engine.estimated_cost({'config':control},'S3')[0]==180
    assert session['cost_model']['commissioned_stage_reference_seconds']=={'S1':7}


def test_missing_target_artifacts_record_failed_attempt_without_runner(tmp_path):
    path=tmp_path/'config.json';path.write_text(json.dumps({'backend':'qairt_npu','model_path':str(tmp_path/'missing'),'sdk_dir':str(tmp_path/'missing-sdk')}))
    result=c.commission(path,output=tmp_path/'commissioning.json',steps=['s1'],
                        runner=lambda *a:pytest.fail('No launch with missing artifacts'),inspect_artifacts=True)
    assert result['attempts'][0]['status']=='failed'
    assert result['metrics']['s1_wall_s']['value'] is None


def test_dev35_composes_tracker_without_taking_a_second_lock(tmp_path,monkeypatch):
    import turbo.experiments as experiments
    archive=tmp_path/'archive';archive.mkdir()
    write_json(archive/'manifest.json',{'status':'completed_qualified','case_set_complete':True})
    captured=[]
    def tracker(name,path,**kwargs):
        captured.append(kwargs)
        # This is the lock the real tracker takes internally; TargetRunner must
        # not already own it in this process.
        with archive_lock(kwargs['root'],'hardware-execution',timeout=.01):pass
        return archive
    monkeypatch.setattr(experiments,'run',tracker)
    runner=c.TargetRunner(archives=tmp_path/'experiments')
    result=runner('dev35',tmp_path,config(tmp_path))
    assert captured[0]['dataset']=='dev' and 'dev35_wall_s' in result['metrics']
    write_json(archive/'manifest.json',{'status':'completed_diagnostic','case_set_complete':False})
    with pytest.raises(RuntimeError,match='incomplete'):runner('dev35',tmp_path,tmp_path/'config.json')
