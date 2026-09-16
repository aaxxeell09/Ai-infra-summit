"""Regression tests for the adversarial tracking audit (see TRACKING_AUDIT.md).

Every test here reproduces a specific finding. All of them operate on synthetic
archives in temporary directories and never touch local/experiments or eval/results.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import turbo.experiments as E

REPO = Path(__file__).resolve().parents[1]


def _report(candidate, n=4, correct=2, tag='a'):
    rows = [dict(id=f'dev_{i + 1:03d}', case_sha256=f'{tag}{i}', task_success=i < correct,
                 latency_ms=1.0, task_latency_ms=2.0, invalid_output=False, split='development',
                 expected_tool='read_file', no_action_correct=True, profile={'generated_tokens': 3})
            for i in range(n)]
    return dict(schema_version=2, status='measured', benchmark_version='secretary-eval-v2',
                candidate_name=candidate, results=rows, git_commit='0' * 40, dirty=False,
                config={'backend': 'llama_cpp_cpu'},
                inference_backend={'backend_id': 'llama_cpp_cpu'}, model_label='m.gguf')


def _telemetry(candidate, joules):
    return dict(candidate_name=candidate,
                scope='Complete evaluator child process: validation, hashes, load, cases.',
                raw_before={'channels_pwh': {'SYS': 0.0}, 'monotonic_s': 0.0, 'error': None},
                raw_after={'channels_pwh': {'SYS': joules / 3.6e-9}, 'monotonic_s': 300.0, 'error': None},
                energy={'channels': {'SYS': {'energy_j': joules}}})


def _sealable_archive(root):
    archive = E.reserve(root, 'sealme')
    metadata = E.initialize(archive, {'hypothesis': 'h', 'change': 'c', 'git_commit': 'a',
                                      'git_status': '', 'git_diff': '', 'command': ['x']}, b'{}\n')
    for name in ('result.json', 'kpi.json'):
        (archive / name).write_text('{}\n', encoding='utf-8')
    for name in ('KPI.txt', 'stdout.log', 'stderr.log'):
        (archive / name).write_text('x\n', encoding='utf-8')
    metadata.update(status='completed_diagnostic')
    (archive / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return archive


# --- TRK-001: telemetry must be bound to its result, never by filename alone -------------

def test_backfill_refuses_mismatched_telemetry_identity(tmp_path):
    source = tmp_path / 'candidate_alpha.json'
    source.write_text(json.dumps(_report('alpha')), encoding='utf-8')
    foreign = tmp_path / 'candidate_alpha_telemetry.json'
    foreign.write_text(json.dumps(_telemetry('beta', 5000.0)), encoding='utf-8')
    with pytest.raises(ValueError, match='Telemetry observed candidate'):
        E.backfill(source, tmp_path / 'archives', foreign)
    assert not list((tmp_path / 'archives').glob('EXP-*/artifact-hashes.sha256'))


def test_backfill_accepts_and_records_matching_telemetry_identity(tmp_path):
    source = tmp_path / 'candidate_alpha.json'
    source.write_text(json.dumps(_report('alpha', n=4, correct=2)), encoding='utf-8')
    own = tmp_path / 'candidate_alpha_telemetry.json'
    own.write_text(json.dumps(_telemetry('alpha', 350.0)), encoding='utf-8')
    archive = E.backfill(source, tmp_path / 'archives', own)
    manifest = E.read_json(archive / 'manifest.json')
    assert manifest['telemetry_binding'] == 'declared_identity_match'
    assert E.read_json(archive / 'kpi.json')['gross_sys_j_per_correct_task'] == pytest.approx(175.0)


def test_backfill_marks_legacy_telemetry_binding_unverified(tmp_path):
    source = tmp_path / 'candidate_alpha.json'
    source.write_text(json.dumps(_report('alpha')), encoding='utf-8')
    legacy = tmp_path / 'candidate_alpha_telemetry.json'
    legacy.write_text(json.dumps({k: v for k, v in _telemetry('alpha', 350.0).items()
                                  if k != 'candidate_name'}), encoding='utf-8')
    archive = E.backfill(source, tmp_path / 'archives', legacy)
    assert E.read_json(archive / 'manifest.json')['telemetry_binding'] == 'unverified_filename_only'


def test_backfill_refuses_foreign_telemetry_when_the_result_names_nothing(tmp_path):
    report = _report('alpha')
    report.pop('candidate_name')
    source = tmp_path / 'candidate_alpha.json'
    source.write_text(json.dumps(report), encoding='utf-8')
    foreign = tmp_path / 'candidate_alpha_telemetry.json'
    foreign.write_text(json.dumps(_telemetry('beta', 5000.0)), encoding='utf-8')
    with pytest.raises(ValueError, match='offered as a companion of'):
        E.backfill(source, tmp_path / 'archives', foreign)


def test_backfill_accepts_companion_matching_the_source_label(tmp_path):
    report = _report('alpha')
    report.pop('candidate_name')
    source = tmp_path / 'candidate_alpha.json'
    source.write_text(json.dumps(report), encoding='utf-8')
    own = tmp_path / 'candidate_alpha_telemetry.json'
    own.write_text(json.dumps(_telemetry('alpha', 350.0)), encoding='utf-8')
    archive = E.backfill(source, tmp_path / 'archives', own)
    assert E.read_json(archive / 'manifest.json')['telemetry_binding'] == 'source_label_match'


def test_telemetry_identity_reads_recorded_child_argv():
    assert E.telemetry_identity({'command': ['py', '--candidate-name', 'gamma']}) == 'gamma'
    assert E.telemetry_identity({'command': ['py', '--candidate-name']}) is None
    assert E.telemetry_identity({}) is None
    assert E.telemetry_identity(None) is None


# --- TRK-002: only one supervised experiment may execute at a time -----------------------
#
# archive_lock() creates its lock FILE before acquiring the OS lock, so file existence
# proves nothing. Every test below waits for a marker the holder writes only AFTER
# acquisition. The first test is deliberately independent of the tracker so that a
# failure separates "the Windows mutex is broken" from "the harness raced".

_HOLDER = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from turbo.experiments import archive_lock
root, name, held, stop = sys.argv[2:6]
with archive_lock(root, name, timeout=30):
    Path(held).write_text('held', encoding='utf-8')   # only after acquisition
    deadline = time.monotonic() + 120
    while not Path(stop).exists() and time.monotonic() < deadline:
        time.sleep(0.02)
Path(held + '.released').write_text('released', encoding='utf-8')
"""

_CONTENDER = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from turbo.experiments import archive_lock
root, name, out = sys.argv[2:5]
record = {'os_name': os.name, 'pid': os.getpid()}
try:
    with archive_lock(root, name, timeout=1):
        record['outcome'] = 'ACQUIRED'
except TimeoutError as exc:
    record['outcome'] = 'REFUSED'
    record['detail'] = str(exc)
    cause = exc.__cause__
    if cause is not None:
        record['cause'] = type(cause).__name__
        record['errno'] = getattr(cause, 'errno', None)
except Exception as exc:
    record['outcome'] = 'ERROR'
    record['detail'] = type(exc).__name__ + ': ' + str(exc)
Path(out).write_text(json.dumps(record), encoding='utf-8')
"""


def _contend(script, root, name, out):
    subprocess.run([sys.executable, str(script), str(REPO), str(root), name, str(out)],
                   check=True, timeout=120)
    return json.loads(Path(out).read_text(encoding='utf-8'))


def _wait_for(path, seconds=90):
    deadline = time.monotonic() + seconds
    while not Path(path).exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f'timed out waiting for {path}')
        time.sleep(0.02)


def test_two_processes_cannot_hold_the_same_archive_lock(tmp_path):
    """Direct evidence for TRK-002, independent of the experiment tracker."""
    root = tmp_path / 'root'
    root.mkdir()
    holder_script = tmp_path / 'holder.py'
    holder_script.write_text(_HOLDER, encoding='utf-8')
    contender_script = tmp_path / 'contender.py'
    contender_script.write_text(_CONTENDER, encoding='utf-8')
    held, stop, out = tmp_path / 'held', tmp_path / 'stop', tmp_path / 'out'
    holder = subprocess.Popen([sys.executable, str(holder_script), str(REPO),
                               str(root.resolve()), 'proof', str(held), str(stop)])
    try:
        _wait_for(held)
        assert not (Path(str(held) + '.released')).exists(), 'holder released too early'
        # The lock file exists whether or not anyone holds the lock: archive_lock
        # opens it before acquiring. This is precisely why a file-existence probe
        # is not a valid handshake, and why the marker above is written only after
        # acquisition. Keep both assertions together so the distinction stays visible.
        assert (root / '.proof.lock').exists()
        blocked = _contend(contender_script, root, 'proof', out)
        assert blocked['outcome'] == 'REFUSED', (
            'a second process entered a lock already held by another process: ' + repr(blocked))
    finally:
        stop.write_text('stop', encoding='utf-8')
        holder.wait(timeout=120)
    _wait_for(Path(str(held) + '.released'))
    released = _contend(contender_script, root, 'proof', out)
    assert released['outcome'] == 'ACQUIRED', 'the lock was never released: ' + repr(released)


def _tracker_config(tmp_path):
    model = tmp_path / 'm.gguf'
    model.write_bytes(b'w')
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    (sdk / 'g.so').write_bytes(b'l')
    config = tmp_path / 'c.json'
    config.write_text(json.dumps({'model_path': str(model), 'sdk_dir': str(sdk)}), encoding='utf-8')
    child = tmp_path / 'child.py'
    child.write_text('print("ok")', encoding='utf-8')
    return config, child


def test_second_concurrent_run_is_refused(tmp_path):
    root = tmp_path / 'archives'
    root.mkdir()
    config, child = _tracker_config(tmp_path)
    holder_script = tmp_path / 'holder.py'
    holder_script.write_text(_HOLDER, encoding='utf-8')
    held, stop = tmp_path / 'held', tmp_path / 'stop'
    holder = subprocess.Popen([sys.executable, str(holder_script), str(REPO), str(root.resolve()),
                               'hardware-execution', str(held), str(stop)])
    try:
        _wait_for(held)
        with pytest.raises(TimeoutError, match='hardware-execution'):
            E.run('blocked', config, root=root, repo=REPO, dataset='dev', change='c',
                  hypothesis='h', command_override=[sys.executable, str(child)],
                  timeout=30, execution_lock_timeout=1, diagnostic_dirty=True)
    finally:
        stop.write_text('stop', encoding='utf-8')
        holder.wait(timeout=120)
    assert not list(root.glob('EXP-*')), 'a refused run must not allocate an EXP ID'


def test_run_releases_the_execution_lock(tmp_path):
    root = tmp_path / 'archives'
    root.mkdir()
    config, child = _tracker_config(tmp_path)
    for _ in range(2):
        E.run('sequential', config, root=root, repo=REPO, dataset='dev', change='c',
              hypothesis='h', command_override=[sys.executable, str(child)], timeout=30,
              diagnostic_dirty=True)
    assert len(list(root.glob('EXP-*'))) == 2


# --- TRK-004: every frozen benchmark hash must be compared -------------------------------

def test_wrong_inventory_hash_blocks_qualification(tmp_path, monkeypatch):
    from eval.validate_dataset import validate
    frozen = validate()
    report = _report('x')
    report.update(inventory_sha256='0' * 64)
    reasons = E.frozen_provenance_errors(report, frozen)
    assert any('inventory_sha256' in reason for reason in reasons)
    report['inventory_sha256'] = frozen['inventory_sha256']
    assert not any('inventory_sha256' in reason for reason in E.frozen_provenance_errors(report, frozen))


def test_wrong_protocol_version_blocks_qualification():
    from eval.validate_dataset import validate
    from eval.run_secretary_eval import PROTOCOL
    frozen = validate()
    report = _report('x')
    report.update(inventory_sha256=frozen['inventory_sha256'], protocol_version='made-up-v9')
    assert any('protocol_version' in reason for reason in E.frozen_provenance_errors(report, frozen))
    report['protocol_version'] = PROTOCOL
    assert not any('protocol_version' in reason for reason in E.frozen_provenance_errors(report, frozen))


# --- TRK-007: the CSV ledger must not hand a spreadsheet a formula -----------------------

def test_csv_ledger_neutralises_formula_prefix(tmp_path):
    archive = E.reserve(tmp_path, 'inj')
    metadata = E.initialize(archive, {'hypothesis': 'h', 'change': "=cmd|' /C calc'!A0",
                                      'git_commit': 'a', 'git_status': '', 'git_diff': '',
                                      'command': ['x']}, b'{}\n')
    for name in ('result.json', 'kpi.json'):
        (archive / name).write_text('{}\n', encoding='utf-8')
    (archive / 'KPI.txt').write_text('x\n', encoding='utf-8')
    (archive / 'stdout.log').write_text('o\n', encoding='utf-8')
    (archive / 'stderr.log').write_text('e\n', encoding='utf-8')
    metadata.update(status='completed_diagnostic')
    (archive / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    E.seal(archive)
    rows = E._ledger(tmp_path)
    import csv as csv_module
    with (tmp_path / 'EXPERIMENT_LEDGER.csv').open(encoding='utf-8', newline='') as handle:
        exported = list(csv_module.DictReader(handle))
    assert exported[0]['change'] == "'=cmd|' /C calc'!A0"
    assert not exported[0]['change'].startswith(('=', '+', '-', '@'))
    assert rows[0]['change'] == "=cmd|' /C calc'!A0", 'the row object keeps the raw text'
    markdown = (tmp_path / 'EXPERIMENT_LEDGER.md').read_text(encoding='utf-8')
    assert "=cmd\\|' /C calc'!A0" in markdown, 'markdown keeps the raw text, pipe-escaped'


@pytest.mark.parametrize('value', ['=1+1', '+1', '-1', '@SUM(A1)', '\t=1', '\r=1'])
def test_csv_formula_prefixes_are_neutralised(value):
    assert E.csv_safe(value).startswith("'")
    assert E.csv_safe(value)[1:] == value


@pytest.mark.parametrize('value', ['ok', '', '1.5', 'a-b', None, 3, True])
def test_csv_safe_leaves_ordinary_values_untouched(value):
    assert E.csv_safe(value) == value


# --- TRK-008: archive directories are flushed where the platform supports it ------------
#
# Contract (option A of the audit follow-up): directory fsync is a POSIX durability
# improvement. Windows has no portable equivalent, so fsync_directory is a documented
# no-op there and atomic replacement alone carries the guarantee. Both platforms assert
# something real rather than skipping.

def test_fsync_directory_reports_the_platform_contract(tmp_path):
    result = E.fsync_directory(tmp_path)
    if os.name == 'nt':
        assert result is False, 'Windows directory fsync must report itself unsupported'
    else:
        assert result is True, 'POSIX directory fsync must actually flush'


def test_fsync_directory_never_raises(tmp_path):
    assert E.fsync_directory(tmp_path / 'does-not-exist') is False
    target = tmp_path / 'f.txt'
    target.write_text('x', encoding='utf-8')
    assert E.fsync_directory(target) in (True, False)


def test_atomic_flushes_the_containing_directory(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(E, 'fsync_directory', lambda path: seen.append(Path(path)) or False)
    E.atomic(tmp_path / 'sub' / 'f.json', '{}\n')
    assert seen == [tmp_path / 'sub']


def test_seal_flushes_the_archive_directory(tmp_path, monkeypatch):
    archive = _sealable_archive(tmp_path)
    seen = []
    monkeypatch.setattr(E, 'fsync_directory', lambda path: seen.append(Path(path)) or False)
    E.seal(archive)
    assert archive in seen


def test_atomic_replacement_is_correct_even_when_directory_fsync_is_unsupported(tmp_path, monkeypatch):
    """The Windows path: no directory flush, but replacement still wins and leaves no debris."""
    monkeypatch.setattr(E, 'fsync_directory', lambda path: False)
    target = tmp_path / 'f.json'
    E.atomic(target, '{"generation":1}\n')
    assert json.loads(target.read_text(encoding='utf-8')) == {'generation': 1}
    E.atomic(target, '{"generation":2}\n')
    assert json.loads(target.read_text(encoding='utf-8')) == {'generation': 2}
    assert [p.name for p in tmp_path.iterdir()] == ['f.json'], 'no temporary debris'


# --- TRK-010: an invalid counter resolution must report its real reason ------------------

def _block(joules, duration, **extra):
    return dict(measurement_scope='full_process_energy',
                raw_before={'channels_pwh': {'SYS': 0.0}, 'monotonic_s': 0.0, 'error': None},
                raw_after={'channels_pwh': {'SYS': joules / 3.6e-9}, 'monotonic_s': duration,
                           'error': None}, **extra)


@pytest.mark.parametrize('resolution', [-1.0, 0.0, float('nan'), float('inf'), True, 'x'])
def test_invalid_counter_resolution_reports_its_real_reason(resolution):
    joules, reason = E.block_energy(_block(350.0, 100.0, declared_counter_resolution_s=resolution))[0::2]
    assert joules is None
    assert reason == 'Invalid declared counter resolution'


def test_short_block_still_reports_the_interval_reason():
    joules, _, reason = E.block_energy(_block(350.0, 5.0, declared_counter_resolution_s=1.0))
    assert joules is None
    assert reason == 'Block shorter than ten declared counter intervals'


def test_valid_resolution_still_accepts_a_long_block():
    joules, scope, reason = E.block_energy(_block(350.0, 100.0, declared_counter_resolution_s=1.0))
    assert joules == pytest.approx(350.0)
    assert scope == 'full_process_energy'
    assert reason is None
