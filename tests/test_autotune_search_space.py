"""The registry must refuse controls the frozen contract cannot express.

These tests are deliberately written against the repository's own code rather
than against the registry's self-description: if someone widens the runner's
allowed keys or relaxes a native validation branch, the assertions that read
those files fail and the registry is forced to catch up.
"""
import re
from pathlib import Path

import pytest

from turbo.optimizer import lane_c, search_space as space

ROOT = Path(__file__).resolve().parents[1]


def test_runner_allowed_keys_match_the_frozen_runner():
    source = (ROOT / 'eval/run_secretary_eval.py').read_text(encoding='utf-8')
    match = re.search(r"allowed = \{(.+?)\}", source, re.S)
    assert match, 'The frozen runner no longer declares an allowed-key set'
    declared = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert declared == set(space.RUNNER_ALLOWED_KEYS)


def test_no_sampler_control_is_admissible_anywhere():
    for name in ('top_k', 'top_p', 'temperature', 'seed'):
        assert name not in space.RUNNER_ALLOWED_KEYS
        for backend in space.BACKENDS:
            assert not space.admissible_for_qualified_search(name, backend)
            assert space.lane(name, backend) == space.LANE_DIAGNOSTIC
            assert space.value_errors(name, 1, backend)


def test_qairt_exposes_only_the_two_controls_the_native_layer_accepts():
    assert space.supported_parameters('qairt_npu') == ('max_tokens', 'stop_after_tool_call')
    native = (ROOT / 'turbo/native.py').read_text(encoding='utf-8')
    assert 'QAIRT does not support llama.cpp thread/batch/speculation settings' in native
    assert 'QAIRT context must match the compiled artifact' in native
    for name in ('threads', 'threads_batch', 'ubatch', 'n_batch', 'context', 'spec_type'):
        assert not space.admissible_for_qualified_search(name, 'qairt_npu')


def test_llama_backends_carry_the_large_space():
    for backend in ('llama_cpp_cpu', 'llama_cpp_htp'):
        assert space.space_size(backend) > space.space_size('qairt_npu')
        assert space.lane('threads', backend) == space.LANE_LLAMA_MASS


def test_lane_a_is_qairt_and_lane_b_is_llama():
    assert space.lane('max_tokens', 'qairt_npu') == space.LANE_QAIRT_QUALIFIED
    assert space.lane('max_tokens', 'llama_cpp_cpu') == space.LANE_LLAMA_MASS


def test_unknown_parameter_is_unknown_not_permitted():
    spec = space.parameter('a_knob_nobody_declared')
    assert spec['support_status'] == space.UNKNOWN
    assert space.value_errors('a_knob_nobody_declared', 1, 'qairt_npu')


def test_declared_space_is_hashable_and_stable():
    first, second = space.declared_space('qairt_npu'), space.declared_space('qairt_npu')
    assert first == second and first['space_sha256'] == second['space_sha256']
    assert space.declared_space('llama_cpp_cpu')['space_sha256'] != first['space_sha256']


def test_every_value_outside_the_enumeration_is_refused():
    assert space.value_errors('max_tokens', 999, 'qairt_npu')
    assert space.value_errors('max_tokens', 1.0 * 64, 'qairt_npu'), 'float 64.0 is not int 64'
    assert not space.value_errors('max_tokens', 64, 'qairt_npu')


def test_stop_after_tool_call_is_qairt_only_like_the_native_layer():
    assert space.admissible_for_qualified_search('stop_after_tool_call', 'qairt_npu')
    for backend in ('llama_cpp_cpu', 'llama_cpp_htp'):
        assert not space.admissible_for_qualified_search('stop_after_tool_call', backend)


def test_lane_c_items_answer_all_five_owner_questions():
    for key, record in lane_c.RESEARCH_ITEMS.items():
        for field in ('missing_capability', 'smallest_safe_extension', 'benchmark_semantics',
                      'experimental_validation', 'priority'):
            assert isinstance(record[field], str) and record[field].strip(), key + ' lacks ' + field
        assert record['files_that_would_change']
        assert record['qualified_search_allowed'] is False


def test_the_sampler_question_is_registered_and_refused():
    item = lane_c.item('QAIRT_EXPLICIT_SAMPLER_CONTROL')
    assert 'sampler' in item['title'].lower()
    assert item['benchmark_semantics'] == lane_c.SEMANTICS_UNCHANGED
    assert 'five times' in item['experimental_validation']
    assert 'Qualified search is not permitted' in lane_c.refuse_qualified('QAIRT_EXPLICIT_SAMPLER_CONTROL')
    with pytest.raises(ValueError):
        lane_c.item('NOT_A_REAL_ITEM')


def test_registry_hash_changes_when_an_item_changes():
    first = lane_c.registry()['registry_sha256']
    original = lane_c.RESEARCH_ITEMS['QAIRT_ACTION_GRAMMAR']['priority']
    lane_c.RESEARCH_ITEMS['QAIRT_ACTION_GRAMMAR'] = dict(
        lane_c.RESEARCH_ITEMS['QAIRT_ACTION_GRAMMAR'], priority='changed')
    try:
        assert lane_c.registry()['registry_sha256'] != first
    finally:
        lane_c.RESEARCH_ITEMS['QAIRT_ACTION_GRAMMAR'] = dict(
            lane_c.RESEARCH_ITEMS['QAIRT_ACTION_GRAMMAR'], priority=original)
