"""Synthetic report fixtures only: no hardware measurements."""
import copy
import json
from pathlib import Path
from eval.decision_table import build, markdown, SLOTS, PROVENANCE

POLICY = {'min_accuracy_pct': 90, 'max_e2e_latency_ms': 200, 'latency_stat': 'p95'}
QUALITY = json.loads((Path(__file__).resolve().parents[1]/'eval/quality_policy.json').read_text())


def fixture():
    row = {'id': 'x', 'case_sha256': 'test-case', 'task_success': True, 'tool_correct': True,
           'action_correct': True, 'arguments_correct': True, 'no_action_correct': True,
           'latency_ms': 50, 'task_latency_ms': 120, 'warm_task_latency_ms': 100,
           'category': 'read', 'expected_tool': 'read_file', 'invalid_output': False,
           'energy': {'scope': 'warm_task', 'channel': 'SYS', 'gross_energy_j': 2, 'duration_s': .3, 'raw_before': {'monotonic_s': 1, 'channels_pwh': {'SYS': 1}}, 'raw_after': {'monotonic_s': 1.3, 'channels_pwh': {'SYS': 1 + 2/3.6e-9}}}}
    base = {k: 'test-only' for k in PROVENANCE}
    base.update(schema_version=2, status='measured', type='candidate', dirty=False, git_commit='test-head',
                model_sha256='test-gguf', config_sha256='test-config',
                results=[dict(copy.deepcopy(row), id=str(i)) for i in range(20)],
                energy_measurement={'schema_version': 'secretary-energy-v1', 'valid': True, 'invalid_reasons': [],
                    'signature': {'boundary': 'warm_task_v1', 'channel': 'SYS', 'warmup_count': 3,
                    'idle_window_s': 5, 'idle_repeats': 3, 'counter_resolution_s': .1,
                    'instrumentation_sha256': {'x': 'test'}, 'protocol_sha256': 'test',
                    'runtime_files_sha256': {'x': 'test'}, 'power_condition': {'ac_line_status': 'ac', 'active_scheme_guid': 'test-guid', 'power_mode': 'test-mode', 'battery_saver': False},
                    'machine': {'system': 'test', 'machine': 'test', 'hardware_note': 'test'}}})
    for field in ('power_before', 'power_ready', 'power_after'):
        base['energy_measurement'][field] = copy.deepcopy(base['energy_measurement']['signature']['power_condition'])
    reports = {slot: dict(copy.deepcopy(base), inference_backend={'backend_id': backend}) for slot, backend in SLOTS.items()}
    reports['qairt']['model_sha256'] = 'test-qairt'
    baseline = copy.deepcopy(reports['cpu'])
    baseline.update(type='baseline', baseline_approval={'status': 'confirmed', 'confirmed_by': 'Henry',
                    'application_commit': 'test-head', 'config_sha256': 'test-config'})
    return reports, baseline


def run(reports, baseline, policy=POLICY):
    return build(reports, baseline, policy, QUALITY, 'test-head')


def test_missing_is_unknown():
    result = run({}, None)
    assert result['winner'] is None
    assert all(r['status'] == 'NOT_MEASURED' for r in result['rows'])
    assert 'NOT ENOUGH DATA' in markdown(result)


def test_failed_tasks_still_consume_energy():
    reports, baseline = fixture()
    reports['cpu']['results'][0]['task_success'] = False
    result = run(reports, baseline)
    row = result['rows'][0]
    assert row['gross_energy_j'] == 40
    assert row['joules_per_correct_task'] == 40/19


def test_zero_correct_is_undefined():
    reports, baseline = fixture()
    for row in reports['cpu']['results']: row['task_success'] = False
    result = run(reports, baseline)
    assert result['rows'][0]['joules_per_correct_task'] is None
    assert result['winner'] is None


def test_missing_or_invalid_energy_blocks_all_selection():
    for value in (None, -1, float('nan')):
        reports, baseline = fixture()
        reports['htp']['results'][0]['energy']['gross_energy_j'] = value
        assert run(reports, baseline)['winner'] is None


def test_signatures_and_current_commit_must_match():
    reports, baseline = fixture()
    reports['htp']['energy_measurement']['signature']['channel'] = 'CPU'
    assert run(reports, baseline)['winner'] is None
    reports, baseline = fixture()
    reports['htp']['git_commit'] = 'historical'
    assert run(reports, baseline)['winner'] is None


def test_policy_requires_explicit_thresholds():
    reports, baseline = fixture()
    assert run(reports, baseline, dict(POLICY, min_accuracy_pct=None))['winner'] is None
    assert run(reports, baseline, dict(POLICY, max_e2e_latency_ms=99))['winner'] is None


def test_approved_gate_required_and_preserved():
    reports, baseline = fixture()
    result = run(reports, None)
    assert result['winner'] is None
    assert result['rows'][0]['quality_gate']['status'] == 'NOT_EVALUATED'
    baseline['evaluator_sha256'] = 'old'
    result = run(reports, baseline)
    assert result['winner'] is None
    assert result['rows'][0]['quality_gate']['status'] == 'NOT_COMPARABLE'


def test_eligible_minimum_energy_selection():
    reports, baseline = fixture()
    for row in reports['htp']['results']:
        row['energy']['gross_energy_j'] = 1
        row['energy']['raw_after']['channels_pwh']['SYS'] = 1 + 1/3.6e-9
    result = run(reports, baseline)
    assert result['comparison_status'] == 'COMPARABLE'
    assert result['winner'] == 'llama_cpp_htp'


def test_p95_requires_twenty_samples():
    reports, baseline = fixture()
    reports['cpu']['results'].pop()
    assert run(reports, baseline)['winner'] is None


def test_backend_case_and_gguf_mismatch_block_selection():
    for mutation in ('backend', 'cases', 'model'):
        reports, baseline = fixture()
        if mutation == 'backend': reports['htp']['inference_backend']['backend_id'] = 'llama_cpp_cpu'
        if mutation == 'cases': reports['htp']['results'][0]['case_sha256'] = 'different'
        if mutation == 'model': reports['htp']['model_sha256'] = 'different'
        assert run(reports, baseline)['winner'] is None


def test_malformed_flags_and_schema_rejected():
    for field, value in [('task_success', 2), ('invalid_output', 'false')]:
        reports, baseline = fixture()
        reports['cpu']['results'][0][field] = value
        result = run(reports, baseline)
        assert result['comparison_status'] == 'NOT_COMPARABLE'
        assert result['winner'] is None
    reports, baseline = fixture()
    reports['cpu']['schema_version'] = 1
    assert run(reports, baseline)['winner'] is None


def test_raw_observations_and_power_required():
    reports, baseline = fixture()
    del reports['cpu']['results'][0]['energy']['raw_before']
    assert run(reports, baseline)['winner'] is None
    reports, baseline = fixture()
    reports['cpu']['energy_measurement']['signature']['power_condition']['battery_saver'] = None
    assert run(reports, baseline)['winner'] is None


def test_summary_and_modes():
    reports, baseline = fixture()
    result = run(reports, baseline)
    assert result['modes']['BALANCED'] is None
    assert result['modes']['FAST']
    assert result['objective_winners']['highest_accuracy']
    summary = result['rows'][0]['measurement_summary']
    assert summary['energy_per_task_j']['mean'] == 2
    assert summary['energy_per_task_j']['p95'] == 2
    assert summary['total_net_energy_j'] is None
    assert 'Clarify %' in markdown(result)


def test_old_baseline_energy_not_eligible_even_if_original_gate_passes():
    reports, baseline = fixture()
    del baseline['energy_measurement']
    result = run(reports, baseline)
    assert result['rows'][0]['quality_gate']['status'] == 'PASS'
    assert not result['rows'][0]['eligible']
    assert result['winner'] is None
    assert result['comparison_status'] == 'NOT_COMPARABLE'


def test_raw_counter_arithmetic_and_resolution_are_checked():
    for field in ('gross_energy_j', 'duration_s'):
        reports, baseline = fixture()
        reports['cpu']['results'][0]['energy'][field] *= 2
        assert run(reports, baseline)['comparison_status'] == 'NOT_COMPARABLE'
    reports, baseline = fixture()
    reports['cpu']['energy_measurement']['signature']['counter_resolution_s'] = .2
    assert run(reports, baseline)['winner'] is None


def test_invalid_reason_cannot_be_marked_valid():
    reports, baseline = fixture()
    reports['cpu']['energy_measurement']['invalid_reasons'] = ['counter reset']
    result = run(reports, baseline)
    assert result['winner'] is None
    assert 'UNAVAILABLE' in markdown(result)
