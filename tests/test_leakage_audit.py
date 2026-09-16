"""Synthetic exposure probes; never copy frozen heldout prompts into tests."""
import hashlib
import subprocess

from eval.leakage_audit import audit


def setup_repo(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    archive = tmp_path / 'eval/results/reviewed.json'
    archive.parent.mkdir(parents=True)
    archive.write_text('{"prompt":"synthetic withheld request"}', encoding='utf-8')
    allow = {'eval/results/reviewed.json': hashlib.sha256(archive.read_bytes()).hexdigest()}
    heldout = [{'id': 'synthetic-heldout', 'prompt': 'synthetic withheld request'}]
    return archive, allow, heldout


def test_exact_reviewed_archive_is_disclosed_not_unseen(tmp_path):
    archive, allow, heldout = setup_repo(tmp_path)
    report = audit(tmp_path, heldout, allow)
    assert report['status'] == 'PASS_WITH_DISCLOSED_EXPOSURE'
    assert not report['heldout_unseen_by_developers']
    assert report['developer_archive_exposure'] == [
        {'id': 'synthetic-heldout', 'file': 'eval/results/reviewed.json'}]


def test_new_result_copy_is_not_blanket_excluded(tmp_path):
    archive, allow, heldout = setup_repo(tmp_path)
    (archive.parent / 'new.json').write_bytes(archive.read_bytes())
    report = audit(tmp_path, heldout, allow)
    assert report['status'] == 'FAIL'
    assert report['unreviewed_exposure'][0]['file'] == 'eval/results/new.json'


def test_changed_archive_fails_even_when_prompt_removed(tmp_path):
    archive, allow, heldout = setup_repo(tmp_path)
    archive.write_text('{}', encoding='utf-8')
    report = audit(tmp_path, heldout, allow)
    assert report['status'] == 'FAIL'
    assert report['archive_integrity_errors']


def test_runtime_prompt_copy_fails_and_is_identified(tmp_path):
    archive, allow, heldout = setup_repo(tmp_path)
    runtime = tmp_path / 'turbo/prompt.py'
    runtime.parent.mkdir()
    runtime.write_text('PROMPT = "synthetic withheld request"', encoding='utf-8')
    report = audit(tmp_path, heldout, allow)
    assert report['status'] == 'FAIL'
    assert report['runtime_source_matches'] == [
        {'id': 'synthetic-heldout', 'file': 'turbo/prompt.py'}]


def test_missing_archive_fails(tmp_path):
    archive, allow, heldout = setup_repo(tmp_path)
    archive.unlink()
    assert audit(tmp_path, heldout, allow)['status'] == 'FAIL'
