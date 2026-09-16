"""Candidate generation is offline arithmetic over the declared space.

No model, no device, no network and no disk: every assertion here is about what
the enumeration is allowed to contain and about that enumeration being identical
on every run, which is the only reason a recorded session can be replayed.
"""
import pytest

from turbo.optimizer import guard, mutation, state
from turbo.optimizer import search_space as space

QAIRT_CONTROL = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
                 'context': 4096, 'max_tokens': 128, 'stop_after_tool_call': False}
LLAMA_CONTROL = {'backend': 'llama_cpp_cpu', 'plugin': 'llama_cpp', 'device': 'cpu',
                 'context': 4096, 'max_tokens': 128, 'threads': 4, 'n_batch': 256}

CANDIDATE_KEYS = {'candidate_id', 'parent_control', 'family', 'variable', 'treatment', 'config',
                  'config_hash', 'hypothesis', 'stage', 'requires_restart',
                  'expected_hardware_seconds', 'priority', 'status'}

SAMPLER_NAMES = ('top_k', 'top_p', 'temperature', 'seed', 'grammar', 'draft_tokens')


def test_generate_is_deterministic():
    first = mutation.generate(QAIRT_CONTROL, 'qairt_npu')
    second = mutation.generate(dict(QAIRT_CONTROL), 'qairt_npu')
    assert first == second
    assert [c['candidate_id'] for c in first] == ['C-%04d' % i for i in range(1, len(first) + 1)]
    assert [c['treatment'] for c in first] == [c['treatment'] for c in second]


def test_qairt_generates_exactly_the_reachable_treatments():
    candidates = mutation.generate(QAIRT_CONTROL, 'qairt_npu')
    assert [c['treatment'] for c in candidates] == [
        'max_tokens=16', 'max_tokens=24', 'max_tokens=32', 'max_tokens=48', 'max_tokens=64',
        'max_tokens=96', 'max_tokens=192', 'max_tokens=256', 'stop_after_tool_call=True']
    # The declared space minus the two values the control already holds.
    assert len(candidates) == space.space_size('qairt_npu') - 2
    assert {c['variable'] for c in candidates} == {'max_tokens', 'stop_after_tool_call'}


def test_qairt_never_generates_a_sampler_parameter():
    candidates = mutation.generate(QAIRT_CONTROL, 'qairt_npu')
    assert all(c['variable'] not in SAMPLER_NAMES for c in candidates)
    assert all(c['family'] != 'sampler' for c in candidates)
    assert all(not set(c['config']) - set(space.RUNNER_ALLOWED_KEYS) for c in candidates)


def test_generate_skips_the_control_value():
    assert all(c['config']['max_tokens'] != 128 for c in mutation.generate(QAIRT_CONTROL, 'qairt_npu')
               if c['variable'] == 'max_tokens')
    shifted = dict(QAIRT_CONTROL, max_tokens=16)
    treatments = [c['treatment'] for c in mutation.generate(shifted, 'qairt_npu')]
    assert 'max_tokens=16' not in treatments and 'max_tokens=128' in treatments


def test_generate_reaches_every_value_when_the_control_omits_the_key():
    control = {k: v for k, v in QAIRT_CONTROL.items() if k != 'max_tokens'}
    values = [c['config']['max_tokens'] for c in mutation.generate(control, 'qairt_npu')
              if c['variable'] == 'max_tokens']
    assert values == list(space.PARAMETERS['max_tokens']['allowed_values'])


def test_candidate_shape_is_exactly_the_contract():
    candidate = mutation.generate(QAIRT_CONTROL, 'qairt_npu')[0]
    assert set(candidate) == CANDIDATE_KEYS
    assert candidate['stage'] == 'S0' and candidate['status'] == 'generated'
    assert candidate['expected_hardware_seconds'] is None and candidate['priority'] is None
    assert candidate['parent_control'] == state.config_hash(QAIRT_CONTROL)
    assert candidate['config_hash'] == state.config_hash(candidate['config'])
    assert candidate['config_hash'] != candidate['parent_control']
    assert isinstance(candidate['requires_restart'], bool)
    assert candidate['hypothesis'].strip().endswith('.') and len(candidate['hypothesis'].split()) > 8
    assert all(c['hypothesis'].strip() for c in mutation.generate(QAIRT_CONTROL, 'qairt_npu'))


def test_every_generated_candidate_changes_exactly_one_field_and_passes_the_guard():
    for candidate in mutation.generate(QAIRT_CONTROL, 'qairt_npu'):
        assert guard.changed_fields(QAIRT_CONTROL, candidate['config']) == [candidate['variable']]
        assert guard.check(candidate, control_config=QAIRT_CONTROL, backend='qairt_npu') == []


def test_llama_candidates_also_pass_the_guard_and_stay_single_variable():
    candidates = mutation.generate(LLAMA_CONTROL, 'llama_cpp_cpu')
    assert len(candidates) > len(mutation.generate(QAIRT_CONTROL, 'qairt_npu'))
    assert 'stop_after_tool_call' not in {c['variable'] for c in candidates}
    for candidate in candidates:
        assert guard.check(candidate, control_config=LLAMA_CONTROL, backend='llama_cpp_cpu') == []


def test_filters_restrict_to_families_and_parameters():
    by_family = mutation.generate(QAIRT_CONTROL, 'qairt_npu', families=['stop'])
    assert [c['treatment'] for c in by_family] == ['stop_after_tool_call=True']
    by_name = mutation.generate(QAIRT_CONTROL, 'qairt_npu', parameters=['max_tokens'])
    assert {c['variable'] for c in by_name} == {'max_tokens'}
    both = mutation.generate(QAIRT_CONTROL, 'qairt_npu', families=['stop'], parameters=['max_tokens'])
    assert both == []


def test_undeclared_filters_and_inputs_fail_closed():
    with pytest.raises(ValueError):
        mutation.generate(QAIRT_CONTROL, 'qairt_npu', parameters=['max_token'])
    with pytest.raises(ValueError):
        mutation.generate(QAIRT_CONTROL, 'qairt_npu', families=['sampling'])
    with pytest.raises(ValueError):
        mutation.generate(QAIRT_CONTROL, 'no_such_backend')
    with pytest.raises(ValueError):
        mutation.generate({}, 'qairt_npu')


def test_start_index_controls_candidate_ids():
    candidates = mutation.generate(QAIRT_CONTROL, 'qairt_npu', start_index=7)
    assert candidates[0]['candidate_id'] == 'C-0007'
    assert candidates[0]['config'] == mutation.generate(QAIRT_CONTROL, 'qairt_npu')[0]['config']


def test_neighbourhood_steps_through_the_declared_order():
    control = dict(QAIRT_CONTROL, max_tokens=64)
    assert [c['config']['max_tokens'] for c in mutation.neighbourhood(control, 'qairt_npu', 'max_tokens')] == [48, 96]
    assert [c['config']['max_tokens'] for c in
            mutation.neighbourhood(control, 'qairt_npu', 'max_tokens', radius=2)] == [32, 48, 96, 128]
    edge = dict(QAIRT_CONTROL, max_tokens=16)
    assert [c['config']['max_tokens'] for c in mutation.neighbourhood(edge, 'qairt_npu', 'max_tokens')] == [24]


def test_neighbourhood_of_a_boolean_is_the_whole_enumeration():
    assert [c['config']['stop_after_tool_call'] for c in
            mutation.neighbourhood(QAIRT_CONTROL, 'qairt_npu', 'stop_after_tool_call', radius=1)] == [True]
    flipped = dict(QAIRT_CONTROL, stop_after_tool_call=True)
    assert [c['config']['stop_after_tool_call'] for c in
            mutation.neighbourhood(flipped, 'qairt_npu', 'stop_after_tool_call', radius=3)] == [False]


def test_neighbourhood_refuses_an_anchor_it_cannot_establish():
    with pytest.raises(ValueError):
        mutation.neighbourhood(dict(QAIRT_CONTROL, max_tokens=100), 'qairt_npu', 'max_tokens')
    with pytest.raises(ValueError):
        mutation.neighbourhood({k: v for k, v in QAIRT_CONTROL.items() if k != 'max_tokens'},
                               'qairt_npu', 'max_tokens')
    with pytest.raises(ValueError):
        mutation.neighbourhood(QAIRT_CONTROL, 'qairt_npu', 'threads')
    with pytest.raises(ValueError):
        mutation.neighbourhood(QAIRT_CONTROL, 'qairt_npu', 'max_tokens', radius=0)


def test_from_llm_space_rejects_top_k_with_a_reason():
    candidates, rejected = mutation.from_llm_space(QAIRT_CONTROL, 'qairt_npu', {'top_k': [40]})
    assert candidates == []
    assert len(rejected) == 1
    parameter, value, reason = rejected[0]
    assert (parameter, value) == ('top_k', 40)
    assert 'top_k' in reason and reason.strip()
    assert all('top_k' not in c['config'] for c in candidates)


def test_from_llm_space_never_clamps_an_out_of_range_value():
    proposed = {'max_tokens': [64, 999, 0], 'temperature': [0.7]}
    candidates, rejected = mutation.from_llm_space(QAIRT_CONTROL, 'qairt_npu', proposed)
    assert [c['treatment'] for c in candidates] == ['max_tokens=64']
    assert ('max_tokens', 999) in [(p, v) for p, v, _ in rejected]
    assert ('max_tokens', 0) in [(p, v) for p, v, _ in rejected]
    assert ('temperature', 0.7) in [(p, v) for p, v, _ in rejected]
    # Not clamped to the nearest declared value, and not silently dropped.
    assert all(c['config']['max_tokens'] not in (999, 256, 0) for c in candidates)
    assert all(reason.strip() for _, _, reason in rejected)


def test_from_llm_space_rejects_wrong_backend_control_value_and_repeats():
    proposed = {'threads': [8], 'max_tokens': [128, 64, 64], 'stop_after_tool_call': 'True'}
    candidates, rejected = mutation.from_llm_space(QAIRT_CONTROL, 'qairt_npu', proposed)
    reasons = {(p, repr(v)): r for p, v, r in rejected}
    assert [c['treatment'] for c in candidates] == ['max_tokens=64']
    assert 'qairt_npu' in reasons[('threads', '8')]
    assert 'control' in reasons[('max_tokens', '128')]
    assert 'Repeated' in reasons[('max_tokens', '64')]
    assert 'array' in reasons[('stop_after_tool_call', "'True'")]


def test_from_llm_space_output_is_guard_clean_and_numbered_continuously():
    candidates, _ = mutation.from_llm_space(QAIRT_CONTROL, 'qairt_npu',
                                            {'max_tokens': [32, 64], 'stop_after_tool_call': [True]},
                                            start_index=3)
    assert [c['candidate_id'] for c in candidates] == ['C-0003', 'C-0004', 'C-0005']
    for candidate in candidates:
        assert guard.check(candidate, control_config=QAIRT_CONTROL, backend='qairt_npu') == []


def test_deduplicate_within_a_batch_and_against_a_seen_set():
    candidates = mutation.generate(QAIRT_CONTROL, 'qairt_npu')
    unique, duplicates = mutation.deduplicate(candidates)
    assert unique == candidates and duplicates == []

    repeated, _ = mutation.from_llm_space(QAIRT_CONTROL, 'qairt_npu', {'max_tokens': [64]})
    unique, duplicates = mutation.deduplicate(candidates + repeated)
    assert len(unique) == len(candidates) and [c['treatment'] for c in duplicates] == ['max_tokens=64']

    seen = {c['config_hash'] for c in candidates if c['variable'] == 'max_tokens'}
    unique, duplicates = mutation.deduplicate(candidates, seen=seen)
    assert [c['treatment'] for c in unique] == ['stop_after_tool_call=True']
    assert len(duplicates) == len(candidates) - 1

    with pytest.raises(ValueError):
        mutation.deduplicate([{'candidate_id': 'C-0001'}])
