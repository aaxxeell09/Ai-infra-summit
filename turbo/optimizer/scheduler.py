"""The loop: keep hardware busy with valid work, and stop when it cannot be.

Two rules shape everything here. Exactly one hardware evaluation runs at a time,
because a second one would contend for the same NPU, CPU and memory bandwidth
while both archives still recorded clean provenance. Everything that is not
hardware (candidate generation, static validation, LLM calls, analysis) runs
while hardware is busy, because an idle device is the only cost that cannot be
recovered later.

The scheduler owns no measurement. It asks an injected executor to run a
candidate and records what comes back. In a dry run the executor is a simulator;
on the target machine it is the experiment tracker. That separation is what
makes the loop testable without a device, and it is also what keeps the tracker
the single authority on measured evidence.
"""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import grid, guard, probe, search_space as space, state as S

SCHEMA = 'local-turbo.autotune-scheduler.v1'

#: Raised out of the loop by Ctrl-C so the session can persist and print a
#: resume command instead of dying with a traceback halfway through a write.
class Interrupted(RuntimeError):
    pass


class HardwareBusy(RuntimeError):
    """A second hardware evaluation was requested while one was active."""


def _now(clock):
    return clock()


class Scheduler:
    """Bounded search loop over one backend, one control, one hardware slot."""

    def __init__(self, session, *, backend, budget, queue, executor, console,
                 owner_decisions=(), clock=time.monotonic, dry_run=False,
                 default_hardware_seconds=None, commissioning_path=None):
        self.state = session
        self.backend = backend
        self.budget = budget
        self.queue = queue
        self.executor = executor
        self.console = console
        self.owner_decisions = tuple(owner_decisions)
        self.clock = clock
        self.dry_run = dry_run
        # Before commissioning, no candidate carries a measured cost. Refusing
        # to start anything with an unknown cost would stall the whole loop, and
        # treating unknown as free would let a long job start with two minutes
        # left. So the session declares one default, it is recorded as a declared
        # default rather than an observation, and commissioning replaces it.
        from turbo.optimizer import hardware_queue as _queue_module
        self.default_hardware_seconds = (default_hardware_seconds
                                         if default_hardware_seconds is not None
                                         else _queue_module.DEFAULT_HARDWARE_SECONDS)
        session.setdefault('cost_model', {})['default_hardware_seconds'] = {
            'value': self.default_hardware_seconds, 'source': 'declared default, not measured'}
        from turbo.optimizer.commissioning import DEFAULT_PATH, load_costs
        control_config = (session.get('current_control') or {}).get('config') or {}
        self.commissioned_costs = {} if dry_run else load_costs(control_config, commissioning_path or DEFAULT_PATH)
        if (session.get('canary_sizes') or {}).get('S2') != 8:
            self.commissioned_costs.pop('S2', None)
        if self.commissioned_costs:
            session['cost_model']['commissioned_stage_reference_seconds'] = dict(self.commissioned_costs)
            session['cost_model']['commissioning_source'] = str(commissioning_path or DEFAULT_PATH)
            session['cost_model']['commissioning_scope'] = 'Measured control costs; candidate cost estimates, not candidate measurements'
        self._active = None
        self._interrupted = False
        self._last_mark = _now(clock)

    # ------------------------------------------------------------------ time

    def _mark(self, bucket):
        """Attribute elapsed wall time to one bucket, exactly once.

        Utilisation is only meaningful when busy and idle partition the session,
        so every interval is charged to exactly one bucket and no interval is
        charged twice.
        """
        now = _now(self.clock)
        elapsed = max(0.0, now - self._last_mark)
        self._last_mark = now
        self.state['timing'][bucket] = self.state['timing'].get(bucket, 0.0) + elapsed
        return elapsed

    # ------------------------------------------------------------ generation

    def generate(self, *, parameters=None, families=None, max_points=grid.DEFAULT_MAX_POINTS,
                 refine_around=None):
        """Produce candidates for the current control and count them honestly."""
        started = _now(self.clock)
        control = self.state['current_control']['config']
        if refine_around:
            candidates = grid.refine(control, self.backend, refine_around,
                                     index_start=self.state['counters']['generated'] + 1)
            rejections = []
        else:
            candidates, rejections = grid.bounded_grid(
                control, self.backend, parameters=parameters, families=families,
                max_points=max_points, index_start=self.state['counters']['generated'] + 1)
        self.state['counters']['generated'] += len(candidates)
        self.state['timing']['generation_s'] += _now(self.clock) - started
        for name, lane, status, evidence in rejections:
            self.console.warn('axis ' + name + ' excluded (' + status + ', lane ' + lane + ')')
        family = families[0] if families else (refine_around or 'grid')
        self.console.generated(str(family), len(candidates))
        return candidates

    # ---------------------------------------------------------------- guard

    def admit(self, candidates, *, lane=guard.QUALIFIED_LANE):
        """Static validation. Everything refused is recorded with its reasons."""
        started = _now(self.clock)
        control = self.state['current_control']['config']
        accepted, rejected = guard.admit(
            candidates, control_config=control, backend=self.backend,
            tested_exact=self.state['tested_exact'], owner_decisions=self.owner_decisions,
            energy_commissioned=self.state.get('energy_commissioned', False),
            split=self.state['split'], lane=lane)
        for candidate, reasons in rejected:
            S.record_rejection(self.state, candidate, reasons)
        unique = []
        seen = set()
        for candidate in accepted:
            if candidate['config_hash'] in seen:
                S.record_rejection(self.state, candidate, ['Duplicate within this batch'])
                continue
            seen.add(candidate['config_hash'])
            unique.append(candidate)
        self.state['counters']['unique'] += len(unique)
        self.state['timing']['static_validation_s'] += _now(self.clock) - started
        self.console.guard(str(lane), len(unique), len(rejected) + len(accepted) - len(unique))
        return unique

    # ------------------------------------------------------------- hardware

    def estimated_cost(self, candidate, stage=None):
        """Best available cost for this candidate, and whether it was measured."""
        declared = candidate.get('expected_hardware_seconds')
        if declared is not None:
            return declared, 'candidate estimate'
        reference = self.commissioned_costs.get(stage or candidate.get('stage'))
        if reference is not None:
            return reference, 'measured commissioning control reference; candidate estimate'
        return self.default_hardware_seconds, 'declared session default, not measured'

    def run_candidate(self, candidate, stage, *, estimated_seconds=None):
        """Run exactly one candidate on hardware, or refuse to start.

        A candidate is never started when the remaining budget cannot cover its
        estimated cost, and an unknown cost is not treated as a small one. The
        one exception is explicit: a caller that passes allow_unknown through
        the budget has decided to accept the risk.
        """
        if self._interrupted:
            raise Interrupted('Scheduling stopped by interrupt')
        if self._active is not None:
            raise HardwareBusy('A hardware evaluation is already active: ' + str(self._active))
        if estimated_seconds is None:
            estimated_seconds, _source = self.estimated_cost(candidate, stage)
        if not self.budget.can_start(estimated_seconds, allow_unknown=self.dry_run):
            self.console.warn('skipping ' + candidate['candidate_id']
                              + ': estimated cost does not fit the remaining budget')
            return None
        self._mark('hardware_idle_s')
        self._active = candidate['candidate_id']
        self.queue.claim(candidate)
        try:
            observation = self.executor(candidate, stage=stage)
        finally:
            self.queue.release(candidate)
            self._active = None
            spent = self._mark('hardware_busy_s')
        outcome = observation.get('outcome', 'unknown') if isinstance(observation, dict) else 'unknown'
        S.record_outcome(self.state, candidate, stage, outcome,
                         hardware_seconds=observation.get('hardware_seconds', spent)
                         if isinstance(observation, dict) else spent,
                         net_cases=observation.get('net_cases') if isinstance(observation, dict) else None)
        self.console.stage(stage, candidate['candidate_id'], str(outcome))
        return observation

    # ------------------------------------------------------------------ loop

    def drain(self, stage, *, limit=None):
        """Run queued candidates on hardware until the budget or queue ends."""
        observations = []
        while len(self.queue) and (limit is None or len(observations) < limit):
            if self.budget.exhausted or self._interrupted:
                break
            candidate = self.queue.pop()
            observation = self.run_candidate(candidate, stage)
            if observation is None:
                break
            observations.append((candidate, observation))
        return observations

    def enqueue(self, candidates, *, phase=None, family_stats=None, priority=None):
        """Place admitted candidates in the hardware queue with a priority."""
        from turbo.optimizer import hardware_queue
        for candidate in candidates:
            score = (priority(candidate) if callable(priority)
                     else hardware_queue.priority(candidate,
                                                  family_stats=family_stats or self.state['families'],
                                                  phase=phase or self.budget.phase()))
            candidate['priority'] = score
            self.queue.push(candidate, score)
        return len(candidates)

    # ------------------------------------------------------------- lifecycle

    def install_interrupt_handler(self):
        """Turn Ctrl-C into an orderly stop rather than a half-written state."""
        def handler(signum, frame):
            self._interrupted = True
            self.console.warn('interrupt received; finishing the active evaluation and saving')
        try:
            signal.signal(signal.SIGINT, handler)
        except ValueError:
            # Not on the main thread; the caller keeps its own handling.
            pass
        return self

    @property
    def interrupted(self):
        return self._interrupted

    def finish(self, path):
        """Persist the session and return the command that resumes it."""
        self._mark('hardware_idle_s')
        self.state['elapsed_seconds'] = self.budget.elapsed_s
        S.save(self.state, path)
        return ('python scripts/autotune.py --resume ' + str(path))

    def counts(self):
        """The five counts a report must keep distinct."""
        counters = self.state['counters']
        hardware = sum(counters.get(stage, 0) for stage in ('S1', 'S2', 'S3', 'S4', 'S5'))
        return {'GENERATED_CANDIDATES': counters['generated'],
                'STATICALLY_VALID_CANDIDATES': counters['unique'],
                'DIAGNOSTIC_CANDIDATES': counters.get('S2', 0),
                'HARDWARE_ATTEMPTS': hardware,
                'QUALIFIED_EXPERIMENTS': counters.get('qualified_experiments', 0)}


def tracker_executor(*, root, dataset='dev', timeout=600, diagnostic_dirty=False,
                     config_directory=None, runner=None, verify_archive=True):
    """Executor that runs a candidate through the real experiment tracker.

    Every hardware evaluation becomes an ordinary archive: TurboLab adds no
    competing record, and it never writes into an existing one. The candidate's
    config is materialised beside the session so the archive captures the exact
    bytes that were run.

    What comes back is not the tracker's return value dressed up. The archive is
    re-read through turbo/optimizer/observation.py, read only, so the funnel
    compares the evidence that was actually sealed rather than whatever this
    process happened to hold in memory.
    """
    import json
    from turbo.experiments import run as tracker_run
    from turbo.optimizer import observation as observation_module

    directory = Path(config_directory) if config_directory else S.DEFAULT_HOME / 'candidates'
    execute = runner or tracker_run

    def executor(candidate, *, stage):
        directory.mkdir(parents=True, exist_ok=True)
        config_path = directory / (candidate['candidate_id'] + '.json')
        payload = json.dumps(candidate['config'], indent=2, ensure_ascii=False,
                             allow_nan=False) + '\n'
        if config_path.exists() and config_path.read_text(encoding='utf-8') != payload:
            raise ValueError('Refusing to overwrite a different config for '
                             + candidate['candidate_id'])
        config_path.write_text(payload, encoding='utf-8', newline='\n')
        started = time.monotonic()
        archive = execute(candidate['candidate_id'], config_path, root=root, dataset=dataset,
                          change=candidate['treatment'], hypothesis=candidate['hypothesis'],
                          control=candidate.get('control_experiment_id'),
                          diagnostic_dirty=diagnostic_dirty, timeout=timeout)
        elapsed = round(time.monotonic() - started, 3)
        return observation_module.from_archive(archive, stage=stage, hardware_seconds=elapsed,
                                               verify_archive=verify_archive)

    return executor


def startup_probe_executor(*, repo=ROOT, python=None, timeout_s=180,
                           config_directory=None, runner=None):
    """S1: prove the configuration loads and answers once. Nothing more.

    It runs the existing bounded smoke helper, which performs a single short
    generation through the same native layer the evaluator uses. That answers
    the only question S1 asks. It writes no archive and makes no benchmark
    claim, and the record says so, because a liveness result that drifted into a
    report as a score would be the worst kind of number: cheap, plausible and
    about nothing.
    """
    import json
    import sys as _sys

    directory = Path(config_directory) if config_directory else S.DEFAULT_HOME / 'candidates'
    interpreter = python or _sys.executable

    def executor(candidate, *, stage):
        from turbo.optimizer import probe
        refusals = probe.config_acceptable(candidate['config'], candidate['config'].get('backend'))
        if refusals:
            return dict(probe.startup_observation(loaded=False, outcome=probe.REFUSED,
                                                  runtime_error='; '.join(refusals),
                                                  detail='Refused before launch by the static '
                                                         'pre-check that mirrors the runner'),
                        stage=stage, simulated=False, hardware_seconds=0.0, archive=None,
                        qualified=False, promotion_evidence=False)
        directory.mkdir(parents=True, exist_ok=True)
        config_path = directory / (candidate['candidate_id'] + '.json')
        payload = json.dumps(candidate['config'], indent=2, ensure_ascii=False,
                             allow_nan=False) + '\n'
        if not config_path.exists():
            config_path.write_text(payload, encoding='utf-8', newline='\n')
        command = [interpreter, '-X', 'utf8', str(Path(repo) / 'scripts/backend_smoke.py'),
                   '--config', str(config_path)]
        record = probe.run_startup_probe(command, timeout_s=timeout_s, cwd=str(repo),
                                         runner=runner)
        record.update(stage=stage, simulated=False, archive=None, qualified=False,
                      promotion_evidence=False,
                      hardware_seconds=record.get('startup_seconds') or 0.0,
                      outcome='survive' if record['outcome'] == probe.LOADED else record['outcome'])
        return record

    return executor


def canary_executor(*, repo=ROOT, python=None, seed_label, sizes, output_directory,
                    timeout_s=900, config_directory=None, runner=None):
    """S2 and S3: a fixed development subset, labelled, elimination only.

    ``sizes`` maps a stage to its subset size. A stage with no size declared is
    explicitly skipped, never silently widened to the full development set:
    running 35 cases while the log says S2 would make a cheap stage expensive
    and an expensive comparison look cheap, and nobody reading the session would
    know which had happened.
    """
    import json
    import subprocess as _subprocess
    import sys as _sys

    directory = Path(config_directory) if config_directory else S.DEFAULT_HOME / 'candidates'
    interpreter = python or _sys.executable
    outputs = Path(output_directory)
    execute = runner or _subprocess.run

    def executor(candidate, *, stage):
        size = (sizes or {}).get(stage)
        if not size:
            return {'outcome': 'skipped', 'stage': stage, 'simulated': False, 'archive': None,
                    'qualified': False, 'promotion_evidence': False, 'hardware_seconds': 0.0,
                    'skip_reason': 'No diagnostic subset size is declared for ' + stage
                                   + ', and widening it to the full development set would '
                                     'misreport a cheap stage as an expensive one'}
        directory.mkdir(parents=True, exist_ok=True)
        outputs.mkdir(parents=True, exist_ok=True)
        config_path = directory / (candidate['candidate_id'] + '.json')
        if not config_path.exists():
            config_path.write_text(json.dumps(candidate['config'], indent=2, ensure_ascii=False,
                                              allow_nan=False) + '\n',
                                   encoding='utf-8', newline='\n')
        output = outputs / (candidate['candidate_id'] + '-' + stage + '.json')
        command = [interpreter, '-X', 'utf8', str(Path(repo) / 'scripts/diagnostic_canary.py'),
                   '--config', str(config_path), '--size', str(size),
                   '--seed-label', str(seed_label), '--output', str(output)]
        started = time.monotonic()
        try:
            completed = execute(command, cwd=str(repo), timeout=timeout_s,
                                capture_output=True, text=True)
        except _subprocess.TimeoutExpired:
            return {'outcome': 'timed_out', 'stage': stage, 'simulated': False, 'archive': None,
                    'qualified': False, 'promotion_evidence': False, 'hardware_seconds': None,
                    'detail': 'Canary exceeded ' + str(timeout_s) + ' s'}
        elapsed = round(time.monotonic() - started, 3)
        if completed.returncode != 0 or not output.is_file():
            return {'outcome': 'failed', 'stage': stage, 'simulated': False, 'archive': None,
                    'qualified': False, 'promotion_evidence': False, 'hardware_seconds': elapsed,
                    'runtime_error': (completed.stderr or '').strip()[-2000:] or None}
        from turbo.json_io import read_json
        record = read_json(output, require_object=True)
        record.update(stage=stage, simulated=False, archive=None, hardware_seconds=elapsed,
                      outcome='survive')
        return record

    return executor


def simulated_archive_executor(root, *, inner):
    """Wrap a simulated stage result in a real sealed archive, then read it back.

    This exists so a dry run exercises the archive observation adapter rather
    than handing the funnel a dictionary that the real path would never produce.
    The archive is written through the tracker's own writers, sealed, verified
    and read back through turbo/optimizer/observation.py, which is exactly the
    sequence a tracked run performs.

    ``root`` must be a throwaway directory. These archives describe nothing that
    was measured, so leaving them beside real evidence would be creating fake
    evidence; the caller owns a temporary directory and discards it.
    """
    import json as _json
    from turbo.experiments import finish as _finish, initialize as _initialize, reserve as _reserve
    from turbo.optimizer import observation as observation_module

    root = Path(root)

    def executor(candidate, *, stage):
        simulated = inner(candidate, stage=stage)
        rows = simulated.get('rows')
        if not rows:
            return simulated
        path = _reserve(root, 'simulated-' + candidate['candidate_id'] + '-' + stage)
        _initialize(path, {'name': path.name, 'command': ['simulated'],
                           'environment': {'system': 'simulated'}},
                    config_bytes=_json.dumps(candidate['config']).encode('utf-8'))
        report = {'schema_version': 2, 'status': 'measured',
                  'benchmark_version': 'secretary-eval-v2',
                  'results': [{'case_id': row['case_id'], 'task_success': row['task_success'],
                               'invalid_output': index < simulated.get('invalid', 0),
                               'expected_tool': 'move_file',
                               'failure_reasons': [] if row['task_success'] else ['WRONG_ACTION'],
                               'latency_ms': simulated.get('median_task_latency_ms'),
                               'warm_task_latency_ms': simulated.get('median_task_latency_ms'),
                               'profile': {'generated_tokens': 20}}
                              for index, row in enumerate(rows)]}
        manifest = _json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        _finish(path, dict(manifest), result=report, status='completed_diagnostic')
        record = observation_module.from_archive(path, stage=stage,
                                                 hardware_seconds=simulated['hardware_seconds'])
        record.update(simulated=True, outcome=simulated.get('outcome', record['outcome']),
                      note='Simulated shape from --dry-run, sealed into a throwaway archive so '
                           'the observation adapter is exercised. Not a measurement.')
        return record

    return executor


def staged_executor(*, probe=None, canary=None, tracker=None):
    """Route each stage to the executor that is allowed to answer it.

    S1 is liveness, S2 and S3 are labelled diagnostics, S4 and S5 are tracked
    measurements. One executor for every stage, as an earlier version had, meant
    the real path ran the full development set five times and called the first
    three of them cheap.
    """
    routes = {'S1': probe, 'S2': canary, 'S3': canary, 'S4': tracker, 'S5': tracker}

    def executor(candidate, *, stage):
        route = routes.get(stage)
        if route is None:
            return {'outcome': 'skipped', 'stage': stage, 'simulated': False, 'archive': None,
                    'qualified': False, 'promotion_evidence': False, 'hardware_seconds': 0.0,
                    'skip_reason': 'No executor is configured for ' + stage}
        return route(candidate, stage=stage)

    return executor


def simulated_executor(*, latency_model, rng=None, effect_model=None):
    """Executor for --dry-run: no hardware, no API, no archive.

    It advances a virtual clock and returns observations shaped exactly like the
    real ones, so the funnel, the budget arithmetic and the stage rules are all
    genuinely exercised. Every record is stamped ``simulated=True`` and carries
    an explicit note, because a plausible number is the easiest thing in this
    system to mistake for a measurement. Nothing it produces may be reported,
    compared or archived as evidence.

    The effect model is a deterministic function of the candidate's config hash,
    not a random draw: a dry run that gave different answers on each invocation
    could not be used to test the loop's decisions.
    """
    import hashlib

    def _unit(candidate, salt):
        seed = hashlib.sha256((candidate['config_hash'] + '|' + salt).encode('utf-8')).digest()
        return int.from_bytes(seed[:4], 'big') / 0xFFFFFFFF

    def default_effect(candidate, stage, attempted):
        correct = int(round(attempted * (0.45 + 0.35 * _unit(candidate, 'accuracy'))))
        invalid = int(round(attempted * 0.15 * _unit(candidate, 'invalid')))
        latency = 400.0 + 900.0 * _unit(candidate, 'latency')
        return correct, invalid, round(latency, 3)

    effect = effect_model or default_effect
    attempted_by_stage = {'S1': 0, 'S2': 8, 'S3': 18, 'S4': 35, 'S5': 35}

    def executor(candidate, *, stage):
        seconds = latency_model(candidate, stage)
        record = {'outcome': 'completed', 'hardware_seconds': seconds, 'stage': stage,
                  'simulated': True, 'archive': None, 'net_cases': None,
                  'note': 'Simulated shape from --dry-run. Not a measurement and never '
                          'comparable with a tracked result.'}
        if stage == 'S1':
            record.update(loaded=True, exit_code=0, runtime_error=None,
                          startup_seconds=round(seconds, 3), outcome='survive')
            return record
        attempted = attempted_by_stage.get(stage, 0)
        correct, invalid, latency = effect(candidate, stage, attempted)
        # Per-case rows, not just a total, because the stage rules compare cases
        # and a total cannot tell an improvement from an equal-sized trade.
        rows, remaining = [], correct
        for index in range(attempted):
            success = _unit(candidate, stage + '|case|' + str(index)) < (correct / attempted
                                                                        if attempted else 0)
            rows.append({'case_id': 'dev-%02d' % index, 'task_success': bool(success)})
        observed = sum(1 for row in rows if row['task_success'])
        record.update(attempted=attempted, correct=observed, invalid=invalid,
                      invalid_rate=round(invalid / attempted, 6) if attempted else None,
                      median_task_latency_ms=latency, median_latency_ms=latency,
                      latency_boundary='simulated: no boundary was measured', rows=rows,
                      latency_gate_ok=True, deterministic_output=False,
                      outcome='survive')
        return record

    return executor
