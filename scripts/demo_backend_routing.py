"""Sequential public presentation diagnostics, never the golden benchmark."""
import argparse, json, time, urllib.request, hashlib, sys, subprocess, datetime
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8083');p.add_argument('--case',choices=['gpu','npu','auto-quick','auto-reasoning'],required=True);p.add_argument('--output',required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
(out/'client.json').write_text(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'argv':sys.argv,'scope':'Public answer presentation, not a correctness benchmark'},indent=2))
manifest_path=root/'benchmarks/results/screen-01/sweep.json';m=json.loads(manifest_path.read_text())
from turbo.live_comparison import PROMPTS

def config(cell):
 r=json.loads((root/f'benchmarks/results/screen-01/{cell}.json').read_text())
 return dict(cell_id=cell,model=m['model_name'],model_sha256=m['model_sha256'],runtime_sha256=m['runtime_sha256'],plugin='llama_cpp',requested_device=r['device'],source_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),params=r['params'])
def call(path,data=None):
 req=urllib.request.Request(args.base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=12) as f:return json.load(f)
prompt='reasoning' if args.case=='auto-reasoning' else 'quick';ident=out.name
body=dict(schema_version='local-turbo.comparison-request.v1',request_id=ident,comparison='routing' if args.case.startswith('auto') else 'speed',execution='sequential',prompt_id=prompt,prompt=PROMPTS[prompt],baseline=config('cpu-t0'),selected=None if args.case.startswith('auto') else config(args.case),routing={'selection':'auto','policy':'public-demo-v1','allow_uncalibrated':True} if args.case.startswith('auto') else None)
(out/'request.json').write_text(json.dumps(body,indent=2));(out/'capabilities.json').write_text(json.dumps(call('/api/live-comparisons/capabilities'),indent=2))
state=call('/api/live-comparisons',body)
(out/'start.json').write_text(json.dumps(state,indent=2))
started=time.monotonic();last=0
while state['state']=='running':
 if time.monotonic()-started>135:
  (out/'cancel.json').write_text(json.dumps(call(f'/api/live-comparisons/{ident}/cancel',{}),indent=2));raise SystemExit('Cancellation requested; reconcile SAME ID before retry')
 time.sleep(.5);state=call(f'/api/live-comparisons/{ident}')
 if time.monotonic()-last>10:
  print(json.dumps({'id':ident,'state':state['state'],'events':len(state['events'])}),flush=True);last=time.monotonic()
 (out/'last-status.json').write_text(json.dumps(state,indent=2))
(out/'device-result.json').write_text(json.dumps(state,indent=2))
print(json.dumps({'state':state['state'],'error':state['error'],'routing':(state.get('result') or {}).get('routing'),'lanes':{k:{a:v.get(a) for a in ['status','answer','total_time_s','native_decode_tps','native_prefill_tps','ttft_ms','effective_configuration']} for k,v in (state.get('result') or {}).get('lanes',{}).items()}}),flush=True)
