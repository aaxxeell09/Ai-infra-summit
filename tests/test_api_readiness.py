"""Provider readiness without network, credentials, or local model inference."""
import json
import sys
from types import SimpleNamespace

import pytest

from scripts import api_probe
from turbo.optimizer import proposer, critic, llm
from turbo.optimizer.api_status import classify_exception

SECRET = 'sk-test-secret-never-print'
ENV = {'ANTHROPIC_API_KEY': SECRET, 'OPENAI_API_KEY': SECRET,
       'ANTHROPIC_MODEL': 'test-claude', 'OPENAI_MODEL': 'test-gpt'}


def install_sdk(monkeypatch, provider, *, error=None):
    captures = []
    def create(**kwargs):
        captures.append(('request', kwargs))
        if error:
            raise error
        return SimpleNamespace(content=[SimpleNamespace(type='text', text='OK')],
                               choices=[SimpleNamespace(message=SimpleNamespace(content='OK'))])
    def client(**kwargs):
        captures.append(('client', kwargs))
        return SimpleNamespace(messages=SimpleNamespace(create=create),
                               chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, provider, SimpleNamespace(**{
        'Anthropic' if provider == 'anthropic' else 'OpenAI': client}))
    return captures


@pytest.mark.parametrize('workspace', [None, '', '  ', 'workspace-test'])
def test_anthropic_workspace_header(monkeypatch, workspace):
    captures = install_sdk(monkeypatch, 'anthropic')
    env = dict(ENV)
    if workspace is not None:
        env['ANTHROPIC_WORKSPACE_ID'] = workspace
    client = proposer.AnthropicClient(env=env)
    assert client.complete('s', 'u', timeout_s=2) == 'OK'
    options = captures[0][1]
    assert options['max_retries'] == 0
    if workspace and workspace.strip():
        assert options['default_headers'] == {'anthropic-workspace-id': workspace}
    else:
        assert 'default_headers' not in options
    assert SECRET not in json.dumps(captures)
    client.complete('s', 'u', timeout_s=2)
    assert sum(kind == 'client' for kind, _ in captures) == 1


@pytest.mark.parametrize('provider,factory', [('anthropic', proposer.AnthropicClient), ('openai', critic.OpenAIClient)])
def test_missing_key_sdk_and_model(monkeypatch, provider, factory):
    with pytest.raises(llm.LLMUnavailable) as caught:
        factory(env={}).complete('s', 'u', timeout_s=1)
    assert caught.value.category == 'key_unavailable'
    with pytest.raises(llm.LLMUnavailable) as caught:
        factory(env={provider.upper()+'_API_KEY': SECRET}).complete('s', 'u', timeout_s=1)
    assert caught.value.category == 'model_error'
    monkeypatch.setitem(sys.modules, provider, None)
    with pytest.raises(llm.LLMUnavailable) as caught:
        factory(env=ENV).complete('s', 'u', timeout_s=1)
    assert caught.value.category == 'sdk_unavailable'


def api_error(status, body=None):
    exc = RuntimeError(SECRET)
    exc.status_code = status
    exc.body = body or {}
    return exc


@pytest.mark.parametrize('error,expected', [
    (api_error(401), 'auth_error'), (api_error(403), 'auth_error'),
    (api_error(400, {'error': {'message': 'requires anthropic-workspace-id '+SECRET}}), 'auth_error'),
    (api_error(429, {'error': {'code': 'insufficient_quota'}}), 'quota_error'),
    (api_error(400, {'message': 'Your credit balance is too low'}), 'quota_error'),
    (api_error(429), 'rate_limit'),
    (api_error(404, {'error': {'code': 'model_not_found'}}), 'model_error'),
    (api_error(400, {'error': {'param': 'model'}}), 'model_error'),
    (TimeoutError(SECRET), 'timeout'), (ConnectionError(SECRET), 'connection_error'),
    (ImportError(SECRET), 'sdk_unavailable'), (api_error(500), 'api_error'),
    (llm.LLMProtocolError(SECRET), 'protocol_error'),
])
def test_exception_classification(error, expected):
    assert classify_exception(error) == expected


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
def test_safe_sdk_failure_probe_and_wall_latency(monkeypatch, provider):
    install_sdk(monkeypatch, provider, error=api_error(401, {'error': {'message': SECRET}}))
    clock = iter([2.0, 2.125])
    result = api_probe.probe(provider, env=ENV, clock=lambda: next(clock))
    assert result['error_category'] == 'auth_error'
    assert result['latency_ms'] == 125
    assert SECRET not in json.dumps(result)


def test_all_providers_independent_and_cli_never_leaks(monkeypatch, capsys):
    for key,value in ENV.items():monkeypatch.setenv(key,value)
    install_sdk(monkeypatch, 'anthropic', error=api_error(429, {'code':'insufficient_quota'}))
    install_sdk(monkeypatch, 'openai')
    assert api_probe.main(['--provider','all']) == 1
    captured = capsys.readouterr()
    assert not captured.err and SECRET not in captured.out
    rows=json.loads(captured.out)['results']
    assert [r['status'] for r in rows] == ['error','ok']
    assert rows[0]['error_category'] == 'quota_error'


def test_cli_suppresses_external_debug_output(monkeypatch,capsys):
    def noisy(provider, **kwargs):
        import logging
        print(SECRET); print(SECRET,file=sys.stderr); logging.error(SECRET)
        return {'provider':provider,'status':'ok'}
    monkeypatch.setattr(api_probe,'probe',noisy)
    assert api_probe.main(['--provider','openai']) == 0
    output=capsys.readouterr()
    assert SECRET not in output.out+output.err
    assert len(json.loads(output.out)['results']) == 1


def test_model_misconfiguration_cannot_echo_key(monkeypatch):
    install_sdk(monkeypatch,'openai')
    result=api_probe.probe('openai',env={**ENV,'OPENAI_MODEL':SECRET})
    assert result['model']=='[REDACTED]' and SECRET not in json.dumps(result)


@pytest.mark.parametrize('timeout',[float('nan'),float('inf'),0,-1,121])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):api_probe.probe('openai',timeout_s=timeout)


@pytest.mark.parametrize('category', [[], {}, ['auth_error'], 123, 'synthetic-secret'])
def test_malformed_or_unapproved_exception_category_is_safe(category):
    error = RuntimeError('synthetic-secret')
    error.category = category
    assert classify_exception(error) == 'api_error'
