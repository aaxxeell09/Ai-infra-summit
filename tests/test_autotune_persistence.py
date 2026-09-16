"""Durable recovery with fake executors and the real CLI/stage routing only."""
import copy
import io
import json
from pathlib import Path
import subprocess

import pytest

from scripts import autotune
from turbo.optimizer import probe, state as S
from test_autotune_scheduler import build, QAIRT


def persistent_engine(tmp_path):
    engine, clock, state = build()
    engine.checkpoint_path = tmp_path / 'session.json'
    engine.checkpoint()
    return engine, clock, state


def test_s1_exception_checkpoint_traceback_and_claim_cleanup(tmp_path):
    engine, _, state = persistent_engine(tmp_path)
    candidate = engine.admit(engine.generate())[0]

    def crash(candidate, *, stage):
        assert S.load(engine.checkpoint_path)['hardware_journal']['job']['status'] == 'started'
        raise RuntimeError('synthetic S1 failure')

    engine.executor = crash
    with pytest.raises(RuntimeError):
        engine.run_candidate(candidate, 'S1', job_id='job')
    saved = S.load(engine.checkpoint_path)
    job = saved['hardware_journal']['job']
    assert job['status'] == 'failed' and job['qualified'] is False
    assert 'observation' not in job and saved['counters']['S1'] == 0
    assert job['failure']['error_class'] == 'RuntimeError'
    assert 'synthetic S1 failure' in job['failure']['traceback']
    assert job['failure']['hardware_observation'] is None
    assert engine.counts()['HARDWARE_ATTEMPTS'] == 1
    assert engine.counts()['QUALIFIED_EXPERIMENTS'] == 0
    assert engine.queue.active is None and engine._active is None
    assert not engine._hardware_mutex.locked()


def test_completed_job_replayed_from_full_observation_without_hardware(tmp_path):
    engine, _, _ = persistent_engine(tmp_path)
    candidate = engine.admit(engine.generate())[0]
    first = engine.run_candidate(candidate, 'S1', job_id='job')
    saved = S.load(engine.checkpoint_path)
    assert saved['hardware_journal']['job']['observation'] == first
    assert saved['queue_snapshot']['active'] is None
    resumed, _, _ = build()
    resumed.state = saved
    resumed.checkpoint_path = engine.checkpoint_path
    resumed.executor = lambda *a, **k: pytest.fail('Completed hardware must not run again')
    assert resumed.run_candidate(candidate, 'S1', job_id='job') == first
    assert saved['counters']['S1'] == 1


def test_unknown_inflight_job_is_not_automatically_relaunched(tmp_path):
    engine, _, state = persistent_engine(tmp_path)
    candidate = engine.admit(engine.generate())[0]
    state['hardware_journal']['uncertain'] = {'status': 'started'}
    engine.executor = lambda *a, **k: pytest.fail('Unknown completion requires reconciliation')
    with pytest.raises(RuntimeError, match='reconciliation'):
        engine.run_candidate(candidate, 'S1', job_id='uncertain')
    assert engine.queue.active is None and not engine._hardware_mutex.locked()


def test_rejection_is_checkpointed_and_atomic_write_preserves_old_state(tmp_path, monkeypatch):
    engine, _, _ = persistent_engine(tmp_path)
    candidate = engine.generate()[0]
    invalid = copy.deepcopy(candidate); invalid['config']['sdk_dir'] = 'changed-forbidden-location'
    assert engine.admit([invalid]) == []
    assert S.load(engine.checkpoint_path)['rejected']
    before = engine.checkpoint_path.read_bytes()
    import turbo.experiments as experiments
    def fail_replace(*args):
        raise OSError('synthetic interrupted atomic replace')
    monkeypatch.setattr(experiments.os, 'replace', fail_replace)
    with pytest.raises(OSError):
        engine.checkpoint()
    assert engine.checkpoint_path.read_bytes() == before
    assert S.load(engine.checkpoint_path)['rejected']


def install_fake_cli(monkeypatch, tmp_path, *, fail_on=2):
    config = tmp_path / 'control.json'; config.write_text(json.dumps(QAIRT), encoding='utf-8')
    home = tmp_path / 'session'
    calls = []
    original_staged = autotune.scheduler_module.staged_executor
    def fake_later(candidate, *, stage):
        if candidate.get('is_control'):
            return {'outcome': 'survive', 'stage': stage, 'hardware_seconds': 0,
                    'qualified': False, 'correct': 1, 'attempted': 1, 'invalid': 0}
        return {'outcome': 'failed', 'runtime_error': 'synthetic stop after S1', 'stage': stage,
                'hardware_seconds': 0, 'qualified': False, 'promotion_evidence': False}
    # Actual staged router and actual default S1 executor; later stages are
    # injected fake runners so this integration cannot reach model inference.
    monkeypatch.setattr(autotune.scheduler_module, 'staged_executor',
        lambda **kwargs: original_staged(probe=kwargs['probe'], canary=fake_later, tracker=fake_later))
    monkeypatch.setattr(autotune, 'build_llm', lambda *args: (None, None, {'proposer': 'UNAVAILABLE', 'critic': 'UNAVAILABLE'}))
    def fake_subprocess(command, **kwargs):
        assert str(command[3]).endswith('backend_smoke.py')
        checkpoint = S.load(home / 'session.json')
        assert checkpoint['workflow']['active_batch'] is not None
        assert any(job['status'] == 'started' for job in checkpoint['hardware_journal'].values())
        calls.append(Path(command[-1]).name)
        if len(calls) == fail_on:
            raise RuntimeError('synthetic child-launch failure')
        return subprocess.CompletedProcess(command, 0, 'synthetic startup', '')
    monkeypatch.setattr(probe.subprocess, 'run', fake_subprocess)
    argv = ['--control-config', str(config), '--session-dir', str(home), '--budget-minutes', '10',
            '--stage-limit', '3', '--s2-cases', '8', '--s3-cases', '18', '--canary-seed', 'synthetic-pilot']
    return home, calls, argv


def test_real_routing_s1_fake_subprocess_failure_then_resume_no_completed_duplicates(tmp_path, monkeypatch, capsys):
    home, calls, argv = install_fake_cli(monkeypatch, tmp_path)
    assert autotune.main(argv) == 1
    saved = S.load(home / 'session.json')
    assert saved['session_status'] == 'failed'
    jobs = list(saved['hardware_journal'].values())
    completed = next(job for job in jobs if job['status'] == 'completed')
    failed = next(job for job in jobs if job['status'] == 'failed')
    assert failed['qualified'] is False and 'observation' not in failed
    completed_name = completed['candidate']['candidate_id'] + '.json'
    assert calls.count(completed_name) == 1
    output = capsys.readouterr().err
    assert str((home / 'session.json').resolve()) in output and '--resume' in output
    assert 'RuntimeError' in output
    # Only --resume is needed: the exact original development settings are restored.
    assert autotune.main(['--resume', str(home / 'session.json')]) == 0
    resumed = S.load(home / 'session.json')
    assert calls.count(completed_name) == 1
    assert calls.count(failed['candidate']['candidate_id'] + '.json') == 1
    assert resumed['resume_settings']['s2_cases'] == 8
    assert resumed['resume_settings']['s3_cases'] == 18
    assert resumed['resume_settings']['canary_seed'] == 'synthetic-pilot'
    assert resumed['workflow']['active_batch'] is None
    assert resumed['split'] == 'development'
    assert resumed['counters'].get('qualified_experiments', 0) == 0


def test_postprocessing_crash_replays_observation_not_hardware(tmp_path, monkeypatch):
    home, calls, argv = install_fake_cli(monkeypatch, tmp_path, fail_on=None)
    real_funnel = autotune.funnel
    crashed = []
    def crash_once(stage, *args):
        if not crashed:
            crashed.append(True)
            raise RuntimeError('synthetic postprocessing failure')
        return real_funnel(stage, *args)
    monkeypatch.setattr(autotune, 'funnel', crash_once)
    assert autotune.main(argv) == 1
    before = list(calls)
    assert len(before) == 3
    assert autotune.main(['--resume', str(home / 'session.json')]) == 0
    for name in before:
        assert calls.count(name) == 1


def test_control_measurement_uses_scheduler_claim_and_checkpoint(tmp_path):
    engine, _, state = persistent_engine(tmp_path)
    def fake(candidate, *, stage):
        assert engine.queue.active is candidate
        assert S.load(engine.checkpoint_path)['hardware_journal']['control']['status'] == 'started'
        return {'outcome': 'failed', 'hardware_seconds': 0, 'stage': stage, 'qualified': False}
    engine.executor = fake
    result = autotune.measure_control(engine, state, 'S2', job_id='control')
    assert result['qualified'] is False
    assert S.load(engine.checkpoint_path)['hardware_journal']['control']['status'] == 'completed'
    assert engine.queue.active is None


def test_heldout_is_unreachable_on_cli_resume(tmp_path, monkeypatch):
    home, _, argv = install_fake_cli(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as exc:
        autotune.main(argv + ['--split', 'heldout'])
    assert exc.value.code != 0


def test_a_second_process_controller_cannot_enter_the_same_session(tmp_path):
    import sys
    from turbo.experiments import archive_lock, digest
    path = tmp_path / 'session.json'
    path.write_text('{"sentinel":"unchanged"}', encoding='utf-8')
    code = '''
import sys
from scripts.autotune import run_session
try:
    run_session(None, clock=None, executor=None, session_path=sys.argv[1], console=None)
except TimeoutError:
    raise SystemExit(23)
raise SystemExit(99)
'''
    before = path.read_bytes()
    with archive_lock(path.parent, 'autotune-session-' + digest(path.name)[:16], timeout=0):
        child = subprocess.run([sys.executable, '-c', code, str(path)],
                               cwd=autotune.ROOT, capture_output=True, text=True, timeout=10)
    assert child.returncode == 23, child.stderr
    assert path.read_bytes() == before


def test_failed_control_blocks_candidate_execution_and_promotion_on_resume(tmp_path):
    from types import SimpleNamespace
    engine, _, state = persistent_engine(tmp_path)
    candidate = engine.admit(engine.generate())[0]
    state['workflow'] = {'pool': {stage: [] for stage in ('S1','S2','S3','S4','S5')},
                         'active_batch': None, 'batch_counter': 0,
                         'confirmations': {}, 'dev35_observations': {}}
    state['workflow']['pool']['S4'] = [candidate]
    calls = []
    def fail_control(record, *, stage):
        calls.append(record['candidate_id'])
        assert record.get('is_control'), 'Candidate must not run without usable control'
        raise RuntimeError('synthetic control failure')
    engine.executor = fail_control
    for _ in range(2):
        with pytest.raises(RuntimeError):
            autotune._run_batch(engine, state, SimpleNamespace(stage_limit=1), 'S4', 'focus', engine.console)
    assert len(calls) == 1
    assert state['counters']['promotions'] == 0
    assert state['workflow']['pool']['S4'] == [candidate]
    assert not engine.queue.active and not engine._hardware_mutex.locked()
