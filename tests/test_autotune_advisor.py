"""The model is in the loop, and it cannot reach hardware without two refusals.

These tests exist because an earlier version instantiated the adapters, printed
their status and never called them, which made --mock-llm prove only that a
client can be constructed. Every test here asserts on a call actually happening
or on a proposal actually changing what the loop does.
"""
import json

import pytest

from turbo.optimizer import advisor as advisor_module, guard, llm, search_space as space
from turbo.optimizer import state as state_module

QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
         'model_path': 'local/bundle', 'sdk_dir': 'local/sdk',
         'max_tokens': 128, 'stop_after_tool_call': False}

ADMISSIBLE = {'family': 'output_budget', 'mechanism': 'shorter budget truncates runaway output',
              'why_now': 'no shorter budget has been measured',
              'search_space': {'max_tokens': [32, 64]},
              'expected_signal': 'fewer invalid outputs', 'abandon_if': 'correctness falls'}
SAMPLER = {'family': 'sampler', 'mechanism': 'explicit greedy decoding removes a confound',
           'why_now': 'requested zero does not establish greedy decoding',
           'search_space': {'top_k': [1]},
           'expected_signal': 'identical repeats', 'abandon_if': 'repeats still differ'}


def client_for(payload, model):
    """The shipped MockClient already records every call in ``.calls``.

    Using it directly rather than a test-local counting subclass means these
    tests exercise the same client --mock-llm uses, so a dry run and a test
    cannot diverge in what they prove.
    """
    return llm.MockClient({}, model=model, default=json.dumps(payload))


def session():
    return state_module.new_session(backend='qairt_npu', split='development', budget_minutes=60,
                                    control_name='ctl', control_config=QAIRT)


def build(proposal=None, critique=None):
    record = session()
    proposer_client = client_for(proposal, 'mock-proposer') if proposal else None
    critic_client = client_for(critique, 'mock-critic') if critique else None
    advisor = advisor_module.Advisor(record, proposer_client=proposer_client,
                                     critic_client=critic_client)
    return record, advisor, proposer_client, critic_client


def test_the_proposer_client_is_actually_called():
    record, advisor, client, _ = build({'hypotheses': [ADMISSIBLE]})
    hypotheses = advisor.propose(backend='qairt_npu', remaining_minutes=42.0, phase='explore')
    assert len(client.calls) == 1, 'the proposer was never invoked'
    assert len(hypotheses) == 1
    assert record['llm']['LLM_PROPOSER_CALLS'] == 1
    assert record['llm']['LLM_HYPOTHESES'] == 1


def test_the_critic_client_is_actually_called():
    from turbo.optimizer import critic as critic_module
    record, advisor, _, client = build(critique={'findings': []})
    candidate = {'candidate_id': 'C-1', 'family': 'output_budget', 'variable': 'max_tokens',
                 'treatment': 'max_tokens=64'}
    handle = advisor.submit_critique([candidate], phase='explore')
    assert handle is not None
    advisor.collect_critiques(wait_s=5.0)
    critic_module.shutdown(wait=True)
    assert len(client.calls) == 1, 'the critic was never invoked'
    assert record['llm']['LLM_CRITIC_CALLS'] == 1


def test_a_proposal_changes_which_bounded_family_is_explored():
    _record, advisor, _client, _ = build({'hypotheses': [ADMISSIBLE]})
    hypotheses = advisor.propose(backend='qairt_npu', remaining_minutes=42.0, phase='explore')
    families = advisor.families_to_explore(hypotheses, backend='qairt_npu',
                                           fallback=space.families('qairt_npu'))
    assert families == ('output_budget',)
    assert 'stop' in space.families('qairt_npu'), 'the fallback would have included stop'


def test_an_unsupported_proposal_never_reaches_hardware_but_stays_visible():
    record, advisor, _client, _ = build({'hypotheses': [SAMPLER]})
    hypotheses = advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore')
    assert len(hypotheses) == 1 and hypotheses[0]['admissible'] is False
    built, rejected = advisor.candidates_from(hypotheses, control_config=QAIRT,
                                              backend='qairt_npu')
    assert built == []
    assert rejected and 'top_k' in str(rejected)
    assert record['llm']['LLM_REJECTED_HYPOTHESES'] == 1
    assert any(h['family'] == 'sampler' and h['admissible'] is False
               for h in record['llm']['hypotheses']), 'the research idea must stay recorded'


def test_every_llm_candidate_still_has_to_pass_the_guard():
    _record, advisor, _client, _ = build({'hypotheses': [ADMISSIBLE]})
    hypotheses = advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore')
    built, _rejected = advisor.candidates_from(hypotheses, control_config=QAIRT,
                                               backend='qairt_npu')
    assert built
    for candidate in built:
        assert candidate['origin'] == 'llm'
        assert guard.check(candidate, control_config=QAIRT, backend='qairt_npu') == []


def test_a_proposal_naming_a_value_outside_the_enumeration_is_not_clamped():
    proposal = {'hypotheses': [dict(ADMISSIBLE, search_space={'max_tokens': [32, 999]})]}
    _record, advisor, _client, _ = build(proposal)
    hypotheses = advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore')
    built, rejected = advisor.candidates_from(hypotheses, control_config=QAIRT,
                                              backend='qairt_npu')
    assert hypotheses[0]['admissible'] is False, '999 is outside the declared enumeration'
    assert built == []
    assert not any(c for c in built if c['config'].get('max_tokens') == 256), 'no clamping'


def test_a_blocking_finding_removes_a_candidate_but_can_never_admit_one():
    _record, advisor, _, _ = build(critique={'findings': []})
    candidates = [{'candidate_id': 'C-1'}, {'candidate_id': 'C-2'}]
    findings = [{'kind': 'confounding', 'candidate_id': 'C-1', 'severity': 'block',
                 'detail': 'confounded with the artifact change'}]
    kept, dropped = advisor.deprioritise(candidates, findings)
    assert [c['candidate_id'] for c in kept] == ['C-2']
    assert [c['candidate_id'] for c in dropped] == ['C-1']
    warn_only = [{'kind': 'other', 'candidate_id': 'C-2', 'severity': 'warn', 'detail': 'x'}]
    kept, dropped = advisor.deprioritise(candidates, warn_only)
    assert len(kept) == 2 and dropped == []


def test_a_missing_credential_leaves_the_deterministic_search_intact():
    record = session()
    advisor = advisor_module.Advisor(record, proposer_client=None, critic_client=None)
    assert advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore') == []
    assert advisor.submit_critique([{'candidate_id': 'C-1'}], phase='explore') is None
    assert record['llm']['LLM_PROPOSER_CALLS'] == 0
    assert advisor.available == {'proposer': False, 'critic': False}


def test_an_api_failure_is_recorded_and_does_not_end_the_session():
    class Failing(llm.MockClient):
        def complete(self, system, user, *, timeout_s):
            raise llm.LLMUnavailable('connection reset')

    record = session()
    advisor = advisor_module.Advisor(record, proposer_client=Failing({}, model='x'))
    assert advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore') == []
    assert record['llm']['failures'] and record['llm']['failures'][0]['where'] == 'proposer'


def test_a_malformed_proposal_is_refused_rather_than_repaired():
    _record, advisor, _client, _ = build({'hypotheses': [{'family': 'output_budget'}]})
    assert advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore') == []


def test_the_proposer_digest_carries_no_case_text_or_heldout_content():
    from turbo.optimizer import proposer
    record = session()
    digest = proposer.digest_for_proposer(record, backend='qairt_npu', remaining_minutes=42.0,
                                          phase='explore')
    blob = json.dumps(digest).lower()
    for forbidden in ('heldout', 'held_out', 'golden', 'expected_output', 'case_text'):
        assert forbidden not in blob


def test_the_counters_are_distinct_quantities():
    record, advisor, _client, _ = build({'hypotheses': [ADMISSIBLE, SAMPLER]})
    advisor.propose(backend='qairt_npu', remaining_minutes=10.0, phase='explore')
    counters = advisor.report_counters()
    assert counters['LLM_HYPOTHESES'] == 2
    assert counters['LLM_ADMISSIBLE_HYPOTHESES'] == 1
    assert counters['LLM_REJECTED_HYPOTHESES'] == 1
    assert set(counters) == set(advisor_module.COUNTERS)


@pytest.mark.parametrize('failure', [
    llm.LLMUnavailable('api_key=synthetic-secret private-endpoint?token=synthetic-secret'),
    llm.LLMProtocolError('raw provider response: synthetic-secret'),
    OSError('private cache path /synthetic-secret/entry.json'),
    RuntimeError('SDK setup synthetic-secret'),
])
def test_optional_proposal_boundary_is_fail_open_without_persisting_exception_text(monkeypatch, failure):
    record = session()
    advisor = advisor_module.Advisor(record, proposer_client=client_for({'hypotheses': []}, 'fake'))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(advisor_module.proposer, 'propose', fail)
    assert advisor.propose(backend='qairt_npu', remaining_minutes=10, phase='explore') == []
    assert record['llm']['failures'][0]['where'] == 'proposer'
    assert 'synthetic-secret' not in json.dumps(record, allow_nan=False)
    assert advisor.families_to_explore([], backend='qairt_npu', fallback=('output_budget',)) == ('output_budget',)


@pytest.mark.parametrize('operation', ['get', 'put'])
def test_real_proposal_cache_io_failure_does_not_escape_advisor(operation):
    class BrokenCache:
        def get(self, key):
            if operation == 'get':
                raise OSError('cache credential synthetic-secret')
            return None

        def put(self, key, response):
            raise OSError('cache credential synthetic-secret')

    record = session()
    advisor = advisor_module.Advisor(
        record, proposer_client=client_for({'hypotheses': [ADMISSIBLE]}, 'fake'), cache=BrokenCache())
    proposals = advisor.propose(backend='qairt_npu', remaining_minutes=10, phase='explore')
    # A provider layer may itself recover from an unwritable optional cache;
    # otherwise the advisor safely falls back. Neither path can stop search.
    assert isinstance(proposals, list)
    assert 'synthetic-secret' not in json.dumps(record, allow_nan=False)


def test_failed_and_cancelled_critic_futures_are_removed_without_stalling():
    from concurrent.futures import Future
    record = session()
    advisor = advisor_module.Advisor(record)
    failed, cancelled, successful = Future(), Future(), Future()
    failed.set_exception(OSError('private cache synthetic-secret'))
    cancelled.cancel()
    successful.set_result({'findings': [], 'source': {'_elapsed_s': .25}})
    advisor._pending = [failed, cancelled, successful]
    assert advisor.collect_critiques() == []
    assert advisor._pending == []
    assert len(record['llm']['failures']) == 2
    assert record['llm']['LLM_API_WAIT_SECONDS'] == .25
    assert 'synthetic-secret' not in json.dumps(record, allow_nan=False)


def test_critic_submit_failure_is_optional_and_has_no_pending_handle(monkeypatch):
    record, advisor, _, _ = build(critique={'findings': []})

    def fail(*args, **kwargs):
        raise OSError('threadpool cache synthetic-secret')

    monkeypatch.setattr(advisor_module.critic_module, 'submit', fail)
    assert advisor.submit_critique([{'candidate_id': 'C-1'}], phase='explore') is None
    assert advisor._pending == []
    assert 'synthetic-secret' not in json.dumps(record, allow_nan=False)


@pytest.mark.parametrize('elapsed', [float('inf'), float('nan'), -1, 'synthetic-secret', None, True])
def test_untrusted_failure_elapsed_cannot_poison_json_state(elapsed):
    record = session()
    advisor = advisor_module.Advisor(record)
    failure = llm.LLMUnavailable('synthetic-secret')
    failure.elapsed_s = elapsed
    advisor._record_failure('proposer', failure)
    assert record['llm']['LLM_API_WAIT_SECONDS'] == 0
    assert 'synthetic-secret' not in json.dumps(record, allow_nan=False)
