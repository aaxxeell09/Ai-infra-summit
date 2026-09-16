"""Archive every experiment before execution; never overwrite an experiment."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from turbo.experiments import DEFAULT_ARCHIVES, backfill, ledger, read_json, run, verify


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=DEFAULT_ARCHIVES)
    sub=p.add_subparsers(dest='action',required=True)
    r=sub.add_parser('run');r.add_argument('--name',required=True);r.add_argument('--config',type=Path,required=True)
    r.add_argument('--dataset',choices=['dev','all'],default='dev');r.add_argument('--change',required=True)
    r.add_argument('--hypothesis',required=True);r.add_argument('--control');r.add_argument('--diagnostic-dirty',action='store_true')
    r.add_argument('--timeout',type=float,default=600);r.add_argument('--capture-full-process-energy',action='store_true')
    r.add_argument('--counter-resolution',type=float)
    b=sub.add_parser('backfill');b.add_argument('source',type=Path);b.add_argument('--telemetry',type=Path)
    b=sub.add_parser('backfill-known');b.add_argument('--search',type=Path,action='append')
    sub.add_parser('ledger');v=sub.add_parser('verify');v.add_argument('archive',type=Path)
    a=p.parse_args(argv)
    try:
        paths=[]
        if a.action=='run':
            paths=[run(a.name,a.config,root=a.root,dataset=a.dataset,change=a.change,hypothesis=a.hypothesis,
                       control=a.control,diagnostic_dirty=a.diagnostic_dirty,timeout=a.timeout,
                       capture_energy=a.capture_full_process_energy,counter_resolution=a.counter_resolution)]
        elif a.action=='backfill':paths=[backfill(a.source,a.root,a.telemetry)]
        elif a.action=='backfill-known':
            for folder in a.search or [ROOT/'local',ROOT/'eval/results']:
                for source in sorted(folder.rglob('*.json')):
                    if source.resolve().is_relative_to(a.root.resolve()):continue
                    try:data=read_json(source)
                    except (ValueError,OSError):continue
                    if not isinstance(data,dict):continue
                    if ((data.get('schema_version')==2 and isinstance(data.get('results'),list)
                         and data.get('benchmark_version')=='secretary-eval-v2') or data.get('kind')=='counter_update_probe'):
                        label=source.stem.removeprefix('candidate_')
                        candidates=[source.with_name(source.stem+'_telemetry.json'),source.with_name(label+'-telemetry.json')]
                        telemetry=next((t for t in candidates if t.exists()),None)
                        paths.append(backfill(source,a.root,telemetry))
        elif a.action=='ledger':print(json.dumps(ledger(a.root),indent=2));return 0
        else:
            errors=verify(a.archive);print(json.dumps({'errors':errors,'valid':not errors}));return bool(errors)
        for path in paths:
            m=read_json(path/'manifest.json')
            print(m['experiment_id']);print((path/'KPI.txt').read_text(),end='')
            print('STATUS='+m['status']+'\nARCHIVE='+str(path))
        if a.action=='run' and paths:
            status=read_json(paths[0]/'manifest.json')['status']
            return 124 if status=='timeout' else 1 if status in ('failed','incomplete') else 0
        return 0
    except (ValueError,OSError) as exc:p.error(str(exc))


if __name__=='__main__':raise SystemExit(main())
