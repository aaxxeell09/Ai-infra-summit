import json
import pytest
from turbo.secretary_loop import decode_action, run_feedback


def action(name, **arguments):
    return {'text': '<tool_call>'+json.dumps(dict(name=name, arguments=arguments))+'</tool_call>'}


def test_disabled_does_not_create_workspace_or_infer(tmp_path):
    p=tmp_path/'unused'
    r=run_feedback(lambda _: pytest.fail('must not infer'), 'request', p)
    assert r['status']=='disabled' and not p.exists()


@pytest.mark.parametrize('text', [
    '<tool_call>{"name":"list_files","arguments":{}}</tool_call> trailing',
    '{"name":"list_files","name":"read_file","arguments":{}}',
    '<tool_call>{"name":"list_files","arguments":{}}</tool_call><tool_call>bad</tool_call>',
    '{"name":"move_file","arguments":{"path":"../outside","destination":"new.txt"}}',
    '{"name":"read_file","arguments":{"path":"C:/outside"}}',
    '{"name":"delete_file","arguments":{}}',
])
def test_strict_whole_response_and_paths(text):
    with pytest.raises(ValueError): decode_action(text)


def test_feedback_reaches_next_turn_then_one_verified_mutation(tmp_path):
    answers=iter([action('search_files',query='no synthetic matches here'),
                  action('move_file',path='todo.txt',destination='archive/todo.txt')])
    calls=[]
    def complete(messages):
        if calls:
            assert messages[-1]['role']=='tool'
            assert json.loads(messages[-1]['content'])['result']['matches']==[]
            assert messages[-2]['tool_calls'][0]['id']==messages[-1]['tool_call_id']
        calls.append(1);return next(answers)
    root=tmp_path/'fixture'
    r=run_feedback(complete,'Synthetic request',root,enabled=True)
    assert r['status']=='mutation_executed_awaiting_verification' and r['task_success'] is None
    assert len(r['turns'])==2 and not (root/'todo.txt').exists()
    assert (root/'archive/todo.txt').read_text()=='reply to Dana\nfile expense report\nwater the plant\n'


def test_repeat_stops_without_second_tool_execution(tmp_path):
    r=run_feedback(lambda _:action('list_files'),'Synthetic request',tmp_path/'fixture',enabled=True)
    assert r['status']=='repeated_action' and len(r['turns'])==2
    assert 'tool_result' not in r['turns'][-1]


def test_existing_workspace_refused(tmp_path):
    with pytest.raises(FileExistsError):run_feedback(lambda _:None,'Request',tmp_path,enabled=True)


def test_late_response_cannot_mutate(tmp_path,monkeypatch):
    import turbo.secretary_loop as mod
    clock=iter([0,0,2,2]);monkeypatch.setattr(mod.time,'monotonic',lambda:next(clock))
    root=tmp_path/'fixture'
    r=run_feedback(lambda _:action('move_file',path='todo.txt',destination='archive/todo.txt'),
                   'Request',root,enabled=True,max_seconds=1)
    assert r['status']=='deadline' and (root/'todo.txt').exists()


def test_clarify_and_done_do_not_claim_success(tmp_path):
    for n,response in enumerate([action('clarify',question='Which file?'),{'text':'DONE'}]):
        r=run_feedback(lambda _:response,'Request',tmp_path/str(n),enabled=True)
        assert r['task_success'] is None and r['initial_snapshot']==r['final_snapshot']
