# TurboLab

Bounded autonomous search over Secretary configurations that the current frozen
contract can actually express.

```sh
python scripts/autotune.py --budget-minutes 120 --backend qairt_npu --split development \
  --control-config local/qairt-single-action.json
python scripts/autotune_status.py local/autotune/session.json
python scripts/autotune_final.py local/autotune/session.json --config local/final.json
```

`--dry-run` simulates a whole session with no hardware and no API calls, through
the same stage routing the real path uses. Its S4 and S5 routes seal a real
archive in a throwaway directory and read it back through the observation
adapter, so the adapter is exercised rather than bypassed; those archives
describe nothing that was measured and are discarded when the session ends.
`--mock-llm` swaps in deterministic clients that answer with a real proposal.

## What it does not do

It creates no measurement. Every hardware evaluation goes through
`scripts/experiment_tracker.py` and becomes an ordinary archive with the usual
provenance. TurboLab state is orchestration metadata: deleting
`local/autotune/` loses a session's bookkeeping and no evidence at all.

It cannot reach heldout cases. `--split` accepts only `development`, the
executor passes only `dataset='dev'`, and the guard refuses a candidate that
names any other split. The single command that may evaluate heldout is
`scripts/autotune_final.py --run-heldout`, which first freezes the
configuration by hash and closes the session, so a heldout number can never
steer another round of search. Its result is deliberately not written back into
the session.

It does not optimize energy. Energy is not commissioned, so a candidate that
declares an energy objective is refused until `energy_commissioned` is set.

## The three lanes

`BACKEND_CAPABILITY_MATRIX.md` is generated from
`turbo/optimizer/search_space.py` and is the source of truth.

**Lane A, official QAIRT.** The frozen runner accepts a closed set of
configuration keys, and `turbo/native.py` rejects most of them for the qairt
plugin: context must equal the compiled artifact, and thread, batch and
speculation settings are refused outright. What remains is `max_tokens` and
`stop_after_tool_call`, which is eleven single-variable treatments. That number
is small and it is a finding about the current contract, not a defect of the
search engine.

**Lane B, llama.cpp mass search.** On `llama_cpp_cpu` and `llama_cpp_htp`,
`threads`, `threads_batch`, `n_batch`, `ubatch`, `context`, `max_tokens` and
`spec_type` are all live. That is 39 single-variable treatments and 52,920
bounded grid points, so high-volume search genuinely exists here.

**Lane C, research items the contract cannot express.** Explicit QAIRT sampler
control, constrained decoding, prompt and schema variants, a deterministic
router, code patches. These are registered in `turbo/optimizer/lane_c.py` with
the missing capability, the smallest safe protocol extension, the files that
would change, whether benchmark semantics move and how each would have to be
validated. None of them may reach a qualified experiment. They are recorded so
the questions survive the fact that today's runner cannot ask them.

## Single variable versus bounded grid

`turbo/campaign_plan.py` refuses a treatment that differs from its control in
more than one field, so a candidate that changes one field keeps causal
attribution and a grid point that changes four does not. Both are generated,
and the difference is carried in the candidate itself: a grid point declares
every field it moves and records `causal_attribution: False`. A multi-field
candidate that does not declare itself is refused as a hidden multi-variable
mutation.

## The funnel, and which executor answers each stage

`scheduler.staged_executor` routes every stage to the executor entitled to
answer it. One executor for all five stages, as the first version had, meant the
real path ran the full development set five times and logged the first three as
cheap.

| stage | executor | what it is | writes an archive |
|---|---|---|---|
| S0 | none | static admission, zero inference | no |
| S1 | `startup_probe_executor` | `scripts/backend_smoke.py`, one bounded generation | no |
| S2 | `canary_executor` | `scripts/diagnostic_canary.py`, `--s2-cases` development cases | no |
| S3 | `canary_executor` | same, `--s3-cases` development cases | no |
| S4 | `tracker_executor` | full 35 development cases through `experiment_tracker` | yes |
| S5 | `tracker_executor` | confirmation repeat, same path | yes |

`--s2-cases` and `--s3-cases` default to 0, which **skips** that stage and says
so. They are never widened to the full development set behind a label that says
eight: that would make a cheap stage expensive and an expensive comparison look
cheap, and the session log would not show which had happened.

S1 is liveness and records `correctness_claim: False`. S2 and S3 produce records
stamped `DIAGNOSTIC_CANARY` with `qualified: False` and `promotion_evidence:
False`. `scripts/diagnostic_canary.py` is not a second evaluator: it imports the
frozen runner's own `execute` and the frozen scoring path unchanged and only
chooses fewer cases, so a canary and a tracked run cannot disagree about what a
correct answer is. It can load exactly one dataset file, the development split,
and takes no argument that could change that.

S4 and S5 go through the tracker and produce ordinary archives. What comes back
is not the tracker's return value: the sealed archive is re-read through
`turbo/optimizer/observation.py`, read only and verified first, so the funnel
compares the evidence that was actually sealed. A missing field there produces
`evidence_complete: False` with the reason, and every rule above treats that as
unable to clear its gate rather than as a pass.

Promotion requires a net improvement of at least two development cases, a
latency gate that is an explicit pass, and a confirming repeat. The latency gate
refuses to compare two different boundary labels and returns None, which the
selector treats as a failure to pass. Determinism, once established empirically,
relaxes how many repeats are needed; it is not itself a promotion requirement.

The control is re-measured at each stage, because an elimination rule with no
same-stage baseline has nothing to compare against and abstains rather than
guessing.

## Phases and the device

For a 120 minute budget: exploration above 60 minutes remaining, focus down to
20, confirmation only down to 10, and closing below that. The phase policy
rations breadth, not the device. When the only work left is waiting on a later
phase, the scheduler runs it anyway and logs `RELAX`, because idle hardware
seconds are the one cost no later phase can recover.

Before commissioning no candidate has a measured cost. The session declares one
default (180 s) and records it as a declared default rather than an
observation. Unknown cost is therefore neither free nor a reason to stall.

## Honest counts

A report distinguishes `GENERATED_CANDIDATES`, `STATICALLY_VALID_CANDIDATES`,
`DIAGNOSTIC_CANDIDATES`, `HARDWARE_ATTEMPTS` and `QUALIFIED_EXPERIMENTS`. A
generated configuration is not a test, a run or an experiment, and the report
never calls it one.

## Crash recovery and interruption

State is written atomically after each session, so a crashed write leaves the
previous state readable. `--resume` restores the control, the queue, completed
candidates and elapsed budget, and a completed treatment is never rerun because
deduplication is by configuration hash. Ctrl-C stops scheduling, lets the
active evaluation finish, persists, and prints the resume command.

## Model adapters, and what they are actually wired to

`turbo/optimizer/advisor.py` is the single place a model influences the loop, and
`scripts/autotune.py` has exactly one call site for each of `propose` and
`submit_critique`. There is no separate mock path: `--mock-llm` swaps which
client answers and nothing else, and it answers with a real proposal rather than
an empty one, so a dry run exercises schema validation, bounded mapping, guard
admission and family selection.

During an exploring or focusing round the proposer is asked for hypotheses. What
a model may change is which **declared** family gets attention this round. It
cannot invent a family, widen an enumeration or start anything: its parameter
names and values are looked up in the declared enumerations by
`mutation.from_llm_space`, anything outside them is rejected with a reason and
never clamped inward, and what survives is an ordinary candidate that
`guard.check` still has to admit. The path from a model's words to a device runs
through two refusals it cannot argue with.

An idea the contract cannot express is labelled inadmissible and kept in the
session record rather than dropped, which is how the QAIRT sampler question
stays visible instead of disappearing into a log line.

The critic runs off the hardware path through `concurrent.futures` and is
harvested between treatments. A blocking finding removes a candidate from the
round; it can never admit one, because a critic that could wave a candidate
through would be a second, weaker gate beside the real one.

Counters are reported separately and never merged: `LLM_PROPOSER_CALLS`,
`LLM_CRITIC_CALLS`, `LLM_HYPOTHESES`, `LLM_ADMISSIBLE_HYPOTHESES`,
`LLM_REJECTED_HYPOTHESES`, `LLM_API_WAIT_SECONDS`.

A missing credential is a session fact reported as `UNAVAILABLE`, not a failure.
The deterministic search does not depend on a model, so a session with no
credentials generates, admits and runs exactly as it otherwise would. No
credential value is ever read into a variable, logged or cached.
