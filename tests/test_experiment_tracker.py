import json
from pathlib import Path
import subprocess
import sys

import pytest
from turbo import experiments as e


def report():
    return dict(schema_version=2,status='measured',benchmark_version='secretary-eval-v2',dirty=True,
                git_commit='historical',model_label='test-model',config={'path':r'C:\modèles\模型'},
                results=[dict(id=f'dev_{i}',case_sha256=str(i),split='development',task_success=i==0,
                              invalid_output=i==1,no_action_correct=False,expected_tool='read_file',
                              latency_ms=10+i,task_latency_ms=20+i,failure_reasons=[])
                         for i in range(3)])


def telemetry():
    return dict(measurement_scope='full_process_energy',raw_before={'monotonic_s':1,'channels_pwh':{'SYS':100}},
                raw_after={'monotonic_s':31,'channels_pwh':{'SYS':10000000100}},declared_counter_resolution_s=1)


def source(tmp_path):
    p=tmp_path/'historical.json';p.write_text(json.dumps(report()),encoding='utf-8');return p


def test_unique_ids_folder_collision_and_portable_names(tmp_path):
    a=e.reserve(tmp_path,'one');b=e.reserve(tmp_path,'one')
    assert a.name=='EXP-001_one' and b.name=='EXP-002_one'
    (tmp_path/'EXP-003_existing').mkdir()
    assert e.reserve(tmp_path,'four').name=='EXP-004_four'
    with pytest.raises(ValueError):e.reserve(tmp_path,'../escape')


def test_stale_lock_file_does_not_block_new_run(tmp_path):
    (tmp_path/'.allocation.lock').write_text('existing')
    assert e.reserve(tmp_path,'recovered').name=='EXP-001_recovered'


def test_backfill_idempotent_preserves_sources_and_historical_dirty(tmp_path):
    p=source(tmp_path);original=p.read_bytes();root=tmp_path/'archives'
    a=e.backfill(p,root);assert e.backfill(p,root)==a
    assert p.read_bytes()==original and (a/'result.json').read_bytes()==original
    m=e.read_json(a/'manifest.json')
    assert m['dirty'] is True and m['qualification_status']=='historical_diagnostic'
    assert m['git_commit']=='historical' and e.verify(a)==[]
    for required in ('KPI.txt','kpi.json','config.json','command.txt','hypothesis.md','change-from-previous.md',
                     'environment.json','git-head.txt','git-status.txt','git-diff.patch','stdout.log','stderr.log','reproduce.txt'):
        assert (a/required).is_file()
    assert (a/'reproduce.txt').read_text().strip()=='NOT_RECORDED'


def test_ledger_appends_and_incomplete_remains_visible(tmp_path):
    p=source(tmp_path);root=tmp_path/'archives';e.backfill(p,root)
    q=e.reserve(root,'incomplete')
    rows=e.ledger(root)
    assert len(rows)==2 and rows[1]['status']=='incomplete'
    assert 'EXP-002' in (root/'EXPERIMENT_LEDGER.md').read_text()
    assert e.verify(q)


def test_tampering_and_extra_files_fail_and_suppress_ledger_kpis(tmp_path):
    archive=e.backfill(source(tmp_path),tmp_path/'archives')
    (archive/'result.json').write_text('{}')
    assert e.verify(archive)
    rows=e.ledger(archive.parent)
    assert rows[0]['success_rate_pct'] is None
    assert rows[0]['status']=='integrity_failure'
    assert rows[0]['qualification']=='unqualified_integrity_failure'
    assert 'integrity_failure' in (archive.parent/'EXPERIMENT_LEDGER.md').read_text()
    with pytest.raises(FileExistsError):e.seal(archive)


def test_checksum_manifest_inventory_unicode(tmp_path):
    p=e.reserve(tmp_path,'unicode');meta=e.initialize(p,{'change':'Unicode inventory'})
    (p/'é 中文.txt').write_text('hello',encoding='utf-8')
    e.finish(p,meta,result=report());assert e.verify(p)==[]
    (p/'extra.txt').write_text('x');assert e.verify(p)


@pytest.mark.parametrize('raw',[b'{}',b'\xef\xbb\xbf{}','{"x":"C:\\\\modèles\\\\模型"}'.encode()])
def test_utf8_bom_windows_config(tmp_path,raw):
    p=tmp_path/'配置.json';p.write_bytes(raw);assert isinstance(e.read_json(p),dict)


@pytest.mark.parametrize('raw',['{','NaN','Infinity'])
def test_malformed_and_nonfinite_json(tmp_path,raw):
    p=tmp_path/'bad.json';p.write_text(raw)
    with pytest.raises(ValueError):e.read_json(p)


def test_missing_energy_zero_correct_and_all_attempts_numerator():
    r=report();k=e.kpis(r);assert k['gross_sys_j_per_correct_task'] is None
    k=e.kpis(r,telemetry());assert k['gross_sys_j']==36 and k['gross_sys_j_per_correct_task']==36
    assert k['total_tasks']==3 and k['correct_tasks']==1
    for row in r['results']:row['task_success']=False
    assert e.kpis(r,telemetry())['gross_sys_j_per_correct_task'] is None


def test_inference_never_becomes_e2e():
    r=report()
    for row in r['results']:row.pop('task_latency_ms')
    k=e.kpis(r);assert k['median_e2e_ms'] is None and k['inference_latency_ms']['median']==11


def test_invalid_not_complement_of_success():
    k=e.kpis(report());assert k['correct_tasks']==1 and k['invalid_count']==1 and k['total_tasks']==3


def test_invalid_result_flags():
    r=report();r['results'][0]['task_success']=1
    with pytest.raises(ValueError):e.kpis(r)


def test_canonical_artifact_manifest_and_mutation(tmp_path):
    (tmp_path/'nested').mkdir();f=tmp_path/'nested/a.bin';f.write_bytes(b'a')
    before=e.artifact_identity(tmp_path);assert before['files'][0]['path']=='nested/a.bin'
    f.write_bytes(b'b');assert e.artifact_identity(tmp_path)!=before


def setup_run(tmp_path,monkeypatch,dirty=False):
    state=dict(git_commit='synthetic',branch='test',dirty=dirty,git_status=' M file' if dirty else '',git_diff='diff' if dirty else '')
    monkeypatch.setattr(e,'git_state',lambda *args:state.copy())
    config=tmp_path/'配置.json';config.write_bytes(b'\xef\xbb\xbf{"note":"snapshot"}')
    return config,tmp_path/'archives'


def test_dirty_rejection_before_archive_creation(tmp_path,monkeypatch):
    config,root=setup_run(tmp_path,monkeypatch,True)
    with pytest.raises(ValueError,match='Dirty'):e.run('dirty',config,root=root,change='x',hypothesis='y',command_override=[sys.executable,'-c','pass'])
    assert not root.exists()


def test_diagnostic_dirty_subprocess_failure_preserves_snapshot(tmp_path,monkeypatch):
    config,root=setup_run(tmp_path,monkeypatch,True)
    p=e.run('failure',config,root=root,change='changes',hypothesis='because',diagnostic_dirty=True,
            command_override=[sys.executable,'-c','import sys;print("partial");sys.exit(3)'])
    m=e.read_json(p/'manifest.json');assert m['status']=='failed' and m['qualification_status']=='diagnostic_dirty'
    assert (p/'config.json').read_bytes()==config.read_bytes()
    assert 'partial' in (p/'stdout.log').read_text()
    assert m['change']=='changes' and e.verify(p)==[]


def test_timeout_preserves_logs_and_allocates_new_id(tmp_path,monkeypatch):
    config,root=setup_run(tmp_path,monkeypatch)
    p=e.run('timeout',config,root=root,change='x',hypothesis='y',timeout=.1,
            command_override=[sys.executable,'-c','import time;print("start",flush=True);time.sleep(5)'])
    assert e.read_json(p/'manifest.json')['status']=='timeout'
    assert 'start' in (p/'stdout.log').read_text() and e.verify(p)==[]
    assert e.reserve(root,'next').name.startswith('EXP-002')


def test_parent_link_and_missing_parent_rejection(tmp_path,monkeypatch):
    config,root=setup_run(tmp_path,monkeypatch)
    parent=e.backfill(source(tmp_path),root)
    p=e.run('child',config,root=root,change='one factor',hypothesis='test',control='EXP-001',command_override=[sys.executable,'-c','pass'])
    assert e.read_json(p/'manifest.json')['control_experiment']=='EXP-001'
    with pytest.raises(ValueError,match='Control'):e.run('bad',config,root=root,change='x',hypothesis='y',control='EXP-999')


def test_backfill_malformed_never_creates_archive(tmp_path):
    p=tmp_path/'bad.json';p.write_text('{')
    with pytest.raises(ValueError):e.backfill(p,tmp_path/'archives')
    assert not (tmp_path/'archives').exists()
