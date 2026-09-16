"""Distinct durable attempts, unchanged treatments; fake subprocesses only."""
import copy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from scripts import autotune
from turbo.optimizer import scheduler, probe, state as S
from test_autotune_scheduler import build


def setup_engine(tmp_path):
    paths = []
    requests = []
    def runner(command, **kwargs):
        assert command[3].endswith('diagnostic_canary.py')
        assert '--size' in command and command[command.index('--size')+1] == '8'
        path = Path(command[command.index('--output')+1])
        requests.append(json.loads((path.parent/'request.json').read_text()))
        paths.append(path)
        # Mirror the actual diagnostic writer's no-overwrite contract.
        with path.open('x', encoding='utf-8') as stream:
            json.dump(probe.canary_result(subset=['synthetic-'+str(i) for i in range(8)],
                      correct=8, attempted=8, invalid=0, median_latency_ms=12), stream)
        return subprocess.CompletedProcess(command, 0, '', '')
    canary = scheduler.canary_executor(seed_label='synthetic-fixed', sizes={'S2':8},
                output_directory=tmp_path/'canaries', config_directory=tmp_path/'configs', runner=runner)
    engine, _, state = build(executor=scheduler.staged_executor(canary=canary))
    engine.checkpoint_path = tmp_path/'session.json'
    engine.checkpoint()
    return engine, state, paths, requests, canary


def test_two_real_batches_same_control_separate_artifacts_and_replay(tmp_path):
    engine, state, paths, requests, _ = setup_engine(tmp_path)
    candidates = engine.admit(engine.generate())[:2]
    original = copy.deepcopy(candidates)
    state['workflow'] = {'pool': {stage: [] for stage in ('S1','S2','S3','S4','S5')},
                         'active_batch': None, 'batch_counter':0,
                         'confirmations':{}, 'dev35_observations':{}}
    state['workflow']['pool']['S2'] = candidates
    args = SimpleNamespace(stage_limit=1)
    assert autotune._run_batch(engine, state, args, 'S2', 'explore', engine.console)
    first = {str(path):path.read_bytes() for path in paths}
    assert autotune._run_batch(engine, state, args, 'S2', 'explore', engine.console)
    assert len(paths) == 4 and len(set(paths)) == 4
    assert all(Path(path).read_bytes() == contents for path,contents in first.items())
    controls = [r for r in requests if r['candidate_id'].startswith('CONTROL-S2-')]
    assert len(controls) == 2
    assert controls[0]['candidate_id'] == controls[1]['candidate_id']
    assert controls[0]['config_hash'] == controls[1]['config_hash'] == state['current_control']['config_hash']
    assert controls[0]['config_sha256'] == controls[1]['config_sha256']
    assert controls[0]['canary_artifact'] != controls[1]['canary_artifact']
    for current, prior in zip(candidates, original):
        assert 'hardware_attempt' not in current
        assert current['config'] == prior['config'] and current['config_hash'] == prior['config_hash']
        assert current['treatment'] == prior['treatment']
    assert paths[1].name == original[0]['candidate_id']+'-S2.json'
    assert paths[3].name == original[1]['candidate_id']+'-S2.json'
    saved = S.load(engine.checkpoint_path)
    resumed, _, _ = build(executor=lambda *a, **k: pytest.fail('Replay must not launch'))
    resumed.state = saved
    for job_id, job in saved['hardware_journal'].items():
        observation = resumed.run_candidate(job['candidate'], job['stage'], job_id=job_id)
        assert observation == job['observation']
    assert len(paths) == 4


def test_stale_legacy_output_rejected_before_launch(tmp_path):
    engine, state, paths, _, canary = setup_engine(tmp_path)
    control = autotune.control_candidate(state, 'S2')
    output = tmp_path/'canaries'/(control['candidate_id']+'-S2.json')
    output.parent.mkdir();output.write_text('{"outcome":"survive"}')
    before = output.read_bytes()
    with pytest.raises(FileExistsError):canary(control, stage='S2')
    assert not paths and output.read_bytes() == before


def test_occupied_durable_attempt_never_reads_stale_output(tmp_path):
    engine, state, paths, _, _ = setup_engine(tmp_path)
    control = autotune.control_candidate(state, 'S2')
    identity = {'session_id':state['session_id'], 'job_id':'B-1:control', 'stage':'S2'}
    directory = tmp_path/'canaries'/'jobs'/S.digest(identity)
    directory.mkdir(parents=True)
    stale = directory/(control['candidate_id']+'-S2.json');stale.write_text('{"correct":8}')
    with pytest.raises(FileExistsError):engine.run_candidate(control, 'S2', job_id='B-1:control')
    assert not paths and stale.read_text() == '{"correct":8}'
    job = S.load(engine.checkpoint_path)['hardware_journal']['B-1:control']
    assert job['status']=='failed' and 'observation' not in job and job['qualified'] is False
    assert engine.queue.active is None


def test_legacy_candidate_name_preserved_but_only_one_launch_allowed(tmp_path):
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        path = Path(command[command.index('--output')+1])
        with path.open('x') as stream:json.dump({'qualified':False}, stream)
        return subprocess.CompletedProcess(command,0,'','')
    engine, _, _ = build()
    candidate = engine.generate()[0]
    executor = scheduler.canary_executor(seed_label='fixed',sizes={'S2':8},output_directory=tmp_path/'out',
                                         config_directory=tmp_path/'configs',runner=runner)
    result = executor(candidate,stage='S2')
    assert Path(result['canary_artifact']) == tmp_path/'out'/(candidate['candidate_id']+'-S2.json')
    with pytest.raises(FileExistsError):executor(candidate,stage='S2')
    assert len(calls)==1


@pytest.mark.parametrize('mode',['crash','timeout','nonzero','missing_output'])
def test_failed_attempt_cannot_relaunch_or_reuse_artifact(tmp_path,mode):
    engine, state, _, _, _ = setup_engine(tmp_path)
    calls=[]
    def runner(command, **kwargs):
        calls.append(command)
        if mode=='crash':raise RuntimeError('synthetic crash')
        if mode=='timeout':raise subprocess.TimeoutExpired(command,1)
        return subprocess.CompletedProcess(command,1 if mode=='nonzero' else 0,'','synthetic failure')
    engine.executor = scheduler.canary_executor(seed_label='fixed',sizes={'S2':8},output_directory=tmp_path/'out',
                                         config_directory=tmp_path/'configs',runner=runner)
    candidate = autotune.control_candidate(state,'S2')
    if mode=='crash':
        with pytest.raises(RuntimeError):engine.run_candidate(candidate,'S2',job_id='B-1:control')
        with pytest.raises(RuntimeError,match='reconciliation'):engine.run_candidate(candidate,'S2',job_id='B-1:control')
    else:
        result=engine.run_candidate(candidate,'S2',job_id='B-1:control')
        assert result['outcome'] in ('failed','timed_out')
        assert engine.run_candidate(candidate,'S2',job_id='B-1:control') == result
    assert len(calls)==1


def test_uncertain_intent_no_launch_and_development_only_stage(tmp_path):
    engine,state,paths,_,canary=setup_engine(tmp_path)
    candidate=autotune.control_candidate(state,'S2')
    state['hardware_journal']['uncertain']={'status':'started'}
    with pytest.raises(RuntimeError,match='reconciliation'):engine.run_candidate(candidate,'S2',job_id='uncertain')
    with pytest.raises(ValueError,match='S2/S3'):canary(candidate,stage='heldout')
    assert not paths


def test_changed_config_snapshot_refused_without_overwrite(tmp_path):
    engine,state,paths,_,_=setup_engine(tmp_path)
    control=autotune.control_candidate(state,'S2')
    engine.run_candidate(control,'S2',job_id='B-1:control')
    config=tmp_path/'configs'/(control['candidate_id']+'.json')
    config.write_text('{}')
    with pytest.raises(ValueError,match='configuration'):engine.run_candidate(control,'S2',job_id='B-2:control')
    assert len(paths)==1 and config.read_text()=='{}'


def test_completed_job_cannot_be_rebound_to_another_config(tmp_path):
    engine,state,paths,_,_=setup_engine(tmp_path)
    control=autotune.control_candidate(state,'S2')
    engine.run_candidate(control,'S2',job_id='B-1:control')
    changed=copy.deepcopy(control)
    changed['config']['max_tokens']=64
    changed['config_hash']=S.config_hash(changed['config'])
    with pytest.raises(ValueError,match='different candidate'):
        engine.run_candidate(changed,'S2',job_id='B-1:control')
    assert len(paths)==1
