"""Inspect or change future coordination decisions; never runs hardware."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from turbo.optimizer.event_coordinator import Coordinator


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--action',choices=['status','heartbeat','reject','repeat','reorder','research'],default='status')
    parser.add_argument('--candidate')
    parser.add_argument('--reason')
    parser.add_argument('--priority',type=float)
    parser.add_argument('--inbox-root',type=Path)
    args=parser.parse_args(argv)
    coordinator=Coordinator(args.state)
    if args.action in ('reject','repeat','reorder'):
        if not args.candidate or not args.reason:parser.error('Candidate and decision reason required')
        coordinator.future(args.candidate,args.action,reason=args.reason,priority=args.priority)
    elif args.action=='heartbeat':coordinator.heartbeat(force=True)
    elif args.action=='research':
        if not args.inbox_root:parser.error('Research inbox root required')
        coordinator.import_research(args.inbox_root)
    print(json.dumps(coordinator.snapshot(),indent=2,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
