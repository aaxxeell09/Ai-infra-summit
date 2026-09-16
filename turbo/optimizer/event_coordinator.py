"""Opt-in event coordination; bookkeeping never confers measurement qualification."""
from __future__ import annotations
import copy
import importlib
import math
from pathlib import Path
import threading
import time
import uuid
from turbo.experiments import archive_lock, digest, write_json
from turbo.json_io import read_json

SCHEMA = 'local-turbo.event-coordinator.v1'
STAGES = ('S1','S2','S3','S4','S5')


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


class Coordinator:
    def __init__(self,path,*,clock=time.time,heartbeat_seconds=600,registry_root=None,require_registry=False):
        self.path=Path(path).resolve();self.clock=clock
        if not number(heartbeat_seconds) or heartbeat_seconds<=0:raise ValueError('Positive heartbeat interval required')
        self.interval=heartbeat_seconds;self.registry_root=Path(registry_root) if registry_root else self.path.parent/'registry'
        self.require_registry=require_registry
        self._thread=None;self._stop=threading.Event();self.observer_error=None
        self._update(lambda state:None)

    def _update(self,change):
        with archive_lock(self.path.parent,'event-coordinator-'+digest(self.path.name)[:16],timeout=5):
            state=read_json(self.path,require_object=True) if self.path.exists() else {
                'schema_version':SCHEMA,'active':None,'events':[],'nodes':{},'controls':{},
                'future':{},'frontier':[],'planner_inbox':[],'last_heartbeat':self.clock(),
                'qualified':False,'registry_delivered':[]}
            if state.get('schema_version')!=SCHEMA:raise ValueError('Unsupported coordinator state')
            result=change(state);write_json(self.path,state)
            return copy.deepcopy(result)

    def snapshot(self):return self._update(lambda state:state)

    def _event(self,state,kind,**fields):
        event=dict(event_id='EV-'+uuid.uuid4().hex,timestamp=self.clock(),kind=kind,qualified=False,**fields)
        state['events'].append(event);return event

    def recover(self,journal,*,code_sha):
        active=self.snapshot()['active']
        if not active:return
        entry=journal.get(active['job_id'],{})
        if entry.get('status')!='completed':
            raise RuntimeError('Uncertain attempt remains blocked; reconcile native job and durable hardware journal first')
        self.complete(active['candidate'],active['stage'],active['job_id'],entry['observation'],
                      control=bool(active['candidate'].get('is_control')),code_sha=active.get('code_sha') or code_sha)

    def heartbeat(self,*,force=False):
        def update(state):
            now=self.clock()
            if not force and now-state['last_heartbeat']<self.interval:return None
            state['last_heartbeat']=now
            return self._event(state,'heartbeat',active=copy.deepcopy(state['active']),
                frontier=copy.deepcopy(state['frontier']),future=copy.deepcopy(state['future']),
                nodes=copy.deepcopy(state['nodes']),planner_inbox=copy.deepcopy(state['planner_inbox']),
                instruction='Review only; active measurement is immutable; changes apply to future jobs')
        return self._update(update)

    def start(self,candidate,stage,job_id,*,code_sha=None):
        if self.require_registry and (not isinstance(code_sha,str) or len(code_sha)!=40 or any(c not in '0123456789abcdef' for c in code_sha)):
            raise ValueError('Registry execution requires a complete code SHA before launch')
        if self.observer_error:raise RuntimeError('Heartbeat observer failed: '+self.observer_error)
        if stage not in STAGES:raise ValueError('Unsupported stage')
        def update(state):
            if state['active']:raise RuntimeError('Uncertain hardware intent requires reconciliation; no automatic rerun')
            state['active']={'job_id':job_id,'candidate':copy.deepcopy(candidate),'stage':stage,'started_at':self.clock(),'code_sha':code_sha}
            fields={}
            if code_sha:
                node={'node_id':candidate['candidate_id'],'parent_ids':list(candidate.get('parent_ids',[])),
                      'config_hash':candidate.get('config_hash') or digest(candidate['config']),'code_sha':code_sha,
                      'protocol_version':'secretary-single-action-v2','hypothesis':candidate.get('hypothesis') or candidate.get('mechanism') or candidate.get('family','unspecified'),
                      'stage':stage,'status':'RUNNING','decision':'observe','reason':'Durable launch intent; no completion or qualification claim','metrics':{},'qualified':False}
                state['nodes'][candidate['candidate_id']]=node;fields['node']=copy.deepcopy(node)
            self._event(state,'hardware_started',job_id=job_id,candidate_id=candidate['candidate_id'],stage=stage,**fields)
        self.flush_registry()
        self._update(update)
        self.flush_registry()
        self.start_observer()

    def start_observer(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear()
        def observe():
            while not self._stop.wait(min(self.interval,1)):
                try:self.heartbeat()
                except Exception as exc:
                    self.observer_error=type(exc).__name__
                    try:self._update(lambda state:self._event(state,'observer_error',error_type=self.observer_error))
                    except Exception:pass  # Unwritable checkpoint; surface synchronously before next launch.
                    return
        self._thread=threading.Thread(target=observe,name='turbolab-heartbeat',daemon=True);self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=2)

    def complete(self,candidate,stage,job_id,observation,*,control=False,code_sha='unknown',protocol_version='secretary-single-action-v2'):
        def update(state):
            active=state['active']
            if not active or active['job_id']!=job_id:raise ValueError('Completion does not match durable active intent')
            if digest(active['candidate'])!=digest(candidate):raise ValueError('Running candidate mutated')
            if not isinstance(observation,dict):raise ValueError('Observation must be object')
            node_id=candidate['candidate_id'];cfg=candidate.get('config_hash') or digest(candidate['config'])
            failure=observation.get('outcome') in ('failed','crashed','timed_out','refused','skipped') or bool(observation.get('runtime_error'))
            decision='reject' if failure else 'review'
            reason='Hardware failure/invalid execution' if failure else 'Completed observation; existing stage gate retains decision authority'
            if control and not failure:
                key=stage+':'+cfg
                state['controls'].setdefault(key,[]).append(copy.deepcopy(observation))
                decision='control_observed';reason='Control repeat retained without replacing earlier observations'
            node={'node_id':node_id,'parent_ids':list(candidate.get('parent_ids',[])),
                'config_hash':cfg,'code_sha':code_sha,'protocol_version':protocol_version,
                'hypothesis':candidate.get('hypothesis') or candidate.get('mechanism') or candidate.get('family','unspecified'),
                'stage':stage,'status':'REJECTED' if failure else 'OBSERVED','decision':decision,'reason':reason,
                'evidence_paths':[observation['archive']] if observation.get('archive') else [],
                'metrics':copy.deepcopy(observation),'qualified':False}
            state['nodes'][node_id]=node;state['active']=None
            return self._event(state,'hardware_completed',node=copy.deepcopy(node),job_id=job_id)
        event=self._update(update);self.flush_registry();return event

    def uncertain(self,candidate,stage,job_id,error,*,code_sha=None):
        def update(state):
            # Retain active intent: a Python exception cannot prove native children stopped.
            node={'node_id':candidate['candidate_id'],'parent_ids':list(candidate.get('parent_ids',[])),
                  'config_hash':candidate.get('config_hash') or digest(candidate['config']),'code_sha':code_sha or 'unknown',
                  'protocol_version':'secretary-single-action-v2','hypothesis':candidate.get('hypothesis') or candidate.get('mechanism') or candidate.get('family','unspecified'),
                  'stage':stage,'status':'REJECTED','decision':'block_and_reconcile',
                  'reason':'Exception leaves native completion uncertain; no automatic rerun','metrics':{},'qualified':False}
            state['nodes'][candidate['candidate_id']]=node
            return self._event(state,'hardware_failed_uncertain',job_id=job_id,stage=stage,
                candidate_id=candidate['candidate_id'],error_type=type(error).__name__,node=copy.deepcopy(node),
                decision='block_and_reconcile',reason='Do not automatically repeat uncertain native work')
        event=self._update(update);self.flush_registry();return event

    def decide(self,candidate,stage,gate,reason,*,observation=None,control_config_hash=None,max_noise_repeats=2,job_id=None):
        """Existing gates decide; observed control noise can defer with bounded repeats."""
        def update(state):
            node=state['nodes'].get(candidate['candidate_id'])
            if node is None:return None
            reasons=list(reason)
            latest=next((e for e in reversed(state['events']) if e['kind']=='hardware_completed' and e['node']['node_id']==candidate['candidate_id']),None)
            decision_job=job_id or (latest['job_id'] if latest else None)
            prior=next((e for e in reversed(state['events']) if e['kind']=='stage_decision' and e.get('job_id')==decision_job),None)
            if prior:return prior['decision']
            decision='advance' if gate=='survive' else 'reject'
            if stage=='S5' and gate=='survive':decision='review_promotion'
            controls=state['controls'].get(stage+':'+str(control_config_hash),[])
            identity=observation_identity(observation or {})
            controls=[row for row in controls if identity is not None and observation_identity(row)==identity]
            counts=[row.get('correct') for row in controls if number(row.get('correct'))]
            value=(observation or {}).get('correct')
            repeats=sum(e['kind']=='stage_decision' and e.get('config_hash')==node['config_hash'] and e.get('stage')==stage and e.get('decision')=='repeat' for e in state['events'])
            if gate=='survive' and stage in ('S2','S3','S4','S5') and len(counts)>=2 and number(value):
                spread=max(counts)-min(counts)
                delta=abs(value-counts[-1])
                near=spread>0 and delta<=spread
                basis='correct-count range '+str(spread)+'; absolute delta '+str(delta)
                if spread==0 and delta==0:
                    boundary=(observation or {}).get('latency_boundary')
                    samples=[row.get('median_task_latency_ms') for row in controls
                             if boundary and row.get('latency_boundary')==boundary and number(row.get('median_task_latency_ms'))]
                    latency=(observation or {}).get('median_task_latency_ms')
                    if len(samples)>=2 and number(latency):
                        latency_range=max(samples)-min(samples)
                        latency_delta=abs(latency-samples[-1])
                        near=latency_delta<=latency_range
                        basis='equal observed quality; latency range '+str(latency_range)+' ms; absolute delta '+str(latency_delta)+' ms; boundary '+str(boundary)
                if near and not (observation or {}).get('runtime_error') and (observation or {}).get('outcome') not in ('failed','timed_out','crashed'):
                    decision='repeat' if repeats<max_noise_repeats else 'hold'
                    reasons+=['Observed control noise: '+basis+'; bounded repeats '+str(repeats)+'/'+str(max_noise_repeats)]
            requested=state['future'].get(candidate['candidate_id'],{})
            if requested.get('action')=='repeat' and decision!='reject':
                decision='repeat';reasons+=[requested['reason']]
                del state['future'][candidate['candidate_id']]
            node.update(decision=decision,reason='; '.join(reasons),status='REPEAT_NEEDED' if decision=='repeat' else 'READY' if decision=='advance' else 'OBSERVED' if decision in ('hold','review_promotion') else 'REJECTED')
            self._event(state,'stage_decision',node=copy.deepcopy(node),config_hash=node['config_hash'],stage=stage,decision=decision,job_id=decision_job)
            return decision
        result=self._update(update);self.flush_registry();return result

    def record_selection(self,selection):
        if selection.get('decision')!='promote' or selection.get('confirmed') is not True:return
        def update(state):
            node=state['nodes'].get(selection.get('candidate_id'))
            if not node:return
            stages={event['node']['stage'] for event in state['events'] if event['kind']=='hardware_completed' and event['node']['node_id']==node['node_id']}
            if not {'S4','S5'}<=stages:raise ValueError('Individual promotion needs both durable S4 and S5 observations')
            if node['decision']=='individually_promoted':return
            node.update(status='PROMOTED',decision='individually_promoted',reason='Existing selector approved confirmed individual change; bookkeeping, not energy qualification')
            self._event(state,'selector_decision',node=copy.deepcopy(node))
        self._update(update);self.flush_registry()

    def future(self,node_id,action,*,reason,priority=None):
        if action not in ('reject','repeat','reorder'):raise ValueError('Only future reject/repeat/reorder allowed')
        if not reason:raise ValueError('Decision reason required')
        if action=='reorder' and (not number(priority)):raise ValueError('Finite priority required')
        def update(state):
            if state['active'] and state['active']['candidate']['candidate_id']==node_id:
                raise ValueError('Cannot change running job; target another future candidate')
            state['future'][node_id]={'action':action,'reason':reason,'priority':priority}
            self._event(state,'future_changed',node_id=node_id,action=action,reason=reason,priority=priority)
        self._update(update)

    def ready(self,pool,score):
        """A planner frontier of at most four branches; no fabricated second branch."""
        def update(state):
            eligible=[]
            for stage,candidates in pool.items():
                for candidate in candidates:
                    rule=state['future'].get(candidate['candidate_id'],{})
                    if rule.get('action')=='reject':continue
                    parents=candidate.get('parent_ids',[])
                    if len(parents)>1 and any(state['nodes'].get(p,{}).get('decision')!='individually_promoted' for p in parents):continue
                    priority=rule.get('priority') if rule.get('action')=='reorder' else score(candidate,stage)
                    if not number(priority):continue
                    eligible.append((priority,stage,copy.deepcopy(candidate)))
            eligible.sort(key=lambda item:(-item[0],item[2]['candidate_id'],item[1]))
            branches=[];frontier=[]
            for item in eligible:
                branch=item[2].get('branch_id') or item[2].get('family') or item[2]['candidate_id']
                if branch not in branches:
                    if len(branches)>=4:continue
                    branches.append(branch)
                frontier.append(item)
            state['frontier']=[{'candidate_id':c['candidate_id'],'stage':s,'priority':p} for p,s,c in frontier]
            return frontier[0] if frontier else None
        return self._update(update)

    def import_research(self,root):
        """Inbox projections are planner context, never admission or hardware work."""
        module=importlib.import_module('turbo.research_inbox')
        findings=module.list_findings(root)
        self._update(lambda state:state.update(planner_inbox=copy.deepcopy(findings)))
        return findings

    def flush_registry(self):
        try:module=importlib.import_module('turbo.experiment_registry')
        except ImportError:
            if self.require_registry:raise RuntimeError('Event-driven execution requires experiment registry integration; observations remain in durable outbox')
            return
        # Serialized outbox; registry must deduplicate supplied event_id after a crash.
        def update(state):
            for event in state['events']:
                if 'node' not in event or event['event_id'] in state['registry_delivered']:continue
                payload={k:v for k,v in event['node'].items() if k not in ('metrics','qualified')}
                payload['decision_reason']=payload.pop('reason')
                payload['parent_ids']=[registry_id(state['nodes'][parent]) for parent in payload['parent_ids']]
                metrics,boundaries=registry_metrics(event['node'].get('metrics',{}))
                payload.update(metrics=metrics,metric_boundaries=boundaries)
                payload['node_id']=registry_id(payload)
                try:module.append_event(self.registry_root,dict(payload,event_id=event['event_id']))
                except Exception:
                    if self.require_registry:raise
                    break
                state['registry_delivered'].append(event['event_id'])
        self._update(update)


def registry_id(node):
    return node['node_id']+'-'+node['config_hash'][:12]+'-'+node['code_sha'][:8]


def observation_identity(observation):
    rows=observation.get('rows');attempted=observation.get('attempted')
    protocol=observation.get('protocol_version') or observation.get('benchmark_version')
    if type(attempted) is not int or attempted<=0 or not isinstance(rows,list) or len(rows)!=attempted or not protocol:return None
    identities=[]
    for row in rows:
        case_id=row.get('case_id') or row.get('id');case_hash=row.get('case_sha256')
        if not case_id or not case_hash:return None
        identities.append((case_id,case_hash))
    if len(set(x[0] for x in identities))!=attempted:return None
    return digest({'attempted':attempted,'rows':sorted(identities),'protocol':protocol})


def registry_metrics(observation):
    values={};boundaries={}
    attempted=observation.get('attempted');correct=observation.get('correct')
    if number(attempted) and attempted>0 and number(correct) and 0<=correct<=attempted:
        values['correctness']=correct/attempted;boundaries['correctness']='correct / attempted in the supplied stage observation; not independently qualified'
    fields={'invalid_rate':'invalid_rate','median_task_latency_ms':'latency_ms','ttft_ms':'ttft_ms',
            'decode_tokens_per_second':'decode_tokens_per_second','energy_j':'energy_j','memory_bytes':'memory_bytes'}
    source_boundaries=observation.get('metric_boundaries') or {}
    for source,target in fields.items():
        value=observation.get(source)
        boundary=source_boundaries.get(source) or source_boundaries.get(target)
        if source=='invalid_rate':boundary='invalid outputs / attempted in supplied stage observation'
        if source=='median_task_latency_ms':boundary=observation.get('latency_boundary') or boundary
        if number(value) and value>=0 and boundary:
            values[target]=value;boundaries[target]=str(boundary)
    return values,boundaries


def diagnostic_runner(archives_root,*,runner=None):
    """Wrap existing subprocess probes in a child-owned shared hardware lock."""
    import subprocess
    import sys
    root=Path(__file__).resolve().parents[2]
    execute=runner or subprocess.run
    def run(command,**kwargs):
        command=list(command)
        matches=[i for i,item in enumerate(command) if Path(str(item)).name in ('backend_smoke.py','diagnostic_canary.py')]
        if len(matches)!=1:raise ValueError('Unsupported diagnostic command')
        index=matches[0]
        if Path(command[index]).resolve()!=(root/'scripts'/Path(command[index]).name).resolve():
            raise ValueError('Diagnostic script must be repository-owned')
        guarded=[sys.executable,'-X','utf8',str(root/'scripts/autotune_hardware_worker.py'),
                 '--archives-root',str(Path(archives_root).resolve()),'--script',Path(command[index]).name,
                 '--',*command[index+1:]]
        return execute(guarded,**kwargs)
    return run
