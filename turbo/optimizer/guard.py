"""Fail-closed admission control for autotune candidates.

Every rule here answers one question: could accepting this candidate produce a
measurement that is wrong, incomparable or forbidden? A candidate is admitted
only when no rule objects. Silence is never permission: an unrecognised control,
an unreadable config or an undecided owner question all produce a reason.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import search_space as space

SCHEMA = 'local-turbo.autotune-guard.v1'

#: Repository paths whose bytes define the frozen benchmark. A candidate that
#: proposes touching any of these is rejected outright; changing them is an
#: owner-approved versioning decision, never a tuning step.
FROZEN_PATHS = (
    'eval/datasets/secretary_dev.json',
    'eval/datasets/secretary_heldout.json',
    'eval/benchmark_manifest.json',
    'eval/fixtures/files.json',
    'eval/scoring.py',
    'eval/secretary_adapter.py',
    'eval/validate_dataset.py',
    'eval/run_secretary_eval.py',
    'eval/quality_policy.json',
    'eval/decision_policy.json',
    'eval/decision_table.py',
    'eval/energy_measurement.py',
    'eval/report_validation.py',
    'benchmarks/secretary_tasks.json',
    'turbo/service.py',
    'turbo/secretary.py',
)

#: Directories whose existing contents are historical evidence.
PROTECTED_TREES = ('eval/results', 'benchmarks/results', 'local/experiments')

#: The only configuration fields a V1 candidate may change. This is an explicit
#: allowlist rather than a denylist: a key nobody has reasoned about must not
#: become a treatment because it happened to be absent from a denylist.
V1_MUTABLE_KEYS = ('max_tokens', 'stop_after_tool_call', 'threads', 'threads_batch',
                   'n_batch', 'ubatch', 'context', 'spec_type')

#: Splits an optimization loop may execute against. Heldout is absent by design.
SEARCH_SPLITS = ('development',)

#: Owner decisions whose absence makes a dependent operation fail closed.
#: Values are the TRK finding and what the operation would otherwise assume.
OWNER_DECISIONS = {
    'campaign_plan_binding': 'TRK-003: a campaign report cannot yet state planned versus completed runs',
    'generation_protocol_binding': 'TRK-005: a report whose generation_protocol contradicts its config still qualifies',
    'mandatory_counter_resolution': 'TRK-006: full-process energy can be captured with no declared counter resolution',
}


def _config_errors(config):
    if not isinstance(config, dict) or not config:
        return ['Config must be a nonempty JSON object']
    errors = []
    unknown = sorted(set(config) - set(space.RUNNER_ALLOWED_KEYS))
    if unknown:
        errors.append('Config keys the frozen runner rejects: ' + ', '.join(unknown))
    if config.get('grammar'):
        errors.append('grammar is refused by the frozen runner')
    return errors


def changed_fields(control_config, candidate_config):
    """Top-level keys whose value or presence differs. Arrays are one field."""
    changed = []
    for key in sorted(set(control_config) | set(candidate_config)):
        if key not in control_config or key not in candidate_config:
            changed.append(key)
        elif (control_config[key] != candidate_config[key]
              or type(control_config[key]) is not type(candidate_config[key])):
            changed.append(key)
    return changed


QUALIFIED_LANE = 'qualified'
DIAGNOSTIC_LANE = 'diagnostic'
LANES = (QUALIFIED_LANE, DIAGNOSTIC_LANE)


def check(candidate, *, control_config, backend, tested_exact=(), owner_decisions=(),
          energy_commissioned=False, split='development', paths_touched=(),
          lane=QUALIFIED_LANE):
    """Return every reason this candidate must not run. Empty means admitted.

    ``tested_exact`` holds config hashes already measured; ``owner_decisions``
    names the decisions the operator has implemented. Both default to the
    conservative empty case.

    ``lane`` selects the admission standard. The qualified lane is the only one
    that may produce a tracker experiment, and it admits a control only when the
    search-space registry marks it supported on this backend. The diagnostic
    lane is looser about that one point and about nothing else: frozen files,
    heldout cases, multi-variable mutations and energy claims are refused in
    both. A Lane C research item is refused in both, because planning it is a
    document, not a run.
    """
    reasons = []
    if not isinstance(candidate, dict):
        return ['Candidate must be an object']
    if lane not in LANES:
        return ['Unknown admission lane: ' + repr(lane)]
    research = candidate.get('lane_c_item')
    if research:
        from turbo.optimizer import lane_c
        try:
            return [lane_c.refuse_qualified(research)]
        except ValueError as exc:
            return [str(exc)]

    if split not in SEARCH_SPLITS:
        reasons.append('Split ' + repr(split) + ' may not be used for optimization search')

    declared_split = candidate.get('split', split)
    if declared_split not in SEARCH_SPLITS:
        reasons.append('Candidate declares forbidden split ' + repr(declared_split))
    if candidate.get('dataset') in ('all', 'heldout'):
        reasons.append('Candidate requests a dataset containing heldout cases')

    for path in paths_touched:
        posix = Path(path).as_posix()
        if posix in FROZEN_PATHS:
            reasons.append('Candidate would modify frozen evaluation file: ' + posix)
        elif any(posix == tree or posix.startswith(tree + '/') for tree in PROTECTED_TREES):
            reasons.append('Candidate would modify retained evidence: ' + posix)

    config = candidate.get('config')
    reasons.extend(_config_errors(config))
    if not isinstance(control_config, dict) or not control_config:
        reasons.append('Control config must be a nonempty JSON object')
    if reasons:
        return reasons

    changed = changed_fields(control_config, config)
    integration = bool(candidate.get('integration_test'))
    if not changed:
        reasons.append('Candidate is identical to the control')
    elif len(changed) > 1 and not integration:
        # campaign_plan.plan refuses this too; catching it here keeps the
        # rejection interpretable instead of surfacing as a planner traceback.
        reasons.append('Hidden multi-variable mutation: ' + ', '.join(changed))
    elif len(changed) > 1:
        # A bounded grid point changes several fields at once. That is a
        # legitimate integration configuration, but it can never carry causal
        # attribution to one variable, so it must say so about itself and it
        # must declare every field it moves.
        declared = candidate.get('variables')
        if not isinstance(declared, (list, tuple)) or sorted(declared) != sorted(changed):
            reasons.append('Integration candidate must declare every changed field; changed '
                           + ', '.join(changed))
        if candidate.get('causal_attribution') is not False:
            reasons.append('Integration candidate must record causal_attribution=False')
        for field in changed:
            if field not in V1_MUTABLE_KEYS:
                reasons.append(field + ' is outside the V1 mutable allowlist')
            elif lane == QUALIFIED_LANE:
                reasons.extend(space.value_errors(field, config[field], backend))
    else:
        field = changed[0]
        declared = candidate.get('variable')
        if declared is not None and declared != field:
            reasons.append('Declared variable ' + repr(declared) + ' does not match changed field ' + repr(field))
        if field not in V1_MUTABLE_KEYS:
            reasons.append(field + ' is outside the V1 mutable allowlist')
        elif lane == QUALIFIED_LANE:
            reasons.extend(space.value_errors(field, config[field], backend))
        else:
            # The diagnostic lane still refuses a value outside the declared
            # enumeration: a probe on an undeclared value is uninterpretable
            # whichever lane it runs in.
            spec = space.parameter(field)
            allowed = spec['allowed_values']
            if allowed is not None and not any(config[field] is option
                                               or config[field] == option
                                               and type(config[field]) is type(option)
                                               for option in allowed):
                reasons.append(field + ': value ' + repr(config[field])
                               + ' is outside the declared enumeration')
            if spec['support_status'] == space.UNSUPPORTED:
                reasons.append(field + ': unsupported control (' + spec['evidence'] + ')')

    if config.get('backend') not in (None, backend):
        reasons.append('Candidate backend contradicts the session backend')

    digest = candidate.get('config_hash')
    if not isinstance(digest, str) or not digest:
        reasons.append('Candidate carries no config hash')
    elif digest in tested_exact:
        reasons.append('Exact treatment already measured: ' + digest)

    if candidate.get('optimize_energy'):
        if not energy_commissioned:
            reasons.append('Energy optimization requested before energy commissioning passed')
    if candidate.get('objective') in ('j_per_correct_task', 'energy') and not energy_commissioned:
        reasons.append('Energy objective requested before energy commissioning passed')

    for key in candidate.get('requires_owner_decision', ()):
        if key not in owner_decisions:
            reasons.append('Blocked on owner decision ' + key + ' (' + OWNER_DECISIONS.get(key, 'undocumented') + ')')

    if candidate.get('changes_measurement_boundary'):
        reasons.append('Candidate changes a measurement boundary')

    hypothesis = candidate.get('hypothesis')
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        reasons.append('Candidate carries no hypothesis')

    return reasons


def admit(candidates, **context):
    """Split candidates into (accepted, [(candidate, reasons), ...])."""
    accepted, rejected = [], []
    for candidate in candidates:
        reasons = check(candidate, **context)
        if reasons:
            rejected.append((candidate, reasons))
        else:
            accepted.append(candidate)
    return accepted, rejected
