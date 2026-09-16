"""Synthetic clocks and executors only: no native model or remote API."""
import copy
import sys
import types
import pytest
from turbo.experiments import digest
from turbo.optimizer.event_coordinator import Coordinator


def candidate(name='a',family='budget'):
    config={'max_tokens':32}
    return dict(candidate_id=name,config=config,config_hash=digest(config),family=family,hypothesis='Synthetic mechanism')


def complete(co,c,stage='S1',job='one',obs=None,control=False):
    co.start(c,stage,job,code_sha='a'*40)
    return co.complete(c,stage,job,obs or {'loaded':True,'outcome':'survive'},control=control,code_sha='a'*40)


def test_heartbeat_preserves_active_and_blocks_mutations(tmp_path):
    clock=[0];co=Coordinator(tmp_path/'state.json',clock=lambda:clock[0]);c=candidate()
    co.start(c,'S1','one');before=co.snapshot()['active'];clock[0]=601
    packet=co.heartbeat();assert packet['kind']=='heartbeat'
    assert co.snapshot()['active']==before
    with pytest.raises(ValueError):co.future('a','reject',reason='cannot cancel running work')
    co.future('b','reorder',reason='future only',priority=2)
    assert co.snapshot()['active']==before
    co.complete(c,'S1','one',{'loaded':True},code_sha='a'*40)


def test_uncertain_restart_never_reruns(tmp_path):
    path=tmp_path/'state.json';co=Coordinator(path);c=candidate();co.start(c,'S1','one')
    co.uncertain(c,'S1','one',RuntimeError())
    resumed=Coordinator(path)
    with pytest.raises(RuntimeError):resumed.recover({'one':{'status':'started'}},code_sha='a'*40)
    with pytest.raises(RuntimeError):resumed.start(c,'S1','two')
    resumed.recover({'one':{'status':'completed','observation':{'loaded':True}}},code_sha='a'*40)
    assert resumed.snapshot()['active'] is None


def test_noise_repeats_are_bounded_and_evidence_retained(tmp_path):
    co=Coordinator(tmp_path/'state.json');control=candidate('control')
    identity={'attempted':1,'rows':[{'case_id':'dev_001','case_sha256':'b'*64}],'protocol_version':'test'}
    for i,count in enumerate([15,17]):complete(co,control,'S4',str(i),dict(identity,correct=count,outcome='survive'),True)
    c=candidate()
    for i,expected in enumerate(['repeat','repeat','hold']):
        complete(co,c,'S4','c'+str(i),{'correct':18,'outcome':'survive'})
        assert co.decide(c,'S4','survive',['existing gate'],observation=dict(identity,correct=18),control_config_hash=control['config_hash'])==expected
    assert len(co.snapshot()['controls']['S4:'+control['config_hash']])==2


def test_future_priority_rejection_and_four_branch_frontier(tmp_path):
    co=Coordinator(tmp_path/'state.json');pool={'S1':[candidate(str(i),str(i)) for i in range(6)]}
    co.future('5','reorder',reason='valuable information',priority=99)
    co.future('4','reject',reason='unsupported')
    assert co.ready(pool,lambda c,s:int(c['candidate_id']))[2]['candidate_id']=='5'
    assert len(co.snapshot()['frontier'])==4
    assert all(row['candidate_id']!='4' for row in co.snapshot()['frontier'])
    assert len(pool['S1'])==6  # Planner never mutates caller or running snapshots.


def test_combination_requires_individual_promotions(tmp_path):
    co=Coordinator(tmp_path/'state.json');c=candidate();c['parent_ids']=['x','y']
    assert co.ready({'S1':[c]},lambda *a:1) is None


def test_registry_outbox_retry_and_missing_dependency_blocks(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'turbo.experiment_registry',None)
    required=Coordinator(tmp_path/'required.json',require_registry=True)
    with pytest.raises(RuntimeError):required.start(candidate(),'S1','one',code_sha='a'*40)
    assert required.snapshot()['active'] is None
    co=Coordinator(tmp_path/'optional.json');complete(co,candidate())
    assert co.snapshot()['registry_delivered']==[]
    saved={}
    def append(root,event):
        assert event['status'] in ('RUNNING','OBSERVED') and event['decision_reason']
        saved[event['event_id']]=event
    monkeypatch.setitem(sys.modules,'turbo.experiment_registry',types.SimpleNamespace(append_event=append))
    co.flush_registry();co.flush_registry();assert len(saved)==2


def test_research_is_planner_context_only(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'turbo.research_inbox',types.SimpleNamespace(list_findings=lambda root:[{'status':'NEW_EXPERIMENT','title':'Idea'}]))
    co=Coordinator(tmp_path/'state.json');co.import_research(tmp_path)
    assert co.snapshot()['planner_inbox']
    assert co.ready({},lambda *a:1) is None


def test_mutated_active_candidate_fails_closed(tmp_path):
    co=Coordinator(tmp_path/'state.json');c=candidate();co.start(c,'S1','one');c['config']['max_tokens']=64
    with pytest.raises(ValueError):co.complete(c,'S1','one',{'loaded':True},code_sha='a'*40)
    assert co.snapshot()['active'] is not None
    co._stop.set()


def test_decision_replay_does_not_spend_repeat_twice(tmp_path):
    co=Coordinator(tmp_path/'state.json');c=candidate();complete(co,c)
    co.future('a','repeat',reason='Explicit future repeat')
    assert co.decide(c,'S1','survive',['gate'],job_id='one')=='repeat'
    count=len(co.snapshot()['events'])
    assert co.decide(c,'S1','survive',['gate'],job_id='one')=='repeat'
    assert len(co.snapshot()['events'])==count


def test_noise_cannot_override_rejection_or_compare_different_cases(tmp_path):
    co=Coordinator(tmp_path/'state.json');control=candidate('control');c=candidate()
    identity={'attempted':1,'rows':[{'case_id':'dev_001','case_sha256':'b'*64}],'protocol_version':'test'}
    for i in range(2):complete(co,control,'S2',str(i),dict(identity,correct=1),True)
    complete(co,c,'S2','c',dict(identity,correct=1))
    assert co.decide(c,'S2','drop',['invalid-output gate'],observation=dict(identity,correct=1),control_config_hash=control['config_hash'])=='reject'
    complete(co,c,'S2','d',dict(identity,correct=1))
    other=dict(identity,rows=[{'case_id':'dev_002','case_sha256':'c'*64}],correct=1)
    assert co.decide(c,'S2','survive',['gate'],observation=other,control_config_hash=control['config_hash'])=='advance'


def test_diagnostic_worker_owns_common_lock(tmp_path,monkeypatch):
    from scripts import autotune_hardware_worker as worker
    from turbo.experiments import archive_lock
    def run(path,run_name):
        with pytest.raises(TimeoutError):
            with archive_lock(tmp_path,'hardware-execution',timeout=0):pass
    monkeypatch.setattr(worker.runpy,'run_path',run)
    assert worker.main(['--archives-root',str(tmp_path),'--script','backend_smoke.py','--','--config','fake'])==0


def test_registry_contract_and_lineage_projection(tmp_path,monkeypatch):
    # Strict contract adapter exercises the actual published registry field rules.
    from turbo.optimizer.event_coordinator import registry_id
    saved={};co=Coordinator(tmp_path/'state.json')
    def append(root,event):
        assert len(event['code_sha'])==40 and len(event['config_hash'])==64
        assert event['status'] in ('RUNNING','OBSERVED','READY','REPEAT_NEEDED','REJECTED','PROMOTED')
        assert event['decision_reason']
        assert all(parent in {e['node_id'] for e in saved.values()} for parent in event['parent_ids'])
        assert all(name in event['metric_boundaries'] for name,value in event['metrics'].items() if value is not None)
        if event['event_id'] in saved:assert event==saved[event['event_id']]
        saved[event['event_id']]=copy.deepcopy(event)
    monkeypatch.setitem(sys.modules,'turbo.experiment_registry',types.SimpleNamespace(append_event=append))
    parent=candidate('parent');complete(co,parent,obs={'attempted':4,'correct':3,'invalid_rate':.25,'median_task_latency_ms':12,'latency_boundary':'warm task'})
    child=candidate('child');child['parent_ids']=['parent'];complete(co,child,job='two')
    events=[event for event in saved.values() if event['status']=='OBSERVED'];assert events[0]['metrics']['correctness']==.75
    assert events[0]['metrics']['latency_ms']==12
    assert events[1]['parent_ids']==[events[0]['node_id']]


def test_opt_in_cli_uses_fake_executors_and_persists_events(tmp_path):
    import subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/autotune.py'),'--dry-run','--mock-llm',
                           '--event-driven','--budget-minutes','8','--max-points','2','--session-dir',str(tmp_path)],
                          capture_output=True,text=True,timeout=30,cwd=root)
    assert result.returncode==0,result.stderr
    co=Coordinator(tmp_path/'coordination.json');state=co.snapshot()
    assert state['active'] is None
    assert any(e['kind']=='hardware_completed' for e in state['events'])
    assert any(e['kind']=='stage_decision' for e in state['events'])


def test_equal_quality_clear_latency_improvement_not_repeated(tmp_path):
    co=Coordinator(tmp_path/'state.json');control=candidate('control');c=candidate()
    identity={'attempted':1,'rows':[{'case_id':'dev_001','case_sha256':'b'*64}],'protocol_version':'test','latency_boundary':'warm task','correct':1}
    for i,latency in enumerate([100,110]):complete(co,control,'S2',str(i),dict(identity,median_task_latency_ms=latency),True)
    complete(co,c,'S2','fast',dict(identity,median_task_latency_ms=50))
    assert co.decide(c,'S2','survive',['gate'],observation=dict(identity,median_task_latency_ms=50),control_config_hash=control['config_hash'])=='advance'
    complete(co,c,'S2','near',dict(identity,median_task_latency_ms=105))
    assert co.decide(c,'S2','survive',['gate'],observation=dict(identity,median_task_latency_ms=105),control_config_hash=control['config_hash'])=='repeat'


def test_tracker_child_lock_rejects_unsupported_scopes_before_io(tmp_path):
    from turbo.experiments import run
    for extra in ({'dataset':'all'},{'capture_energy':True},{'command_override':['untrusted']}):
        with pytest.raises(ValueError,match='Child-owned'):
            run('fake',tmp_path/'missing',change='test',hypothesis='test',child_hardware_lock=True,**extra)


def test_full_worker_development_only_and_shared_lock(tmp_path,monkeypatch):
    from scripts import autotune_hardware_worker as worker
    from turbo.experiments import archive_lock
    seen=[]
    def run(path,run_name):
        seen.append(path)
        with pytest.raises(TimeoutError):
            with archive_lock(tmp_path,'hardware-execution',timeout=0):pass
    monkeypatch.setattr(worker.runpy,'run_path',run)
    assert worker.main(['--archives-root',str(tmp_path),'--script','run_secretary_eval.py','--','--dataset','dev'])==0
    assert '/eval/run_secretary_eval.py' in seen[0]
    with pytest.raises(SystemExit):worker.main(['--archives-root',str(tmp_path),'--script','run_secretary_eval.py','--','--dataset','all'])


def test_rejection_during_control_prevents_treatment_launch(tmp_path):
    from scripts import autotune
    co=Coordinator(tmp_path/'state.json');c=candidate();control=candidate('control');control['is_control']=True
    batch={'id':'B-1','stage':'S2','phase':'explore','waiting':[c],'selected':[c],'control':control}
    state={'workflow':{'active_batch':batch,'pool':{s:[] for s in ('S1','S2','S3','S4','S5')},
                      'confirmations':{},'dev35_observations':{}},'hardware_journal':{},'families':{}}
    calls=[]
    def run(candidate,stage,job_id):
        calls.append(candidate['candidate_id']);co.future('a','reject',reason='New invalidity found while control ran')
        return {'outcome':'survive'}
    engine=types.SimpleNamespace(event_coordinator=co,run_candidate=run,checkpoint=lambda:None)
    assert autotune._run_batch(engine,state,types.SimpleNamespace(stage_limit=1),'S2','explore',types.SimpleNamespace())
    assert calls==['control'] and state['workflow']['active_batch'] is None


@pytest.mark.parametrize('override',['--dataset=heldout','--data','--dat','--dataset'])
def test_worker_rejects_dataset_alias_override(tmp_path,monkeypatch,override):
    from scripts import autotune_hardware_worker as worker
    monkeypatch.setattr(worker.runpy,'run_path',lambda *a,**k:pytest.fail('Must refuse before loading evaluator'))
    args=['--archives-root',str(tmp_path),'--script','run_secretary_eval.py','--','--dataset','dev',override]
    if '=' not in override:args+=['heldout']
    with pytest.raises(SystemExit):worker.main(args)


def test_tracker_constructs_bound_native_child_without_parent_hardware_lock(tmp_path,monkeypatch):
    import json
    from contextlib import contextmanager
    from turbo import experiments as ex
    from eval import validate_dataset
    repo=tmp_path/'repo';(repo/'scripts').mkdir(parents=True)
    (repo/'scripts/autotune_hardware_worker.py').write_text('# synthetic worker, never executed')
    config=tmp_path/'config.json';config.write_text(json.dumps({'model_path':'model','sdk_dir':'sdk','backend':'qairt_npu'}))
    monkeypatch.setattr(ex,'git_state',lambda *a:{'git_commit':'a'*40,'branch':'test','dirty':False,'git_status':'','git_diff':''})
    monkeypatch.setattr(ex,'artifact_identity',lambda *a:{'sha256':'b'*64})
    monkeypatch.setattr(ex,'captured_runner_identity',lambda *a:{})
    monkeypatch.setattr(ex,'capture_environment',lambda:{'source':'synthetic'})
    monkeypatch.setattr(validate_dataset,'validate',lambda:{})
    seen=[];locks=[];original_lock=ex.archive_lock
    @contextmanager
    def lock(root,name,**kwargs):
        locks.append(name)
        with original_lock(root,name,**kwargs):yield
    monkeypatch.setattr(ex,'archive_lock',lock)
    class Child:
        pid=123;returncode=0
        def __init__(self,command,**kwargs):seen.append(command)
        def wait(self,timeout):return 0
        def poll(self):return 0
    monkeypatch.setattr(ex.subprocess,'Popen',Child)
    archive=ex.run('synthetic',config,root=tmp_path/'archives',repo=repo,change='test',hypothesis='test',child_hardware_lock=True)
    assert 'hardware-execution' not in locks
    assert 'autotune_hardware_worker.py' in seen[0][3]
    assert seen[0][seen[0].index('--script')+1]=='run_secretary_eval.py'
    manifest=ex.read_json(archive/'manifest.json')
    assert manifest['hardware_lock_owner']=='native_child'
    assert len(manifest['hardware_worker_sha256'])==64
    assert manifest['status']=='failed'  # No fake report is promoted into evidence.


def test_different_archive_roots_share_one_worker_hardware_slot(tmp_path,monkeypatch):
    from scripts import autotune_hardware_worker as worker
    monkeypatch.setattr(worker,'GLOBAL_HARDWARE_ROOT',tmp_path/'shared-machine-slot')
    def run(path,run_name):
        with pytest.raises(TimeoutError):
            worker.main(['--archives-root',str(tmp_path/'second-archive'),'--script','backend_smoke.py'])
    monkeypatch.setattr(worker.runpy,'run_path',run)
    assert worker.main(['--archives-root',str(tmp_path/'first-archive'),'--script','backend_smoke.py'])==0
