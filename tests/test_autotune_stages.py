"""Each stage runs through the executor entitled to answer it, or is skipped.

An earlier version built one tracker executor with dataset='dev' and used it for
all five stages, so the real path ran the full development set five times while
logging the first three as cheap. These tests pin the routing so that cannot
come back silently.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from turbo.optimizer import probe, scheduler as scheduler_module

QAIRT = {'backend': 'qairt_npu', 'plugin': 'qairt', 'device': 'npu',
         'sdk_dir': 'local/sdk', 'model_path': 'local/bundle', 'max_tokens': 128}


def candidate(**overrides):
    record = {'candidate_id': 'C-0001', 'config': dict(QAIRT), 'family': 'output_budget',
              'variable': 'max_tokens', 'treatment': 'max_tokens=64',
              'hypothesis': 'a stated hypothesis'}
    record.update(overrides)
    return record


class FakeCompleted:
    def __init__(self, returncode=0, stderr='', stdout=''):
        self.returncode, self.stderr, self.stdout = returncode, stderr, stdout


# ----------------------------------------------------------------- routing

def test_each_stage_goes_to_its_own_executor():
    seen = []

    def make(label):
        def executor(record, *, stage):
            seen.append((label, stage))
            return {'outcome': 'survive', 'stage': stage}
        return executor

    executor = scheduler_module.staged_executor(probe=make('probe'), canary=make('canary'),
                                                tracker=make('tracker'))
    for stage in ('S1', 'S2', 'S3', 'S4', 'S5'):
        executor(candidate(), stage=stage)
    assert seen == [('probe', 'S1'), ('canary', 'S2'), ('canary', 'S3'),
                    ('tracker', 'S4'), ('tracker', 'S5')]


def test_an_unconfigured_stage_is_skipped_explicitly():
    executor = scheduler_module.staged_executor(tracker=lambda c, *, stage: {'outcome': 'x'})
    record = executor(candidate(), stage='S2')
    assert record['outcome'] == 'skipped'
    assert 'No executor is configured' in record['skip_reason']
    assert record['qualified'] is False and record['promotion_evidence'] is False


# --------------------------------------------------------------- S1 probe

def test_the_startup_probe_makes_no_benchmark_claim():
    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.startup_probe_executor(
            config_directory=Path(directory), runner=lambda *a, **k: FakeCompleted(0))
        record = executor(candidate(), stage='S1')
    assert record['outcome'] == 'survive'
    assert record['correctness_claim'] is False
    assert record['qualified'] is False and record['promotion_evidence'] is False
    assert record['archive'] is None
    assert 'correct' not in record and 'attempted' not in record


def test_the_startup_probe_refuses_a_config_the_runner_would_reject_without_launching():
    launched = []

    def runner(*args, **kwargs):
        launched.append(args)
        return FakeCompleted(0)

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.startup_probe_executor(
            config_directory=Path(directory), runner=runner)
        record = executor(candidate(config=dict(QAIRT, threads=8)), stage='S1')
    assert launched == [], 'a config QAIRT rejects must not reach a device'
    assert record['outcome'] == probe.REFUSED
    assert 'threads' in record['runtime_error']


def test_the_startup_probe_runs_the_bounded_smoke_helper_not_the_evaluator():
    seen = {}

    def runner(command, **kwargs):
        seen['command'] = command
        return FakeCompleted(0)

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.startup_probe_executor(
            config_directory=Path(directory), runner=runner)
        executor(candidate(), stage='S1')
    joined = ' '.join(seen['command'])
    assert 'backend_smoke.py' in joined
    assert 'run_secretary_eval' not in joined
    assert '--dataset' not in joined


# -------------------------------------------------------------- S2 and S3

def test_a_stage_without_a_declared_subset_size_is_skipped_not_widened():
    launched = []
    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.canary_executor(
            seed_label='x', sizes={'S2': 8}, output_directory=Path(directory) / 'out',
            config_directory=Path(directory) / 'cfg',
            runner=lambda *a, **k: launched.append(a) or FakeCompleted(0))
        record = executor(candidate(), stage='S3')
    assert launched == []
    assert record['outcome'] == 'skipped'
    assert 'widening it to the full development set' in record['skip_reason']


def test_the_canary_invokes_the_diagnostic_runner_with_a_bounded_subset():
    seen = {}

    def runner(command, **kwargs):
        seen['command'] = command
        index = command.index('--output')
        Path(command[index + 1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[index + 1]).write_text(json.dumps(
            dict(probe.canary_result(subset=['a'] * 8, correct=5, attempted=8, invalid=1,
                                     median_latency_ms=540.0),
                 rows=[{'case_id': 'dev-%d' % i, 'task_success': i < 5} for i in range(8)])),
            encoding='utf-8')
        return FakeCompleted(0)

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.canary_executor(
            seed_label='AT-1', sizes={'S2': 8}, output_directory=Path(directory) / 'out',
            config_directory=Path(directory) / 'cfg', runner=runner)
        record = executor(candidate(), stage='S2')
    joined = ' '.join(seen['command'])
    assert 'diagnostic_canary.py' in joined
    assert '--size 8' in joined and '--seed-label AT-1' in joined
    assert 'heldout' not in joined
    assert record['label'] == probe.DIAGNOSTIC_LABEL
    assert record['qualified'] is False and record['promotion_evidence'] is False
    assert record['attempted'] == 8 and len(record['rows']) == 8


def test_a_canary_failure_is_reported_rather_than_read_as_a_score():
    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.canary_executor(
            seed_label='x', sizes={'S2': 8}, output_directory=Path(directory) / 'out',
            config_directory=Path(directory) / 'cfg',
            runner=lambda *a, **k: FakeCompleted(2, stderr='model failed to load'))
        record = executor(candidate(), stage='S2')
    assert record['outcome'] == 'failed'
    assert 'model failed to load' in record['runtime_error']
    assert 'correct' not in record


def test_a_canary_timeout_reports_no_duration():
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='x', timeout=1)

    with tempfile.TemporaryDirectory() as directory:
        executor = scheduler_module.canary_executor(
            seed_label='x', sizes={'S2': 8}, output_directory=Path(directory) / 'out',
            config_directory=Path(directory) / 'cfg', runner=runner)
        record = executor(candidate(), stage='S2')
    assert record['outcome'] == 'timed_out' and record['hardware_seconds'] is None


# ------------------------------------------------------ the diagnostic runner

def test_the_diagnostic_runner_can_only_ever_load_development_cases():
    source = (Path(__file__).resolve().parents[1] / 'scripts/diagnostic_canary.py').read_text(
        encoding='utf-8')
    assert 'secretary_heldout' not in source
    assert 'secretary_dev.json' in source
    assert '--dataset' not in source, 'it must not accept a split argument at all'


def test_the_diagnostic_runner_reuses_the_frozen_execute_and_scoring():
    source = (Path(__file__).resolve().parents[1] / 'scripts/diagnostic_canary.py').read_text(
        encoding='utf-8')
    assert 'from eval.run_secretary_eval import execute' in source
    assert 'def score' not in source, 'a second scoring definition would be a second evaluator'


def test_the_diagnostic_runner_loads_the_declared_development_split():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / 'scripts/diagnostic_canary.py'
    spec = importlib.util.spec_from_file_location('diagnostic_canary_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = module.load_development_cases()
    assert len(cases) == 35, 'the development split is 35 cases'
