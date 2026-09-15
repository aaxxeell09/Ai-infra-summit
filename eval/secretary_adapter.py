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


def execute_in_fixture(tool, arguments, expected, fixture_root):
    """Never touches personal data: independently copied temporary roots per trial."""
    with tempfile.TemporaryDirectory() as actual_dir, tempfile.TemporaryDirectory() as gold_dir:
        shutil.copytree(fixture_root,actual_dir,dirs_exist_ok=True)
        shutil.copytree(fixture_root,gold_dir,dirs_exist_ok=True)
        # Block traversal before delegating to real executor, even inside a disposable fixture.
        for k in ['path','destination']:
            if k in arguments:
                p=Path(arguments[k].replace('\\','/'))
                if p.is_absolute() or '..' in p.parts or ':' in arguments[k]:
                    return {'execution_ok':False,'final_state_match':False,'error':'Unsafe fixture path'}
        normalized=dict(arguments)
        for k in ['path','destination']:
            if k in normalized: normalized[k]=normalized[k].replace('\\','/')
        outcome=execute_tool(actual_dir,tool,normalized)
        golden_args=expected['arguments'] if expected['tool']!='clarify' else {'question':'Clarify.'}
        gold=execute_tool(gold_dir,expected['tool'],golden_args)
        if not gold['ok']: raise ValueError('Golden action is not executable on fixture')
        return {'execution_ok':outcome['ok'],'final_state_match':snapshot(actual_dir)==snapshot(gold_dir),
                'error':outcome.get('error')}
