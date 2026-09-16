"""Archive integrity/concurrency and supervised failure tests; no inference hardware."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from turbo import experiments as e


def report():
    return {'schema_version': 2, 'status': 'measured', 'results': [
        {'task_success': True, 'invalid_output': False, 'task_latency_ms': 12}]}


def source(tmp_path):
    path=tmp_path/'source.json'
    path.write_bytes(json.dumps(report()).encode())
    return path


def test_concurrent_backfill_is_idempotent_and_ledger_consistent(tmp_path):
    src=source(tmp_path); root=tmp_path/'archives'
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths=list(pool.map(lambda _:e.backfill(src,root),range(12)))
    assert len(set(paths))==1
    assert len(e.archives(root))==1
    assert e.verify(paths[0])==[]
    assert len(e.ledger(root))==1


def test_concurrent_reservations_unique(tmp_path):
    with ThreadPoolExecutor(max_workers=6) as pool:
        paths=list(pool.map(lambda n:e.reserve(tmp_path,'n'+str(n)),range(12)))
    assert len(set(paths))==12
    assert {int(p.name.split('_')[0][4:]) for p in paths}==set(range(1,13))


def test_os_lock_released_on_crash_and_wait_is_bounded(tmp_path):
    code='from turbo.experiments import archive_lock; import os,sys\nwith archive_lock(sys.argv[1], "allocation"):\n os._exit(7)\n'
    child=subprocess.run([sys.executable,'-c',code,str(tmp_path)],cwd=e.ROOT,timeout=5)
    assert child.returncode==7
    with e.archive_lock(tmp_path,'allocation',timeout=.1):
        with pytest.raises(TimeoutError,match='lock deadline'):
            with e.archive_lock(tmp_path,'allocation',timeout=.05): pass
    assert e.reserve(tmp_path,'after-crash').is_dir()


def test_backfill_parses_captured_bytes_only(tmp_path,monkeypatch):
    src=source(tmp_path); raw=src.read_bytes(); reads=[]
    original=Path.read_bytes
    def read(path):
        if path==src:
            reads.append(path)
            value=original(path)
            path.write_bytes(b'{"results":[]}')
            return value
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    archive=e.backfill(src,tmp_path/'archives')
    assert len(reads)==1
    assert (archive/'result.json').read_bytes()==raw
    assert (archive/'source-artifacts'/src.name).read_bytes()==raw
    assert e.read_json(archive/'kpi.json')['total_tasks']==1


def test_empty_and_symlinked_checksum_manifest_rejected(tmp_path):
    empty=tmp_path/'EXP-001_empty';empty.mkdir()
    (empty/'artifact-hashes.sha256').write_bytes(b'')
    assert 'Missing required archive structure' in e.verify(empty)
    target=tmp_path/'hashes';target.write_bytes(b'')
    (empty/'artifact-hashes.sha256').unlink()
    try: (empty/'artifact-hashes.sha256').symlink_to(target)
    except OSError: pytest.skip('Symlink creation unavailable')
    assert 'symlink' in ' '.join(e.verify(empty))


def test_initialize_cannot_modify_sealed_archive(tmp_path):
    archive=e.backfill(source(tmp_path),tmp_path/'archives')
    before={p.name:p.read_bytes() for p in archive.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):e.initialize(archive,{'change':'overwrite'})
    assert before=={p.name:p.read_bytes() for p in archive.iterdir() if p.is_file()}


def test_abandoned_backfill_gets_new_archive(tmp_path):
    src=source(tmp_path);root=tmp_path/'archives'
    fingerprint=e.digest({'result':e.sha(src),'telemetry':None})
    abandoned=e.reserve(root,'abandoned')
    e.initialize(abandoned,{'source_fingerprint':fingerprint})
    original=(abandoned/'manifest.json').read_bytes()
    archive=e.backfill(src,root)
    assert archive!=abandoned
    assert (abandoned/'manifest.json').read_bytes()==original
    assert not e.verify(archive)


def setup_run(tmp_path,monkeypatch):
    monkeypatch.setattr(e,'capture_environment',lambda:{'capture_scope':'synthetic test only'})
    import eval.validate_dataset as validator
    monkeypatch.setattr(validator,'validate',lambda:{})
    monkeypatch.setattr(e,'git_state',lambda repo:{'git_commit':'abc','dirty':False,'branch':'main','git_status':'','git_diff':''})
    config=tmp_path/'config.json';config.write_text('{}')
    return config


def test_supervisor_failure_kills_child_and_archives_energy(tmp_path,monkeypatch):
    import turbo.telemetry as telemetry
    config=setup_run(tmp_path,monkeypatch)
    class Meter:
        calls=0
        closed=False
        def sample(self):
            self.calls+=1
            return {'channels_pwh':{'SYS':self.calls*1000000000},'monotonic_s':self.calls*10,'error':None}
        def close(self):self.closed=True
    meter=Meter()
    monkeypatch.setattr(telemetry,'EnergyMeter',lambda:meter)
    monkeypatch.setattr(telemetry,'power_snapshot',lambda:{'ac_line_status':'ac'})
    write=e.write_json; injected=[]
    def fail_once(path,value):
        if path.name=='manifest.json' and value.get('child_pid') and not injected:
            injected.append(True)
            raise OSError('synthetic manifest write failure')
        return write(path,value)
    monkeypatch.setattr(e,'write_json',fail_once)
    popen=e.subprocess.Popen; children=[]
    def launch(*args,**kwargs):
        proc=popen(*args,**kwargs);children.append(proc);return proc
    monkeypatch.setattr(e.subprocess,'Popen',launch)
    archive=e.run('failure',config,root=tmp_path/'archives',change='test',hypothesis='test',
                  command_override=[sys.executable,'-c','import time;time.sleep(30)'],capture_energy=True)
    assert children[0].poll() is not None
    assert meter.calls==2 and meter.closed
    assert e.read_json(archive/'manifest.json')['status']=='failed'
    assert e.read_json(archive/'telemetry.json')['raw_after']['channels_pwh']['SYS']==2000000000
    assert not e.verify(archive)


def test_probe_cannot_be_control(tmp_path,monkeypatch):
    config=setup_run(tmp_path,monkeypatch)
    probe=tmp_path/'probe.json';probe.write_text('{"kind":"counter_update_probe"}')
    root=tmp_path/'archives';archive=e.backfill(probe,root)
    with pytest.raises(ValueError,match='completed measured task report'):
        e.run('controlled',config,root=root,change='test',hypothesis='test',
              control=archive.name.split('_')[0],command_override=[sys.executable,'-c','pass'])


def test_raw_energy_is_explicitly_diagnostic_even_with_valid_counter_delta():
    telemetry={'measurement_scope':'full_process_energy',
               'raw_before':{'channels_pwh':{'SYS':1},'monotonic_s':1},
               'raw_after':{'channels_pwh':{'SYS':1000000001},'monotonic_s':11}}
    metric=e.kpis(report(),telemetry)
    assert metric['gross_sys_j_per_correct_task']==pytest.approx(3.6)
    assert metric['energy_qualification']=='diagnostic_uncommissioned'
    assert metric['energy_comparable'] is False


def test_ledger_survives_malformed_manifest_without_trusting_kpis(tmp_path):
    archive=e.reserve(tmp_path,'malformed')
    (archive/'manifest.json').write_text('[]')
    rows=e.ledger(tmp_path)
    assert rows[0]['status']=='incomplete'
    (archive/'manifest.json').write_text('{"primary_kpis":{},"inference_backend":"bad","notes":3}')
    rows=e.ledger(tmp_path)
    assert rows[0]['qualification']=='unqualified_integrity_failure'
    assert rows[0]['success_rate_pct'] is None


@pytest.mark.parametrize('directory', [False, True])
def test_captured_model_digest_matches_existing_runner_algorithm(tmp_path,directory):
    from turbo.tuning import _sha256
    model=tmp_path/'model'
    if directory:
        (model/'nested').mkdir(parents=True)
        (model/'nested'/'weights.bin').write_bytes(b'synthetic shard')
        (model/'config.json').write_bytes(b'{}')
    else: model.write_bytes(b'synthetic gguf')
    snapshot=e.captured_runner_identity(e.ROOT,model,{'model':e.artifact_identity(model)})
    assert snapshot['model_sha256']==_sha256(model)
    assert e.runner_identity_errors(snapshot,snapshot)==[]
    for field in ('model_sha256','evaluator_sha256','application_sources_sha256'):
        forged=dict(snapshot);forged[field]='nonempty-but-wrong'
        assert field in ' '.join(e.runner_identity_errors(forged,snapshot))


@pytest.mark.parametrize('status,incomplete', [('failed',False),('timeout',False),('completed_diagnostic',True)])
def test_partial_attempt_keeps_gross_energy_but_not_complete_denominator(tmp_path,status,incomplete):
    path=e.reserve(tmp_path,'partial')
    metadata=e.initialize(path,{'case_set_complete':not incomplete})
    telemetry={'measurement_scope':'full_process_energy',
               'raw_before':{'channels_pwh':{'SYS':1},'monotonic_s':1},
               'raw_after':{'channels_pwh':{'SYS':1000000001},'monotonic_s':11}}
    e.finish(path,metadata,report(),telemetry,status=status)
    k=e.read_json(path/'kpi.json')
    assert k['gross_sys_j']==pytest.approx(3.6)
    assert k['correct_tasks']==1
    assert k['gross_sys_j_per_correct_task'] is None
    assert k['energy_denominator_complete'] is False
    assert 'Incomplete' in k['energy_unavailable_reason']
    assert not e.verify(path)


def test_sampling_observations_preserved_without_guessing_effective_defaults():
    data=report()
    data['results'][0]['sampling']={'requested_temperature':0,'sdk_top_k':0,'sdk_zero_temperature_uses_default':True}
    observed=e.report_metadata(data)['sampling']
    assert observed['rows_with_sampling']==1
    assert observed['reported_by_case'][0]['sampling']==data['results'][0]['sampling']
    assert observed['effective'] is None and observed['seed'] is None
    data['results'][0]['sampling']['effective']={'temperature':.8,'seed':42}
    observed=e.report_metadata(data)['sampling']
    assert observed['effective']=={'temperature':.8,'seed':42} and observed['seed']==42
    data['results'].append({'id':'missing-observation','task_success':False})
    observed=e.report_metadata(data)['sampling']
    assert observed['effective'] is None and len(observed['effective_by_case'])==1
    assert observed['total_rows']==2 and observed['rows_with_sampling']==1


@pytest.mark.parametrize('forged', [None,'model_sha256','evaluator_sha256'])
def test_run_qualification_checks_captured_identity(tmp_path,monkeypatch,forged):
    import eval.report_validation as validation
    from eval.scoring import load_dataset
    config=setup_run(tmp_path,monkeypatch)
    model=tmp_path/'model.gguf';model.write_bytes(b'synthetic model only')
    sdk=tmp_path/'sdk';sdk.mkdir();(sdk/'geniex.dll').write_bytes(b'synthetic library only')
    settings={'model_path':str(model),'sdk_dir':str(sdk),'backend':'llama_cpp_cpu'}
    config.write_text(json.dumps(settings))
    cases=load_dataset([e.ROOT/'eval/datasets/secretary_dev.json'])
    identities=e.captured_runner_identity(e.ROOT,model,{'model':e.artifact_identity(model)})
    # Isolate source/model binding from the separately tested backend validator.
    monkeypatch.setattr(validation,'backend_identity_errors',lambda *args:[])
    class Child:
        pid=123456789
        returncode=0
        def __init__(self,command,**kwargs): self.command=command
        def poll(self):return 0
        def wait(self,timeout):
            out=Path(self.command[self.command.index('--output-dir')+1]);out.mkdir()
            result={**identities,'schema_version':2,'status':'measured','git_commit':'abc','dirty':False,
                    'config_sha256':e.digest(settings),'dataset_sha256':e.digest(cases),
                    'results':[{'id':c['id'],'case_sha256':e.digest(c),'task_success':True,
                                'invalid_output':False,'task_latency_ms':1} for c in cases]}
            if forged:result[forged]='forged-nonempty-identity'
            (out/'candidate_synthetic.json').write_text(json.dumps(result))
            return 0
    monkeypatch.setattr(e.subprocess,'Popen',Child)
    path=e.run('identity',config,root=tmp_path/'archives',change='synthetic test',hypothesis='identity must match')
    metadata=e.read_json(path/'manifest.json')
    if forged:
        assert metadata['status']=='completed_diagnostic'
        assert metadata['qualification_status']=='unqualified'
        assert forged in ' '.join(metadata['notes'])
    else:
        assert metadata['status']=='completed_qualified'
    assert not e.verify(path)


def test_environment_inventory_uses_bounded_allowlisted_version_commands(monkeypatch):
    calls=[]
    monkeypatch.setattr(e.shutil,'which',lambda name:'/synthetic/'+name)
    def version(command,**kwargs):
        calls.append((command,kwargs))
        return subprocess.CompletedProcess(command,0,command[0].rsplit('/',1)[-1]+' version 1.2.3\nextra\n','')
    monkeypatch.setattr(e.subprocess,'run',version)
    monkeypatch.setenv('PRIVATE_SECRET_FOR_TEST','must not appear')
    result=e.capture_environment()
    assert [cmd for cmd,_ in calls]==[['/synthetic/'+name,'--version'] for name in ('git','node','npm')]
    assert all(kwargs['timeout']==2 and kwargs['check'] is False for _,kwargs in calls)
    assert all(result['software'][name]['status']=='available' for name in ('git','node','npm'))
    assert result['software']['node']['version']=='node version 1.2.3'
    assert result['os'] and result['architecture'] and result['python_version']
    assert 'PRIVATE_SECRET_FOR_TEST' not in json.dumps(result) and 'must not appear' not in json.dumps(result)


def test_environment_missing_and_timed_out_tools_are_nonfatal(monkeypatch):
    monkeypatch.setattr(e.shutil,'which',lambda name:None if name=='node' else '/synthetic/'+name)
    def version(command,**kwargs):
        if command[0].endswith('git'):raise subprocess.TimeoutExpired(command,kwargs['timeout'])
        raise FileNotFoundError('executable disappeared')
    monkeypatch.setattr(e.subprocess,'run',version)
    result=e.capture_environment()
    assert all(item['status']=='unavailable' and item['version'] is None for item in result['software'].values())
    assert '2 seconds' in result['software']['git']['reason']
    assert 'not found' in result['software']['node']['reason']


def test_historical_environment_is_never_filled_from_ingestion_host(tmp_path,monkeypatch):
    monkeypatch.setattr(e,'capture_environment',lambda:pytest.fail('Must not inspect ingestion host'))
    data=report();data['environment']={'machine':'historical recorded machine','python':'old recorded version'}
    src=tmp_path/'historical.json';src.write_text(json.dumps(data))
    archive=e.backfill(src,tmp_path/'archives')
    assert e.read_json(archive/'environment.json')==data['environment']
    assert e.read_json(archive/'manifest.json')['environment']==data['environment']
