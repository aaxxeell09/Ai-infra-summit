import hashlib
import json
from pathlib import Path
from turbo.service import Engine
from turbo.secretary import create_fixture,execute_tool,grade_task,load_tasks


def make_engine(tmp_path):
    model = tmp_path/'model.gguf'; model.write_bytes(b'test weights')
    rec = tmp_path/'rec.json'
    rec.write_text(json.dumps({'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'scope':{'evidence':'test','quality_calibrated':False},'modes':{'fast':{'device':'cpu','threads':10,'context':4096,'metrics':{'decode_tps':90,'tokens_per_joule':1.4}},'efficient':{'device':'npu','threads':0,'context':4096,'metrics':{'decode_tps':36,'tokens_per_joule':2.1}}}}))
    return Engine({'models':{'small':{'path':str(model)}},'default':'small','recommendation_file':str(rec),'data_dir':str(tmp_path/'demo')})


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
