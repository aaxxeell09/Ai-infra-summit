import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from eval.compare_backends import MATCH, SLOTS, build, markdown

ROOT = Path(__file__).resolve().parents[1]


def reports():
    base = json.loads((ROOT/'eval/results/candidate_cpu-t10-v2.json').read_text())
    result = {}
    for slot, backend in SLOTS.items():
        report = copy.deepcopy(base)
        report['inference_backend'] = {'backend_id': backend}
        report['git_commit'] = slot
        result[slot] = report
    return result


def test_energy_not_required_for_correctness_latency():
    result = build(reports(), 'dev')
    assert result['correctness_latency_comparable'] is True
    assert result['energy_comparable'] is False
    assert result['overall_winner'] is None
    assert [r['metrics']['tasks'] for r in result['rows']] == [35]*3
    assert result['rows'][0]['provenance']['dataset_sha256'] == reports()['cpu']['dataset_sha256']
    assert result['rows'][0]['source_case_count'] == 50
    assert 'No overall winner' in markdown(result)


@pytest.mark.parametrize('key', MATCH)
def test_provenance_mismatch_blocks_comparability(key):
    data = reports(); data['qairt'][key] = 'changed'
    result = build(data)
    assert not result['correctness_latency_comparable']
    assert any(key in reason for reason in result['correctness_latency_reasons'])


def test_metrics_ignore_precomputed_summary_and_include_failures():
    data = reports()
    for report in data.values():
        report['results'] = report['results'][:20]
        for i, case in enumerate(report['results']):
            case.update(task_success=i == 0, invalid_output=i == 1, latency_ms=i + 1,
                        expected_tool='clarify', no_action_correct=i < 2)
        report['metrics'] = {'task_accuracy': 100}
    metric = build(data)['rows'][0]['metrics']
    assert metric['task_success'] == 1
    assert metric['accuracy_pct'] == 5
    assert metric['invalid_output_rate'] == .05
    assert metric['clarification_accuracy_pct'] == 10
    assert metric['inference_latency_ms'] == {'mean': 10.5, 'median': 10.5, 'p95': 19, 'samples': 20}


@pytest.mark.parametrize('mutation', ['duplicate', 'hash', 'missing', 'nan', 'flag', 'identity'])
def test_invalid_reports_do_not_compare(mutation):
    data = reports(); report = data['qairt']; case = report['results'][0]
    if mutation == 'duplicate': report['results'][1]['id'] = case['id']
    if mutation == 'hash': case['case_sha256'] = 'different'
    if mutation == 'missing': case.pop('case_sha256')
    if mutation == 'nan': case['latency_ms'] = float('nan')
    if mutation == 'flag': case['task_success'] = 'true'
    if mutation == 'identity': report['inference_backend']['backend_id'] = 'llama_cpp_cpu'
    assert not build(data)['correctness_latency_comparable']


def test_fewer_than_twenty_samples_p95_unavailable():
    data = reports()
    for r in data.values(): r['results'] = r['results'][:2]
    assert build(data)['rows'][0]['metrics']['inference_latency_ms']['p95'] is None


def test_candidate_generation_settings_are_disclosed_not_blocked():
    data = reports(); data['qairt']['generation_protocol']['stop_after_first_tool_call'] = True
    result = build(data)
    assert result['correctness_latency_comparable']
    assert any('generation_protocol' in r for r in result['warnings'])


def test_existing_reports_legacy_identity_and_evaluator_mismatch():
    paths = {'cpu': 'candidate_cpu-t10-v2', 'htp': 'baseline', 'qairt': 'candidate_qairt-native-06-v1'}
    data = {slot: json.loads((ROOT/'eval/results'/f'{name}.json').read_text()) for slot, name in paths.items()}
    original = copy.deepcopy(data)
    result = build(data, 'dev')
    assert data == original
    assert [r['backend']['backend_id'] for r in result['rows']] == list(SLOTS.values())
    assert not result['correctness_latency_comparable']
    assert any('evaluator_sha256' in r for r in result['correctness_latency_reasons'])


def test_cli_writes_new_files_and_refuses_overwrite(tmp_path):
    args = [sys.executable, str(ROOT/'eval/compare_backends.py')]
    for slot, report in reports().items():
        path = tmp_path/f'{slot}.json'; path.write_text(json.dumps(report)); args += ['--'+slot, str(path)]
    output = tmp_path/'comparison.md'
    args += ['--dataset', 'dev', '--output', str(output)]
    subprocess.run(args, check=True, capture_output=True)
    assert json.loads(output.with_suffix('.json').read_text())['correctness_latency_comparable']
    original = output.read_bytes()
    assert subprocess.run(args, capture_output=True).returncode != 0
    assert output.read_bytes() == original


def test_valid_energy_is_separate_and_still_selects_no_winner():
    from test_decision_table import fixture
    data, _ = fixture()
    for r in data.values():
        r.update(scope='single_action_with_fixture_execution', warmup='three')
    result = build(data)
    assert result['correctness_latency_comparable']
    assert result['energy_comparable']
    assert result['overall_winner'] is None
    data['qairt']['energy_measurement']['signature']['channel'] = 'CPU'
    result = build(data)
    assert result['correctness_latency_comparable']
    assert not result['energy_comparable']
