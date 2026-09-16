"""Internal diagnostic child: shared hardware lock spans the native lifetime."""
import argparse
import getpass
import hashlib
import tempfile
from pathlib import Path
import runpy
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from turbo.experiments import archive_lock
GLOBAL_HARDWARE_ROOT=Path(tempfile.gettempdir())/('turbolab-hardware-'+hashlib.sha256(getpass.getuser().encode()).hexdigest()[:16])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archives-root',type=Path,required=True)
    p.add_argument('--script',choices=['backend_smoke.py','diagnostic_canary.py','run_secretary_eval.py'],required=True)
    p.add_argument('arguments',nargs=argparse.REMAINDER)
    a=p.parse_args(argv)
    arguments=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
    if a.script=='run_secretary_eval.py':
        allowed={'--dataset','--candidate-name','--config','--output-dir'}
        if len(arguments)%2 or any(arguments[i] not in allowed for i in range(0,len(arguments),2)):
            p.error('Evaluator options must use exact supported names and separate values')
        options=dict(zip(arguments[::2],arguments[1::2]))
        if len(options)!=len(arguments)//2 or options.get('--dataset')!='dev':
            p.error('Exactly one development dataset option is required; duplicates refused')
        script=ROOT/'eval'/a.script
    else:script=ROOT/'scripts'/a.script
    original=sys.argv
    # Fixed order across all sessions, then the existing archive-root lock for compatibility.
    with archive_lock(GLOBAL_HARDWARE_ROOT,'hardware-execution',timeout=0), archive_lock(a.archives_root.resolve(),'hardware-execution',timeout=0):
        try:
            sys.argv=[str(script),*arguments]
            runpy.run_path(sys.argv[0],run_name='__main__')
        finally:sys.argv=original
    return 0


if __name__=='__main__':raise SystemExit(main())
