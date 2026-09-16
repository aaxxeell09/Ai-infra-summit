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
    args=p.parse_args(argv)
    if not args.enable_candidate:p.error('Explicit --enable-candidate required; default service remains unchanged')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():p.error('Clean committed source required')
    config=parse_json(args.config.read_bytes(),require_object=True)
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
        'model_sha256':None,'completed':False}
    path=Path(config['model_path'])
    if path.is_file():
        with path.open('rb') as stream:record['model_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    else:
        from turbo.tuning import _sha256
        record['model_sha256']=_sha256(path)
    def save(): (args.output/'diagnostic.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    save();runtime=NativeRuntime(config['sdk_dir'])
    try:
        with NativeModel(runtime,config['model_path'],**options) as model:
            result=run_feedback(lambda messages:model.chat(messages,tools=TOOLS,max_tokens=128,temperature=0,reset=True),
                task['prompt'],args.output/'workspace',enabled=True)
            record['loop']=result
            calls=[r['action'] for r in result['turns'] if 'tool_result' in r]
            results=[r['tool_result'] for r in result['turns'] if 'tool_result' in r]
            record['existing_demo_verification']=grade_task(task,calls,results,args.output/'workspace')
            record['completed']=True
    except Exception as exc:record['error']=str(exc)
    finally:
        record['total_process_elapsed_s']=time.monotonic()-start
        record['timing_scope']='SDK/model hashing, model load, fixture creation, feedback loop and final-state verification; not frozen v2 timing'
        save()
        runtime.close()
    print(json.dumps({'completed':record['completed'],'loop_status':record.get('loop',{}).get('status'),'verification':record.get('existing_demo_verification')}))
    return 0 if record['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
