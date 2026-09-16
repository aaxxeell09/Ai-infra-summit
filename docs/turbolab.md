# TurboLab

Bounded autonomous search over Secretary configurations that the current frozen
contract can actually express.

```sh
python scripts/autotune.py --budget-minutes 120 --backend qairt_npu --split development \
  --control-config local/qairt-single-action.json
python scripts/autotune_status.py local/autotune/session.json
python scripts/autotune_final.py local/autotune/session.json --config local/final.json
```

`--dry-run` simulates a whole session with no hardware and no API calls.
`--mock-llm` replaces both model adapters with deterministic stubs.

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

## The funnel

S0 static only, no inference. S1 a startup probe, liveness and nothing more.
S2 a small diagnostic canary, elimination only, never a promotion. S3 a larger
development subset. S4 the full 35 development cases through the tracker. S5 a
confirmation repeat. Promotion requires a net improvement of at least two
development cases, a latency gate that is an explicit pass, and a confirming
repeat. Determinism, once established empirically, relaxes how many repeats are
needed; it is not itself a promotion requirement.

The control is re-measured at each stage, because an elimination rule with no
same-stage baseline has nothing to compare against and abstains rather than
guessing.

S2 and S3 currently need a diagnostic probe, since the frozen runner exposes
only development, heldout and all. `turbo/optimizer/probe.py` defines that
interface and labels every result `DIAGNOSTIC_CANARY`, with `qualified: False`
and `promotion_evidence: False` in the record itself. Until the probe is wired
to hardware, a session can run with startup probes and dev35 alone.

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

## Model adapters

Anthropic proposes search families and OpenAI criticises, both behind an
interface, both cached by prompt hash, neither able to execute anything: an LLM
proposal becomes a bounded deterministic search space, which the guard then
admits or refuses. A missing credential is a session fact reported as
`UNAVAILABLE`, not a failure, and no credential value is ever read into a
variable, logged or cached.
