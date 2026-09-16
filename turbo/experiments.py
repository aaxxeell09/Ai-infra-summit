"""Immutable, local-only experiment archives. Does not change Secretary scoring.

An archive is writable while incomplete and sealed by artifact-hashes.sha256.
Recovery never edits an abandoned archive; later attempts receive new identifiers.
Ledgers are rebuildable indexes, not the evidence itself.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

from .json_io import parse_json

SCHEMA = 'local-turbo.experiment.v1'
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVES = ROOT / 'local/experiments'
ID_RE = re.compile(r'^EXP-(\d+)_')
PRIMARY = ('success_rate_pct', 'median_e2e_ms', 'gross_sys_j_per_correct_task')
EVALUATOR_FILES = ('eval/scoring.py','eval/run_secretary_eval.py',
                   'eval/validate_dataset.py','eval/secretary_adapter.py')
APPLICATION_FILES = ('turbo/secretary.py','turbo/service.py','turbo/native.py',
                     'turbo/policy.py','turbo/tuning.py')


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return parse_json(Path(path).read_bytes())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic(path, data):
    """Atomic replacement for an active manifest or rebuildable index only."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data.encode('utf-8') if isinstance(data, str) else data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def stats(values):
    if not values or any(not finite(v) for v in values):
        return dict(n=len(values), mean=None, median=None, p95=None, stddev=None, cv=None, min=None, max=None)
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else None
    return dict(n=len(values), mean=mean, median=statistics.median(values),
                p95=sorted(values)[math.ceil(.95*len(values))-1] if len(values) >= 20 else None,
                stddev=sd, cv=sd/mean if sd is not None and mean > 0 else None,
                min=min(values), max=max(values))


def taxonomy(row):
    """Diagnostic labels from frozen flags; never rescore raw model output."""
    if row.get('task_success') is True: return ['correct']
    reasons = set(row.get('failure_reasons') or [])
    labels = []
    mapping = {'TIMEOUT':'timeout', 'MODEL_ERROR':'runtime_error',
               'EXECUTION_ERROR':'execution_failure', 'WRONG_FINAL_STATE':'filesystem_state_failure',
               'FAILED_TO_CLARIFY':'clarify_failure', 'UNNECESSARY_CLARIFICATION':'wrong_no_action',
               'WRONG_ACTION':'wrong_tool', 'WRONG_ARGUMENT':'wrong_arguments',
               'WRONG_SOURCE':'wrong_arguments', 'WRONG_DESTINATION':'wrong_arguments'}
    if row.get('invalid_output') is True: labels.append('invalid_format')
    labels += [v for k,v in mapping.items() if k in reasons]
    return sorted(set(labels)) or ['unclassified_incorrect']


def rows_of(report):
    if not isinstance(report, dict): raise ValueError('result must be an object')
    rows = report.get('results')
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('result.results must be an array of objects')
    if any(type(r.get('task_success')) is not bool for r in rows):
        raise ValueError('each task_success must be boolean')
    return rows


def block_energy(telemetry):
    """Accept raw-consistent full-process/block SYS evidence, never guessed energy."""
    if not isinstance(telemetry, dict): return None, None, 'No telemetry'
    scope = telemetry.get('measurement_scope')
    if scope not in ('full_process_energy', 'warm_suite_block'):
        # Existing observer records a verbose, explicit complete-process scope.
        if str(telemetry.get('scope','')).startswith('Complete evaluator child process:'):
            scope = 'full_process_energy'
        else: return None, None, 'Unknown energy boundary'
    before, after = telemetry.get('raw_before'), telemetry.get('raw_after')
    if not isinstance(before, dict) or not isinstance(after, dict): return None, scope, 'Missing raw counters'
    try:
        a,b = before['channels_pwh']['SYS'],after['channels_pwh']['SYS']
        dt = after['monotonic_s'] - before['monotonic_s']
        if before.get('error') or after.get('error') or not finite(a) or not finite(b) or b <= a or not finite(dt) or dt <= 0:
            return None, scope, 'Invalid/stale/reset raw counters'
        joules = (b-a)*3.6e-9
        declared = ((telemetry.get('energy') or {}).get('channels') or {}).get('SYS',{}).get('energy_j')
        if declared is not None and (not finite(declared) or not math.isclose(declared,joules,rel_tol=1e-7)):
            return None, scope, 'Counter energy mismatch'
        resolution = telemetry.get('declared_counter_resolution_s')
        if resolution is not None and (not finite(resolution) or resolution <= 0 or dt < 10*resolution):
            return None, scope, 'Block shorter than ten declared counter intervals'
        if not finite(joules): return None, scope, 'Nonfinite energy'
        return joules, scope, None
    except (KeyError, TypeError): return None, scope, 'Malformed raw counters'


def kpis(report, telemetry=None, *, complete=True):
    rows=rows_of(report); n=len(rows); correct=sum(r['task_success'] for r in rows)
    inference=stats([r.get('latency_ms') for r in rows])
    boundary=None; latency=stats([])
    if rows and all(finite(r.get('warm_task_latency_ms')) for r in rows):
        boundary='warm_task_v1: excludes fixture preparation, load and final filesystem audit'
        latency=stats([r['warm_task_latency_ms'] for r in rows])
    elif rows and all(finite(r.get('task_latency_ms')) for r in rows):
        boundary='recorded_task_latency_ms: evaluator task boundary; not user-facing cold E2E'
        latency=stats([r['task_latency_ms'] for r in rows])
    total, energy_scope, energy_reason=block_energy(telemetry)
    if not n: total=None; energy_reason='No attempted task results'
    if not complete: energy_reason='Incomplete experiment/task result set; raw block energy retained without J/correct'
    invalid=sum(r.get('invalid_output') is True for r in rows) if all(type(r.get('invalid_output')) is bool for r in rows) else None
    clar=[r for r in rows if r.get('expected_tool',(r.get('expected') or {}).get('tool'))=='clarify']
    tokens=stats([(r.get('profile') or {}).get('generated_tokens') for r in rows])
    counts={}
    for r in rows:
        for label in taxonomy(r): counts[label]=counts.get(label,0)+1
    return dict(success_rate_pct=100*correct/n if n else None,correct_tasks=correct,total_tasks=n,
                median_e2e_ms=latency['median'],p95_e2e_ms=latency['p95'],mean_e2e_ms=latency['mean'],
                latency_boundary=boundary,latency_unavailable_reason=None if boundary else 'No task latency recorded; inference is not E2E',
                inference_latency_ms=inference,gross_sys_j=total,
                gross_sys_j_per_correct_task=total/correct if complete and total is not None and correct else None,
                energy_denominator_complete=bool(complete and n),
                energy_scope=energy_scope,energy_qualification='diagnostic_uncommissioned' if total is not None else 'unavailable',
                energy_comparable=False,energy_unavailable_reason=energy_reason or ('Zero correct tasks' if not correct else None),
                invalid_count=invalid,invalid_rate=invalid/n if invalid is not None and n else None,
                clarify_accuracy=100*sum(r.get('no_action_correct') is True for r in clar)/len(clar) if clar and all(type(r.get('no_action_correct')) is bool for r in clar) else None,
                clarify_cases=len(clar),generated_tokens=tokens,
                total_generated_tokens=sum((r.get('profile') or {}).get('generated_tokens') for r in rows) if tokens['mean'] is not None else None,
                error_taxonomy=counts,diagnostic_labels_overlap=True)


def capture_environment():
    """Small allowlisted software inventory; no environment variables or hostname."""
    software={}
    for name in ('git','node','npm'):
        executable=shutil.which(name)
        if executable is None:
            software[name]={'status':'unavailable','version':None,'reason':'Executable not found'}
            continue
        try:
            completed=subprocess.run([executable,'--version'],capture_output=True,text=True,
                                     encoding='utf-8',errors='replace',timeout=2,check=False)
            output=(completed.stdout or completed.stderr or '').strip()
            if completed.returncode or not output:
                software[name]={'status':'unavailable','version':None,
                                'reason':'Version command failed or returned no output','returncode':completed.returncode}
            else:
                software[name]={'status':'available','version':output.splitlines()[0][:256]}
        except subprocess.TimeoutExpired:
            software[name]={'status':'unavailable','version':None,'reason':'Version command exceeded 2 seconds'}
        except OSError:
            software[name]={'status':'unavailable','version':None,'reason':'Version command could not execute'}
    return {'python':sys.version,'platform':sys.platform,'os':platform.system(),
            'os_release':platform.release(),'os_version':platform.version(),
            'architecture':platform.machine(),'python_version':platform.python_version(),
            'python_implementation':platform.python_implementation(),'software':software,
            'capture_scope':'Supervisor host at execution; allowlisted OS and software versions only'}


def git_state(repo=ROOT):
    def git(*args): return subprocess.check_output(['git',*args],cwd=repo).decode('utf-8',errors='replace').strip()
    status=git('status','--porcelain')
    return dict(git_commit=git('rev-parse','HEAD'),branch=git('branch','--show-current'),
                dirty=bool(status),git_status=status,git_diff=git('diff','HEAD','--binary'))


def artifact_identity(path):
    """New canonical manifest; never replaces legacy model hash semantics."""
    path=Path(path)
    if not path.exists(): raise ValueError('Artifact missing: '+str(path))
    if path.is_symlink(): raise ValueError('Artifact symlinks are unsupported')
    files=[path] if path.is_file() else sorted(path.rglob('*'))
    entries=[]
    for p in files:
        if p.is_symlink(): raise ValueError('Artifact contains symlink: '+str(p))
        if p.is_file(): entries.append(dict(path=p.name if path.is_file() else p.relative_to(path).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    if not entries: raise ValueError('Empty artifact')
    return dict(schema_version='artifact.posix.v1',files=entries,sha256=digest(entries))


@contextmanager
def archive_lock(root, name, timeout=30):
    """OS-owned lock: released on process exit; its persistent file is harmless.

    Distinct allocation/backfill/ledger locks are acquired only in that direction:
    backfill may allocate and rebuild a ledger; no operation acquires backfill
    while holding either other lock.
    """
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    path=root/('.'+name+'.lock')
    if path.is_symlink(): raise ValueError('Lock symlinks unsupported')
    with path.open('a+b') as stream:
        if stream.seek(0,os.SEEK_END)==0:
            stream.write(b'0');stream.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic()>=deadline: raise TimeoutError('Archive lock deadline exceeded: '+name) from exc
                time.sleep(.02)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def reserve(root, name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}',name): raise ValueError('name must be a short portable slug')
    root=Path(root)
    with archive_lock(root,'allocation'):
        index=max([int(m.group(1)) for p in root.iterdir() if (m:=ID_RE.match(p.name))]+[0])+1
        path=root/f'EXP-{index:03d}_{name}'
        path.mkdir(exist_ok=False)
        return path


def archives(root):
    return sorted((p for p in Path(root).glob('EXP-*') if p.is_dir()),
                  key=lambda p:(int(ID_RE.match(p.name).group(1)) if ID_RE.match(p.name) else -1,p.name))


def seal(path):
    path=Path(path)
    if path.is_symlink(): raise ValueError('Archive symlinks unsupported')
    if (path/'artifact-hashes.sha256').exists(): raise FileExistsError('Archive already sealed')
    lines=[]
    for p in sorted(path.rglob('*')):
        if p.is_symlink(): raise ValueError('Archive symlinks unsupported')
        if p.is_file(): lines.append(sha(p)+'  '+p.relative_to(path).as_posix())
    with (path/'artifact-hashes.sha256').open('x',encoding='utf-8',newline='\n') as f:
        f.write('\n'.join(lines)+'\n');f.flush();os.fsync(f.fileno())


def verify(path):
    path=Path(path);manifest=path/'artifact-hashes.sha256'
    if path.is_symlink() or manifest.is_symlink(): return ['Archive or checksum manifest is a symlink']
    if not manifest.is_file(): return ['Archive incomplete: checksum manifest absent']
    errors=[];expected={}
    try: lines=manifest.read_text(encoding='utf-8').splitlines()
    except (OSError,UnicodeError): return ['Unreadable checksum manifest']
    for line in lines:
        try: h,name=line.split('  ',1)
        except ValueError: errors.append('Malformed checksum line');continue
        target=path/name
        if not re.fullmatch('[a-f0-9]{64}',h) or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name or ':' in name or '\x00' in name or name in expected:
            errors.append('Unsafe or duplicate checksum entry');continue
        expected[name]=h
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(path.resolve()):errors.append('Missing/unsafe: '+name)
        elif sha(target)!=h:errors.append('Hash mismatch: '+name)
    actual={p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file() and p!=manifest}
    if actual!=set(expected):errors.append('Archive file inventory differs')
    required={'manifest.json','result.json','config.json','kpi.json','KPI.txt',
              'hypothesis.md','change-from-previous.md','git-head.txt','git-status.txt',
              'git-diff.patch','command.json','command.txt','reproduce.txt',
              'environment.json','stdout.log','stderr.log'}
    if not required.issubset(expected): errors.append('Missing required archive structure')
    if any(p.is_symlink() for p in path.rglob('*')): errors.append('Archive contains symlink')
    if not errors:
        try:
            data=read_json(path/'manifest.json')
            if (not isinstance(data,dict) or data.get('schema_version')!=SCHEMA
                    or data.get('experiment_id')!=path.name.split('_',1)[0]
                    or data.get('status') not in {'failed','timeout','completed_diagnostic',
                                               'completed_qualified','historical_diagnostic'}):
                errors.append('Invalid archive manifest identity/status')
        except (ValueError,OSError): errors.append('Malformed archive manifest')
    return errors


def initialize(path, metadata, config_bytes=None):
    path=Path(path)
    if path.is_symlink() or any(path.iterdir()):
        raise FileExistsError('Archive initialization requires a new empty directory')
    metadata={**metadata,'schema_version':SCHEMA,'experiment_id':path.name.split('_',1)[0],
              'name':path.name.split('_',1)[1],'archive_created_utc':now(),'status':'incomplete'}
    write_json(path/'manifest.json',metadata)
    for filename,key in [('hypothesis.md','hypothesis'),('change-from-previous.md','change'),
                         ('git-head.txt','git_commit'),('git-status.txt','git_status'),('git-diff.patch','git_diff')]:
        (path/filename).write_text(str(metadata.get(key) if metadata.get(key) is not None else 'NOT_RECORDED')+'\n',encoding='utf-8')
    (path/'config.json').write_bytes(config_bytes if config_bytes is not None else b'{"availability":"not_recorded"}\n')
    command=metadata.get('command')
    write_json(path/'command.json',command)
    text=(subprocess.list2cmdline(command) if os.name=='nt' else shlex.join(command)) if isinstance(command,list) else (command or 'NOT_RECORDED')
    (path/'command.txt').write_text(text+'\n',encoding='utf-8')
    (path/'reproduce.txt').write_text(text+'\n',encoding='utf-8')
    write_json(path/'environment.json',metadata.get('environment') or {'availability':'not_recorded'})
    return metadata


def finish(path, metadata, result=None, telemetry=None, status='completed_diagnostic', notes=None):
    if (path/'artifact-hashes.sha256').exists():raise FileExistsError('Cannot change sealed archive')
    metric=None
    if result is not None:
        try:
            complete=status not in {'failed','timeout'} and metadata.get('case_set_complete') is not False and result.get('status')=='measured'
            metric=kpis(result,telemetry,complete=complete)
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            status='failed';notes=(notes or [])+['Malformed result: '+str(exc)]
    if not (path/'result.json').exists(): write_json(path/'result.json',result if result is not None else {'availability':'not_recorded'})
    if telemetry is not None and not (path/'telemetry.json').exists():write_json(path/'telemetry.json',telemetry)
    for name in ('stdout.log','stderr.log'):
        if not (path/name).exists():(path/name).write_text('NOT_RECORDED\n',encoding='utf-8')
    write_json(path/'kpi.json',metric or {k:None for k in PRIMARY})
    def display(v):return 'UNAVAILABLE' if v is None else f'{v:.3f}'
    k=metric or {}
    (path/'KPI.txt').write_text('SUCCESS='+display(k.get('success_rate_pct'))+'%\nMEDIAN_TASK='+display(k.get('median_e2e_ms'))+' ms\nENERGY='+display(k.get('gross_sys_j_per_correct_task'))+' J/correct\nLATENCY_SCOPE='+str(k.get('latency_boundary'))+'\nENERGY_SCOPE='+str(k.get('energy_scope'))+'\nENERGY_QUALIFICATION='+str(k.get('energy_qualification','unavailable'))+'\n',encoding='utf-8')
    metadata.update(status=status,finished_utc=now(),primary_kpis=metric,notes=notes or [],
                    energy_qualification=k.get('energy_qualification','unavailable'),energy_comparable=False)
    write_json(path/'manifest.json',metadata)
    seal(path)
    ledger(path.parent)
    return metadata


def sampling_evidence(report):
    """Retain sampler observations verbatim; never infer effective zero/seed defaults."""
    rows=report.get('results') or []
    observations=[];effective=[];variants=[]
    for index,row in enumerate(rows):
        if not isinstance(row,dict) or not isinstance(row.get('sampling'),dict): continue
        value=row['sampling']
        observations.append({'row_index':index,'case_id':row.get('id'),'sampling':value})
        if value not in variants: variants.append(value)
        actual=value.get('effective')
        if not isinstance(actual,dict):
            actual={key:value[key] for key in value if key.startswith('effective_')}
        if actual: effective.append({'row_index':index,'case_id':row.get('id'),'values':actual})
    unanimous=effective[0]['values'] if effective and len(effective)==len(rows) and all(x['values']==effective[0]['values'] for x in effective) else None
    return dict(requested=report.get('generation_protocol'),reported_by_case=observations,
                distinct_reported=variants,rows_with_sampling=len(observations),total_rows=len(rows),
                effective=unanimous,effective_by_case=effective,
                seed=unanimous.get('seed',unanimous.get('effective_seed')) if unanimous else None,
                note='Reported row fields preserved; effective values only when explicitly recorded. Zero does not prove greedy; missing values unknown.')


def captured_runner_identity(repo, model, artifacts):
    """Bind legacy evaluator digests to captured bytes without changing their format."""
    repo=Path(repo)
    result={'evaluator_sha256':{name:sha(repo/name) for name in EVALUATOR_FILES},
            'application_sources_sha256':{name:sha(repo/name) for name in APPLICATION_FILES},
            'model_sha256':None}
    if model and artifacts.get('model'):
        entries=artifacts['model']['files']
        if Path(model).is_file(): result['model_sha256']=entries[0]['sha256']
        else:
            legacy=hashlib.sha256()
            for entry in entries:
                # Match the existing evaluator's platform-native directory hash.
                # The separate artifact.posix.v1 identity stays portable.
                legacy.update(str(Path(entry['path'])).encode()+b'\0')
                legacy.update(bytes.fromhex(entry['sha256']))
            result['model_sha256']=legacy.hexdigest()
    return result


def runner_identity_errors(report, captured):
    errors=[]
    for key in ('evaluator_sha256','application_sources_sha256','model_sha256'):
        if not captured.get(key) or report.get(key)!=captured[key]:
            errors.append('Runner identity differs from captured bytes: '+key)
    return errors


def report_metadata(report):
    keys=('git_commit','branch','dirty','benchmark_version','protocol_version','dataset_sha256',
          'fixture_sha256','inventory_sha256','action_schema_sha256','system_prompt_sha256',
          'evaluator_sha256','application_sources_sha256','model_sha256','config_sha256',
          'inference_backend','generation_protocol','environment','runtime_version','timestamp','warmup','model_hash_method')
    data={k:report.get(k) for k in keys}
    data.update(model=report.get('model_label'),config=report.get('config'),
                sampling=sampling_evidence(report),
                evidence={'provenance':'OBSERVED_LOG','kpis':'DERIVED','unrecorded':'UNKNOWN'})
    return data


def backfill(source, root=DEFAULT_ARCHIVES, telemetry_path=None):
    source=Path(source).resolve();raw=source.read_bytes();report=parse_json(raw)
    probe=isinstance(report,dict) and report.get('kind')=='counter_update_probe'
    if not probe: rows_of(report)
    telemetry_raw=Path(telemetry_path).read_bytes() if telemetry_path else None
    telemetry=parse_json(telemetry_raw) if telemetry_raw is not None else None
    with archive_lock(root,'backfill'):
        return _backfill(source,root,telemetry_path,raw,report,probe,telemetry_raw,telemetry)


def _backfill(source, root, telemetry_path, raw, report, probe, telemetry_raw, telemetry):
    fingerprint=digest({'result':hashlib.sha256(raw).hexdigest(),'telemetry':hashlib.sha256(telemetry_raw).hexdigest() if telemetry_raw is not None else None})
    for existing in archives(root):
        try:m=read_json(existing/'manifest.json')
        except (OSError,ValueError):continue
        if m.get('source_fingerprint')==fingerprint:
            if not (existing/'artifact-hashes.sha256').exists(): continue  # abandoned attempt stays untouched
            if verify(existing):raise ValueError('Existing backfill is incomplete or tampered: '+str(existing))
            return existing
    slug=re.sub('[^A-Za-z0-9_-]','-',source.stem)[:85].strip('-') or 'historical'
    path=reserve(root,slug)
    meta={**report_metadata(report),'source_fingerprint':fingerprint,'source_path':str(source),
          'qualification_status':'historical_diagnostic','hypothesis':'NOT_RECORDED',
          'change':'Historical copy; original artifacts unchanged','command':report.get('run_command') or report.get('command'),
          'control_experiment':None,'git_status':None,'git_diff':None}
    meta=initialize(path,meta,json.dumps(report.get('config') or {'availability':'not_recorded'},ensure_ascii=False).encode())
    (path/'result.json').write_bytes(raw)
    related=path/'source-artifacts';related.mkdir()
    # Preserve companions by exact source stem, and explicitly supplied telemetry.
    candidates=set(source.parent.glob(source.stem+'*'))
    if telemetry_path:candidates.add(Path(telemetry_path))
    for item in sorted(candidates):
        if item.is_file() and not item.is_symlink():
            target=related/item.name
            captured=raw if item.resolve()==source else telemetry_raw if telemetry_path and item.resolve()==Path(telemetry_path).resolve() else item.read_bytes()
            if target.exists() and target.read_bytes()!=captured:raise ValueError('Companion collision')
            if not target.exists():target.write_bytes(captured)
    if telemetry_raw is not None:(path/'telemetry.json').write_bytes(telemetry_raw)
    finish(path,meta,None if probe else report,telemetry,'historical_diagnostic',
           ['Historical values were not reconstructed from current machine state.']+(['Energy counter probe, no task KPI'] if probe else []))
    return path


def ledger(root):
    with archive_lock(root,'ledger'):
        return _ledger(root)


def _ledger(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    fields=['experiment_id','timestamp','backend','model','change','success_rate_pct','correct_tasks','total_tasks',
            'median_e2e_ms','p95_e2e_ms','gross_sys_j','gross_sys_j_per_correct_task','invalid_rate','clarify_accuracy',
            'git_commit','dirty','status','qualification','latency_boundary','energy_scope','notes']
    rows=[]
    for path in archives(root):
        try:
            m=read_json(path/'manifest.json')
            if not isinstance(m,dict): raise ValueError('Manifest must be an object')
        except (ValueError,OSError):
            rows.append(dict(experiment_id=path.name.split('_')[0],status='incomplete',notes='Manifest absent or malformed'));continue
        k=m.get('primary_kpis') or {};backend=m.get('inference_backend') or {}
        if not isinstance(k,dict): k={}
        if not isinstance(backend,dict): backend={}
        notes=m.get('notes') or []
        if not isinstance(notes,list): notes=[str(notes)]
        errors=verify(path)
        if errors: k={}
        rows.append({**{f:k.get(f) for f in fields},'experiment_id':m.get('experiment_id',path.name.split('_')[0]),
                     'timestamp':m.get('timestamp') or m.get('archive_created_utc'),'backend':backend.get('backend_id'),
                     'model':m.get('model'),'change':m.get('change'),'git_commit':m.get('git_commit'),'dirty':m.get('dirty'),
                     'status':'incomplete' if errors and not (path/'artifact-hashes.sha256').exists() else 'integrity_failure' if errors else m.get('status','unknown'),
                     'qualification':'unqualified_integrity_failure' if errors else m.get('qualification_status'),'notes':'; '.join(map(str,errors+notes))})
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    atomic(root/'EXPERIMENT_LEDGER.csv',stream.getvalue())
    md=['# Experiment ledger','','SUCCESS / LATENCY / ENERGY. UNKNOWN is not zero. No overall winner.',
        'Task latency uses the recorded boundary; inference-only results do not supply E2E.','',
        '| EXP | SUCCESS | MEDIAN TASK ms | ENERGY J/correct | backend | change | correct/attempted | invalid | clarify % | qualification | status | scope |',
        '|---|---:|---:|---:|---|---|---|---|---:|---:|---|---|']
    def cell(v):return 'UNAVAILABLE' if v is None else str(round(v,3) if type(v) is float else v).replace('|','\\|').replace('\n',' ')
    for r in rows:
        vals=[r.get('experiment_id'),r.get('success_rate_pct'),r.get('median_e2e_ms'),r.get('gross_sys_j_per_correct_task'),r.get('backend'),r.get('change'),f"{r.get('correct_tasks')}/{r.get('total_tasks')}",r.get('invalid_rate'),r.get('clarify_accuracy'),r.get('qualification'),r.get('status'),r.get('energy_scope')]
        md.append('| '+' | '.join(cell(v) for v in vals)+' |')
    atomic(root/'EXPERIMENT_LEDGER.md','\n'.join(md)+'\n')
    return rows


def stop_child(child):
    """Bounded cleanup of the isolated child group, including on supervisor errors."""
    notes=[]
    try:
        if os.name=='nt':
            completed=subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],
                                     capture_output=True,check=False,timeout=5)
            if completed.returncode: notes.append('Process-tree cleanup returned '+str(completed.returncode))
        else:
            os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    except (OSError,subprocess.TimeoutExpired) as exc:
        notes.append('Process-tree cleanup error: '+str(exc))
    if child.poll() is None:
        try: child.kill()
        except OSError as exc: notes.append('Child cleanup error: '+str(exc))
    try: child.wait(timeout=5)
    except subprocess.TimeoutExpired: notes.append('Child cleanup deadline exceeded; process may remain alive')
    return notes


def capture_block(meter,before,power_before,resolution):
    """Retain even failed counter observations; qualification remains diagnostic."""
    from turbo.telemetry import energy_delta,power_snapshot
    try: after=meter.sample()
    except Exception as exc: after={'channels_pwh':{},'monotonic_s':time.perf_counter(),'error':str(exc)}
    before=before or {'channels_pwh':{},'monotonic_s':None,'error':'Initial counter sample unavailable'}
    try: power_after=power_snapshot()
    except Exception as exc: power_after={'error':str(exc)}
    try: energy=energy_delta(before,after)
    except Exception as exc: energy={'channels':{},'error':str(exc)}
    return dict(measurement_scope='full_process_energy',raw_before=before,raw_after=after,
                energy=energy,power_before=power_before,power_after=power_after,
                declared_counter_resolution_s=resolution,hardware_resolution_s=None,
                energy_qualification='diagnostic_uncommissioned',energy_comparable=False)


def run(name, config_path, *, root=DEFAULT_ARCHIVES, repo=ROOT, dataset='dev', change, hypothesis,
        control=None, diagnostic_dirty=False, timeout=600, command_override=None, capture_energy=False,
        counter_resolution=None):
    """Bounded child supervisor. Exit2 from evaluator is a recorded quality outcome."""
    root=Path(root).resolve();repo=Path(repo).resolve()
    if dataset not in ('dev','all'):raise ValueError('Only dev or explicitly requested all milestones')
    if not change.strip() or not hypothesis.strip():raise ValueError('change and hypothesis required')
    if not finite(timeout) or timeout<=0:raise ValueError('timeout must be positive')
    config_path=Path(config_path).resolve();config_raw=config_path.read_bytes();config=parse_json(config_raw)
    if not isinstance(config,dict):raise ValueError('Config must be an object')
    state=git_state(repo)
    if state['dirty'] and not diagnostic_dirty:raise ValueError('Dirty worktree: commit before measurement or explicitly use --diagnostic-dirty')
    if control:
        matches=[p for p in archives(root) if p.name.split('_')[0]==control]
        if len(matches)!=1 or verify(matches[0]):raise ValueError('Control archive missing/incomplete/tampered')
        control_meta=read_json(matches[0]/'manifest.json')
        control_result=read_json(matches[0]/'result.json')
        if (control_meta.get('status') not in {'completed_qualified','completed_diagnostic','historical_diagnostic'}
                or not isinstance(control_result,dict) or control_result.get('schema_version')!=2
                or control_result.get('status')!='measured' or not rows_of(control_result)):
            raise ValueError('Control must contain a completed measured task report')
    if os.environ.get('GENIEX_QAIRT_LIB'):raise ValueError('Untracked GENIEX_QAIRT_LIB override refused')
    from eval.validate_dataset import validate
    frozen=validate()
    def artifact_path(key):
        value=config.get(key)
        if value is None: return None
        if not isinstance(value,str) or not value:
            raise ValueError(key+' must be a nonempty path string')
        path=Path(value)
        # The unchanged runner resolves relative configuration paths against its
        # cwd. Bind the supervisor to that same directory, not its caller's cwd.
        return (path if path.is_absolute() else repo/path).resolve()
    model=artifact_path('model_path');sdk=artifact_path('sdk_dir')
    pre={key:artifact_identity(value) for key,value in [('model',model),('sdk',sdk)] if value}
    runner_before=captured_runner_identity(repo,model,pre)
    if command_override is None and (not model or not sdk):raise ValueError('Configured local model and SDK required')
    path=reserve(root,name);out=path/'runner-output'
    command=command_override or [sys.executable,'-X','utf8',str(Path(repo)/'eval/run_secretary_eval.py'),
               '--dataset',dataset,'--candidate-name',path.name.split('_')[0],
               '--config',str(path/'config.json'),'--output-dir',str(out)]
    metadata=initialize(path,{**state,'timestamp':now(),'change':change,'hypothesis':hypothesis,
                 'control_experiment':control,'dataset':dataset,'benchmark':frozen,'command':command,
                 'execution_cwd':str(repo),'resolved_artifact_paths':{'model_path':str(model) if model else None,'sdk_dir':str(sdk) if sdk else None},
                 'qualification_status':'diagnostic_dirty' if state['dirty'] else 'pending_validation',
                 'environment':capture_environment(),'artifact_identity_before':pre,
                 'runner_identity_before':runner_before,'case_set_complete':False,
                 'config_sha256':digest(config)},config_raw)
    meter=None;before=None;telemetry=None;status='failed';result=None;notes=[];exit_code=None;child=None;power_before=None
    try:
        if capture_energy:
            from turbo.telemetry import EnergyMeter,power_snapshot
            meter=EnergyMeter();power_before=power_snapshot();before=meter.sample()
        with (path/'stdout.log').open('xb') as stdout,(path/'stderr.log').open('xb') as stderr:
            child=subprocess.Popen(command,cwd=repo,stdout=stdout,stderr=stderr,
                                   **({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}))
            metadata['child_pid']=child.pid;write_json(path/'manifest.json',metadata)
            try:exit_code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                notes.extend(stop_child(child));status='timeout';notes.append('Child deadline exceeded; retained partial evidence')
        if meter: telemetry=capture_block(meter,before,power_before,counter_resolution)
        candidates=list(out.glob('candidate_*.json')) if out.exists() else []
        if len(candidates)==1:
            (path/'result.json').write_bytes(candidates[0].read_bytes());result=read_json(path/'result.json');rows_of(result)
        if status!='timeout':
            status='completed_diagnostic' if result and exit_code in (0,2) else 'failed'
        after_state=git_state(repo)
        post={key:artifact_identity(value) for key,value in [('model',model),('sdk',sdk)] if value}
        runner_after=captured_runner_identity(repo,model,post)
        metadata.update(runner_identity_after=runner_after,runner_sources_changed=runner_before!=runner_after,artifact_identity_after=post,artifact_changed_during_run=pre!=post,
                        source_changed_during_run=after_state!=state,child_exit_code=exit_code)
        if result:
            observed=report_metadata(result)
            metadata.update({k:v for k,v in observed.items() if k not in ('git_commit','branch','dirty','environment','config_sha256')})
            reasons=[]
            if command_override is not None: reasons.append('Custom command is diagnostic only')
            from eval.scoring import load_dataset
            files=[Path(repo)/'eval/datasets/secretary_dev.json']
            if dataset=='all': files.append(Path(repo)/'eval/datasets/secretary_heldout.json')
            expected_cases=load_dataset(files)
            expected_map={c['id']:digest(c) for c in expected_cases}
            actual_map={r.get('id'):r.get('case_sha256') for r in result['results']}
            metadata['case_set_complete']=actual_map==expected_map and len(actual_map)==len(result['results'])
            if not metadata['case_set_complete']: reasons.append('Case IDs/hashes differ from selected frozen dataset')
            if result.get('schema_version')!=2 or result.get('status')!='measured': reasons.append('Runner result is not a measured v2 report')
            for key in ('benchmark_version','fixture_sha256','action_schema_sha256','system_prompt_sha256'):
                if result.get(key)!=frozen.get(key): reasons.append('Frozen provenance mismatch: '+key)
            if result.get('dataset_sha256')!=digest(expected_cases): reasons.append('Dataset hash mismatch')
            if not all(finite(row.get('task_latency_ms')) for row in result['results']):
                reasons.append('Incomplete/nonfinite/negative task_latency_ms; task timing cannot qualify')
            if any('warm_task_latency_ms' in row for row in result['results']) and not all(
                    finite(row.get('warm_task_latency_ms')) for row in result['results']):
                reasons.append('Incomplete/nonfinite/negative warm_task_latency_ms; warm timing cannot qualify')
            reasons+=runner_identity_errors(result,runner_before)
            if runner_before!=runner_after: reasons.append('Runner source bytes changed during run')
            try:
                from eval.report_validation import backend_identity_errors
                reasons+=backend_identity_errors(result, config.get('backend'))
            except ImportError: reasons.append('Identity validator unavailable')
            for k in ('git_commit','dirty','config_sha256'):
                if result.get(k)!=metadata[k]:reasons.append('Runner/supervisor mismatch: '+k)
            expected_count=35 if dataset=='dev' else 50
            if len(result['results'])!=expected_count:reasons.append('Incomplete case count')
            if pre!=post or after_state!=state:reasons.append('Source or artifact changed during run')
            if status=='completed_diagnostic' and not state['dirty'] and not reasons:
                metadata['qualification_status']='clean_reproducible_measurement_not_product_approval'
                status='completed_qualified'
            else:
                metadata['qualification_status']='diagnostic_dirty' if state['dirty'] else 'unqualified'
            notes+=reasons
    except Exception as exc:
        notes.append(type(exc).__name__+': '+str(exc));status='failed'
    finally:
        if child is not None and child.poll() is None:
            notes.extend(stop_child(child))
        if meter:
            if telemetry is None: telemetry=capture_block(meter,before,power_before,counter_resolution)
            try: meter.close()
            except Exception as exc: notes.append('Energy cleanup failed: '+str(exc))
        metadata['child_exit_code']=child.returncode if child is not None else None
        if status in ('failed','timeout'): metadata['qualification_status']='diagnostic_dirty' if state['dirty'] else 'unqualified'
    finish(path,metadata,result,telemetry,status,notes)
    return path
