# Standalone explicit-action proposal candidate

**Status: opt-in diagnostic candidate, not integrated into the application or
frozen evaluator. No quality, latency, token-throughput, or energy benefit has
been measured.**

## Why this is separate from existing routing

`turbo/router.py` ranks measured small/large model profiles and can execute
serial model fallbacks. `turbo/policy.py` chooses a measured runtime profile using
context, quality tier, and estimated latency or decode rate. Neither module maps
an explicit file command directly to a Secretary action. The candidate in
`turbo/secretary_proposal.py` is therefore a separate experiment, not a replacement
for either router.

The justification for a small deterministic candidate is narrow: an entire
request sometimes already gives the action and every argument explicitly.
Recognizing a small exact grammar allows the project to investigate such cases
without guessing missing information. That is a testable hypothesis, not proof
that bypassing model generation improves the final system.

## Interface and supported grammar

```python
from turbo.secretary_proposal import propose

result = propose(
    'Read "samples/alpha.txt".',
    ['samples/alpha.txt'],
    enabled=True,
)
# status is "proposal" or "abstain". Nothing is executed.
```

The default is disabled; only `enabled=True` enables proposals. The function
returns a version label, reason, `executed=False`, `quality_validated=False`, and
either an explicit `{name, arguments}` proposal or `action=None`.

Supported complete English commands:

- `List files`, `List all files`, or `List every file`, optionally ending with
  `in the workspace`.
- `Read "relative/path.txt"` or `Read the file "relative/path.txt"`.
- `Move "source/path.txt" to "destination/path.txt"`.
- `Search files for "literal text"` or `Search for literal "literal text"`.

A leading `Please` and a final period are optional. Command words are
case-insensitive; argument spelling and path case are preserved exactly.
Arguments use double quotes. Unsupported paraphrases deliberately abstain.

The CLI is equally diagnostic:

```sh
python scripts/propose_secretary_action.py \
  --prompt 'Read "samples/alpha.txt".' \
  --inventory local/synthetic-inventory.json \
  --enable-candidate
```

Without the opt-in flag it abstains. The CLI prints a proposal; it never executes
one, calls a model, or reads the contents of inventory files.

## Conservative boundaries

The recognizer requires a complete grammar match. Negation, compound commands,
conditions, hypothetical questions, quoted examples, additional constraints,
and incomplete arguments fall back through abstention. Words such as “and” or
“do not” inside an explicitly quoted search literal remain literal search text.
There is no learned intent classifier and no benchmark-specific exception.

Paths use a narrow portable ASCII whitelist. Absolute paths, traversal,
backslashes, colons/alternate streams, wildcards, reserved Windows device names,
trailing-dot/space components, and unfamiliar spellings abstain. Source paths
must exactly match the provided file inventory. Existing destinations,
case-colliding names, known directories, and destinations whose parent is a
known file abstain. Move destinations need an explicit filename with an
extension; the candidate never infers a basename or folder intent.

These rules intentionally produce false negatives, including valid Unicode
paths, single-quoted paths, filenames without extensions as move destinations,
and ordinary natural-language paraphrases. That is preferable for this bounded
experiment to silently broadening intent inference.

Inventory strings cannot prove real filesystem containment. A future consumer
must independently validate the current filesystem, symlinks/junctions and
atomic overwrite behavior at execution time. This candidate is not authorization
to execute a move and is not a safety boundary.

## Evidence and required validation

Tests in `tests/test_secretary_proposal.py` use synthetic instructions and names.
They cover supported paraphrases, adversarial false positives, intentional false
negatives, negation/compound requests, inventory ambiguity, path hazards, and
explicit opt-in. They demonstrate rule behavior, not real-world action accuracy.
No dataset IDs, golden answers, development prompts, or heldout prompts are used.

Before any integration:

1. Review a separately versioned workflow contract and define fallback behavior.
   Keep the existing frozen evaluation path unchanged.
2. Evaluate proposal precision and coverage on independently prepared synthetic
   and development diagnostics. Keep abstentions, incorrect proposals, and all
   fallback attempts visible. Do not use heldout feedback to tune rules.
3. Run baseline and candidate through the same approved action validation and
   isolated execution protocol. Do not change golden answers or forgive multiple
   actions to improve candidate results.
4. Measure complete tasks on the Snapdragon, including proposal cost, model
   fallback, failures, and retries. Preserve task success, task latency, and gross
   SYS joules per correct task with compatible measurement boundaries.
5. Record requested/resolved backend and actual dispatch evidence for fallback
   calls. A proposal producing zero model tokens is not increased native decode
   tokens/second and must not be presented as such.

Quality and energy conclusions remain **REQUIRES_HARDWARE_VALIDATION**. No
production recommendation or automatic winner follows from these unit tests.
