"""Freeze a TurboLab result and run the one explicit heldout evaluation.

This is a separate command on purpose. The optimization loop can never reach
heldout cases, and the only way they are ever evaluated is an operator typing
this. Once a session is frozen here, its configuration is fixed by hash and the
loop refuses to keep optimizing it, so a heldout number can never be used to
steer another round of search.

The heldout result is written where the operator asks and is NOT fed back into
the session state. That is the whole point: a heldout score that influences the
next search stops being a heldout score.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turbo.experiments import atomic, digest
from turbo.json_io import read_json
from turbo.optimizer import state as state_module

FREEZE_SCHEMA = 'local-turbo.autotune-final.v1'


def freeze(state, *, config_path, note=None):
    """Record the exact configuration a session ended on, by hash.

    The byte hash and the semantic hash are both recorded: the first identifies
    the file that will be run, the second identifies the treatment regardless of
    formatting, and a later reader needs to be able to tell those apart.
    """
    raw = Path(config_path).read_bytes()
    config = read_json(config_path, require_object=True)
    control = state.get('current_control') or {}
    if control.get('config_hash') and state_module.config_hash(config) != control['config_hash']:
        raise ValueError('The supplied config is not the session final control; refusing to '
                         'freeze a configuration this session did not reach')
    import hashlib
    return {'schema_version': FREEZE_SCHEMA,
            'session_id': state.get('session_id'),
            'backend': state.get('backend'),
            'frozen_at': state_module.now(),
            'config_byte_sha256': hashlib.sha256(raw).hexdigest(),
            'config_semantic_sha256': state_module.config_hash(config),
            'control_name': control.get('name'),
            'control_experiment_id': control.get('experiment_id'),
            'optimization_closed': True,
            'note': note,
            'heldout_status': 'not evaluated by this command unless --run-heldout was given'}


def close_session(state, record, path):
    """Mark the session closed so no further optimization can reopen it."""
    state['finished_at'] = state_module.now()
    state['final_freeze'] = record
    state_module.save(state, path)
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('session', nargs='?', type=Path,
                   default=state_module.DEFAULT_HOME / 'session.json')
    p.add_argument('--config', type=Path, required=True,
                   help='The exact configuration the session ended on')
    p.add_argument('--output', type=Path,
                   default=state_module.DEFAULT_HOME / 'reports/final-freeze.json')
    p.add_argument('--note')
    p.add_argument('--run-heldout', action='store_true',
                   help='Also run the 15 heldout cases through the frozen runner. '
                        'This is the only command in TurboLab that may do so.')
    p.add_argument('--candidate-name', help='Report label for the heldout run')
    p.add_argument('--heldout-output-dir', type=Path,
                   default=ROOT / 'local/secretary-eval-final')
    args = p.parse_args(argv)

    if not args.session.exists():
        p.error('No session at ' + str(args.session))
    try:
        state = state_module.load(args.session)
        record = freeze(state, config_path=args.config, note=args.note)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic(args.output, json.dumps(record, indent=2, ensure_ascii=False,
                                   allow_nan=False).encode('utf-8') + b'\n')
    close_session(state, record, args.session)
    print(json.dumps(record, indent=2))

    if not args.run_heldout:
        print('Frozen. Heldout was not evaluated. Re-run with --run-heldout to evaluate it.')
        return 0
    if not args.candidate_name:
        p.error('--candidate-name is required for a heldout evaluation')
    from eval.run_secretary_eval import main as run_eval
    print('Running the heldout split once, explicitly, on a frozen configuration.')
    code = run_eval(['--dataset', 'heldout', '--candidate-name', args.candidate_name,
                     '--config', str(args.config),
                     '--output-dir', str(args.heldout_output_dir)])
    print('Heldout evaluation exit code: ' + str(code))
    print('This result is deliberately not written back into the session state.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
