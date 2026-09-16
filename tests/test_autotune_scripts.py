"""The three entry points, exercised without hardware, credentials or network."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turbo.optimizer import state as state_module

AUTOTUNE = ROOT / 'scripts/autotune.py'
STATUS = ROOT / 'scripts/autotune_status.py'
FINAL = ROOT / 'scripts/autotune_final.py'


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], cwd=ROOT, text=True,
                          capture_output=True, timeout=300)


def dry_session(directory, *extra):
    return run(AUTOTUNE, '--dry-run', '--mock-llm', '--budget-minutes', '30',
               '--session-dir', str(directory), *extra)


def test_a_dry_run_completes_and_reports_the_five_distinct_counts():
    with tempfile.TemporaryDirectory() as directory:
        result = dry_session(Path(directory))
        assert result.returncode == 0, result.stderr
        counts = json.loads(result.stdout[result.stdout.index('{'):])
    assert set(counts) == {'GENERATED_CANDIDATES', 'STATICALLY_VALID_CANDIDATES',
                           'DIAGNOSTIC_CANDIDATES', 'HARDWARE_ATTEMPTS',
                           'QUALIFIED_EXPERIMENTS'}
    assert counts['GENERATED_CANDIDATES'] >= counts['STATICALLY_VALID_CANDIDATES']
    assert counts['QUALIFIED_EXPERIMENTS'] == 0


def test_a_dry_run_writes_a_resumable_session_and_a_summary():
    with tempfile.TemporaryDirectory() as directory:
        assert dry_session(Path(directory)).returncode == 0
        session = state_module.load(Path(directory) / 'session.json')
        summary = json.loads((Path(directory) / 'reports/session-summary.json')
                             .read_text(encoding='utf-8'))
    assert session['split'] == 'development'
    assert summary['dry_run'] is True
    assert 'heldout' not in json.dumps(summary).lower()


def test_the_split_flag_accepts_nothing_but_development():
    result = run(AUTOTUNE, '--dry-run', '--split', 'heldout')
    assert result.returncode != 0
    assert 'heldout' in (result.stderr + result.stdout)
    assert 'invalid choice' in result.stderr


def test_a_dry_run_never_touches_the_experiment_archives():
    with tempfile.TemporaryDirectory() as directory:
        before = sorted(p.name for p in (ROOT / 'local/experiments').glob('*')) \
            if (ROOT / 'local/experiments').exists() else []
        assert dry_session(Path(directory)).returncode == 0
        after = sorted(p.name for p in (ROOT / 'local/experiments').glob('*')) \
            if (ROOT / 'local/experiments').exists() else []
    assert before == after


def test_the_llama_backend_generates_a_genuinely_large_space():
    with tempfile.TemporaryDirectory() as directory:
        result = dry_session(Path(directory), '--backend', 'llama_cpp_cpu',
                             '--control-config', str(ROOT / 'configs/llama-cpu-secretary.example.json'))
        assert result.returncode == 0, result.stderr
        counts = json.loads(result.stdout[result.stdout.index('{'):])
    assert counts['GENERATED_CANDIDATES'] > 50


def test_status_is_read_only_and_reports_unmeasured_fields_as_such():
    with tempfile.TemporaryDirectory() as directory:
        assert dry_session(Path(directory)).returncode == 0
        session_path = Path(directory) / 'session.json'
        before = session_path.read_bytes()
        result = run(STATUS, str(session_path))
        assert session_path.read_bytes() == before
    assert result.returncode == 0
    assert 'HARDWARE UTILISATION' in result.stdout
    assert 'SPLIT' in result.stdout and 'development' in result.stdout


def test_status_refuses_a_missing_session():
    result = run(STATUS, '/nonexistent/session.json')
    assert result.returncode != 0


def test_final_freezes_the_configuration_and_closes_the_session():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        assert dry_session(directory).returncode == 0
        session_path = directory / 'session.json'
        state = state_module.load(session_path)
        config_path = directory / 'final.json'
        config_path.write_text(json.dumps(state['current_control']['config'], indent=2),
                               encoding='utf-8')
        result = run(FINAL, str(session_path), '--config', str(config_path),
                     '--output', str(directory / 'final-freeze.json'))
        assert result.returncode == 0, result.stderr
        record = json.loads((directory / 'final-freeze.json').read_text(encoding='utf-8'))
        closed = json.loads(session_path.read_text(encoding='utf-8'))
    assert record['optimization_closed'] is True
    assert record['config_semantic_sha256'] == closed['current_control']['config_hash']
    assert closed['finished_at']
    assert 'Heldout was not evaluated' in result.stdout


def test_final_refuses_a_configuration_the_session_never_reached():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        assert dry_session(directory).returncode == 0
        session_path = directory / 'session.json'
        state = state_module.load(session_path)
        foreign = dict(state['current_control']['config'], max_tokens=16384)
        config_path = directory / 'foreign.json'
        config_path.write_text(json.dumps(foreign), encoding='utf-8')
        result = run(FINAL, str(session_path), '--config', str(config_path),
                     '--output', str(directory / 'x.json'))
    assert result.returncode != 0
    assert 'not the session final control' in result.stderr


def test_a_closed_session_cannot_be_resumed():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        assert dry_session(directory).returncode == 0
        session_path = directory / 'session.json'
        state = state_module.load(session_path)
        config_path = directory / 'final.json'
        config_path.write_text(json.dumps(state['current_control']['config']), encoding='utf-8')
        assert run(FINAL, str(session_path), '--config', str(config_path),
                   '--output', str(directory / 'f.json')).returncode == 0
        result = dry_session(directory, '--resume', str(session_path))
    assert result.returncode != 0
    assert 'already finished' in result.stderr


def test_heldout_needs_an_explicit_flag_and_a_candidate_name():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        assert dry_session(directory).returncode == 0
        session_path = directory / 'session.json'
        state = state_module.load(session_path)
        config_path = directory / 'final.json'
        config_path.write_text(json.dumps(state['current_control']['config']), encoding='utf-8')
        result = run(FINAL, str(session_path), '--config', str(config_path),
                     '--output', str(directory / 'f.json'), '--run-heldout')
    assert result.returncode != 0
    assert '--candidate-name is required' in result.stderr


def test_the_loop_never_names_the_heldout_split_anywhere_in_its_source():
    source = AUTOTUNE.read_text(encoding='utf-8')
    assert "'heldout'" not in source
    assert "dataset='dev'" in source or "'dev'" in source
    final_source = FINAL.read_text(encoding='utf-8')
    assert "'heldout'" in final_source, 'the final command is the only one that may name it'
