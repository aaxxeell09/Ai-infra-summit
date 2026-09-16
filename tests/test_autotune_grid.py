"""Bounded grids may be large, but never at the cost of saying what they are."""
import pytest

from turbo.optimizer import grid, guard, search_space as space

CPU = {'backend': 'llama_cpp_cpu', 'plugin': 'llama_cpp', 'device': 'cpu',
       'model_path': 'local/m.gguf', 'threads': 10, 'threads_batch': 0, 'n_batch': 0,
       'ubatch': 0, 'context': 4096, 'max_tokens': 128, 'spec_type': 'none'}
QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
         'model_path': 'local/bundle', 'max_tokens': 128, 'stop_after_tool_call': False}


def test_reachable_counts_separate_single_variable_from_cartesian():
    counts = grid.reachable_treatment_count('llama_cpp_cpu')
    assert counts['single_variable_treatments'] == space.space_size('llama_cpp_cpu')
    assert counts['full_cartesian_points'] > counts['single_variable_treatments']
    qairt = grid.reachable_treatment_count('qairt_npu')
    assert qairt['single_variable_treatments'] == 11
    assert set(qairt['axes']) == {'max_tokens', 'stop_after_tool_call'}


def test_the_llama_space_is_genuinely_large_and_the_qairt_space_is_not():
    assert grid.reachable_treatment_count('llama_cpp_cpu')['full_cartesian_points'] > 1000
    assert grid.reachable_treatment_count('qairt_npu')['full_cartesian_points'] < 100


def test_an_oversized_grid_is_refused_rather_than_truncated():
    with pytest.raises(ValueError) as excinfo:
        grid.bounded_grid(CPU, 'llama_cpp_cpu', max_points=10)
    assert 'exceeds max_points' in str(excinfo.value)


def test_every_grid_point_passes_the_guard_it_declares_itself_to():
    points, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu',
                                  parameters=['threads', 'n_batch', 'max_tokens'])
    assert len(points) > 100
    for point in points:
        assert guard.check(point, control_config=CPU, backend='llama_cpp_cpu') == [], point['treatment']


def test_single_field_points_keep_attribution_and_multi_field_points_do_not():
    points, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu', parameters=['threads', 'n_batch'])
    singles = [p for p in points if p['variable']]
    multis = [p for p in points if not p['variable']]
    assert singles and multis
    assert all('integration_test' not in p for p in singles)
    assert all(p['integration_test'] and p['causal_attribution'] is False for p in multis)
    assert all(sorted(p['variables']) == sorted(p['variables']) and len(p['variables']) > 1
               for p in multis)


def test_the_control_itself_is_never_emitted():
    points, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu', parameters=['threads'])
    assert all(point['config']['threads'] != CPU['threads'] for point in points)


def test_grids_are_deterministic():
    first, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu', parameters=['threads', 'ubatch'])
    second, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu', parameters=['threads', 'ubatch'])
    assert [p['config_hash'] for p in first] == [p['config_hash'] for p in second]
    assert [p['candidate_id'] for p in first] == [p['candidate_id'] for p in second]


def test_an_unsupported_axis_is_reported_not_silently_dropped():
    points, rejections = grid.bounded_grid(QAIRT, 'qairt_npu',
                                           parameters=['max_tokens', 'top_k', 'threads'])
    names = {name for name, _lane, _status, _evidence in rejections}
    assert names == {'top_k', 'threads'}
    assert all(name not in point['config'] or point['config'][name] == QAIRT.get(name)
               for point in points for name in ('top_k',))


def test_refinement_stays_inside_the_declared_enumeration():
    candidates = grid.refine(CPU, 'llama_cpp_cpu', 'threads', radius=1)
    values = [c['config']['threads'] for c in candidates]
    assert values == [8, 12]
    assert all(c['variable'] == 'threads' for c in candidates)


def test_refinement_of_an_unanchored_control_offers_the_whole_axis():
    off_grid = dict(CPU, threads=11)
    values = [c['config']['threads'] for c in grid.refine(off_grid, 'llama_cpp_cpu', 'threads')]
    assert values == list(space.PARAMETERS['threads']['allowed_values'])


def test_refinement_refuses_a_control_the_backend_cannot_vary():
    with pytest.raises(ValueError) as excinfo:
        grid.refine(QAIRT, 'qairt_npu', 'threads')
    assert 'not refinable' in str(excinfo.value)
    with pytest.raises(ValueError):
        grid.refine(QAIRT, 'qairt_npu', 'top_k')


def test_restart_requirement_is_carried_from_the_registry():
    tokens = grid.refine(QAIRT, 'qairt_npu', 'max_tokens', radius=1)
    stop = grid.refine(QAIRT, 'qairt_npu', 'stop_after_tool_call')
    assert all(c['requires_restart'] is False for c in tokens)
    assert all(c['requires_restart'] is True for c in stop)


def test_every_candidate_carries_a_real_hypothesis():
    points, _ = grid.bounded_grid(CPU, 'llama_cpp_cpu', parameters=['threads', 'n_batch'])
    assert all(len(point['hypothesis']) > 40 for point in points)
