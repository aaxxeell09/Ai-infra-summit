"""Prepare or explicitly execute target commissioning. Default is plan-only."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from turbo.optimizer.commissioning import DEFAULT_PATH,STEPS,TargetRunner,commission,diagnostic_worker
from turbo.experiments import git_state


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',choices=['qairt_npu'],default='qairt_npu')
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,default=DEFAULT_PATH)
    p.add_argument('--changed-config',type=Path)
    p.add_argument('--execute',action='store_true',help='Explicitly authorize inference on target; omit for plan-only')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--acknowledge-interrupted',action='store_true',help='Only after independently checking surviving hardware jobs')
    p.add_argument('--step',action='append',choices=tuple(STEPS))
    p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--diagnostic-worker',choices=['resident','s1','s2','s3'],help=argparse.SUPPRESS)
    from turbo.experiments import DEFAULT_ARCHIVES
    p.add_argument('--archives-root',type=Path,default=DEFAULT_ARCHIVES)
    p.add_argument('--worker-output',type=Path,help=argparse.SUPPRESS)
    a=p.parse_args(argv)
    if a.diagnostic_worker:
        if not a.worker_output or not a.execute:p.error('Worker requires --execute and output')
        diagnostic_worker(a.diagnostic_worker,a.config,a.worker_output,changed_config=a.changed_config,archives=a.archives_root);return 0
    if a.execute and git_state()['dirty']:p.error('Commit clean commissioning code before target execution')
    runner=TargetRunner(timeout=a.timeout,changed_config=a.changed_config,archives=a.archives_root) if a.execute else None
    result=commission(a.config,output=a.output,runner=runner,steps=a.step or tuple(STEPS),
                      resume=a.resume,acknowledge_interrupted=a.acknowledge_interrupted,inspect_artifacts=a.execute,archives=a.archives_root)
    print(str(a.output.resolve()))
    return 1 if any(attempt['status']=='failed' for attempt in result['attempts']) else 0


if __name__=='__main__':raise SystemExit(main())
