"""One hardware job at a time, honest counts, and no heldout anywhere."""
import json
import tempfile
from pathlib import Path

import pytest

from turbo.optimizer import (budget as budget_module, console as console_module, grid, guard,
                             hardware_queue, scheduler as scheduler_module, state as state_module)

QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
         'model_path': 'local/bundle', 'sdk_dir': 'local/sdk',
         'max_tokens': 128, 'stop_after_tool_call': False}


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def build(*, executor=None, minutes=120.0, clock=None, stream=None):
    clock = clock or FakeClock()
    session = state_module.new_session(backend='qairt_npu', split='development',
                                       budget_minutes=minutes, control_name='ctl',
                                       control_config=QAIRT)
    console = console_module.Console(stream=stream or __import__('io').StringIO(), colour=False)

    def default(candidate, *, stage):
        clock.advance(10.0)
        return {'outcome': 'survive', 'hardware_seconds': 10.0, 'stage': stage,
                'loaded': True, 'exit_code': 0, 'startup_seconds': 10.0}

    engine = scheduler_module.Scheduler(
        session, backend='qairt_npu', budget=budget_module.Budget(minutes, clock=clock),
        queue=hardware_queue.HardwareQueue(), executor=executor or default, console=console,
        clock=clock)
    return engine, clock, session


def test_a_second_hardware_job_cannot_start_while_one_is_active():
    engine, _clock, _session = build()
    candidates = engine.admit(engine.generate())
    inner = {}

    def reentrant(candidate, *, stage):
        with pytest.raises(scheduler_module.HardwareBusy):
            engine.run_candidate(candidates[1], stage)
        inner['checked'] = True
        return {'outcome': 'survive', 'hardware_seconds': 1.0, 'stage': stage}

    engine.executor = reentrant
    engine.enqueue(candidates[:1])
    engine.run_candidate(candidates[0], 'S1')
    assert inner['checked']
    assert engine.queue.active is None


def test_generation_and_admission_counts_stay_distinct():
    engine, _clock, session = build()
    candidates = engine.generate()
    admitted = engine.admit(candidates)
    counts = engine.counts()
    assert counts['GENERATED_CANDIDATES'] == len(candidates)
    assert counts['STATICALLY_VALID_CANDIDATES'] == len(admitted)
    assert counts['HARDWARE_ATTEMPTS'] == 0
    assert counts['QUALIFIED_EXPERIMENTS'] == 0


def test_a_duplicate_within_a_batch_is_rejected_once():
    engine, _clock, session = build()
    candidates = engine.generate()
    admitted = engine.admit(candidates + candidates[:2])
    assert len(admitted) == len(candidates)
    assert session['counters']['static_rejected'] >= 2


def test_a_candidate_already_measured_is_not_rerun():
    engine, _clock, session = build()
    first = engine.admit(engine.generate())
    engine.enqueue(first[:1])
    engine.drain('S1', limit=1)
    again = engine.admit(first)
    assert first[0]['config_hash'] not in {c['config_hash'] for c in again}


def test_busy_and_idle_partition_the_session():
    engine, clock, session = build()
    candidates = engine.admit(engine.generate())
    clock.advance(5.0)
    engine.enqueue(candidates[:2])
    engine.drain('S1', limit=2)
    timing = session['timing']
    assert timing['hardware_busy_s'] == pytest.approx(20.0)
    assert timing['hardware_idle_s'] == pytest.approx(5.0)


def test_a_candidate_is_not_started_when_it_cannot_fit_the_budget():
    engine, _clock, _session = build(minutes=1.0)
    candidates = engine.admit(engine.generate())
    candidates[0]['expected_hardware_seconds'] = 600.0
    engine.enqueue(candidates[:1])
    assert engine.run_candidate(candidates[0], 'S1', estimated_seconds=600.0) is None


def test_an_unknown_cost_becomes_a_declared_default_not_a_free_one(): 
    engine, _clock, session = build(minutes=120.0)
    cost, source = engine.estimated_cost({'expected_hardware_seconds': None})
    assert cost == engine.default_hardware_seconds and 'not measured' in source
    assert session['cost_model']['default_hardware_seconds']['source'] == (
        'declared default, not measured')
    measured, source = engine.estimated_cost({'expected_hardware_seconds': 12.0})
    assert measured == 12.0 and source == 'candidate estimate'


def test_the_declared_default_still_refuses_a_job_that_cannot_fit():
    engine, _clock, _session = build(minutes=1.0)
    candidates = engine.admit(engine.generate())
    engine.enqueue(candidates[:1])
    assert engine.run_candidate(candidates[0], 'S1') is None


def test_an_interrupt_stops_scheduling_and_prints_a_resume_command():
    engine, _clock, _session = build()
    candidates = engine.admit(engine.generate())
    engine.enqueue(candidates)
    engine._interrupted = True
    assert engine.drain('S1') == []
    with tempfile.TemporaryDirectory() as directory:
        command = engine.finish(Path(directory) / 'session.json')
    assert command.startswith('python scripts/autotune.py --resume ')


def test_the_simulated_executor_stamps_every_record_as_simulated():
    clock = FakeClock()
    executor = scheduler_module.simulated_executor(
        latency_model=lambda candidate, stage: 1.0)
    candidate = grid.refine(QAIRT, 'qairt_npu', 'max_tokens', radius=1)[0]
    for stage in ('S1', 'S2', 'S4'):
        record = executor(candidate, stage=stage)
        assert record['simulated'] is True and record['archive'] is None
        assert 'Not a measurement' in record['note']


def test_the_simulated_executor_is_deterministic():
    executor = scheduler_module.simulated_executor(latency_model=lambda c, s: 1.0)
    candidate = grid.refine(QAIRT, 'qairt_npu', 'max_tokens', radius=2)[0]
    first, second = executor(candidate, stage='S4'), executor(candidate, stage='S4')
    assert first['correct'] == second['correct']
    assert first['median_latency_ms'] == second['median_latency_ms']


def test_the_tracker_executor_writes_the_exact_config_and_calls_the_tracker():
    calls = {}

    def fake_run(name, config_path, **kwargs):
        calls['name'] = name
        calls['config'] = json.loads(Path(config_path).read_text(encoding='utf-8'))
        calls['kwargs'] = kwargs
        return Path('local/experiments/EXP-999_x')

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.tracker_executor(
            root=Path(directory) / 'archives', config_directory=Path(directory) / 'candidates',
            runner=fake_run)
        candidate = grid.refine(QAIRT, 'qairt_npu', 'max_tokens', radius=1)[0]
        record = executor(candidate, stage='S4')
    assert calls['name'] == candidate['candidate_id']
    assert calls['config'] == candidate['config']
    assert calls['kwargs']['dataset'] == 'dev'
    assert record['archive'].endswith('EXP-999_x')


def test_the_tracker_executor_never_requests_heldout():
    import inspect
    source = inspect.getsource(scheduler_module.tracker_executor)
    assert "dataset='dev'" in source and 'heldout' not in source and "'all'" not in source


def test_a_different_config_never_overwrites_a_candidate_file():
    def fake_run(*args, **kwargs):
        return Path('local/experiments/EXP-1_x')

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.tracker_executor(
            root=Path(directory) / 'archives', config_directory=Path(directory) / 'candidates',
            runner=fake_run)
        candidate = grid.refine(QAIRT, 'qairt_npu', 'max_tokens', radius=1)[0]
        executor(candidate, stage='S4')
        clashing = dict(candidate, config=dict(candidate['config'], max_tokens=256))
        with pytest.raises(ValueError):
            executor(clashing, stage='S4')
