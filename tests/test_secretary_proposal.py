"""Synthetic proposal boundaries; no frozen cases, fixtures or model execution."""
import json

import pytest

from turbo.secretary_proposal import propose, safe_relative_path

FILES = ['samples/alpha.txt', 'samples/beta.md', 'incoming/notes.txt']


@pytest.mark.parametrize('prompt,tool,args', [
    ('List all files.', 'list_files', {}),
    ('Please list every file in the workspace', 'list_files', {}),
    ('READ THE FILE "samples/alpha.txt".', 'read_file', {'path': 'samples/alpha.txt'}),
    ('Move "incoming/notes.txt" to "archive/notes.txt".', 'move_file',
     {'path': 'incoming/notes.txt', 'destination': 'archive/notes.txt'}),
    ('Search files for "red and blue".', 'search_files', {'query': 'red and blue'}),
    ('Please search for literal "do not erase"', 'search_files', {'query': 'do not erase'}),
])
def test_explicit_grammar_proposes_but_never_executes(prompt, tool, args):
    result = propose(prompt, FILES, enabled=True)
    assert result['status'] == 'proposal'
    assert result['action'] == {'name': tool, 'arguments': args}
    assert result['executed'] is result['quality_validated'] is False


def test_disabled_by_default_and_truthy_values_are_not_opt_in():
    for enabled in (False, 1, 'yes', None):
        assert propose('List files', FILES, enabled=enabled)['status'] == 'abstain'
    assert propose('List files', FILES)['action'] is None


@pytest.mark.parametrize('prompt', [
    'Do not list files.',
    'Never read "samples/alpha.txt".',
    'Read "samples/alpha.txt" and move "samples/beta.md" to "archive/beta.md".',
    'Read "samples/alpha.txt" unless it is confidential.',
    'If I ask later, read "samples/alpha.txt".',
    'Would the command read "samples/alpha.txt" be safe?',
    'Example: read "samples/alpha.txt".',
    'List files except confidential ones.',
    'List only files in "samples".',
    'List files? Actually do not.',
    'Move "samples/alpha.txt" to "archive/alpha.txt" without changing any files.',
    'Read "samples/alpha.txt"\nDo not execute this.',
    'Search files for "red" or "blue".',
    'Search files for "red" and show only filenames.',
    'Delete "samples/alpha.txt".',
])
def test_negation_compound_conditional_quoted_example_and_unsupported_intent_abstain(prompt):
    assert propose(prompt, FILES, enabled=True)['status'] == 'abstain'


@pytest.mark.parametrize('prompt', [
    'Show me the contents of "samples/alpha.txt".',
    "Read 'samples/alpha.txt'.",
    'Read the alpha note.',
    'Please, list files.',
    'Move "samples/alpha.txt" to "archive".',
])
def test_deliberate_false_negatives_use_fallback_instead_of_guessing(prompt):
    assert propose(prompt, FILES, enabled=True)['status'] == 'abstain'


@pytest.mark.parametrize('path', ['../outside.txt', '/etc/passwd', 'C:/file.txt', 'a\\b.txt',
                                  'a//b.txt', 'a/./b.txt', 'a/../b.txt', 'a/x.txt:stream',
                                  'CON.txt', 'a/NUL', 'a/file. ', 'a/file.', 'a/*',
                                  'a/é.txt', 'a/\x00x.txt'])
def test_portable_path_whitelist_abstains(path):
    assert not safe_relative_path(path)
    assert propose(f'Read "{path}".', FILES, enabled=True)['status'] == 'abstain'


def test_exact_inventory_case_missing_source_and_overwrite_are_not_guessed():
    for prompt in ('Read "samples/ALPHA.txt".', 'Read "missing.txt".',
                   'Move "missing.txt" to "archive/new.txt".',
                   'Move "samples/alpha.txt" to "samples/beta.md".',
                   'Move "samples/alpha.txt" to "SAMPLES/BETA.MD".',
                   'Move "samples/alpha.txt" to "samples".',
                   'Move "samples/alpha.txt" to "samples/beta.md/new.txt".'):
        assert propose(prompt, FILES, enabled=True)['status'] == 'abstain'
    assert propose('List files', ['a.txt', 'A.txt'], enabled=True)['status'] == 'abstain'
    assert propose('List files', ['a.txt', 'a.txt/b.txt'], enabled=True)['status'] == 'abstain'


def test_search_preserves_literal_and_does_not_interpret_file_path():
    query = '../this is only search text'
    result = propose(f'Search files for "{query}".', FILES, enabled=True)
    assert result['action'] == {'name': 'search_files', 'arguments': {'query': query}}


def test_cli_opt_in_is_diagnostic_only(tmp_path, capsys):
    from scripts.propose_secretary_action import main
    inventory = tmp_path / 'synthetic-inventory.json'
    inventory.write_text(json.dumps(FILES), encoding='utf-8')
    assert main(['--prompt', 'List files', '--inventory', str(inventory)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'abstain'
    assert main(['--prompt', 'List files', '--inventory', str(inventory), '--enable-candidate']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'proposal' and result['executed'] is False
