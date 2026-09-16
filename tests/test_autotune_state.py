"""Session state must survive a crash without ever inventing a measurement."""
import json
import tempfile
from pathlib import Path

import pytest

from turbo.optimizer import state as S

CONTROL = {'backend': 'qairt_npu', 'model_path': 'local/bundle', 'sdk_dir': 'local/sdk',
           'max_tokens': 128, 'stop_after_tool_call': False}


def session():
    return S.new_session(backend='qairt_npu', split='development', budget_minutes=120,
                         control_name='ctl', control_config=CONTROL)


def candidate(**overrides):
    config = dict(CONTROL, **overrides.pop('config', {'max_tokens': 64}))
    record = {'candidate_id': 'C-0001', 'family': 'output_budget', 'variable': 'max_tokens',
              'config': config, 'config_hash': S.config_hash(config)}
    record.update(overrides)
    return record


def test_config_hash_ignores_machine_paths_but_not_treatment_values():
    here = dict(CONTROL, model_path='D:/models/bundle', sdk_dir='D:/sdk', hardware_note='laptop')
    assert S.config_hash(here) == S.config_hash(CONTROL)
    assert S.config_hash(dict(CONTROL, max_tokens=64)) != S.config_hash(CONTROL)


def test_heldout_sessions_cannot_be_created():
    with pytest.raises(ValueError):
        S.new_session(backend='qairt_npu', split='heldout', budget_minutes=10,
                      control_name='c', control_config=CONTROL)


def test_repeated_outcomes_append_rather_than_overwrite():
    state, record = session(), candidate()
    S.record_outcome(state, record, 'S4', 'survive', hardware_seconds=30.0, net_cases=3)
    S.record_outcome(state, record, 'S4', 'survive', hardware_seconds=31.0, net_cases=1)
    observations = state['tested_exact'][record['config_hash']]['observations']
    assert [o['net_cases'] for o in observations] == [3, 1]
    assert state['families']['output_budget']['net_case_deltas'] == [3, 1]


def test_hardware_seconds_accumulate_per_family():
    state, record = session(), candidate()
    S.record_outcome(state, record, 'S1', 'survive', hardware_seconds=2.5)
    S.record_outcome(state, record, 'S2', 'drop', hardware_seconds=7.5)
    assert state['families']['output_budget']['hardware_seconds_spent'] == 10.0
    assert state['families']['output_budget']['survived_s2'] == 0


def test_an_unknown_stage_is_refused():
    with pytest.raises(ValueError):
        S.record_outcome(session(), candidate(), 'S9', 'survive')


def test_promote_then_rollback_restores_the_previous_control_exactly():
    state, record = session(), candidate()
    before = dict(state['current_control'])
    S.promote(state, record, experiment_id='EXP-042')
    assert state['current_control']['experiment_id'] == 'EXP-042'
    assert state['counters']['promotions'] == 1
    S.rollback(state)
    assert state['current_control'] == before
    assert state['counters']['promotions'] == 0


def test_rollback_without_history_is_refused():
    with pytest.raises(ValueError):
        S.rollback(session())


def test_save_and_load_round_trip():
    state = session()
    S.record_outcome(state, candidate(), 'S2', 'survive')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        S.save(state, path)
        restored = S.load(path)
    assert restored['session_id'] == state['session_id']
    assert restored['tested_exact'] == state['tested_exact']


def test_load_refuses_a_foreign_schema_or_a_heldout_split():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        path.write_text(json.dumps({'schema_version': 'something-else'}), encoding='utf-8')
        with pytest.raises(ValueError):
            S.load(path)
        state = dict(session(), split='heldout')
        path.write_text(json.dumps(state), encoding='utf-8')
        with pytest.raises(ValueError):
            S.load(path)


def test_resume_refuses_a_finished_session_and_records_the_resume():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        state = session()
        S.save(state, path)
        resumed = S.resume(path)
        assert len(resumed['resumed']) == 1
        S.save(dict(state, finished_at=S.now()), path)
        with pytest.raises(ValueError):
            S.resume(path)


def test_a_failed_write_leaves_the_previous_state_readable():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        first = session()
        S.save(first, path)
        broken = dict(first)
        broken['counters'] = {'generated': float('inf')}
        with pytest.raises(ValueError):
            S.save(broken, path)
        assert S.load(path)['session_id'] == first['session_id']


def test_failure_history_starts_at_zero_for_every_declared_class():
    state = session()
    assert set(state['failure_history']) == set(S.FAILURE_CLASSES)
    assert set(state['failure_history'].values()) == {0}


def test_already_tested_reflects_recorded_outcomes_only():
    state, record = session(), candidate()
    assert not S.already_tested(state, record['config_hash'])
    S.record_outcome(state, record, 'S1', 'survive')
    assert S.already_tested(state, record['config_hash'])
