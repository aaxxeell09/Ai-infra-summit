"""ToolWire: a compact typed action format with snapshot-bound path symbols.

This is a project experiment, not a claim that compact tool representations are
new. It reduces generated syntax; it does not make an inference kernel faster.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionCodec:
    files: tuple[str, ...]

    @classmethod
    def from_files(cls, files):
        return cls(tuple(sorted(set(files))))

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.files).encode()).hexdigest()

    def instructions(self):
        table = '\n'.join(f'{i}={p}' for i, p in enumerate(self.files))
        return ('Return ONE compact JSON action, no prose. File symbols:\n' + table +
                '\nActions: {"r":FILE_ID} read file; {"l":"."} list all files; '
                '{"s":"QUERY"} search files; {"m":[FILE_ID,"DESTINATION_PATH"]} move file; '
                '{"q":"QUESTION"} ask for missing information. '
                'Use q if the request is ambiguous. Preserve all constraints and exact paths.')

    def decode(self, text, *, snapshot_digest):
        if snapshot_digest != self.digest:
            raise ValueError('File symbol snapshot changed; regenerate the action')
        action = json.loads(text)
        if not isinstance(action, dict) or len(action) != 1:
            raise ValueError('Expected exactly one compact action')
        op, value = next(iter(action.items()))

        def file_path(index):
            if type(index) is not int or index < 0 or index >= len(self.files):
                raise ValueError('Unknown file symbol')
            return self.files[index]

        if op == 'r':
            return 'read_file', {'path': file_path(value)}
        if op in {'l', 's', 'q'}:
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Expected a nonempty string')
            if op == 'l':
                if value != '.':
                    raise ValueError('Only whole-workspace listing is supported')
                return 'list_files', {}
            name, key = {'l': ('list_files', 'path'), 's': ('search_files', 'query'),
                         'q': ('clarify', 'question')}[op]
            return name, {key: value}
        if op == 'm':
            if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], str):
                raise ValueError('Move requires [file symbol, destination path]')
            return 'move_file', {'path': file_path(value[0]), 'destination': value[1]}
        raise ValueError('Unknown compact action')

    def grammar(self):
        # Grammar constrains representation only. Semantic intent still requires
        # model evaluation; file tool validation remains mandatory.
        ids = ' | '.join('"' + str(i) + '"' for i in range(len(self.files))) or '"-1"'
        return '\n'.join([
            'root ::= "{" ws ("\\\"r\\\"" ws ":" ws file | "\\\"l\\\"" ws ":" ws string | "\\\"s\\\"" ws ":" ws string | "\\\"q\\\"" ws ":" ws string | "\\\"m\\\"" ws ":" ws "[" ws file ws "," ws string ws "]") ws "}"',
            'file ::= ' + ids,
            'string ::= "\\\"" char* "\\\""',
            'char ::= [^"\\\\\\x00-\\x1F] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])',
            'ws ::= [ \\t\\n\\r]*',
        ])
