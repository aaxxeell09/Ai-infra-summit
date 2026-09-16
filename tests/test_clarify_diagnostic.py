"""Offline diagnostics only: no native model, tools executed or dataset changes."""
import json
from pathlib import Path
import pytest
from turbo import clarify_diagnostic as d


def call(name='clarify', arguments=None):
    return '<tool_call>'+json.dumps({'name': name, 'arguments': arguments if arguments is not None else {'question': 'Which file?'}})+'</tool_call>'


@pytest.fixture
def setup():
    codec, files = d.codec_and_files()
    cases = d.development()
    return codec, files, cases, next(c for c in cases if c['id'] == 'dev_022')


@pytest.mark.parametrize('raw,label', [
    ('Clarify.', 'plain_prose_instead_of_tool_call'),
    (call('list_files', {}), 'semantic_decision_failure'),
    (call(arguments={}), 'missing_or_empty_question'),
    (call(arguments={'question': '  '}), 'missing_or_empty_question'),
    (call('move_file', {'path': 'a', 'destination': 'b'})+call(), 'clarification_after_action'),
    ('<tool_call>{bad}</tool_call>', 'malformed_or_noncontract_output'),
    ('<tool_call>{', 'unbalanced_tool_call_tags'),
])
def test_taxonomy_keeps_frozen_rejection(setup, raw, label):
    codec, _, _, case = setup
    result = d.classify(case, raw, codec)
    assert label in result['labels']
    assert result['frozen_action_only_success'] is False


def test_raw_json_fence_and_tags_are_all_supported_not_parser_mismatch(setup):
    codec, _, _, case = setup
    value = json.dumps({'name': 'clarify', 'arguments': {'question': 'Which file?'}})
    for raw in (value, '```json\n'+value+'\n```', call()):
        result = d.classify(case, raw, codec)
        assert result['frozen_action_only_success'] is True
        assert result['labels'] == []


def test_question_required_despite_empty_golden_arguments(setup):
    codec, _, _, case = setup
    assert case['expected']['arguments'] == {}
    assert d.classify(case, call(arguments={}), codec)['frozen_parse_error'] == 'ValueError'


def test_diagnostic_does_not_forgive_multiple_actions(setup):
    codec, _, _, case = setup
    result = d.classify(case, call()+call(), codec)
    assert result['parsed_call_count'] == 2
    assert result['frozen_action_only_success'] is False


def test_reported_length_is_a_signal_not_an_assumed_cause(setup):
    codec, _, _, case = setup
    assert 'reported_length_stop' in d.classify(case, call(), codec, {'stop_reason':'length'})['labels']
    assert 'reported_length_stop' not in d.classify(case, 'Clarify.', codec)['labels']


def test_candidates_are_separate_copies_and_cannot_modify_schema(setup):
    codec, _, _, _ = setup
    original = json.dumps(d.TOOLS, sort_keys=True)
    result = d.candidate('schema', codec)
    assert json.dumps(d.TOOLS, sort_keys=True) == original
    for before, after in zip(d.TOOLS, result['tools']):
        assert before['function']['parameters'] == after['function']['parameters']
        if before['function']['name'] != 'clarify': assert before == after
    assert result['lane'] == 'C' and result['qualified'] is False
    exported = d.candidate('prompt', codec)['system_prompt']
    assert 'at most four' not in exported and 'exactly one' in exported
    assert 'at most four' in codec.instructions()


def test_shadow_detector_uses_inventory_not_case_labels():
    files = ['one/example.log', 'two/example.log', 'unique.log']
    assert d.ambiguity_shadow('Read example.log.', files)['decision'] == 'would_clarify'
    for prompt in ('Read one/example.log.', 'Read unique.log.', 'Do not read example.log.',
                   'Read example.log from one.', 'Search example.log.', 'Move example.log to x.log.'):
        assert d.ambiguity_shadow(prompt, files)['decision'] == 'abstain'


def test_shadow_false_positive_coverage_all_development(setup):
    _, files, cases, _ = setup
    flagged = [c for c in cases if d.ambiguity_shadow(c['prompt'], files)['decision'] != 'abstain']
    assert [c['id'] for c in flagged] == ['dev_023']
    assert all(c['expected']['tool'] == 'clarify' for c in flagged)


@pytest.mark.parametrize('change', ['unknown_id', 'mixed_split', 'hash', 'expected', 'duplicate'])
def test_foreign_or_changed_case_evidence_rejected_before_analysis(tmp_path, setup, monkeypatch, change):
    codec, _, cases, case = setup
    row = {'id':case['id'], 'case_sha256':d.digest(case), 'output_text':call()}
    rows = [row]
    if change == 'unknown_id': row['id'] = 'unseen_999'
    elif change == 'mixed_split': row['split'] = 'evaluation_only'
    elif change == 'hash': row['case_sha256'] = 'invalid'
    elif change == 'expected': row['expected'] = {'tool':'list_files'}
    else: rows.append(dict(row))
    path = tmp_path/'result.json';path.write_text(json.dumps({'results':rows}))
    monkeypatch.setattr(d, 'classify', lambda *a, **k: pytest.fail('No raw analysis before identity validation'))
    with pytest.raises(ValueError):d.analyze_result(path, cases, codec)


def test_sparse_canary_has_no_invented_raw_diagnosis(tmp_path, setup):
    codec, _, cases, case = setup
    path = tmp_path/'result.json'
    path.write_text(json.dumps({'rows':[{'case_id':d.digest(case), 'failure_reasons':['PARSE_ERROR']}]}))
    result = d.analyze_result(path, cases, codec)
    assert result['clarify_raw_available'] == 0
    assert result['rows'][0]['analysis'] is None


def test_historical_development_stop_does_not_fix_clarify(setup):
    codec, _, cases, _ = setup
    roots = sorted((d.ROOT/'eval/results/qairt-repeats-0700').glob('candidate_EXP-*.json'))
    assert len(roots) == 6
    for path in roots:
        result = d.analyze_result(path, cases, codec)
        rows = [r for r in result['rows'] if r['expected_tool']=='clarify']
        assert len(rows)==9 and not any(r['archived_task_success'] for r in rows)
        assert not any('missing_or_empty_question' in r['analysis']['labels'] for r in rows)


def test_cli_no_native_import_or_overwrite(tmp_path, monkeypatch):
    import sys
    from scripts.clarify_diagnostic import main
    monkeypatch.setitem(sys.modules, 'turbo.native', None)
    output = tmp_path/'diagnostic.json'
    args = ['--diagnostic-only', '--export-candidate','prompt','--output',str(output)]
    assert main(args) == 0
    data = json.loads(output.read_text())
    assert data['inference_performed'] is False and data['qualified'] is False
    saved = output.read_bytes()
    with pytest.raises(SystemExit):main(args)
    assert output.read_bytes() == saved
    with pytest.raises(SystemExit):main(['--output', str(tmp_path/'other.json')])
