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
    assert {'GENERATED_CANDIDATES', 'STATICALLY_VALID_CANDIDATES', 'DIAGNOSTIC_CANDIDATES',
            'HARDWARE_ATTEMPTS', 'QUALIFIED_EXPERIMENTS'} <= set(counts)
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
    """Without a proposal narrowing it, the llama.cpp sweep is genuinely wide."""
    with tempfile.TemporaryDirectory() as directory:
        result = run(AUTOTUNE, '--dry-run', '--budget-minutes', '30',
                     '--backend', 'llama_cpp_cpu', '--session-dir', str(directory),
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


# ------------------------------------------- the dry run exercises the real path

def test_the_dry_run_actually_calls_the_proposer_and_the_critic():
    with tempfile.TemporaryDirectory() as directory:
        result = dry_session(Path(directory))
        assert result.returncode == 0, result.stderr
        counts = json.loads(result.stdout[result.stdout.index('{'):])
        session = state_module.load(Path(directory) / 'session.json')
    assert counts['LLM_PROPOSER_CALLS'] >= 1, 'the proposer was never invoked'
    assert counts['LLM_CRITIC_CALLS'] >= 1, 'the critic was never invoked'
    assert counts['LLM_HYPOTHESES'] >= 1
    assert session['llm']['LLM_PROPOSER_CALLS'] == counts['LLM_PROPOSER_CALLS']


def test_the_dry_run_keeps_an_inadmissible_research_idea_visible():
    with tempfile.TemporaryDirectory() as directory:
        result = dry_session(Path(directory))
        assert result.returncode == 0, result.stderr
        session = state_module.load(Path(directory) / 'session.json')
    recorded = session['llm']['hypotheses']
    assert any(h['admissible'] is False for h in recorded), 'a rejected idea must stay recorded'
    assert any(h['admissible'] is True for h in recorded)
    assert 'inadmissible research idea' in result.stdout


def test_a_proposal_changes_which_bounded_family_the_dry_run_explores():
    """The mock proposes only output_budget, so stop must not be swept as well.

    This is the observable difference an LLM is allowed to make: which declared
    family gets attention. It cannot invent a family, and it cannot widen the
    enumeration, so the assertion is about attention and nothing else.
    """
    with tempfile.TemporaryDirectory() as directory:
        guided = dry_session(Path(directory))
        assert guided.returncode == 0, guided.stderr
    with tempfile.TemporaryDirectory() as directory:
        unguided = run(AUTOTUNE, '--dry-run', '--budget-minutes', '30',
                       '--session-dir', str(directory))
        assert unguided.returncode == 0, unguided.stderr

    def families(output):
        return {line.split()[2] for line in output.splitlines()
                if len(line.split()) > 2 and line.split()[1] == 'GEN'}

    assert families(guided.stdout) == {'output_budget'}
    assert 'stop' in families(unguided.stdout)
    assert json.loads(unguided.stdout[unguided.stdout.index('{'):])['LLM_PROPOSER_CALLS'] == 0


def test_the_dry_run_routes_stages_and_exercises_the_archive_adapter():
    with tempfile.TemporaryDirectory() as directory:
        result = dry_session(Path(directory))
        assert result.returncode == 0, result.stderr
    # A dev35 drop citing an invalid rate can only come from the archived KPI
    # block, which means the observation adapter ran on a sealed archive.
    assert 'DEV35' in result.stdout
    assert 'S1' in result.stdout and 'S2' in result.stdout


def test_the_dry_run_leaves_no_simulated_archive_behind():
    with tempfile.TemporaryDirectory() as directory:
        assert dry_session(Path(directory)).returncode == 0
        leftovers = list(Path(directory).rglob('simulated-*'))
        assert leftovers == [], 'a simulated archive on disk would be manufactured evidence'


def test_the_mock_and_the_real_clients_take_the_same_integration_path():
    """--mock-llm must differ from a real run only in which client answers."""
    source = AUTOTUNE.read_text(encoding='utf-8')
    mock_branch = source[source.index('def build_llm'):source.index('def phase_plan')]
    assert 'MockClient' in mock_branch and 'AnthropicClient' in mock_branch
    # One advisor, one call site: the loop cannot have a separate mock path.
    assert source.count('advisor.propose(') == 1
    assert source.count('advisor.submit_critique(') == 1
    assert source.count('advisor_module.Advisor(') == 1


def test_missing_credentials_still_produce_a_complete_deterministic_session():
    with tempfile.TemporaryDirectory() as directory:
        result = run(AUTOTUNE, '--dry-run', '--budget-minutes', '30',
                     '--session-dir', str(directory))
        assert result.returncode == 0, result.stderr
        counts = json.loads(result.stdout[result.stdout.index('{'):])
    assert counts['LLM_PROPOSER_CALLS'] == 0
    assert counts['GENERATED_CANDIDATES'] > 0, 'deterministic search must not depend on a model'
    assert counts['HARDWARE_ATTEMPTS'] > 0


def test_the_real_path_builds_one_executor_per_stage_role():
    source = AUTOTUNE.read_text(encoding='utf-8')
    assert 'staged_executor(' in source
    assert 'startup_probe_executor(' in source
    assert 'canary_executor(' in source
    assert source.count('tracker_executor(') == 1, (
        'one tracker executor, reached only by S4 and S5')


def test_the_canary_stages_are_off_by_default_and_must_be_asked_for():
    result = run(AUTOTUNE, '--help')
    assert '--s2-cases' in result.stdout and '--s3-cases' in result.stdout
    flat = ' '.join(result.stdout.split())
    assert '0 skips S2 explicitly' in flat
    assert '0 skips S3 explicitly' in flat
