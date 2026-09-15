"""Compare a measured candidate against its frozen golden reference."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eval.scoring import compare


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline',type=Path)
    p.add_argument('candidate',type=Path)
    p.add_argument('--policy',type=Path,default=ROOT/'eval/quality_policy.json')
    args=p.parse_args(argv)
    result=compare(json.loads(args.candidate.read_text()),json.loads(args.baseline.read_text()),
                   json.loads(args.policy.read_text()))
    print(json.dumps(result,indent=2,allow_nan=False))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__': raise SystemExit(main())
