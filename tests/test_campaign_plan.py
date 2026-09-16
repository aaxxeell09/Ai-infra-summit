"""Offline plans use synthetic configuration JSON; no model or hardware calls."""
from collections import Counter
import copy
import hashlib
import json

import pytest

from turbo.campaign_plan import differences, plan, verify_plan, write_plan
from turbo.experiments import digest


def configs(tmp_path):
    control = tmp_path / 'control.json'
    a = tmp_path / 'candidate-a.json'
    b = tmp_path / 'candidate-b.json'
    control.write_text('{"threads":1,"max_tokens":128}', encoding='utf-8')
    a.write_text('{"threads":2,"max_tokens":128}', encoding='utf-8')
    b.write_text('{"threads":3,"max_tokens":128}', encoding='utf-8')
    candidates = [dict(name=name, config=path, variable='threads', hypothesis='Synthetic test hypothesis')
                  for name, path in [('a', a), ('b', b)]]
    return control, candidates


def test_deterministic_balanced_interleaved_plan(tmp_path):
    control, candidates = configs(tmp_path)
    first = plan('reference', control, candidates)
    assert first == plan('reference', control, candidates)
    assert first['dataset'] == 'dev' and len(first['runs']) == 9
    assert Counter(r['treatment'] for r in first['runs']) == {'reference': 3, 'a': 3, 'b': 3}
    assert [r['run_order'] for r in first['runs']] == list(range(1, 10))
    for block in (1, 2, 3):
        assert {r['treatment'] for r in first['runs'] if r['block_index'] == block} == {'reference', 'a', 'b'}
    for treatment in ('reference', 'a', 'b'):
        assert {r['position_in_block'] for r in first['runs'] if r['treatment'] == treatment} == {1, 2, 3}
    assert first['treatments'][0]['config']['byte_sha256'] == hashlib.sha256(control.read_bytes()).hexdigest()
    assert verify_plan(first)['status'] == 'VERIFIED'


@pytest.mark.parametrize('count', [0, 1, 2, True, 3.0, 1001])
def test_at_least_three_bounded_integer_repetitions(tmp_path, count):
    control, candidates = configs(tmp_path)
    with pytest.raises(ValueError, match='repetitions'):
        plan('reference', control, candidates, count)


def test_single_variable_and_explicit_hypothesis_required(tmp_path):
    control, candidates = configs(tmp_path)
    candidates[0]['config'].write_text('{"threads":2,"max_tokens":64}', encoding='utf-8')
    with pytest.raises(ValueError, match='expected only'):
        plan('reference', control, candidates)
    candidates[0]['config'].write_text('{"threads":2,"max_tokens":128}', encoding='utf-8')
    candidates[0]['hypothesis'] = ' '
    with pytest.raises(ValueError, match='hypothesis'):
        plan('reference', control, candidates)


def test_same_config_or_wrong_declared_variable_is_refused(tmp_path):
    control, candidates = configs(tmp_path)
    candidates[0]['config'] = control
    with pytest.raises(ValueError, match=r'found \[\]'):
        plan('reference', control, candidates)
    control, candidates = configs(tmp_path)
    candidates[0]['variable'] = 'max_tokens'
    with pytest.raises(ValueError, match='expected only'):
        plan('reference', control, candidates)


def test_byte_drift_rejected_even_if_json_meaning_unchanged(tmp_path):
    control, candidates = configs(tmp_path)
    value = plan('reference', control, candidates)
    control.write_text('{"threads": 1, "max_tokens": 128}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Config drift'):
        verify_plan(value)


def test_changed_schedule_and_heldout_rejected_even_if_rehashed(tmp_path):
    control, candidates = configs(tmp_path)
    value = plan('reference', control, candidates)
    changed = copy.deepcopy(value)
    changed['runs'][0]['run_order'] = 99
    changed['plan_sha256'] = digest({k: v for k, v in changed.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='schedule'):
        verify_plan(changed)
    value['dataset'] = 'heldout'
    value['plan_sha256'] = digest({k: v for k, v in value.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='non-development'):
        verify_plan(value)


def test_output_exclusive_and_config_preserved(tmp_path):
    control, candidates = configs(tmp_path)
    value = plan('reference', control, candidates)
    before = control.read_bytes()
    with pytest.raises(ValueError, match='input config'):
        write_plan(control, value)
    output = write_plan(tmp_path / 'new-plan.json', value)
    assert json.loads(output.read_text()) == value
    with pytest.raises(FileExistsError):
        write_plan(output, value)
    assert control.read_bytes() == before


def test_cli_creates_and_verifies_without_launching(tmp_path, capsys):
    from scripts.plan_experiment_campaign import main
    control, candidates = configs(tmp_path)
    output = tmp_path / 'plan.json'
    assert main(['--control-config', str(control), '--candidate', 'a', str(candidates[0]['config']),
                 'threads', 'Synthetic hypothesis', '--output', str(output)]) == 0
    assert main(['--verify', str(output)]) == 0
    assert 'OFFLINE_PLAN_ONLY' in capsys.readouterr().out


def test_nested_variable_is_identified_without_conflating_other_fields():
    assert differences({'runtime': {'threads': 1}, 'label': 'x'},
                       {'runtime': {'threads': 2}, 'label': 'x'}) == ['runtime.threads']


def test_config_snapshot_hash_and_semantics_use_one_captured_read(tmp_path, monkeypatch):
    from pathlib import Path
    from turbo.campaign_plan import config_snapshot
    path = tmp_path / 'changing.json'
    original = b'\xef\xbb\xbf{"threads":1}'
    replacement = b'{"threads":99}'
    path.write_bytes(original)
    read_bytes = Path.read_bytes
    reads = []

    def replace_after_read(current):
        raw = read_bytes(current)
        if current == path:
            reads.append(raw)
            current.write_bytes(replacement)
        return raw

    monkeypatch.setattr(Path, 'read_bytes', replace_after_read)
    snapshot = config_snapshot(path)
    assert reads == [original]
    assert snapshot['byte_sha256'] == hashlib.sha256(original).hexdigest()
    assert snapshot['value'] == {'threads': 1}
    assert snapshot['semantic_sha256'] == digest({'threads': 1})
    assert read_bytes(path) == replacement


@pytest.mark.parametrize('candidates', [None, {}, 'candidate', [None], [42], [[]],
                                        [{'name': 'a', 'variable': 'threads', 'hypothesis': 'test'}],
                                        [{'name': 'a', 'variable': 'threads', 'hypothesis': 'test', 'config': None}]])
def test_malformed_candidate_input_is_a_value_error(tmp_path, candidates):
    control, _ = configs(tmp_path)
    with pytest.raises(ValueError):
        plan('reference', control, candidates)


@pytest.mark.parametrize('treatment', [None, [], {'role': 'candidate'},
                                      {'role': 'candidate', 'name': 'a', 'config': None}])
def test_malformed_verified_treatment_is_a_value_error(tmp_path, treatment):
    control, candidates = configs(tmp_path)
    value = plan('reference', control, candidates)
    value['treatments'][1] = treatment
    value['plan_sha256'] = digest({k: v for k, v in value.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='Malformed campaign treatment'):
        verify_plan(value)
