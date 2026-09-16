"""Characterize frozen-v2 hazards with synthetic inputs, without changing scoring.

These are diagnostic assertions of current behavior, NOT proposed acceptance
criteria for vNext. A versioned evaluator must adopt separately reviewed tests.
No development/heldout prompt or fixture content is copied here.
"""
import json
import os
from pathlib import Path

import pytest

from eval.scoring import score
from eval.secretary_adapter import PreparedFixture, SecretaryAdapter
from turbo.secretary import execute_tool


def synthetic_case(tool='read_file', arguments=None):
    return dict(id='synthetic-parser-diagnostic', prompt='Synthetic diagnostic only.',
                category='synthetic', split='development', difficulty='synthetic',
                expected=dict(tool=tool, arguments=arguments or {'path': 'synthetic.txt'},
                              clarification_required=False))


def encoded(tool='read_file', arguments=None):
    return json.dumps({'name': tool, 'arguments': arguments or {'path': 'synthetic.txt'}})


def tagged(text):
    return '<tool_call>' + text + '</tool_call>'


@pytest.mark.parametrize('suffix', [
    '<tool_call>{"name":"move_file"',
    '<tool_call>{"name":123,"arguments":{}}</tool_call>',
    '<tool_call>["not", "an", "action"]</tool_call>',
])
def test_frozen_v2_currently_accepts_discarded_or_unfinished_extra_call(suffix):
    result = score(synthetic_case(), tagged(encoded()) + suffix, SecretaryAdapter(['synthetic.txt']))
    # Known hazard: exactly-one surviving decoded call is not exactly-one envelope.
    assert result['task_success'] is True
    assert result['invalid_output'] is False


def test_frozen_v2_rejects_two_well_formed_actions():
    result = score(synthetic_case(), tagged(encoded()) * 2, SecretaryAdapter(['synthetic.txt']))
    assert result['task_success'] is False
    assert result['invalid_output'] is True


def test_frozen_v2_literal_closing_marker_depends_on_envelope():
    query = 'literal </tool_call> text'
    case = synthetic_case('search_files', {'query': query})
    raw = encoded('search_files', {'query': query})
    adapter = SecretaryAdapter(['synthetic.txt'])
    assert score(case, raw, adapter)['task_success'] is True
    # Regex recognizes the marker inside the JSON string as the envelope end.
    wrapped = score(case, tagged(raw), adapter)
    assert wrapped['task_success'] is False
    assert wrapped['invalid_output'] is True
    assert wrapped['parse_error'] == 'JSONDecodeError'


def test_frozen_v2_ignores_text_outside_one_complete_envelope():
    text = 'Unrequested introductory text\n' + tagged(encoded()) + '\nUnrequested trailing text'
    result = score(synthetic_case(), text, SecretaryAdapter(['synthetic.txt']))
    assert result['task_success'] is True
    assert result['invalid_output'] is False


def test_frozen_v2_duplicate_json_fields_remain_rejected():
    raw = '{"name":"read_file","name":"read_file","arguments":{"path":"synthetic.txt"}}'
    result = score(synthetic_case(), tagged(raw), SecretaryAdapter(['synthetic.txt']))
    assert result['task_success'] is False
    assert result['invalid_output'] is True


def test_production_absolute_inside_root_differs_from_frozen_fixture_path_contract(tmp_path):
    source = tmp_path / 'synthetic.txt'
    source.write_text('synthetic local-only content', encoding='utf-8')
    # General executor permits an absolute path when its resolved target is inside root.
    assert execute_tool(tmp_path, 'read_file', {'path': str(source.resolve())})['ok'] is True
    expected = {'tool': 'read_file', 'arguments': {'path': source.name}}
    with PreparedFixture(tmp_path, expected) as fixture:
        fixture.run_actual('read_file', {'path': str((Path(fixture.actual_dir) / source.name).resolve())})
        checked = fixture.check()
        assert checked['execution_ok'] is False
        assert checked['error'] == 'Unsafe fixture path'


@pytest.mark.skipif(os.name != 'posix', reason='This diagnostic targets POSIX rename replacement semantics')
def test_posix_check_then_rename_can_overwrite_intervening_destination(tmp_path, monkeypatch):
    source = tmp_path / 'source.txt'
    source.write_bytes(b'synthetic source')
    destination = tmp_path / 'destination.txt'
    rename = Path.rename

    def interleaved_rename(path, target):
        # Deterministic adversarial interleaving, confined to this disposable root.
        # The executor has already checked target.exists() before reaching here.
        Path(target).write_bytes(b'synthetic file created by another writer')
        return rename(path, target)

    monkeypatch.setattr(Path, 'rename', interleaved_rename)
    outcome = execute_tool(tmp_path, 'move_file', {'path': source.name, 'destination': destination.name})
    assert outcome['ok'] is True
    assert destination.read_bytes() == b'synthetic source'
