"""Opt-in real-model feedback diagnostic on a new disposable demo fixture only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from turbo.json_io import parse_json
from turbo.secretary import TOOLS,load_tasks,grade_task
from turbo.secretary_loop import run_feedback,VERSION


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-candidate',action='store_true')
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--task-id',required=True,help='Public demo fixture only; not golden v2')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--constrain-tools',action='store_true',help='Separate grammar diagnostic; requires a successful restrictive native canary')
    args=p.parse_args(argv)
    if not args.enable_candidate:p.error('Explicit --enable-candidate required; default service remains unchanged')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():p.error('Clean committed source required')
    config=parse_json(args.config.read_bytes(),require_object=True)
    grammar = None
    if args.constrain_tools:
        from turbo.tool_grammar import tool_grammar
        grammar = tool_grammar()
    task=next((t for t in load_tasks() if t['id']==args.task_id),None)
    if task is None:p.error('Unknown demo task')
    args.output.mkdir(parents=True,exist_ok=False)
    from turbo.native import NativeRuntime,NativeModel
    from turbo.runtime_identity import runtime_identity
    options={k:config[k] for k in ('device','threads','context','threads_batch','ubatch','n_batch','plugin','backend','stop_after_tool_call') if k in config}
    start=time.monotonic();record={'version':VERSION,'git_commit':commit,'dirty':False,'task_id':args.task_id,'prompt':task['prompt'],
        'config':{k:v for k,v in config.items() if k not in ('sdk_dir','model_path')},'max_turns':6,'max_tokens_per_turn':128,'max_loop_seconds':90,
        'scope':'Separate opt-in interactive diagnostic; not secretary-eval-v2; no quality qualification',
        'sdk_identity':runtime_identity(Path(config['sdk_dir'])/'bin/geniex-bench.exe',config['sdk_dir']),
        'model_sha256':None,'completed':False,
        'grammar_enabled':args.constrain_tools,
        'grammar_sha256':hashlib.sha256(grammar.encode()).hexdigest() if grammar else None}
    if grammar:(args.output/'tool-grammar.gbnf').write_bytes(grammar.encode('utf-8'))
    path=Path(config['model_path'])
    if path.is_file():
        with path.open('rb') as stream:record['model_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    else:
        from turbo.tuning import _sha256
        record['model_sha256']=_sha256(path)
    def save(): (args.output/'diagnostic.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    save()
    try:
        from turbo.feedback_binding import verify_bound_config
        record['recommendation_binding_verified']=verify_bound_config(config,record['model_sha256'],record['sdk_identity'])
    except ValueError as exc:
        record['error']=str(exc);save();return 1
    runtime=NativeRuntime(config['sdk_dir'])
    try:
        with NativeModel(runtime,config['model_path'],**options) as model:
            if grammar:
                from turbo.tool_grammar import CANARY_GRAMMAR,CANARY_TEXT
                canary=model.chat([{'role':'user','content':'Reply only BETA.'}],max_tokens=32,temperature=0,reset=True,grammar=CANARY_GRAMMAR)
                record['grammar_canary']={'expected':CANARY_TEXT,'response':canary,'passed':canary.get('text')==CANARY_TEXT}
                save()
                if not record['grammar_canary']['passed']:
                    raise ValueError('Restrictive native grammar canary failed; no fixture actions attempted')
            result=run_feedback(lambda messages:model.chat(messages,tools=TOOLS,max_tokens=128,temperature=0,reset=True,grammar=grammar),
                task['prompt'],args.output/'workspace',enabled=True,
                max_turns=record['max_turns'],max_seconds=record['max_loop_seconds'])
            record['loop']=result
            calls=[r['action'] for r in result['turns'] if 'tool_result' in r]
            results=[r['tool_result'] for r in result['turns'] if 'tool_result' in r]
            record['existing_demo_verification']=grade_task(task,calls,results,args.output/'workspace')
            record['completed']=result['status'] != 'runtime_error'
            if result['status']=='runtime_error':record['error']=result.get('error','Native feedback loop failed')
    except Exception as exc:record['error']=str(exc)
    finally:
        record['diagnostic_elapsed_s']=time.monotonic()-start
        record['timing_scope']='Artifact hashing, model load, optional canary, fixture creation, feedback loop, verification and model destruction; excludes initial argument/Git reads, final serialization and SDK shutdown; not frozen v2 timing'
        save()
        runtime.close()
    print(json.dumps({'completed':record['completed'],'loop_status':record.get('loop',{}).get('status'),'verification':record.get('existing_demo_verification')}))
    return 0 if record['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
