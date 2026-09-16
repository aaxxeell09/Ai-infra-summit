"""Real-shaped archives in, comparable observations out, nothing invented.

The fixtures here are not hand-written dictionaries: each one is produced by the
tracker's own initialize / finish / seal path, so a change to the archive format
breaks these tests rather than silently producing observations nobody can read.
"""
import json
import tempfile
from pathlib import Path

import pytest

from turbo.experiments import finish, initialize, reserve, verify
from turbo.optimizer import observation as obs
from turbo.optimizer import successive_halving, selector, state as state_module

CONTROL_CONFIG = {'backend': 'qairt_npu', 'model_path': 'local/bundle', 'max_tokens': 128,
                  'stop_after_tool_call': False}


def case_rows(successes, *, invalid=(), latency_ms=500.0):
    rows = []
    for index, ok in enumerate(successes):
        rows.append({'case_id': 'dev-%02d' % index, 'case_sha256': 'c%02d' % index,
                     'task_success': bool(ok), 'invalid_output': index in invalid,
                     'expected_tool': 'move_file', 'failure_reasons': [] if ok else ['WRONG_ACTION'],
                     'latency_ms': latency_ms, 'warm_task_latency_ms': latency_ms,
                     'profile': {'generated_tokens': 20}})
    return rows


def build_archive(root, name, successes, *, invalid=(), latency_ms=500.0,
                  status='completed_qualified'):
    """Create one sealed archive through the tracker's own writers."""
    path = reserve(root, name)
    initialize(path, {'name': name, 'command': ['python', 'eval/run_secretary_eval.py'],
                      'environment': {'system': 'test'}},
               config_bytes=json.dumps(CONTROL_CONFIG).encode('utf-8'))
    report = {'schema_version': 2, 'status': 'measured', 'benchmark_version': 'secretary-eval-v2',
              'results': case_rows(successes, invalid=invalid, latency_ms=latency_ms)}
    manifest = dict(json.loads((path / 'manifest.json').read_text(encoding='utf-8')))
    finish(path, manifest, result=report, status=status)
    assert verify(path) == []
    return path


def test_a_real_shaped_archive_becomes_an_observation():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = build_archive(root, 'control', [True] * 20 + [False] * 15)
        record = obs.from_archive(path, stage='S4', hardware_seconds=42.0)
    assert record['evidence_complete'] is True
    assert record['missing'] == []
    assert record['attempted'] == 35 and record['correct'] == 20
    assert record['invalid'] == 0 and record['invalid_rate'] == 0.0
    assert len(record['rows']) == 35
    assert record['median_task_latency_ms'] == 500.0
    assert record['latency_boundary'] and 'warm_task_v1' in record['latency_boundary']
    assert record['qualified'] is True and record['tracker_status'] == 'completed_qualified'
    assert record['hardware_seconds'] == 42.0
    assert record['simulated'] is False
    assert record['energy_comparable'] is False


def test_reading_an_archive_never_modifies_it():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = build_archive(root, 'control', [True] * 5)
        before = {p.name: p.read_bytes() for p in sorted(path.iterdir()) if p.is_file()}
        obs.from_archive(path, stage='S4')
        after = {p.name: p.read_bytes() for p in sorted(path.iterdir()) if p.is_file()}
    assert before == after
    assert verify(path) == [] if path.exists() else True


def test_a_tampered_archive_produces_no_observation():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = build_archive(root, 'control', [True] * 5)
        (path / 'result.json').write_text('{"schema_version": 2, "results": []}', encoding='utf-8')
        record = obs.from_archive(path, stage='S4')
    assert record['evidence_complete'] is False
    assert record['outcome'] == 'failed'
    assert any('verification failed' in reason for reason in record['missing'])


def test_a_failed_or_incomplete_run_is_not_read_as_a_measurement():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = build_archive(root, 'broken', [True] * 5, status='failed')
        record = obs.from_archive(path, stage='S4')
    assert record['evidence_complete'] is False
    assert record['qualified'] is False
    assert record['outcome'] == 'failed'
    assert record.get('correct') is None, 'a failed run must not report a correct count'


def test_missing_case_rows_fail_closed_rather_than_defaulting_to_zero():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = reserve(root, 'empty')
        initialize(path, {'name': 'empty', 'command': ['x'], 'environment': {}})
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        finish(path, dict(manifest), result={'schema_version': 2, 'status': 'measured',
                                             'results': []},
               status='completed_diagnostic')
        record = obs.from_archive(path, stage='S4')
    assert record['evidence_complete'] is False
    assert record['outcome'] == 'incomplete_evidence'
    assert any('rows' in reason for reason in record['missing'])
    assert record['correct'] == 0, 'zero attempted is still zero correct, but the evidence is flagged'


def test_a_row_without_a_case_identity_is_refused():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = reserve(root, 'anon')
        initialize(path, {'name': 'anon', 'command': ['x'], 'environment': {}})
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        finish(path, dict(manifest),
               result={'schema_version': 2, 'status': 'measured',
                       'results': [{'task_success': True, 'latency_ms': 1.0}]},
               status='completed_diagnostic')
        record = obs.from_archive(path, stage='S4')
    assert record['evidence_complete'] is False
    assert any('case identity' in reason for reason in record['missing'])


def test_the_latency_gate_refuses_to_compare_two_different_boundaries():
    warm = {'median_task_latency_ms': 500.0, 'latency_boundary': 'warm_task_v1: x'}
    task = {'median_task_latency_ms': 500.0, 'latency_boundary': 'recorded_task_latency_ms: y'}
    assert obs.latency_gate(warm, warm) is True
    assert obs.latency_gate(warm, task) is None
    assert obs.latency_gate({'median_task_latency_ms': None}, warm) is None
    slow = {'median_task_latency_ms': 900.0, 'latency_boundary': warm['latency_boundary']}
    assert obs.latency_gate(slow, warm) is False


def test_annotate_gates_never_invents_a_pass():
    record = obs.annotate_gates({'median_task_latency_ms': None}, {'median_task_latency_ms': 500.0})
    assert record['latency_gate_ok'] is None
    assert record['deterministic_output'] is None


# ---------------------------------------------------------------- funnel chain

def deltas(control, candidate):
    return successive_halving.case_deltas_from_rows(control['rows'], candidate['rows'])


def test_a_regression_is_dropped_at_dev35():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = obs.from_archive(build_archive(root, 'ctl', [True] * 20 + [False] * 15),
                                   stage='S4')
        worse = obs.from_archive(build_archive(root, 'worse', [True] * 15 + [False] * 20),
                                 stage='S4')
    obs.annotate_gates(worse, control)
    verdict, reasons = successive_halving.evaluate_s4(worse, control=control,
                                                      deltas=deltas(control, worse))
    assert verdict == 'drop'
    assert reasons


def test_an_improvement_of_at_least_two_cases_survives_to_confirmation():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = obs.from_archive(build_archive(root, 'ctl', [True] * 20 + [False] * 15),
                                   stage='S4')
        better = obs.from_archive(build_archive(root, 'better', [True] * 24 + [False] * 11),
                                  stage='S4')
    obs.annotate_gates(better, control)
    measured = deltas(control, better)
    assert measured['net'] >= 2
    verdict, _reasons = successive_halving.evaluate_s4(better, control=control, deltas=measured)
    assert verdict == 'survive'
    assert successive_halving.next_stage('S4') == 'S5'


def test_a_confirming_repeat_promotes_and_a_contradicting_one_does_not():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = obs.from_archive(build_archive(root, 'ctl', [True] * 20 + [False] * 15),
                                   stage='S4')
        better = obs.from_archive(build_archive(root, 'better', [True] * 24 + [False] * 11),
                                  stage='S4')
        repeat = obs.from_archive(build_archive(root, 'repeat', [True] * 23 + [False] * 12),
                                  stage='S5')
        contradiction = obs.from_archive(build_archive(root, 'nope', [True] * 18 + [False] * 17),
                                         stage='S5')
    obs.annotate_gates(better, control)
    session = state_module.new_session(backend='qairt_npu', split='development',
                                       budget_minutes=30, control_name='ctl',
                                       control_config=CONTROL_CONFIG)
    candidate = {'candidate_id': 'C-0001', 'family': 'output_budget', 'variable': 'max_tokens',
                 'config': dict(CONTROL_CONFIG, max_tokens=64),
                 'config_hash': state_module.config_hash(dict(CONTROL_CONFIG, max_tokens=64))}
    good = selector.consider(session, candidate,
                             dev35_deltas={**deltas(control, better), 'stage': 'S4'},
                             confirmation_deltas={**deltas(control, repeat), 'stage': 'S5'},
                             latency_gate_ok=better['latency_gate_ok'],
                             deterministic_output=False,
                             experiment_id=better['experiment_id'])
    assert good['decision'] == 'promote'
    assert session['current_control']['config_hash'] == candidate['config_hash']

    fresh = state_module.new_session(backend='qairt_npu', split='development',
                                     budget_minutes=30, control_name='ctl',
                                     control_config=CONTROL_CONFIG)
    bad = selector.consider(fresh, candidate,
                            dev35_deltas={**deltas(control, better), 'stage': 'S4'},
                            confirmation_deltas={**deltas(control, contradiction), 'stage': 'S5'},
                            latency_gate_ok=better['latency_gate_ok'],
                            deterministic_output=False,
                            experiment_id=better['experiment_id'])
    assert bad['decision'] != 'promote'
    assert fresh['current_control']['name'] == 'ctl'


def test_missing_metrics_never_promote():
    session = state_module.new_session(backend='qairt_npu', split='development',
                                       budget_minutes=30, control_name='ctl',
                                       control_config=CONTROL_CONFIG)
    candidate = {'candidate_id': 'C-0002', 'config': dict(CONTROL_CONFIG, max_tokens=64),
                 'config_hash': state_module.config_hash(dict(CONTROL_CONFIG, max_tokens=64))}
    decision = selector.consider(session, candidate, dev35_deltas=None,
                                 confirmation_deltas=None, latency_gate_ok=None,
                                 deterministic_output=None, experiment_id=None)
    assert decision['decision'] != 'promote'
    assert session['current_control']['name'] == 'ctl'
