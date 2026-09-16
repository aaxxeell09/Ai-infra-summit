"""Target cost commissioning. Diagnostic timing only; never energy qualification.

Importing this module never loads a model. Real execution requires an explicit
runner and CLI --execute. Each attempt is retained; the summary is rebuildable.
"""
from __future__ import annotations

from contextlib import nullcontext
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from turbo.experiments import (ROOT, DEFAULT_ARCHIVES, archive_lock, artifact_identity,
                               digest, now, stop_child, write_json)
from turbo.json_io import read_json

SCHEMA = 'local-turbo.commissioning.v1'
DEFAULT_PATH = ROOT/'local/autotune/commissioning.json'
METRICS = {
    'cold_load_s':('s','SDK initialization plus model creation in a fresh process; OS caches not flushed'),
    'warm_one_case_s':('s','one development case, generation plus fixture execution and scoring after warmup'),
    'config_change_reload_s':('s','close old model and load explicitly supplied changed model configuration'),
    'same_config_reuse_s':('s','one development case on the same model object/process, without reload'),
    'same_config_process_reused':('boolean','same model object and process reused for a second request'),
    'five_repeat_outputs_equal':('boolean','exact UTF-8 outputs equal across five reset=True requests; not proof of universal determinism'),
    's1_wall_s':('s','existing backend smoke child process wall time'),
    's2_8_wall_s':('s','existing diagnostic canary child process wall time, fixed eight development cases'),
    's2_8_hardware_s':('s','existing canary reported hardware_seconds; excludes parent process overhead'),
    's3_18_wall_s':('s','existing diagnostic canary child process wall time, fixed eighteen development cases'),
    's3_18_hardware_s':('s','existing canary reported hardware_seconds; excludes parent process overhead'),
    'dev35_wall_s':('s','tracker invocation wall time, including validation, hashing and archival'),
    'anthropic_api_s':('s','successful provider SDK request wall time from sanitized API probe; no hardware lock'),
    'openai_api_s':('s','successful provider SDK request wall time from sanitized API probe; no hardware lock'),
}
STEPS = {'resident':tuple(list(METRICS)[:6]),'s1':('s1_wall_s',),'s2':('s2_8_wall_s','s2_8_hardware_s'),'s3':('s3_18_wall_s','s3_18_hardware_s'),
         'dev35':('dev35_wall_s',),'anthropic_api':('anthropic_api_s',),'openai_api':('openai_api_s',)}


def identity(config, *, inspect_artifacts=False):
    result={'backend':config.get('backend'),'config_sha256':digest(config),
            'model_sha256':None,'sdk_sha256':None}
    if inspect_artifacts:
        for key,field in [('model_path','model_sha256'),('sdk_dir','sdk_sha256')]:
            path=Path(config[key]);path=path if path.is_absolute() else ROOT/path
            result[field]=artifact_identity(path)['sha256']
    result['model_config_sha256']=digest(result)
    return result


def metric(name, scope, *, value=None, reason=None, source='unavailable', evidence=None):
    unit,boundary=METRICS[name]
    if source=='measured':
        valid=type(value) is bool if unit=='boolean' else type(value) in (int,float) and math.isfinite(value) and value>=0
        if not valid: raise ValueError('Invalid measured metric: '+name)
    return dict(value=value,unit=unit,source=source,timestamp=now(),boundary=boundary,
                **scope,reason=reason,evidence=evidence)


def commission(config_path, *, output=DEFAULT_PATH, runner=None, steps=tuple(STEPS),
               resume=False, acknowledge_interrupted=False, inspect_artifacts=False,
               archives=DEFAULT_ARCHIVES):
    config_path=Path(config_path).resolve();config=read_json(config_path,require_object=True)
    if config.get('backend')!='qairt_npu': raise ValueError('Commissioning currently requires explicit qairt_npu')
    if set(steps)-set(STEPS): raise ValueError('Unknown commissioning step')
    output=Path(output).resolve();home=output.parent
    with archive_lock(home,'commissioning',timeout=.1):
        artifact_error=None
        try:scope=identity(config,inspect_artifacts=inspect_artifacts)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            scope=identity(config)
            artifact_error='Artifact preflight unavailable: '+str(exc)
        if output.exists():
            if not resume: raise FileExistsError('Commissioning exists; use --resume')
            state=read_json(output,require_object=True)
            if state.get('schema_version')!=SCHEMA:raise ValueError('Unknown commissioning schema')
            if state.get('identity')!=scope:
                if not state.get('attempts') and state.get('identity',{}).get('config_sha256')==scope['config_sha256'] and state.get('identity',{}).get('model_sha256') is None:
                    state['identity']=scope
                    state['metrics']={name:metric(name,scope,reason='Not attempted') for name in METRICS}
                else:raise ValueError('Commissioning identity differs; select a new output path')
        else:
            state=dict(schema_version=SCHEMA,identity=scope,created_utc=now(),
                       metrics={name:metric(name,scope,reason='Not attempted') for name in METRICS},
                       attempts=[],energy_comparable=False,quality_qualified=False)
        write_json(output,state)
        for step in steps:
            previous=[a for a in state['attempts'] if a['step']==step]
            if previous and previous[-1]['status']=='completed': continue
            unfinished=[a for a in previous if a['status']=='running']
            if unfinished and not acknowledge_interrupted:
                raise RuntimeError('Interrupted attempt may have a surviving child; inspect jobs then explicitly acknowledge before resume')
            if runner is None:
                for name in STEPS[step]: state['metrics'][name]=metric(name,scope,reason='Execution not authorized; plan only')
                continue
            attempt=home/'commissioning-attempts'/('ATT-'+uuid.uuid4().hex)
            attempt.mkdir(parents=True,exist_ok=False)
            entry=dict(step=step,path=str(attempt),status='running',timestamp=now(),
                       acknowledged_interrupted=[a['path'] for a in unfinished])
            state['attempts'].append(entry)
            write_json(attempt/'request.json',dict(step=step,identity=scope,config=config,qualification='diagnostic_only'))
            write_json(output,state)
            try:
                if artifact_error and not step.endswith('_api'):raise ValueError(artifact_error)
                # dev35's tracker acquires this same lock internally. APIs never do.
                lock=archive_lock(archives,'hardware-execution',timeout=.1) if step in ('resident','s1','s2','s3') and not getattr(runner,'owns_hardware_lock',False) else nullcontext()
                with lock: response=runner(step,attempt,config_path)
                values=response.get('metrics',{})
                if set(values)-set(STEPS[step]): raise ValueError('Runner returned unrelated metrics')
                if inspect_artifacts and not step.endswith('_api') and identity(config,inspect_artifacts=True)!=scope:
                    raise ValueError('Model/SDK artifacts changed during commissioning')
                for name in STEPS[step]:
                    if name in values:
                        state['metrics'][name]=metric(name,scope,value=values[name],source='measured',evidence=str(attempt/'result.json'))
                    else:
                        state['metrics'][name]=metric(name,scope,reason=response.get('unavailable',{}).get(name,'Runner did not supply metric'),evidence=str(attempt/'result.json'))
                if response.get('changed_config_sha256') and 'config_change_reload_s' in values:
                    state['metrics']['config_change_reload_s']['target_config_sha256']=response['changed_config_sha256']
                entry['status']='completed' if values else 'unavailable'
                result=dict(status=entry['status'],response=response,identity=scope,timestamp=now())
            except Exception as exc:
                entry.update(status='failed',error=type(exc).__name__+': '+str(exc))
                result=dict(entry,identity=scope)
                for name in STEPS[step]:state['metrics'][name]=metric(name,scope,reason=entry['error'],evidence=str(attempt/'result.json'))
            with (attempt/'result.json').open('x',encoding='utf-8') as stream:
                import json
                json.dump(result,stream,indent=2,allow_nan=False)
            write_json(output,state)
        write_json(output,state)
        return state


def child_command(command,attempt,*,timeout):
    """Bounded isolated child with retained logs and PID evidence."""
    write_json(attempt/'command.json',command)
    child=None
    try:
        with (attempt/'stdout.log').open('xb') as out,(attempt/'stderr.log').open('xb') as err:
            child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,
                  **({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}))
            write_json(attempt/'child.json',{'pid':child.pid,'timestamp':now()})
            code=child.wait(timeout=timeout)
            if code: raise RuntimeError('Child exit '+str(code)+'; see retained logs')
    finally:
        if child is not None and child.poll() is None: stop_child(child)


class TargetRunner:
    """Usable target implementation; construction alone never invokes inference."""
    owns_hardware_lock=True

    def __init__(self,*,timeout=900,changed_config=None,api_probe=None,archives=DEFAULT_ARCHIVES):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:raise ValueError('Positive finite timeout required')
        self.timeout=timeout;self.changed_config=changed_config;self.api_probe=api_probe;self.archives=archives

    def __call__(self,step,attempt,config_path):
        if step.endswith('_api'):
            provider=step.removesuffix('_api')
            if self.api_probe is None:
                script=ROOT/'scripts/api_probe.py'
                if not script.is_file():
                    return {'metrics':{},'unavailable':{STEPS[step][0]:'Optional API probe script unavailable'}}
                try:
                    child_command([sys.executable,'-X','utf8',str(script),'--provider',provider,
                                   '--timeout',str(min(120,self.timeout))],attempt,timeout=min(120,self.timeout)+10)
                except RuntimeError:
                    # The sanitized CLI also emits structured JSON for API failures.
                    pass
                data=read_json(attempt/'stdout.log',require_object=True)
                evidence=data['results'][0]
            else:
                evidence=self.api_probe(provider,attempt,timeout=min(120,self.timeout))
            safe={key:evidence.get(key) for key in ('provider','model','timestamp','status','error_category','latency_ms','latency_scope','sdk_version')}
            latency=safe.get('latency_ms')
            if safe.get('provider')!=provider or safe.get('status')!='ok' or type(latency) not in (int,float) or not math.isfinite(latency) or latency<0:
                return {'metrics':{},'api_evidence':safe,'unavailable':{STEPS[step][0]:'API success latency unavailable; see diagnostic evidence'}}
            return {'metrics':{STEPS[step][0]:latency/1000},'api_evidence':safe}
        if step=='dev35':
            from turbo.experiments import run
            start=time.monotonic()
            archive=run('commission-dev35',config_path,root=self.archives,dataset='dev',
                        change='Commission development-run wall cost',hypothesis='Measure scheduler cost; no optimization claim',timeout=self.timeout)
            data=read_json(archive/'manifest.json',require_object=True)
            if data['status'] not in ('completed_qualified','completed_diagnostic') or data.get('case_set_complete') is not True:
                raise RuntimeError('Tracked development run failed or incomplete: '+str(archive))
            return {'metrics':{'dev35_wall_s':time.monotonic()-start},'archive':str(archive)}
        out=attempt/'probe.json'
        command=[sys.executable,'-X','utf8',str(ROOT/'scripts/autotune_commission.py'),
                 '--diagnostic-worker',step,'--execute','--config',str(config_path),
                 '--worker-output',str(out),'--archives-root',str(Path(self.archives).resolve())]
        if step=='resident' and self.changed_config:
            changed_path=attempt/'changed-config.json'
            changed_path.write_bytes(Path(self.changed_config).read_bytes())
            command+=['--changed-config',str(changed_path)]
        start=time.monotonic();child_command(command,attempt,timeout=self.timeout);elapsed=time.monotonic()-start
        if step=='resident':return read_json(out,require_object=True)
        values={STEPS[step][0]:elapsed}
        if step in ('s2','s3') and out.exists():
            values[STEPS[step][1]]=read_json(out,require_object=True).get('hardware_seconds')
        return {'metrics':values,'probe_path':str(out) if out.exists() else None}


def diagnostic_worker(kind,config_path,output,*,changed_config=None,archives=DEFAULT_ARCHIVES):
    """Worker holds the common mutex for its entire native lifetime.

    Existing probes run in this process, not grandchildren: if the controller
    dies, the still-running worker retains its OS lock until native work ends.
    """
    import runpy
    with archive_lock(archives,'hardware-execution',timeout=.1):
        if kind=='resident':return resident_probe(config_path,output,changed_config)
        if kind=='s1':
            original=sys.argv
            try:
                sys.argv=[str(ROOT/'scripts/backend_smoke.py'),'--config',str(config_path)]
                runpy.run_path(sys.argv[0],run_name='__main__')
            finally:sys.argv=original
        elif kind in ('s2','s3'):
            namespace=runpy.run_path(str(ROOT/'scripts/diagnostic_canary.py'),run_name='commissioning_canary')
            result=namespace['run_canary'](read_json(config_path,require_object=True),size=8 if kind=='s2' else 18,seed_label='commissioning-v1')
            with Path(output).open('x',encoding='utf-8') as stream:
                import json
                json.dump(result,stream,indent=2,allow_nan=False)
        else:raise ValueError('Unknown diagnostic worker')


def resident_probe(config_path,output,changed_config=None):
    """Explicit target child only. Imports native runtime lazily; dev case only."""
    from turbo.native import NativeModel,NativeRuntime
    from eval.run_secretary_eval import execute
    from eval.secretary_adapter import SecretaryAdapter,TOOLS
    from eval.scoring import load_dataset
    config=read_json(config_path,require_object=True)
    cases=load_dataset([ROOT/'eval/datasets/secretary_dev.json'])[:1]
    codec=SecretaryAdapter.from_files(read_json(ROOT/'eval/fixtures/files.json'))
    keys=('device','threads','context','threads_batch','ubatch','n_batch','spec_type','draft_tokens','plugin','backend','stop_after_tool_call')
    def create(runtime,c):return NativeModel(runtime,c['model_path'],**{k:c[k] for k in keys if k in c})
    def case(model,c):
        row=execute(cases,codec,lambda messages:model.chat(messages,tools=TOOLS,max_tokens=c.get('max_tokens',128),temperature=0,reset=True),ROOT/'eval/fixtures/secretary_workspace')[0]
        rows.append(row)
        if row.get('execution_error'):raise RuntimeError('Resident generation failed; see partial diagnostic rows')
        return row
    model=None;runtime=None;values={};rows=[]
    try:
        start=time.monotonic();runtime=NativeRuntime(config['sdk_dir']);model=create(runtime,config)
        values['cold_load_s']=time.monotonic()-start
        case(model,config)
        model_id=id(model);pid=os.getpid()
        start=time.monotonic();case(model,config);values['warm_one_case_s']=time.monotonic()-start
        start=time.monotonic();case(model,config);values['same_config_reuse_s']=time.monotonic()-start
        values['same_config_process_reused']=id(model)==model_id and os.getpid()==pid
        repeat=[case(model,config) for _ in range(5)]
        texts=[r.get('output_text') for r in repeat]
        if all(isinstance(t,str) and not r.get('execution_error') for t,r in zip(texts,repeat)):
            values['five_repeat_outputs_equal']=len(set(texts))==1
        if changed_config:
            changed=read_json(changed_config,require_object=True)
            if digest(changed)==digest(config):raise ValueError('Changed config must differ')
            if any(changed.get(k)!=config.get(k) for k in ('sdk_dir','model_path','backend')):
                raise ValueError('Model/SDK/backend change requires separate commissioning')
            start=time.monotonic();model.close();model=create(runtime,changed);values['config_change_reload_s']=time.monotonic()-start
        result={'metrics':values,'changed_config_sha256':digest(changed) if changed_config else None,'rows':rows,'pid':pid,'unavailable':{'config_change_reload_s':'No changed config supplied'},'quality_qualified':False,'energy_comparable':False}
        with Path(output).open('x',encoding='utf-8') as stream:
            import json
            json.dump(result,stream,indent=2,allow_nan=False)
    finally:
        try:
            write_json(Path(output).with_suffix('.partial.json'),{'metrics':values,'rows':rows,'diagnostic_only':True,
                       'note':'Partial diagnostic evidence retained even if worker fails; not automatically admitted as measured costs'})
        finally:
            try:
                if model is not None:model.close()
            finally:
                if runtime is not None:runtime.close()


def reference_cost(config,stage,path=DEFAULT_PATH):
    """Recorded exact-control costs; never reinterpret absent values as zero."""
    try:
        data=read_json(path,require_object=True)
        if data.get('schema_version')!=SCHEMA or data['identity']['config_sha256']!=digest(config):return None
        if not data['identity'].get('model_sha256') or not data['identity'].get('sdk_sha256'):return None
        key={'S1':'s1_wall_s','S2':'s2_8_wall_s','S3':'s3_18_wall_s','S4':'dev35_wall_s','S5':'dev35_wall_s'}.get(stage)
        value=data['metrics'].get(key,{})
        if value.get('source')!='measured' or value.get('model_config_sha256')!=data['identity']['model_config_sha256']:return None
        seconds=value.get('value')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:return None
        return seconds
    except (OSError,ValueError,KeyError,TypeError):return None


def load_costs(config,path=DEFAULT_PATH):
    """Validate model/SDK binding once at session startup, before using estimates."""
    try:
        data=read_json(path,require_object=True)
        if data.get('schema_version')!=SCHEMA or data.get('identity')!=identity(config,inspect_artifacts=True):return {}
        return {stage:value for stage in ('S1','S2','S3','S4','S5')
                if (value:=reference_cost(config,stage,path)) is not None}
    except (OSError,ValueError,KeyError,TypeError):return {}
