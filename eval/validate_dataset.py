"""Validate golden expectations against ActionCodec and a real synthetic fixture."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scoring import load_dataset, digest, TOOLS
from eval.secretary_adapter import SecretaryAdapter as ActionCodec, TOOLS, SCHEMAS, execute_in_fixture

BENCHMARK_VERSION = 'secretary-eval-v2'


def snapshot(root, inventory):
    if not isinstance(inventory, list) or not inventory or any(not isinstance(p, str) for p in inventory):
        raise ValueError('Fixture inventory must be a nonempty string list')
    if len(set(inventory)) != len(inventory):
        raise ValueError('Duplicate fixture path')
    hashes = {}
    for name in inventory:
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name:
            raise ValueError('Unsafe fixture path: ' + name)
        target = root / name
        if not target.is_file() or any((root / Path(*p.parts[:i])).is_symlink() for i in range(1,len(p.parts)+1)):
            raise ValueError('Missing file or symlink in fixture: ' + name)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(inventory):
        raise ValueError('Fixture inventory does not match workspace files')
    return hashes


def validate_cases(cases, inventory):
    codec = ActionCodec.from_files(inventory)
    dirs = {'.'} | {str(p) for name in inventory for p in PurePosixPath(name).parents}
    for c in cases:
        exp = c['expected']
        tool, args = exp['tool'], exp['arguments']
        if c.get('difficulty') not in {'easy','medium','hard'}:
            raise ValueError('Missing difficulty: ' + c['id'])
        if type(exp.get('should_act')) is not bool or exp['should_act'] != (tool != 'clarify'):
            raise ValueError('Inconsistent should_act: ' + c['id'])
        if tool in {'read_file','move_file'}:
            source = args['path']
            if source not in codec.files:
                raise ValueError('Missing fixture source: ' + c['id'])
        if tool == 'move_file':
            dst = args['destination']
            p = PurePosixPath(dst)
            if p.is_absolute() or '..' in p.parts or '\\' in dst or dst in inventory or str(p.parent) not in dirs:
                raise ValueError('Invalid or occupied move destination: ' + c['id'])
        golden_args = args if tool != 'clarify' else {'question':'Please clarify.'}
        decoded, decoded_args = codec.decode(json.dumps({'name':tool,'arguments':golden_args}), snapshot_digest=codec.digest)
        if decoded != tool or (tool != 'clarify' and decoded_args != args):
            raise ValueError('Golden action contradicts current Secretary tools')
        evidence = c.get('rationale', {})
        kind = evidence.get('kind') if isinstance(evidence,dict) else None
        if not isinstance(evidence, dict) or not kind:
            raise ValueError('Missing golden rationale: ' + c['id'])
        if tool != 'clarify':
            if kind not in {'explicit','unique_reference'}:
                raise ValueError('Unexpected action rationale')
            if kind == 'unique_reference':
                match = evidence.get('match')
                matches = [p for p in inventory if match and match in p]
                target = args.get('path',args.get('source'))
                if matches != [target]:
                    raise ValueError('Unique reference is not unique: ' + c['id'])
            continue
        if kind == 'ambiguous_files':
            candidates = evidence.get('candidates', [])
            if len(set(candidates)) < 2 or not set(candidates) <= set(inventory):
                raise ValueError('Ambiguity requires multiple existing candidates')
        elif kind == 'missing_argument':
            if evidence.get('argument') not in {'source','destination','path','query'}:
                raise ValueError('Unknown missing argument')
        elif kind == 'missing_file':
            if not evidence.get('path') or evidence['path'] in inventory:
                raise ValueError('Missing-file rationale contradicts fixture')
        elif kind == 'overwrite':
            if evidence.get('source') not in inventory or evidence.get('destination') not in inventory:
                raise ValueError('Overwrite rationale requires existing files')
        elif kind in {'unsupported','conflicting_constraints'}:
            if not evidence.get('capability' if kind == 'unsupported' else 'description'):
                raise ValueError('Missing rationale detail')
        else:
            raise ValueError('Unknown clarification rationale: ' + str(kind))
    return codec


def leakage(heldout, root=ROOT):
    paths = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=root,text=True).splitlines()
    matches = []
    for name in sorted(set(paths)):
        if name == 'eval/datasets/secretary_heldout.json': continue
        p = root/name
        if not p.is_file() or p.stat().st_size > 2_000_000: continue
        try: text = p.read_text(encoding='utf-8')
        except UnicodeError: continue
        # JSON escaped Unicode is decoded as well; no data/model calls performed.
        try: text += '\n' + json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError: pass
        for c in heldout:
            if c['prompt'] in text:
                matches.append({'id':c['id'],'file':name})
    return matches


def validate(root=ROOT, check_manifest=True):
    paths = [root/'eval/datasets'/n for n in ['secretary_dev.json','secretary_heldout.json']]
    cases = load_dataset(paths)
    if Counter(c['split'] for c in cases) != {'development':35,'heldout':15}:
        raise ValueError('Expected fixed 35/15 split')
    if Counter(c['difficulty'] for c in cases) != {'easy':15,'medium':20,'hard':15}:
        raise ValueError('Expected 15 easy / 20 medium / 15 hard')
    if len({c['prompt'].strip() for c in cases}) != len(cases):
        raise ValueError('Duplicate prompt')
    inventory = json.loads((root/'eval/fixtures/files.json').read_text())
    hashes = snapshot(root/'eval/fixtures/secretary_workspace', inventory)
    codec = validate_cases(cases, inventory)
    for case in cases:
        exp=case['expected']
        args=exp['arguments'] if exp['tool']!='clarify' else {'question':'Clarify.'}
        verified=execute_in_fixture(exp['tool'],args,exp,root/'eval/fixtures/secretary_workspace')
        if not verified['execution_ok'] or not verified['final_state_match']:
            raise ValueError('Golden action cannot execute: '+case['id'])
    result = {'benchmark_version':BENCHMARK_VERSION,'total':len(cases),
              'splits':dict(Counter(c['split'] for c in cases)),
              'difficulties':dict(Counter(c['difficulty'] for c in cases)),
              'dataset_sha256':digest(cases), 'fixture_sha256':digest(hashes),
              'inventory_sha256':codec.digest,
              'action_schema_sha256':digest(TOOLS), 'system_prompt_sha256':hashlib.sha256(codec.instructions().encode()).hexdigest()}
    if check_manifest:
        expected = json.loads((root/'eval/benchmark_manifest.json').read_text())
        for key in result:
            if expected.get(key) != result[key]:
                raise ValueError('Golden manifest changed: '+key+'. Version and review the dataset before running models.')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-leakage',action='store_true')
    args=p.parse_args()
    result=validate()
    if args.check_leakage:
        cases=load_dataset([ROOT/'eval/datasets/secretary_heldout.json'])
        result['heldout_text_matches']=leakage(cases)
    print(json.dumps(result,indent=2))
    return 1 if result.get('heldout_text_matches') else 0


if __name__=='__main__': raise SystemExit(main())
