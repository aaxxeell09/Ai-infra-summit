"""Offline coverage for the autotune language-model path.

Every test here runs with no API key, no vendor SDK and no network: the only
client is llm.MockClient, and the only disk touched is a temporary directory.
"""
import json

import pytest

from turbo.optimizer import analyzer, critic, llm, proposer, state as session_state

SECRET = 'sk-not-a-real-key-000111'

CONTROL_CONFIG = {'backend': 'llama_cpp_cpu', 'threads': 4, 'max_tokens': 128, 'context': 2048}


def mock_key(client, system, user):
    return llm.prompt_digest(llm.request_payload(client, system, user))


def canned(text):
    """A mock that answers every prompt with the same text."""
    return llm.MockClient(lambda system, user: text)


def fresh_state():
    return session_state.new_session(backend='llama_cpp_cpu', split='development',
                                     budget_minutes=120, control_name='reference',
                                     control_config=CONTROL_CONFIG)


# --- credentials -----------------------------------------------------------

def test_credential_status_unavailable_when_unset():
    assert llm.credential_status('TURBO_TEST_KEY', {}) == llm.STATUS_UNAVAILABLE
    assert llm.credential_status('TURBO_TEST_KEY', {'TURBO_TEST_KEY': '  '}) == llm.STATUS_UNAVAILABLE


def test_credential_status_never_returns_the_value():
    env = {'TURBO_TEST_KEY': SECRET}
    status = llm.credential_status('TURBO_TEST_KEY', env)
    assert status == llm.STATUS_AVAILABLE
    assert SECRET not in status and SECRET not in json.dumps({'status': status})


@pytest.mark.parametrize('factory,key_var,model_var', [
    (proposer.AnthropicClient, proposer.ANTHROPIC_KEY_VAR, proposer.ANTHROPIC_MODEL_VAR),
    (critic.OpenAIClient, critic.OPENAI_KEY_VAR, critic.OPENAI_MODEL_VAR)])
def test_vendor_clients_describe_without_leaking_and_refuse_without_credentials(factory, key_var, model_var):
    absent = factory(env={})
    assert absent.status == llm.STATUS_UNAVAILABLE and absent.model is None
    with pytest.raises(llm.LLMUnavailable):
        absent.complete('s', 'u', timeout_s=1)

    present = factory(env={key_var: SECRET, model_var: 'some-model-id'})
    assert present.status == llm.STATUS_AVAILABLE and present.model == 'some-model-id'
    assert SECRET not in json.dumps(present.describe())


def test_model_variable_unset_is_a_clear_failure_not_a_default():
    client = critic.OpenAIClient(env={critic.OPENAI_KEY_VAR: SECRET})
    assert client.model is None
    with pytest.raises(llm.LLMUnavailable) as caught:
        client.complete('s', 'u', timeout_s=1)
    assert critic.OPENAI_MODEL_VAR in str(caught.value)


# --- cache -----------------------------------------------------------------

def test_cache_miss_then_hit_roundtrip(tmp_path):
    cache = llm.ResponseCache(tmp_path / 'analyses')
    assert cache.get('deadbeef') is None
    path = cache.put('deadbeef', {'findings': []})
    assert path.exists()
    assert cache.get('deadbeef') == {'findings': []}


def test_cache_does_not_store_session_bookkeeping_keys(tmp_path):
    cache = llm.ResponseCache(tmp_path)
    cache.put('abc', {'findings': [], '_elapsed_s': 9.0, 'cached': True})
    assert cache.get('abc') == {'findings': []}


@pytest.mark.parametrize('payload', [b'{not json', b'[]', b'{"response": 4}', b'\xff\xfe'])
def test_corrupt_cache_entry_is_a_miss(tmp_path, payload):
    cache = llm.ResponseCache(tmp_path)
    cache.path_for('abc').parent.mkdir(parents=True, exist_ok=True)
    cache.path_for('abc').write_bytes(payload)
    assert cache.get('abc') is None


def test_cache_read_does_not_rewrite_bytes(tmp_path):
    cache = llm.ResponseCache(tmp_path)
    cache.put('abc', {'findings': []})
    before = cache.path_for('abc').read_bytes()
    stamp = cache.path_for('abc').stat().st_mtime_ns
    assert cache.get('abc') == {'findings': []}
    assert cache.path_for('abc').read_bytes() == before
    assert cache.path_for('abc').stat().st_mtime_ns == stamp


# --- call_json -------------------------------------------------------------

def test_call_json_returns_parsed_object_with_timing(tmp_path):
    client = canned('{"findings": []}')
    result = llm.call_json(client, 'system', 'user', cache=llm.ResponseCache(tmp_path), timeout_s=5)
    assert result['findings'] == []
    assert result['cached'] is False and result['_api_calls'] == 1
    assert isinstance(result['_elapsed_s'], float) and result['_elapsed_s'] >= 0.0


def test_call_json_raises_protocol_error_and_never_repairs_text(tmp_path):
    client = canned('Sure! Here is the JSON:\n```json\n{"findings": []}\n```')
    cache = llm.ResponseCache(tmp_path)
    with pytest.raises(llm.LLMProtocolError):
        llm.call_json(client, 'system', 'user', cache=cache, timeout_s=5, retries=1)
    assert len(client.calls) == 2, 'one first attempt plus one declared retry'
    assert list(tmp_path.glob('*.json')) == [], 'a malformed answer is never cached'


def test_call_json_refuses_a_response_claiming_bookkeeping_keys(tmp_path):
    client = canned('{"findings": [], "cached": true}')
    with pytest.raises(llm.LLMProtocolError):
        llm.call_json(client, 'system', 'user', cache=llm.ResponseCache(tmp_path), timeout_s=5)


def test_call_json_timeout_raises_unavailable_with_elapsed_recorded():
    client = llm.MockClient({}, default=TimeoutError('deadline exceeded'))
    with pytest.raises(llm.LLMUnavailable) as caught:
        llm.call_json(client, 'system', 'user', cache=None, timeout_s=0.01)
    assert caught.value.elapsed_s >= 0.0 and caught.value.api_calls == 1
    assert '0.01' in str(caught.value)


def test_call_json_unavailable_client_is_refused_before_any_call():
    class Silent(llm.LLMClient):
        name, model, status = 'silent', None, llm.STATUS_UNAVAILABLE

    with pytest.raises(llm.LLMUnavailable):
        llm.call_json(Silent(), 'system', 'user', cache=None, timeout_s=5)


def test_cache_hit_reports_cached_and_does_not_count_as_an_api_call(tmp_path):
    cache = llm.ResponseCache(tmp_path)
    client = canned('{"findings": []}')
    first = llm.call_json(client, 'system', 'user', cache=cache, timeout_s=5)
    second = llm.call_json(client, 'system', 'user', cache=cache, timeout_s=5)
    assert first['cached'] is False and second['cached'] is True
    assert second['_elapsed_s'] == 0.0 and second['_api_calls'] == 0
    assert len(client.calls) == 1, 'the second call was served from disk'
    assert llm.response_meta(second) == {'elapsed_s': 0.0, 'api_calls': 0, 'cached': True}


def test_mock_client_is_deterministic_by_digest():
    probe = llm.MockClient({})
    key = mock_key(probe, 'system', 'user')
    client = llm.MockClient({key: '{"findings": []}'})
    assert llm.call_json(client, 'system', 'user', cache=None, timeout_s=5)['findings'] == []
    with pytest.raises(llm.LLMUnavailable):
        llm.call_json(llm.MockClient({key: '{"findings": []}'}), 'system', 'other', cache=None, timeout_s=5)


# --- proposer digest -------------------------------------------------------

def loaded_state():
    state = fresh_state()
    candidate = {'candidate_id': 'AT-c1', 'family': 'cpu_parallelism', 'variable': 'threads',
                 'config_hash': 'hash-threads-8', 'config': dict(CONTROL_CONFIG, threads=8)}
    session_state.record_outcome(state, candidate, 'S2', 'survive', hardware_seconds=30.0)
    session_state.record_outcome(state, candidate, 'S4', 'win', hardware_seconds=90.0, net_cases=2)
    state['failure_history']['wrong_tool'] = 4
    state['search_spaces_attempted'].append('threads')
    # Deliberately poisoned: if any of this ever reaches the digest the leak is
    # a silent one, so the test plants it and proves it stays behind.
    state['case_history'] = {'DEV-011': {'prompt': 'Move the quarterly budget to Archive',
                                         'golden': 'move_file'}}
    state['heldout_results'] = [{'id': 'HELD-003', 'task_success': True}]
    return state


def test_proposer_digest_carries_the_session_not_the_cases():
    state = loaded_state()
    payload = proposer.digest_for_proposer(state, backend='llama_cpp_cpu', remaining_minutes=41.5,
                                           phase='exploit')
    text = json.dumps(payload)
    for leaked in ('Move the quarterly budget', 'DEV-011', 'HELD-003', 'golden', 'heldout'):
        assert leaked not in text
    assert proposer.digest_leak_reasons(payload) == []
    assert payload['remaining_minutes'] == 41.5 and payload['phase'] == 'exploit'
    assert payload['qualified_lane']['single_changed_field'] is True
    assert payload['qualified_lane']['bounded_values']['threads'] == [0, 2, 4, 6, 8, 10, 12]
    assert payload['failure_taxonomy']['wrong_tool'] == 4
    assert payload['families']['cpu_parallelism']['dev35_wins'] == 1
    assert 'threads' in payload['search_space']['explored']
    assert 'context' in payload['search_space']['unexplored']
    assert 'stop_after_tool_call' in payload['search_space']['not_available_on_this_backend']
    assert len(payload['recent_outcomes']) == 2


def test_proposer_digest_reports_control_drift_and_bounds_recent_outcomes():
    state = loaded_state()
    session_state.promote(state, {'candidate_id': 'AT-c1', 'config': dict(CONTROL_CONFIG, threads=8),
                                  'config_hash': 'hash-threads-8'})
    payload = proposer.digest_for_proposer(state, backend='llama_cpp_cpu', remaining_minutes=10,
                                           phase='explore', recent=1)
    assert payload['control']['changed_versus_session_start'] == {
        'threads': {'session_start': 4, 'now': 8}}
    assert len(payload['recent_outcomes']) == 1


def test_proposer_digest_refuses_to_emit_planted_case_content():
    payload = {'recent_outcomes': [{'case_prompt': 'move the file'}]}
    assert proposer.digest_leak_reasons(payload)


# --- proposer schema -------------------------------------------------------

def hypothesis(**overrides):
    base = {'family': 'cpu_parallelism', 'mechanism': 'More decode threads shorten per-token latency '
                                                      'until memory bandwidth saturates',
            'why_now': 'threads has one observation and the family is unexplored above 8',
            'search_space': {'threads': [8, 10]}, 'expected_signal': 'median e2e ms falls',
            'abandon_if': 'no change beyond run to run spread'}
    base.update(overrides)
    return base


def proposal_text(*items):
    return json.dumps({'hypotheses': list(items)})


def propose_with(text, *, backend='llama_cpp_cpu', max_hypotheses=5, cache=None):
    return proposer.propose(canned(text), fresh_state(), backend=backend, remaining_minutes=30,
                            phase='explore', cache=cache, max_hypotheses=max_hypotheses)


def test_proposer_accepts_a_well_formed_admissible_hypothesis():
    result = propose_with(proposal_text(hypothesis()))
    assert len(result) == 1
    assert result[0]['admissible'] is True and result[0]['reason'] is None
    assert result[0]['source']['cached'] is False


def test_proposer_keeps_an_inadmissible_hypothesis_instead_of_dropping_it():
    result = propose_with(proposal_text(hypothesis(family='sampler', search_space={'top_k': [20, 40]}),
                                        hypothesis()))
    assert len(result) == 2, 'an unreachable research idea stays visible'
    unreachable = result[0]
    assert unreachable['admissible'] is False
    assert 'top_k' in unreachable['reason']
    assert result[1]['admissible'] is True


def test_proposer_marks_a_wrong_backend_parameter_inadmissible():
    result = propose_with(proposal_text(hypothesis(family='stop',
                                                   search_space={'stop_after_tool_call': [True]})))
    assert result[0]['admissible'] is False
    assert 'llama_cpp_cpu' in result[0]['reason']


def test_proposer_marks_an_out_of_enumeration_value_inadmissible():
    result = propose_with(proposal_text(hypothesis(search_space={'threads': [7]})))
    assert result[0]['admissible'] is False and 'enumeration' in result[0]['reason']


@pytest.mark.parametrize('text', [
    '{"ideas": []}',
    '{"hypotheses": {"family": "cpu_parallelism"}}',
    json.dumps({'hypotheses': [{'family': 'cpu_parallelism'}]}),
    proposal_text(hypothesis(mechanism='   ')),
    proposal_text(hypothesis(family=7)),
    proposal_text(hypothesis(search_space=['threads'])),
    proposal_text(hypothesis(search_space={'threads': []})),
    proposal_text(dict(hypothesis(), extra='undeclared')),
])
def test_proposer_rejects_malformed_proposals(text):
    with pytest.raises(llm.LLMProtocolError):
        propose_with(text)


def test_proposer_enforces_the_hypothesis_limit():
    with pytest.raises(llm.LLMProtocolError):
        propose_with(proposal_text(*[hypothesis() for _ in range(3)]), max_hypotheses=2)


def test_proposer_second_call_is_served_from_cache(tmp_path):
    cache = llm.ResponseCache(tmp_path)
    client = canned(proposal_text(hypothesis()))
    state = fresh_state()
    kwargs = dict(backend='llama_cpp_cpu', remaining_minutes=30, phase='explore', cache=cache)
    proposer.propose(client, state, **kwargs)
    again = proposer.propose(client, state, **kwargs)
    assert again[0]['source']['cached'] is True and again[0]['source']['api_calls'] == 0
    assert len(client.calls) == 1


# --- critic ----------------------------------------------------------------

def finding(**overrides):
    base = {'kind': 'confounding', 'candidate_id': 'AT-c1',
            'detail': 'threads and context both moved between these two archives',
            'severity': 'block'}
    base.update(overrides)
    return base


def critique_text(*items):
    return json.dumps({'findings': list(items)})


def test_critique_returns_findings_and_says_they_are_advisory():
    result = critic.critique(canned(critique_text(finding(), finding(severity='warn'))),
                             {'candidates': ['AT-c1']})
    assert len(result['findings']) == 2 and len(result['blocking']) == 1
    assert result['advisory_only'] is True
    assert 'guard.check' in critic.critique.__doc__


def test_critique_accepts_a_null_candidate_id_and_an_empty_verdict():
    result = critic.critique(canned(critique_text(finding(candidate_id=None, severity='warn'))), {})
    assert result['findings'][0]['candidate_id'] is None
    assert critic.critique(canned('{"findings": []}'), {})['findings'] == []


@pytest.mark.parametrize('text', [
    '{"comments": []}',
    '{"findings": "none"}',
    critique_text(finding(kind='vibes')),
    critique_text(finding(severity='fatal')),
    critique_text(finding(detail='')),
    critique_text(finding(candidate_id=7)),
    critique_text({'kind': 'other', 'detail': 'x'}),
    critique_text(dict(finding(), extra='undeclared')),
])
def test_critique_rejects_malformed_findings(text):
    with pytest.raises(llm.LLMProtocolError):
        critic.critique(canned(text), {})


def test_critique_can_be_submitted_without_blocking_the_hardware_loop():
    import concurrent.futures
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        handle = critic.submit(canned(critique_text(finding())), {'candidates': ['AT-c1']}, pool=pool)
        assert critic.result(handle) in (None, critic.result(handle, wait_s=5))
        settled = critic.result(handle, wait_s=5)
        assert settled['findings'][0]['kind'] == 'confounding'
        assert critic.result(handle) == settled, 'a settled handle returns without waiting'
    finally:
        pool.shutdown(wait=True)


def test_critique_failure_surfaces_only_when_collected():
    handle = critic.submit(canned('not json at all'), {})
    try:
        with pytest.raises(llm.LLMProtocolError):
            critic.result(handle, wait_s=5)
    finally:
        critic.shutdown(wait=True)


# --- analyzer --------------------------------------------------------------

def row(case, *, tool, success, reasons=(), actual=None):
    return {'id': case, 'expected_tool': tool, 'task_success': success,
            'failure_reasons': list(reasons), 'tool': actual}


def synthetic_rows():
    control = [row('DEV-001', tool='move_file', success=True, actual='move_file'),
               row('DEV-002', tool='move_file', success=True, actual='move_file'),
               row('DEV-003', tool='clarify', success=False, reasons=['FAILED_TO_CLARIFY'], actual='read_file'),
               row('DEV-004', tool='read_file', success=False, reasons=['WRONG_ACTION'], actual='list_files'),
               row('DEV-005', tool='read_file', success=True, actual='read_file')]
    candidate = [row('DEV-001', tool='move_file', success=False, reasons=['WRONG_ARGUMENT'], actual='move_file'),
                 row('DEV-002', tool='move_file', success=False, reasons=['WRONG_ARGUMENT'], actual='move_file'),
                 row('DEV-003', tool='clarify', success=True, actual='clarify'),
                 row('DEV-004', tool='read_file', success=False, reasons=['WRONG_ACTION'], actual='list_files')]
    return control, candidate


def test_analyze_cases_clusters_regressions_and_fixes():
    analysis = analyzer.analyze_cases(*synthetic_rows())
    assert analysis['totals'] == {'paired': 4, 'fixed': 1, 'broken': 2, 'unchanged_pass': 0,
                                  'unchanged_fail': 1, 'net_cases': -1}
    assert analysis['regressions_by_expected_tool'] == {'move_file': ['DEV-001', 'DEV-002']}
    assert analysis['regressions_by_reason'] == {'wrong_arguments': ['DEV-001', 'DEV-002']}
    assert analysis['fixes_by_expected_tool'] == {'clarify': ['DEV-003']}
    assert analysis['unpaired'] == {'control_only': ['DEV-005'], 'candidate_only': [],
                                    'excluded_from_pairing': []}
    assert analysis['pairing_source'] == 'turbo.optimizer.statistics.case_deltas'

    top = analysis['clusters'][0]
    assert top['label'] == 'regression: move_file / wrong_arguments'
    assert top['cases'] == ['DEV-001', 'DEV-002'] and top['size'] == 2
    assert {c['label'] for c in analysis['clusters']} == {
        'regression: move_file / wrong_arguments', 'fix: clarify / clarify_failure'}
    assert analyzer.dominant_failures(analysis)[0] == {'reason': 'wrong_arguments', 'cases': 2}


def test_analyze_cases_falls_back_when_statistics_is_absent(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == 'turbo.optimizer.statistics':
            raise ImportError('not written yet')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', refuse)
    analysis = analyzer.analyze_cases(*synthetic_rows())
    assert analysis['pairing_source'] == 'analyzer.fallback_pairing'
    assert analysis['totals']['net_cases'] == -1


def test_analyze_cases_refuses_ambiguous_or_unscored_rows():
    control, candidate = synthetic_rows()
    with pytest.raises(ValueError):
        analyzer.analyze_cases(control + [control[0]], candidate)
    with pytest.raises(ValueError):
        analyzer.analyze_cases(control, candidate + [{'id': 'DEV-009'}])


def test_narration_payload_excludes_raw_rows():
    analysis = analyzer.analyze_cases(*synthetic_rows())
    payload = analyzer.narration_payload(analysis)
    assert 'cases' not in payload and payload['totals'] == analysis['totals']


def narration_text(cases=('DEV-001', 'DEV-002'), **advice):
    budget = {'family': 'cpu_parallelism', 'direction': 'less',
              'why': 'two of three treatments in this family regressed move_file'}
    budget.update(advice)
    return json.dumps({'clusters': [{'label': 'argument drift on move_file', 'cases': list(cases),
                                     'likely_mechanism': 'a shorter budget truncates the destination path'}],
                       'budget_advice': budget})


def test_explain_labels_the_analysis_without_producing_a_metric():
    analysis = analyzer.analyze_cases(*synthetic_rows())
    narration = analyzer.explain(canned(narration_text()), analysis)
    assert narration['clusters'][0]['cases'] == ['DEV-001', 'DEV-002']
    assert narration['budget_advice']['direction'] == 'less'
    assert narration['totals'] == analysis['totals'], 'numbers still come from analyze_cases'


@pytest.mark.parametrize('text', [
    narration_text(cases=('DEV-999',)),
    narration_text(direction='sideways'),
    narration_text(family=''),
    '{"clusters": []}',
    json.dumps({'clusters': [{'label': 'x', 'cases': []}], 'budget_advice': {}}),
])
def test_explain_rejects_malformed_or_invented_narration(text):
    analysis = analyzer.analyze_cases(*synthetic_rows())
    with pytest.raises(llm.LLMProtocolError):
        analyzer.explain(canned(text), analysis)
