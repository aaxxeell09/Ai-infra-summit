import json
import pytest
from turbo.tool_grammar import tool_grammar,CANARY_GRAMMAR,CANARY_TEXT
from turbo.secretary_loop import decode_action
from turbo.secretary import TOOLS


def test_canary_is_single_unrequested_literal():
    assert CANARY_GRAMMAR=='root ::= '+json.dumps(CANARY_TEXT)+'\n'
    assert CANARY_TEXT!='BETA'


def test_grammar_has_every_current_tool_and_no_fixture_specific_values():
    grammar=tool_grammar()
    for i,tool in enumerate(TOOLS):
        rule=next(line for line in grammar.splitlines() if line.startswith(f'action-{i} ::= '))
        assert json.dumps(json.dumps(tool['function']['name'])) in rule
        args={key:'synthetic.txt' for key in tool['function']['parameters']['required']}
        assert decode_action(json.dumps({'name':tool['function']['name'],'arguments':args}))['arguments']==args
    assert 'hexagon' not in grammar and 'invoices' not in grammar
    assert 'envelope | "DONE"' in grammar


def test_new_schema_kind_requires_explicit_support(monkeypatch):
    import turbo.tool_grammar as mod
    monkeypatch.setattr(mod,'TOOLS',[{'function':{'name':'test','parameters':{'required':['n'],'properties':{'n':{'type':'integer'}}}}}])
    with pytest.raises(ValueError):mod.tool_grammar()
