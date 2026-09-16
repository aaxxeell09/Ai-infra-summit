"""Opt-in GBNF for the existing tool syntax; form constraints, never intent proof."""
import json
from .secretary import TOOLS

VERSION = 'secretary-tool-output-gbnf-v1'
CANARY_TEXT = 'CANARY_OK_731'
CANARY_GRAMMAR = 'root ::= "' + CANARY_TEXT + '"\n'


def tool_grammar():
    # Literal JSON spellings are themselves quoted as GBNF terminals.
    lit = lambda text: json.dumps(text, ensure_ascii=True)
    key = lambda text: lit(json.dumps(text))
    rules = ['root ::= ws (envelope | "DONE") ws',
             'envelope ::= "<tool_call>" ws action ws "</tool_call>"',
             'action ::= ' + ' | '.join(f'action-{i}' for i in range(len(TOOLS)))]
    for i, tool in enumerate(TOOLS):
        fn = tool['function']; schema = fn['parameters']; fields = schema['required']
        if set(fields) != set(schema['properties']) or any(v['type'] != 'string' for v in schema['properties'].values()):
            raise ValueError('Grammar supports only the current required-string tool schema')
        argument_parts = [key(field) + ' ws ":" ws string' for field in fields]
        arguments = 'ws ' + ' ws "," ws '.join(argument_parts) + ' ws' if argument_parts else 'ws'
        rules.append(f'action-{i} ::= "{{" ws {key("name")} ws ":" ws {key(fn["name"])} ws "," ws '
                     f'{key("arguments")} ws ":" ws "{{" {arguments} "}}" ws "}}"')
    rules.extend([
        r'string ::= "\"" char+ "\""',
        r'char ::= [^"\\\x00-\x1F] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
        r'ws ::= [ \t\n\r]*',
    ])
    return '\n'.join(rules) + '\n'
