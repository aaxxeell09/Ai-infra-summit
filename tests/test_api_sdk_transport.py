"""Optional installed-SDK wire check: transport is entirely synthetic/offline."""
import pytest


def test_installed_sdk_workspace_header_and_openai_transport(monkeypatch):
    anthropic = pytest.importorskip('anthropic', reason='Optional provider SDK not installed')
    openai = pytest.importorskip('openai', reason='Optional provider SDK not installed')
    # The pinned target SDK versions use httpx2, not legacy httpx.
    httpx = pytest.importorskip('httpx2', reason='Target SDK HTTP transport not installed')
    from turbo.optimizer.proposer import AnthropicClient
    from turbo.optimizer.critic import OpenAIClient
    for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.setenv(key, 'test-not-real-secret')
    monkeypatch.setenv('ANTHROPIC_MODEL','test-claude')
    monkeypatch.setenv('OPENAI_MODEL','test-gpt')
    seen=[]
    def handler(request):
        seen.append((request.url.path,request.headers.get('anthropic-workspace-id')))
        if request.url.path.endswith('/messages'):
            return httpx.Response(200,json={'id':'msg_test','type':'message','role':'assistant',
                'model':'test-claude','content':[{'type':'text','text':'OK'}],
                'stop_reason':'end_turn','stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':1}})
        return httpx.Response(200,json={'id':'chatcmpl_test','object':'chat.completion','created':0,
            'model':'test-gpt','choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}]})
    actual_anthropic=anthropic.Anthropic; actual_openai=openai.OpenAI
    clients=[]
    def construct(actual, options):
        client=actual(**options,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        clients.append(client)
        return client
    monkeypatch.setattr(anthropic,'Anthropic',lambda **kw:construct(actual_anthropic,kw))
    monkeypatch.setattr(openai,'OpenAI',lambda **kw:construct(actual_openai,kw))
    try:
        for workspace in (None,'workspace-test'):
            if workspace:monkeypatch.setenv('ANTHROPIC_WORKSPACE_ID',workspace)
            else:monkeypatch.delenv('ANTHROPIC_WORKSPACE_ID',raising=False)
            assert AnthropicClient().complete('s','u',timeout_s=1)=='OK'
        assert OpenAIClient().complete('s','u',timeout_s=1)=='OK'
        assert seen==[('/v1/messages',None),('/v1/messages','workspace-test'),('/v1/chat/completions',None)]
    finally:
        for client in clients:client.close()
