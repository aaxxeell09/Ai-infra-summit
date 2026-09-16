"""TurboLab: bounded autonomous search over supported Secretary configurations.

The loop keeps one hardware slot busy with candidates that a static guard has
already admitted, and it stops when the budget, the queue or the operator says
so. It creates no measurement of its own: every hardware evaluation goes through
the existing experiment tracker, and every number in the final report either
came from there or is reported as not measured.

Heldout cases are unreachable from this command by construction. Final heldout
evaluation is a separate, explicit command, scripts/autotune_final.py.
"""
import argparse
import copy
import subprocess
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from turbo.json_io import read_json
from turbo.optimizer import observation as observation_module
from turbo.optimizer import (advisor as advisor_module, budget as budget_module,
                             console as console_module, grid, guard, hardware_queue, llm,
                             probe, proposer, report, scheduler as scheduler_module,
                             search_space as space, selector, state as state_module,
                             successive_halving)

DEFAULT_SESSION = state_module.DEFAULT_HOME / 'session.json'

#: What --mock-llm answers. One admissible hypothesis over a declared control and
#: one that names a control the frozen contract cannot express, so a dry run
#: exercises both branches: a real candidate being built, and a research idea
#: staying visible as inadmissible instead of vanishing.
MOCK_PROPOSAL = {'hypotheses': [
    {'family': 'output_budget',
     'mechanism': 'A shorter generation budget truncates runaway output before it becomes a '
                  'second tool call, which is the dominant structural failure recorded so far',
     'why_now': 'The control uses the runner default and no shorter budget has been measured',
     'search_space': {'max_tokens': [32, 48, 64]},
     'expected_signal': 'Fewer invalid structured outputs at equal or better correctness',
     'abandon_if': 'Correctness falls while the invalid rate is unchanged'},
    {'family': 'sampler',
     'mechanism': 'Explicit greedy decoding would remove sampling as a confound',
     'why_now': 'Requested temperature zero does not establish greedy decoding on this plugin',
     'search_space': {'top_k': [1]},
     'expected_signal': 'Byte-identical output across repeats',
     'abandon_if': 'Repeated outputs still differ'}]}

MOCK_CRITIQUE = {'findings': [
    {'kind': 'unsupported_claim', 'candidate_id': None, 'severity': 'warn',
     'detail': 'A shorter budget changes both truncation and cost; attribute carefully'}]}


class VirtualClock:
    """A clock a dry run can advance without waiting.

    A simulated session must exercise the real phase transitions and the real
    budget arithmetic. Sleeping through two hours to do that would make the
    simulator useless, and faking the arithmetic instead would make it a lie, so
    the clock moves and everything else stays real.
    """

    def __init__(self, start=0.0):
        self.value = float(start)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += max(0.0, float(seconds))
        return self.value


def load_control(path):
    config = read_json(path, require_object=True)
    if not config:
        raise ValueError('Control config must be a nonempty object')
    return config


def resolve_backend(config, requested):
    declared = config.get('backend')
    if declared and requested and declared != requested:
        raise ValueError('Control config declares backend ' + repr(declared)
                         + ' but --backend says ' + repr(requested))
    backend = requested or declared
    if backend not in space.BACKENDS:
        raise ValueError('Unknown backend: ' + repr(backend))
    return backend


def build_llm(mock, cache_dir):
    """Return (proposer_client, critic_client, status) without ever raising.

    A missing credential is a session fact, not a failure: the loop runs its
    deterministic search regardless, and the report says the model was
    unavailable rather than pretending no proposal was wanted.
    """
    if mock:
        # The mock answers with a real proposal, not an empty one. A stub that
        # returns nothing proves only that a client can be constructed, which is
        # exactly the gap this exists to close: every step after the call,
        # schema validation, bounded mapping, guard admission and family
        # selection, has to run in a dry run too.
        return (llm.MockClient({}, model='mock-proposer', default=json.dumps(MOCK_PROPOSAL)),
                llm.MockClient({}, model='mock-critic', default=json.dumps(MOCK_CRITIQUE)),
                {'proposer': 'MOCK', 'critic': 'MOCK'})
    status = {'proposer': llm.credential_status(proposer.ANTHROPIC_KEY_VAR),
              'critic': llm.credential_status('OPENAI_API_KEY')}
    client = None
    if status['proposer'] == llm.STATUS_AVAILABLE:
        try:
            client = proposer.AnthropicClient()
        except Exception as exc:                      # the SDK may not be installed at all
            status['proposer'] = llm.STATUS_UNAVAILABLE
            status['proposer_detail'] = type(exc).__name__
    critic_client = None
    if status['critic'] == llm.STATUS_AVAILABLE:
        from turbo.optimizer import critic as critic_module
        try:
            critic_client = critic_module.OpenAIClient()
        except Exception as exc:
            status['critic'] = llm.STATUS_UNAVAILABLE
            status['critic_detail'] = type(exc).__name__
    return client, critic_client, status


def phase_plan(phase, backend):
    """Which stages this phase permits, and how broadly it generates.

    Exploration generates widely and only runs the cheap stages, so a wide
    sweep cannot consume the budget on full development runs. Focus stops
    generating breadth and pushes the survivors up the ladder. The last two
    phases neither generate nor start anything cheap: they finish what is
    already promising, because a candidate started at minute 115 that needs six
    minutes is a candidate whose result nobody will see.

    The mapping is deliberately coarse. A finer policy would need evidence about
    stage costs that does not exist until commissioning has run on the target
    machine, and inventing it here would put a number in the loop that nobody
    measured.
    """
    families = space.families(backend)
    if phase == 'explore':
        return {'stages': ('S1', 'S2'), 'families': families, 'breadth': 'wide',
                'generate': True, 'propose': True}
    if phase == 'focus':
        return {'stages': ('S1', 'S2', 'S3', 'S4'), 'families': families,
                'breadth': 'productive', 'generate': True, 'propose': True}
    if phase == 'confirm_only':
        return {'stages': ('S4', 'S5'), 'families': families, 'breadth': 'best',
                'generate': False, 'propose': False}
    return {'stages': ('S5',), 'families': families, 'breadth': 'best', 'generate': False,
            'propose': False}


def productive_families(state, fallback):
    """Families with observed survival, most productive first.

    With no evidence yet every family is equally plausible, so the fallback is
    the declared order rather than an arbitrary preference.
    """
    ranked = sorted(state['families'].values(),
                    key=lambda record: (record['confirmed_wins'], record['dev35_wins'],
                                        record['survived_s3'], record['survived_s2']),
                    reverse=True)
    names = [record['family'] for record in ranked
             if record['survived_s2'] or record['dev35_wins'] or record['confirmed_wins']]
    return tuple(names) or tuple(fallback)


def generate_by_family(engine, console, families, max_points):
    """Generate one bounded grid per family, never one across all of them.

    The product across families is tens of thousands of points on the llama.cpp
    backends. Most of them say nothing a within-family grid plus later
    refinement does not, and a point that crosses four families explains nothing
    on its own. A family whose own grid still exceeds the bound is skipped with
    its reason rather than truncated, because a truncated design is an arbitrary
    prefix of a design, and the session continues on the families that fit.
    """
    candidates = []
    for family in families:
        try:
            candidates.extend(engine.generate(families=[family], max_points=max_points))
        except ValueError as exc:
            console.warn('family ' + str(family) + ' skipped: ' + str(exc))
    return candidates


def control_candidate(state, stage):
    control = state['current_control']
    return {'candidate_id': 'CONTROL-' + stage + '-' + control['config_hash'][:12],
            'config': copy.deepcopy(control['config']), 'config_hash': control['config_hash'],
            'family': 'control', 'variable': None, 'treatment': 'control', 'is_control': True,
            'hypothesis': 'Reference condition; no optimization claim',
            'requires_restart': False, 'expected_hardware_seconds': None,
            'priority': 1.0, 'status': 'generated'}


def measure_control(engine, state, stage, *, job_id=None, candidate=None):
    """Controls share the same durable scheduler and hardware exclusion as treatments."""
    if stage == 'S1':
        return None
    return engine.run_candidate(candidate or control_candidate(state, stage), stage, job_id=job_id)


def funnel(stage, observations, control_observation, console):
    """Apply the stage rule to each observation and return the survivors.

    The control observation is whatever this stage measured for the current
    control, when the stage measured it. When it did not, the stage rules are
    given None and must say so rather than comparing against an assumed value.
    """
    rules = {'S1': None, 'S2': successive_halving.evaluate_s2,
             'S3': successive_halving.evaluate_s3, 'S4': successive_halving.evaluate_s4}
    survivors, evaluated = [], {}
    for candidate, observation in observations:
        evaluated[candidate['candidate_id']] = observation
        if control_observation is None and candidate.get('is_control'):
            control_observation = observation
        if isinstance(control_observation, dict):
            # The latency gate belongs here, where both observations are in hand
            # and their boundary labels can be compared. A gate computed against
            # a differently scoped baseline would be the substitution the
            # tracking audit ruled out, so annotate_gates returns None instead.
            observation_module.annotate_gates(observation, control_observation)
        if observation.get('rows') and (control_observation or {}).get('rows'):
            # Case-level deltas are what every stage above S2 actually compares,
            # and a confirmation repeat needs them too, so they are computed once
            # here rather than inside each branch.
            observation['net_cases'] = successive_halving.case_deltas_from_rows(
                control_observation['rows'], observation['rows']).get('net')
        if stage == 'S1':
            verdict, reasons = successive_halving.evaluate_s1(observation)
        elif stage == 'S5':
            verdict, reasons = 'survive', ['Confirmation repeat recorded']
        else:
            rule = rules.get(stage)
            if rule is None or control_observation is None:
                verdict, reasons = 'survive', ['No control observation at this stage; '
                                               'elimination deferred rather than guessed']
            else:
                deltas = ({'net': observation['net_cases'], 'stage': stage}
                          if observation.get('net_cases') is not None else None)
                verdict, reasons = (rule(observation, control=control_observation, deltas=deltas)
                                    if stage in ('S3', 'S4')
                                    else rule(observation, control=control_observation))
        if verdict == 'survive':
            survivors.append(candidate)
        else:
            console.stage(stage, candidate['candidate_id'], 'DROP ' + '; '.join(reasons[:1]))
    return survivors, control_observation, evaluated


def promote_best(state, survivors, console, *, selector_module, evaluated, confirmations=None):
    """Ask the selector about the strongest survivor, never about all of them.

    Promotion is a control change, so at most one candidate can win a round. The
    ranking here only decides who is asked; the answer still comes from the
    conservative rule in successive_halving.
    """
    ranked = sorted(survivors, key=lambda c: c.get('priority') or 0.0, reverse=True)
    best = ranked[0]
    dev35 = evaluated.get(best['candidate_id'])
    confirmation = (confirmations or {}).get(best['candidate_id'])
    if dev35 is None or dev35.get('net_cases') is None:
        console.stage('S4', best['candidate_id'],
                      'HOLD no case-level delta recorded; promotion needs measured cases')
        return None
    selection = selector_module.consider(
        state, best, dev35_deltas={'net': dev35['net_cases'], 'stage': 'S4'},
        confirmation_deltas=({'net': confirmation['net_cases'], 'stage': 'S5'}
                             if confirmation and confirmation.get('net_cases') is not None
                             else None),
        latency_gate_ok=bool(dev35.get('latency_gate_ok')),
        deterministic_output=bool(dev35.get('deterministic_output')))
    if selection.get('decision') == 'promote':
        console.promotion(best['candidate_id'], 'net ' + str(dev35['net_cases']) + ' cases')
        console.control(state['controls_history'][-1]['name'], best['candidate_id'])
    else:
        console.stage('S4', best['candidate_id'],
                      str(selection.get('decision')).upper() + ' '
                      + '; '.join(selection.get('reasons', [])[:1]))
    return selection


RESUME_SETTINGS = ('control_config','control_name','backend','split','budget_minutes','session_dir',
                   'archive_root','dry_run','mock_llm','max_points','stage_limit','owner_decision',
                   'simulated_seconds_per_case','s2_cases','s3_cases','canary_seed','canary_timeout',
                   'startup_timeout','llm_timeout','diagnostic_dirty','timeout')


def restore_resume_settings(args):
    if args.resume:
        saved = state_module.load(args.resume).get('resume_settings')
        if saved:
            for key, value in saved.items():
                setattr(args, key, value)
            for key in ('control_config','session_dir','archive_root'):
                if getattr(args, key, None):
                    setattr(args, key, Path(getattr(args, key)))
    return args


def run_session(args, *, clock, executor, session_path, console, advisor=None):
    # One controller per durable session, independently of the hardware mutex.
    # This lock spans authoritative resume loading through the final checkpoint.
    from turbo.experiments import archive_lock, digest
    path = Path(session_path).resolve()
    with archive_lock(path.parent, 'autotune-session-' + digest(path.name)[:16], timeout=0):
        return _run_session_locked(args, clock=clock, executor=executor,
                                   session_path=path, console=console, advisor=advisor)


def _run_session_locked(args, *, clock, executor, session_path, console, advisor=None):
    control_config = load_control(args.control_config)
    backend = resolve_backend(control_config, args.backend)
    if args.resume:
        state = state_module.resume(args.resume)
        if state['backend'] != backend:
            raise ValueError('Resumed session targets backend ' + state['backend'])
        session_budget = budget_module.Budget(state['budget_minutes'], clock=clock)
        session_budget.restore({'schema_version': budget_module.SCHEMA,
                                'elapsed_seconds': state.get('elapsed_seconds', 0.0)})
    else:
        state = state_module.new_session(
            backend=backend, split=args.split, budget_minutes=args.budget_minutes,
            control_name=args.control_name, control_config=control_config,
            search_space_sha256=space.declared_space(backend)['space_sha256'])
        session_budget = budget_module.Budget(args.budget_minutes, clock=clock)
    state['owner_decisions'] = list(args.owner_decision or ())
    if advisor is not None:
        # The advisor is built before the session record exists, because the
        # credential check belongs with the other startup checks. It is bound to
        # the real state here so its counters land in the session that is saved.
        advisor.state = state
        advisor_module.counters(state)

    queue = hardware_queue.HardwareQueue()
    # Durable active batches, not transient queue snapshots, own resume work.

    engine = scheduler_module.Scheduler(
        state, backend=backend, budget=session_budget, queue=queue, executor=executor,
        console=console, owner_decisions=state['owner_decisions'], clock=clock,
        dry_run=args.dry_run, checkpoint_path=session_path).install_interrupt_handler()

    settings = {key: getattr(args, key, None) for key in RESUME_SETTINGS}
    settings['control_config'] = str(Path(args.control_config).resolve())
    settings['session_dir'] = str(Path(args.session_dir).resolve())
    settings['archive_root'] = str(args.archive_root) if getattr(args, 'archive_root', None) else None
    state.setdefault('resume_settings', settings)
    state.setdefault('workflow', {'pool': {stage: [] for stage in ('S1','S2','S3','S4','S5')},
                                'generated_signatures': [], 'seen_phases': [], 'active_batch': None,
                                'batch_counter': 0, 'confirmations': {}, 'dev35_observations': {},
                                'initial_control': copy.deepcopy(state['current_control'])})
    if not args.resume and Path(session_path).exists():
        raise ValueError('Session already exists; use --resume or a new --session-dir: ' + str(session_path))
    state['session_status'] = 'running'
    engine.checkpoint()
    try:
        return _continue_session(args, state, engine, session_budget, console, advisor, session_path)
    except BaseException as exc:
        state['session_status'] = 'failed'
        state.setdefault('failures', []).append(state_module.failure_record(exc, where='session'))
        engine.checkpoint()
        raise


def _continue_session(args, state, engine, session_budget, console, advisor, session_path):
    backend = state['backend']
    console.line('TurboLab session ' + state['session_id'] + ' backend=' + backend
                 + ' split=' + state['split'] + ' budget=' + str(state['budget_minutes']) + ' min')
    counts = grid.reachable_treatment_count(backend)
    console.line('reachable: ' + str(counts['single_variable_treatments'])
                 + ' single-variable treatments, ' + str(counts['full_cartesian_points'])
                 + ' bounded grid points')

    workflow = state['workflow']
    pool = workflow['pool']
    while workflow['active_batch'] is not None or (not session_budget.exhausted and not engine.interrupted):
        if workflow['active_batch'] is not None:
            active = workflow['active_batch']
            if not _run_batch(engine, state, args, active['stage'], active['phase'], console):
                break
            continue
        phase = session_budget.phase()
        if phase not in workflow['seen_phases']:
            workflow['seen_phases'].append(phase)
            console.event('PHASE', phase, 'remaining ' + str(round(session_budget.remaining_minutes, 1)) + ' min')
        plan = phase_plan(phase, backend)
        signature = [state['current_control']['config_hash'], plan['breadth']]
        if plan['generate'] and signature not in workflow['generated_signatures']:
            control_config = state['current_control']['config']
            hypotheses, llm_candidates = [], []
            if advisor is not None and plan['propose']:
                hypotheses = advisor.propose(backend=backend,
                    remaining_minutes=session_budget.remaining_minutes, phase=phase)
            if hypotheses:
                llm_candidates, llm_rejected = advisor.candidates_from(hypotheses,
                    control_config=control_config, backend=backend,
                    start_index=state['counters']['generated'] + 1)
                state['counters']['generated'] += len(llm_candidates)
                for name, value, reason in llm_rejected:
                    console.event('LLM', str(name)[:10], 'rejected ' + repr(value) + ': ' + str(reason)[:70])
            families = advisor.families_to_explore(hypotheses, backend=backend, fallback=()) if hypotheses else None
            if not families:
                families = plan['families'] if plan['breadth'] == 'wide' else productive_families(state, plan['families'])
            candidates = llm_candidates + generate_by_family(engine, console, families, args.max_points)
            admitted = engine.admit(candidates)
            if advisor is not None:
                advisor.submit_critique(admitted, phase=phase, hypotheses=hypotheses)
                admitted, blocked = advisor.deprioritise(admitted, advisor.collect_critiques())
                for candidate in blocked:
                    state_module.record_rejection(state, candidate, ['Critic raised a blocking finding'])
                    engine.checkpoint()
            pool['S1'].extend(admitted)
            workflow['generated_signatures'].append(signature)
            engine.checkpoint()
        progressed = False
        for stage in plan['stages']:
            if not pool[stage] or session_budget.exhausted or engine.interrupted:
                continue
            progressed = _run_batch(engine, state, args, stage, phase, console) or progressed
        if not progressed:
            stage = next((name for name in ('S3','S4','S5','S2','S1') if pool[name]), None)
            if stage is None or session_budget.exhausted or engine.interrupted:
                console.warn('no work remains for the current control')
                break
            console.event('RELAX', phase, 'running ' + stage + ' outside its phase rather than idling the device')
            if not _run_batch(engine, state, args, stage, phase, console):
                break
    if advisor is not None:
        advisor.collect_critiques(wait_s=5.0)
    state['session_status'] = 'interrupted' if engine.interrupted else 'stopped'
    resume_command = engine.finish(session_path)
    summary = report.session_summary(state, started_at=state['created_at'], finished_at=state_module.now(),
        initial_control=workflow['initial_control'], final_control=state['current_control'])
    summary['counts_by_name'] = engine.counts()
    summary['llm_status'] = args.llm_status
    summary['llm_counters'] = advisor.report_counters() if advisor is not None else {name: 0 for name in advisor_module.COUNTERS}
    summary['dry_run'] = bool(args.dry_run)
    directory = state_module.ensure_home(args.session_dir) / 'reports'
    paths = report.write_summary(summary, directory)
    console.line('summary written: ' + ', '.join(str(p) for p in paths))
    if engine.interrupted:
        console.warn('interrupted; recovery state: ' + str(Path(session_path).resolve()))
    return summary


def _run_batch(engine, state, args, stage, phase, console):
    workflow = state['workflow']
    batch = workflow['active_batch']
    if batch is None:
        waiting = workflow['pool'][stage]
        engine.enqueue(waiting, phase=phase)
        ordered = engine.queue.drain()
        workflow['batch_counter'] += 1
        batch = {'id': 'B-' + str(workflow['batch_counter']), 'stage': stage, 'phase': phase,
                 'waiting': copy.deepcopy(ordered),
                 'selected': copy.deepcopy(ordered[:args.stage_limit] if args.stage_limit is not None else ordered),
                 'control': control_candidate(state, stage)}
        workflow['active_batch'] = batch
        engine.checkpoint()
    journal = state['hardware_journal']
    def failed(job):
        return journal.get(job, {}).get('status') == 'failed'
    control_job = batch['id'] + ':control'
    if stage != 'S1' and failed(control_job):
        raise RuntimeError('Control failed at ' + stage + '; batch remains blocked and unqualified pending reconciliation')
    control = None if stage == 'S1' else measure_control(
        engine, state, stage, job_id=control_job, candidate=batch['control'])
    if stage != 'S1':
        if control is None:
            return False  # Budget did not admit the control; do not launch treatments.
        if control.get('runtime_error') or control.get('outcome') in ('failed','crashed','timed_out','refused','skipped'):
            raise RuntimeError('Control has no usable observation at ' + stage + '; batch remains blocked and unqualified')
    observations, failed_ids = [], set()
    for candidate in batch['selected']:
        job = batch['id'] + ':' + candidate['candidate_id']
        if failed(job):
            failed_ids.add(candidate['candidate_id'])
            continue
        observation = engine.run_candidate(candidate, stage, job_id=job)
        if observation is None:
            break
        observations.append((candidate, observation))
    # Replay postprocessing transactionally from durable full observations. If
    # processing fails, restore the pre-processing state; resume replays it only,
    # never a completed hardware invocation.
    before = copy.deepcopy(state)
    try:
        survivors, _, evaluated = funnel(stage, observations, control, console)
        done = failed_ids | {candidate['candidate_id'] for candidate, _ in observations}
        workflow['pool'][stage] = [c for c in batch['waiting'] if c['candidate_id'] not in done]
        if stage == 'S4':
            workflow['dev35_observations'].update(evaluated)
        if stage == 'S5':
            workflow['confirmations'].update(evaluated)
        if stage in ('S4','S5') and survivors:
            promote_best(state, survivors, console, selector_module=selector,
                evaluated=workflow['dev35_observations'], confirmations=workflow['confirmations'])
        following = successive_halving.next_stage(stage)
        if following in workflow['pool']:
            workflow['pool'][following].extend(survivors)
        workflow['active_batch'] = None
        engine.checkpoint()
    except BaseException:
        state.clear()
        state.update(before)
        raise
    return bool(observations or failed_ids)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--budget-minutes', type=float, default=120.0)
    p.add_argument('--backend', choices=space.BACKENDS)
    p.add_argument('--split', choices=['development'], default='development',
                   help='Development only. Heldout is not reachable from this command.')
    p.add_argument('--control-config', type=Path,
                   help='Private JSON control configuration; required unless --dry-run')
    p.add_argument('--control-name', default='control')
    p.add_argument('--session-dir', type=Path, default=state_module.DEFAULT_HOME)
    p.add_argument('--archive-root', type=Path, default=None,
                   help='Experiment tracker root; defaults to the tracker default')
    p.add_argument('--resume', type=Path)
    p.add_argument('--dry-run', action='store_true',
                   help='Simulate the loop with no hardware and no API calls')
    p.add_argument('--mock-llm', action='store_true')
    p.add_argument('--max-points', type=int, default=grid.DEFAULT_MAX_POINTS)
    p.add_argument('--stage-limit', type=int, default=None,
                   help='Maximum hardware evaluations per stage per phase')
    p.add_argument('--owner-decision', action='append',
                   choices=sorted(guard.OWNER_DECISIONS),
                   help='Declare an owner decision as implemented; repeatable')
    p.add_argument('--simulated-seconds-per-case', type=float, default=1.0)
    p.add_argument('--s2-cases', type=int, default=0,
                   help='Development cases in the S2 diagnostic canary. 0 skips S2 explicitly '
                        'rather than silently widening it to the full development set.')
    p.add_argument('--s3-cases', type=int, default=0,
                   help='Development cases in the S3 diagnostic canary. 0 skips S3 explicitly.')
    p.add_argument('--canary-seed',
                   help='Fixes the canary subset before the session so it cannot adapt to results')
    p.add_argument('--canary-timeout', type=float, default=900.0)
    p.add_argument('--startup-timeout', type=float, default=180.0)
    p.add_argument('--llm-timeout', type=float, default=60.0)
    p.add_argument('--diagnostic-dirty', action='store_true')
    p.add_argument('--timeout', type=float, default=600.0)
    args = p.parse_args(argv)
    try:
        restore_resume_settings(args)
    except (ValueError, OSError) as exc:
        p.error(str(exc))

    if args.split != 'development':
        p.error('Only the development split may be optimized')
    if args.dry_run and not args.control_config:
        args.control_config = ROOT / 'configs/qairt-secretary.example.json'
        if args.backend is None:
            args.backend = 'qairt_npu'
    if not args.control_config:
        p.error('--control-config is required unless --dry-run supplies an example')

    console = console_module.Console()
    proposer_client, critic_client, status = build_llm(args.mock_llm,
                                                       state_module.ensure_home(args.session_dir))
    args.llm_status = status
    console.line('proposer=' + str(status['proposer']) + ' critic=' + str(status['critic']))

    if args.dry_run:
        clock = VirtualClock()

        def latency(candidate, stage):
            cases = {'S1': 1, 'S2': 8, 'S3': 18, 'S4': 35, 'S5': 35}.get(stage, 1)
            seconds = cases * args.simulated_seconds_per_case
            seconds += 30.0 if candidate.get('requires_restart') else 0.0
            clock.advance(seconds)
            return seconds

        simulated = scheduler_module.simulated_executor(latency_model=latency, rng=None)
        # A dry run exercises the same routing the real path uses, and the S4
        # and S5 routes go through a real sealed archive so the observation
        # adapter is exercised too. The archives are written into a throwaway
        # directory and discarded: they describe nothing that was measured, and
        # leaving them on disk would be manufacturing evidence.
        simulated_archives = tempfile.TemporaryDirectory(prefix='turbolab-dry-run-')
        args._simulated_archives = simulated_archives
        executor = scheduler_module.staged_executor(
            probe=simulated, canary=simulated,
            tracker=scheduler_module.simulated_archive_executor(
                simulated_archives.name, inner=simulated))
    else:
        clock = time.monotonic
        home = state_module.ensure_home(args.session_dir)
        from turbo.experiments import DEFAULT_ARCHIVES
        # Each stage goes to the executor entitled to answer it. One executor
        # for all five, as an earlier version had, meant the real path ran the
        # full development set five times and called the first three cheap.
        executor = scheduler_module.staged_executor(
            probe=scheduler_module.startup_probe_executor(
                repo=ROOT, timeout_s=args.startup_timeout,
                config_directory=home / 'candidates'),
            canary=scheduler_module.canary_executor(
                repo=ROOT, seed_label=args.canary_seed or 'turbolab',
                sizes={'S2': args.s2_cases, 'S3': args.s3_cases},
                output_directory=home / 'canaries', timeout_s=args.canary_timeout,
                config_directory=home / 'candidates'),
            tracker=scheduler_module.tracker_executor(
                root=args.archive_root or DEFAULT_ARCHIVES, dataset='dev',
                timeout=args.timeout, diagnostic_dirty=args.diagnostic_dirty,
                config_directory=home / 'candidates'))

    advisor = advisor_module.Advisor(
        {}, proposer_client=proposer_client, critic_client=critic_client,
        cache=llm.ResponseCache(state_module.ensure_home(args.session_dir) / 'analyses'),
        console=console, timeout_s=args.llm_timeout)

    session_path = args.resume or (state_module.ensure_home(args.session_dir) / 'session.json')
    try:
        summary = run_session(args, clock=clock, executor=executor,
                              session_path=session_path, console=console, advisor=advisor)
    except BaseException as exc:
        recovery = Path(session_path).resolve()
        failure = state_module.failure_record(exc, where='cli')
        print('Autotune failed: ' + failure['error_class'] + ': ' + failure['message'], file=sys.stderr)
        print('Recovery state: ' + str(recovery), file=sys.stderr)
        print('Resume: ' + subprocess.list2cmdline([sys.executable, str(Path(__file__).resolve()), '--resume', str(recovery)]), file=sys.stderr)
        if not recovery.exists():
            print('No checkpoint available; failure occurred before session initialization.', file=sys.stderr)
        holder = getattr(args, '_simulated_archives', None)
        if holder is not None:
            holder.cleanup()
        return 1
    print(json.dumps({**summary['counts_by_name'], **summary['llm_counters']}, indent=2))
    holder = getattr(args, '_simulated_archives', None)
    if holder is not None:
        holder.cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
