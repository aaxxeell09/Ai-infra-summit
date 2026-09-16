import json
from pathlib import Path
import subprocess
import sys

import pytest
from turbo import research_inbox as inbox


def finding(**updates):
    return dict(dict(finding_id='synthetic-1', title='Synthetic idea', technique='Buffer reuse',
                     mechanism='Reuse allocated memory', source='synthetic test',
                     stack_compatibility='synthetic runtime only', expected_impact='LOW',
                     confidence='LOW', implementation_cost='Unestimated'), **updates)


def test_append_only_classification_and_duplicate(tmp_path):
    root = tmp_path / 'inbox'
    assert inbox.add_finding(root, finding())['created']
    original = (root / 'events/00000001.json').read_bytes()
    assert not inbox.add_finding(root, finding())['created']
    assert not inbox.add_finding(root, finding(finding_id='other', technique=' BUFFER reuse! ',
                                             mechanism='Reuse allocated MEMORY.'))['created']
    inbox.classify_finding(root, 'synthetic-1', 'NEW_EXPERIMENT', 'Synthetic triage')
    inbox.classify_finding(root, 'synthetic-1', 'NEW_EXPERIMENT', 'Synthetic triage')
    inbox.classify_finding(root, 'synthetic-1', 'LOW_PRIORITY', 'Reconsidered')
    assert (root / 'events/00000001.json').read_bytes() == original
    assert len(list((root / 'events').glob('*.json'))) == 3
    assert inbox.list_findings(root)[0]['status'] == 'LOW_PRIORITY'


def test_distinct_stack_or_mechanism_not_collapsed(tmp_path):
    inbox.add_finding(tmp_path, finding())
    assert inbox.add_finding(tmp_path, finding(finding_id='two', mechanism='Never reuse memory'))['created']
    assert inbox.add_finding(tmp_path, finding(finding_id='three', stack_compatibility='other runtime'))['created']
    with pytest.raises(ValueError, match='different contents'):
        inbox.add_finding(tmp_path, finding(title='Changed'))


@pytest.mark.parametrize('updates', [{'expected_impact': 'SUPER'}, {'confidence': 'medium'},
                                     {'title': ''}, {'source': None}, {'finding_id': '../bad'},
                                     {'run_command': 'do hardware'}])
def test_validation(tmp_path, updates):
    with pytest.raises(ValueError):
        inbox.add_finding(tmp_path, finding(**updates))
    assert not list(tmp_path.glob('events/*.json'))


def test_export_only_classified_new_ideas_and_exclusive(tmp_path):
    root = tmp_path / 'inbox'
    for index, status in enumerate([None, *sorted(inbox.STATUSES)]):
        identity = f'idea-{index}'
        inbox.add_finding(root, finding(finding_id=identity, mechanism=f'Synthetic mechanism {index}'))
        if status:
            inbox.classify_finding(root, identity, status, 'Synthetic assessment')
    result = inbox.export_ready_ideas(root, tmp_path / 'ideas.json')
    assert result['executable'] is False
    assert result['scope'] == 'development_planning_only'
    assert len(result['ideas']) == 1
    assert result['ideas'][0]['status'] == 'NEW_EXPERIMENT'
    assert not {'jobs', 'runs', 'command', 'config'} & result.keys()
    with pytest.raises(FileExistsError):
        inbox.export_ready_ideas(root, tmp_path / 'ideas.json')
    with pytest.raises(ValueError):
        inbox.export_ready_ideas(root, root / 'events/export.json')


def test_publish_failure_preserves_journal(tmp_path, monkeypatch):
    inbox.add_finding(tmp_path, finding())
    original = (tmp_path / 'events/00000001.json').read_bytes()
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(inbox.os, 'link', fail)
    with pytest.raises(OSError):
        inbox.classify_finding(tmp_path, 'synthetic-1', 'NEW_EXPERIMENT', 'Synthetic')
    assert inbox.list_findings(tmp_path)[0]['status'] == 'LOW_PRIORITY'
    assert (tmp_path / 'events/00000001.json').read_bytes() == original
    assert len(list((tmp_path / 'events').iterdir())) == 1


def test_unknown_classification_and_corrupt_journal_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        inbox.classify_finding(tmp_path, 'missing', 'NEW_EXPERIMENT', 'Synthetic')
    inbox.add_finding(tmp_path, finding())
    with pytest.raises(ValueError):
        inbox.classify_finding(tmp_path, 'synthetic-1', 'READY', 'Synthetic')
    (tmp_path / 'events/00000003.json').write_text('{}')
    with pytest.raises(ValueError):
        inbox.list_findings(tmp_path)


def test_cli_and_import_boundary(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/research_inbox.py'
    payload = tmp_path / 'finding.json'
    payload.write_text(json.dumps(finding()))
    command = [sys.executable, str(script), '--inbox', str(tmp_path / 'inbox')]
    def run(*args):
        return json.loads(subprocess.check_output(command + list(args), text=True))
    assert run('add', '--file', str(payload))['created']
    assert run('list')[0]['status'] == 'LOW_PRIORITY'
    assert run('classify', 'synthetic-1', 'NEW_EXPERIMENT', '--reason', 'Synthetic')['status'] == 'NEW_EXPERIMENT'
    assert not run('export-ready', '--output', str(tmp_path / 'ideas.json'))['executable']
    code = 'import sys; import turbo.research_inbox; assert not any(x.startswith("turbo.optimizer") for x in sys.modules)'
    subprocess.run([sys.executable, '-c', code], cwd=script.parents[1], check=True)


def test_existing_id_conflict_precedes_near_duplicate_match(tmp_path):
    inbox.add_finding(tmp_path, finding())
    inbox.add_finding(tmp_path, finding(finding_id='two', mechanism='Other mechanism'))
    with pytest.raises(ValueError, match='different contents'):
        inbox.add_finding(tmp_path, finding(finding_id='two'))


def test_concurrent_cli_adds_keep_both_events(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/research_inbox.py'
    processes = []
    for index in range(3):
        payload = tmp_path / f'input-{index}.json'
        payload.write_text(json.dumps(finding(finding_id=f'idea-{index}', mechanism=f'Mechanism {index}')))
        processes.append(subprocess.Popen([sys.executable, str(script), '--inbox', str(tmp_path / 'inbox'),
                                          'add', '--file', str(payload)], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr.decode()
        assert json.loads(stdout)['created']
    assert len(inbox.list_findings(tmp_path / 'inbox')) == 3


def test_unknown_hardware_cost_is_null(tmp_path):
    assert inbox.add_finding(tmp_path, finding())['finding']['hardware_cost_estimate'] is None
    assert not inbox.add_finding(tmp_path, finding(hardware_cost_estimate=None))['created']


@pytest.mark.parametrize('first,second', [('seed=-1', 'seed=1'), ('temperature=0.1', 'temperature=0-1')])
def test_numeric_operator_meaning_not_deduplicated(tmp_path, first, second):
    inbox.add_finding(tmp_path, finding(mechanism=first))
    assert inbox.add_finding(tmp_path, finding(finding_id='second', mechanism=second))['created']
