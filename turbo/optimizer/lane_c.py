"""Lane C: research items the current frozen contract cannot express.

Nothing here may enter a qualified experiment. The register exists so that a
good question does not quietly disappear because today's runner cannot ask it.
The QAIRT sampler question is the clearest example: the repository records that
a requested temperature of zero does not establish greedy decoding, while the
bundle declares its own sampler values, and no configuration path exists to
override them. That is an open research question, not a closed one.

Each item states what capability is missing, the smallest safe extension, which
files would change, whether benchmark semantics move, and how it would be
validated. Those five answers are what an owner needs in order to decide, so an
item without them is incomplete by construction.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import digest

SCHEMA = 'local-turbo.autotune-lane-c.v1'

#: Whether acting on the item would move what the benchmark measures, or only
#: expose an inference control that was always there.
SEMANTICS_UNCHANGED = 'exposes_an_inference_control_only'
SEMANTICS_CHANGED = 'changes_benchmark_semantics'
SEMANTICS_UNDETERMINED = 'undetermined_pending_inspection'


def _item(key, *, title, why, missing_capability, smallest_extension, files_touched,
          semantics, validation, priority, blocked_by=()):
    return {'key': key, 'title': title, 'why': why,
            'missing_capability': missing_capability,
            'smallest_safe_extension': smallest_extension,
            'files_that_would_change': tuple(files_touched),
            'benchmark_semantics': semantics,
            'experimental_validation': validation,
            'priority': priority,
            'blocked_by': tuple(blocked_by),
            'qualified_search_allowed': False}


RESEARCH_ITEMS = {
    'QAIRT_EXPLICIT_SAMPLER_CONTROL': _item(
        'QAIRT_EXPLICIT_SAMPLER_CONTROL',
        title='Explicit QAIRT sampler control (top_k, top_p, temperature, seed)',
        why='docs/qairt-sampling.md records that the pinned QAIRT adapter treats a requested '
            'temperature of zero as a sentinel that defers to the bundle, and that the artifact '
            'we used declares temperature 0.8 and top-k 40. Every QAIRT result therefore ran under '
            'an unrecorded effective sampler, while the llama.cpp comparison ran with seed -1. '
            'The two are not sampled alike, so part of the QAIRT versus llama.cpp gap may be '
            'sampling rather than backend. Nothing in the repository settles this.',
        missing_capability='No path carries a sampler value from the evaluation config to the '
                           'native sampler. eval/run_secretary_eval.py rejects any key outside its '
                           'allowed set, so top_k, top_p, temperature and seed cannot even be '
                           'written in a config file, and turbo/native.py exposes the sampler '
                           'struct fields but the runner never populates them from config.',
        smallest_extension='A versioned runner contract (not an in-place edit of v2) that accepts '
                           'an optional sampler object, records requested and effective values in '
                           'the report, and refuses to run when the effective values cannot be '
                           'read back from the runtime. Requested values that the plugin silently '
                           'overrides must surface as a contradiction, not as a success.',
        files_touched=('eval/run_secretary_eval.py', 'turbo/native.py',
                       'eval/benchmark_manifest.json (new protocol version only)',
                       'docs/qairt-sampling.md'),
        semantics=SEMANTICS_UNCHANGED,
        validation='Run the same development case at least five times per sampler setting on the '
                   'target device and compare raw output text, tool, arguments, token count and '
                   'latency. Greedy decoding is established only when repeated outputs are '
                   'byte-identical; a single matching pair proves nothing. Then compare an '
                   'explicit greedy QAIRT treatment against the current default in a balanced '
                   'campaign with three blocks per treatment.',
        priority='first Lane C item to review after TurboLab V1',
        blocked_by=('owner decision 6: any candidate requiring a frozen runner change needs a new '
                    'explicit protocol',)),

    'QAIRT_ACTION_GRAMMAR': _item(
        'QAIRT_ACTION_GRAMMAR',
        title='Constrained decoding for the production action schema',
        why='13 of 17 invalid QAIRT outputs recorded in the audit were structural. A grammar that '
            'forces a single well-formed tool call would address the failure class directly.',
        missing_capability='eval/run_secretary_eval.py rejects a truthy grammar key outright: '
                           '"ToolWire grammar is not valid for the production Secretary tool '
                           'contract". The pinned adapter does forward inline grammar, but no '
                           'repository evidence shows the installed binary enforcing it.',
        smallest_extension='A deliberately restrictive canary on hardware first, to prove the '
                           'installed binary enforces a grammar at all, then a versioned protocol '
                           'that pairs the grammar with the frozen action schema hash.',
        files_touched=('eval/run_secretary_eval.py', 'turbo/native.py', 'docs/qairt-sampling.md'),
        semantics=SEMANTICS_UNDETERMINED,
        validation='Restrictive canary that must fail in a specific, predicted way if the grammar '
                   'is enforced, before any comparison run.',
        priority='after QAIRT_EXPLICIT_SAMPLER_CONTROL',
        blocked_by=('owner decision 6',)),

    'DIAGNOSTIC_CANARY_SUBSET': _item(
        'DIAGNOSTIC_CANARY_SUBSET',
        title='Small fixed development subsets for cheap elimination',
        why='A funnel needs a cheap elimination stage. The frozen runner exposes development, '
            'heldout and all; there is no supported way to ask for eight cases.',
        missing_capability='eval/run_secretary_eval.py resolves the split to whole dataset files. '
                           'A subset is not expressible, and scripts/experiment_tracker.py only '
                           'passes dev or all.',
        smallest_extension='A separate diagnostic probe that loads development cases only, writes '
                           'a clearly labelled DIAGNOSTIC_CANARY report, and is structurally '
                           'incapable of producing a qualified archive. The frozen runner is not '
                           'touched. The subset must be fixed before a session starts and never '
                           'adapted to favour a candidate.',
        files_touched=('a new diagnostic module under turbo/optimizer/',),
        semantics=SEMANTICS_UNCHANGED,
        validation='Its own agreement with full dev35 must be measured before it is trusted even '
                   'as an eliminator: record how often a canary drop would have discarded a '
                   'candidate that dev35 later rated favourably.',
        priority='optional for V1; startup probes plus dev35 are sufficient to launch',
        blocked_by=()),

    'FROZEN_PROMPT_AND_SCHEMA': _item(
        'FROZEN_PROMPT_AND_SCHEMA',
        title='Prompt and action-schema variants',
        why='Prompt wording is a plausible lever on structured-output validity.',
        missing_capability='The system prompt and action schema are covered by frozen hashes '
                           '(system_prompt_sha256, action_schema_sha256) that the tracker '
                           'revalidates on every run. Changing either invalidates provenance '
                           'identity with every historical result.',
        smallest_extension='A new benchmark version with its own hashes, run as a separate '
                           'protocol, never presented as identical to v2.',
        files_touched=('eval/secretary_adapter.py', 'eval/benchmark_manifest.json',
                       'eval/validate_dataset.py'),
        semantics=SEMANTICS_CHANGED,
        validation='Full 50-case milestone under the new version, with the old version kept '
                   'runnable for comparison.',
        priority='owner decision 6 governs this entirely',
        blocked_by=('owner decision 6',)),

    'DETERMINISTIC_ACTION_ROUTER': _item(
        'DETERMINISTIC_ACTION_ROUTER',
        title='Deterministic routing ahead of the model',
        why='Some cases may be answerable without inference at all, which would move both latency '
            'and energy per correct task.',
        missing_capability='turbo/secretary_proposal.py exists but is disabled by default, '
                           'executes nothing and has only synthetic test evidence.',
        smallest_extension='Keep it disabled inside the evaluation path. Any router that answers '
                           'a benchmark case changes what the benchmark measures, so it needs its '
                           'own protocol and its own reporting, not a config flag.',
        files_touched=('turbo/secretary_proposal.py', 'turbo/router.py',
                       'eval/run_secretary_eval.py'),
        semantics=SEMANTICS_CHANGED,
        validation='Must report how many cases bypassed inference, separately, before any latency '
                   'or energy claim.',
        priority='not before TurboLab V2',
        blocked_by=('owner decision 6',)),

    'CODE_PATCH_CANDIDATES': _item(
        'CODE_PATCH_CANDIDATES',
        title='Model-proposed Python patches as candidates',
        why='Configuration space is small on QAIRT; code changes are the larger lever.',
        missing_capability='No sandbox, no restricted file set, no patch archive and no rollback '
                           'path exists in this repository today.',
        smallest_extension='A dedicated git worktree, an explicit allowlist of editable files, '
                           'unit tests as a gate, a static diff review, the exact patch archived '
                           'with the experiment, and an unconditional rollback afterwards.',
        files_touched=('a new patch harness under turbo/optimizer/',),
        semantics=SEMANTICS_UNDETERMINED,
        validation='A patch that touches any frozen path is refused before it is applied, not '
                   'after it is evaluated.',
        priority='explicitly V2; out of scope for the first implementation',
        blocked_by=()),
}


def item(key):
    """Return one research item, or raise. There is no implicit empty item."""
    try:
        return RESEARCH_ITEMS[key]
    except KeyError:
        raise ValueError('Unknown Lane C research item: ' + str(key)) from None


def registry():
    """The whole register with a provenance hash, safe to serialise."""
    value = {'schema_version': SCHEMA,
             'items': {key: {k: (list(v) if isinstance(v, tuple) else v)
                             for k, v in record.items()}
                       for key, record in RESEARCH_ITEMS.items()}}
    value['registry_sha256'] = digest(value)
    return value


def refuse_qualified(key):
    """Reason a Lane C item may never reach a qualified experiment."""
    record = item(key)
    return (key + ' is Lane C (' + record['title'] + '): ' + record['missing_capability']
            + ' Qualified search is not permitted for it.')
