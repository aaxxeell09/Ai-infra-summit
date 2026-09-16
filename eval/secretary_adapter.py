"""Evaluation adapter for actual Secretary tools, with isolated execution fixtures."""
import json
import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from turbo.secretary import TOOLS, execute_tool, snapshot
from turbo.service import parse_calls

SCHEMAS = {t['function']['name']:t['function']['parameters'] for t in TOOLS}


class SecretaryAdapter:
    def __init__(self, files): self.files=tuple(sorted(set(files)))
    @classmethod
    def from_files(cls, files): return cls(files)
    @property
    def digest(self): return hashlib.sha256(json.dumps(self.files).encode()).hexdigest()
    def instructions(self):
        # Mirrors current Engine.secretary instructions, but substitutes our frozen inventory.
        return ('You are a local file secretary. Emit the required tool calls only, at most four, and preserve exact paths and constraints. Both source and destination are full workspace-relative filenames. Preserve the basename when moving into a folder. Copy source paths exactly from the inventory, including parent folders. Use clarify when essential information is missing. Never invent file contents. Available files:\n'+'\n'.join(self.files))
    def decode(self,text,*,snapshot_digest):
        if snapshot_digest != self.digest: raise ValueError('Inventory mismatch')
        if not isinstance(text,str) or len(text)>65536: raise ValueError('Invalid text')
        calls=parse_calls(text)
        if len(calls)!=1: raise ValueError('This first-action benchmark requires exactly one call')
        name=calls[0]['function']['name']
        args=json.loads(calls[0]['function']['arguments'])
        if name not in SCHEMAS: raise ValueError('Unsupported Secretary tool')
        schema=SCHEMAS[name]
        if set(args)-set(schema['properties']) or set(schema['required'])-set(args):
            raise ValueError('Wrong argument fields')
        if any(not isinstance(v,str) or not v.strip() for v in args.values()):
            raise ValueError('Expected nonempty string arguments')
        return name,args


class PreparedFixture:
    """Prepare independent roots and golden execution outside the warm task interval."""
    def __init__(self, fixture_root, expected):
        self.fixture_root, self.expected = fixture_root, expected

    def __enter__(self):
        from contextlib import ExitStack
        self.stack = ExitStack()
        try:
            self.actual_dir = self.stack.enter_context(tempfile.TemporaryDirectory())
            gold_dir = self.stack.enter_context(tempfile.TemporaryDirectory())
            shutil.copytree(self.fixture_root, self.actual_dir, dirs_exist_ok=True)
            shutil.copytree(self.fixture_root, gold_dir, dirs_exist_ok=True)
            args = self.expected['arguments'] if self.expected['tool'] != 'clarify' else {'question':'Clarify.'}
            gold = execute_tool(gold_dir, self.expected['tool'], args)
            if not gold['ok']: raise ValueError('Golden action is not executable on fixture')
            self.gold_snapshot = snapshot(gold_dir)
            self.outcome = None
            return self
        except BaseException:
            self.stack.close()
            raise

    def run_actual(self, tool, arguments):
        # Same protections and normalization as the original frozen adapter.
        for k in ['path','destination']:
            if k in arguments:
                p=Path(arguments[k].replace('\\','/'))
                if p.is_absolute() or '..' in p.parts or ':' in arguments[k]:
                    self.outcome = {'ok':False,'error':'Unsafe fixture path'}
                    self.unsafe = True
                    return
        self.unsafe = False
        normalized=dict(arguments)
        for k in ['path','destination']:
            if k in normalized: normalized[k]=normalized[k].replace('\\','/')
        self.outcome=execute_tool(self.actual_dir,tool,normalized)

    def check(self):
        return {'execution_ok':self.outcome['ok'],
                'final_state_match':not self.unsafe and snapshot(self.actual_dir)==self.gold_snapshot,
                'error':self.outcome.get('error')}

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


def execute_in_fixture(tool, arguments, expected, fixture_root):
    """Never touches personal data: independently copied temporary roots per trial."""
    with PreparedFixture(fixture_root, expected) as fixture:
        fixture.run_actual(tool, arguments)
        return fixture.check()
