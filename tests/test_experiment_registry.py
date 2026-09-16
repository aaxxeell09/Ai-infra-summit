"""Synthetic bookkeeping only: no model/evaluator/archive execution."""
import copy
import json
import multiprocessing
from pathlib import Path

import pytest
from turbo import experiment_registry as R
from scripts.experiment_registry import main


def event(node='node-1', **changes):
    return dict(node_id=node, parent_ids=[], config_hash='a'*64, code_sha='b'*40,
                protocol_version='synthetic-test-v1', hypothesis='Synthetic test only',
                stage='S1', status='DISCOVERED', decision='schedule', decision_reason='Test evidence', **changes)


def test_append_history_frontier_and_unknowns(tmp_path):
    first=R.append_event(tmp_path,event())
    original=(tmp_path/'events/000000000001.json').read_bytes()
    change=event(); change['status']='OBSERVED'; change['stage']='S2'
    second=R.append_event(tmp_path,change)
    assert second['previous_sha256']==first['sha256']
    assert (tmp_path/'events/000000000001.json').read_bytes()==original
    assert all(v is None for v in second['event']['metrics'].values())
    assert R.current_frontier(tmp_path)==[second]
    change['status']='PROMOTED'; R.append_event(tmp_path,change)
    assert R.current_frontier(tmp_path)==[]
    assert all(e['qualified'] is False for e in R.read_events(tmp_path))


def test_lineage_and_identity(tmp_path):
    child=event('child'); child['parent_ids']=['node-1']
    with pytest.raises(ValueError): R.append_event(tmp_path,child)
    R.append_event(tmp_path,event()); R.append_event(tmp_path,child)
    altered=event(); altered['config_hash']='c'*64
    with pytest.raises(ValueError,match='immutable'): R.append_event(tmp_path,altered)
    altered=event(); altered['parent_ids']=['child']
    with pytest.raises(ValueError,match='immutable'): R.append_event(tmp_path,altered)


def test_event_id_retry_is_idempotent(tmp_path):
    value=event(event_id='request-1')
    first=R.append_event(tmp_path,value)
    assert R.append_event(tmp_path,value)==first
    value['decision_reason']='changed'
    with pytest.raises(ValueError,match='Conflicting'): R.append_event(tmp_path,value)
    assert len(R.read_events(tmp_path))==1


@pytest.mark.parametrize('change', [
    {'metrics':{'energy_j':0}}, {'metrics':{'latency_ms':float('nan')}},
    {'metrics':{'correctness':2},'metric_boundaries':{'correctness':'fraction'}},
    {'repeat_count':True}, {'parent_ids':{}}, {'status':'WINNER'},
    {'qualified':True}, {'code_sha':'unknown'}, {'event_id':[]},
    {'metrics':{'made_up':1}}, {'metric_boundaries':[]},
])
def test_invalid_fail_closed(tmp_path,change):
    value=event(); value.update(change)
    with pytest.raises(ValueError): R.append_event(tmp_path,value)
    assert not list(tmp_path.glob('events/*.json'))


def test_metrics_keep_explicit_boundaries(tmp_path):
    value=event(metrics={'energy_j':1.5},metric_boundaries={'energy_j':'synthetic total process example, not measured'})
    saved=R.append_event(tmp_path,value)
    assert saved['event']['metrics']['energy_j']==1.5
    assert saved['event']['metrics']['ttft_ms'] is None


def test_failed_publication_preserves_history_and_allows_retry(tmp_path,monkeypatch):
    first=R.append_event(tmp_path,event())
    original=R.os.link
    def fail(*args): raise OSError('synthetic crash before publish')
    monkeypatch.setattr(R.os,'link',fail)
    with pytest.raises(OSError): R.append_event(tmp_path,event('second'))
    assert R.read_events(tmp_path)==[first]
    monkeypatch.setattr(R.os,'link',original)
    assert R.append_event(tmp_path,event('second'))['sequence']==2


def test_corruption_and_gap_not_silently_recovered(tmp_path):
    R.append_event(tmp_path,event())
    path=tmp_path/'events/000000000001.json'
    contents=json.loads(path.read_text()); contents['event']['status']='CONFIRMED'
    path.write_text(json.dumps(contents))
    with pytest.raises(ValueError,match='mismatch'): R.read_events(tmp_path)
    with pytest.raises(ValueError): R.append_event(tmp_path,event('second'))
    path.rename(tmp_path/'events/000000000002.json')
    with pytest.raises(ValueError,match='gap'): R.read_events(tmp_path)


def _worker(root,index):
    R.append_event(root,event('parallel-'+str(index)))


def test_concurrent_append_unique_sequence(tmp_path):
    context=multiprocessing.get_context('spawn')
    workers=[context.Process(target=_worker,args=(str(tmp_path),i)) for i in range(4)]
    for worker in workers: worker.start()
    for worker in workers:
        worker.join(15); assert worker.exitcode==0
    assert len(R.read_events(tmp_path))==4


def test_cli_frontier(tmp_path,capsys):
    source=tmp_path/'input.json'; source.write_text(json.dumps(event()))
    root=tmp_path/'registry'
    assert main(['--root',str(root),'append','--event',str(source)])==0
    capsys.readouterr()
    assert main(['--root',str(root),'frontier'])==0
    assert json.loads(capsys.readouterr().out)[0]['event']['node_id']=='node-1'


def test_uncertain_acknowledgement_recovers_by_event_id(tmp_path,monkeypatch):
    value=event(event_id='stable-request')
    original=R.fsync_directory
    def fail_after_publish(path):
        if Path(path).name=='events':
            raise OSError('synthetic crash after complete publication')
        return original(path)
    monkeypatch.setattr(R,'fsync_directory',fail_after_publish)
    with pytest.raises(OSError): R.append_event(tmp_path,value)
    monkeypatch.setattr(R,'fsync_directory',original)
    recovered=R.append_event(tmp_path,value)
    assert recovered['sequence']==1 and len(R.read_events(tmp_path))==1


def test_orphan_temporary_file_never_becomes_evidence(tmp_path):
    directory=tmp_path/'events'; directory.mkdir()
    (directory/'.pending-crashed').write_bytes(b'{partial')
    assert R.read_events(tmp_path)==[]
    assert R.append_event(tmp_path,event())['sequence']==1
