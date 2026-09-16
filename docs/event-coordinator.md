# Opt-in event-driven TurboLab coordination

This branch starts exactly at `389c2e8a8d073254e18c5c213a1f574ca79930df`.
It leaves the default Lane A loop intact. `--event-driven` enables immediate
post-treatment decisions, a durable coordination journal and a global session
heartbeat approximately every 600 seconds. The heartbeat runs through hardware,
planner and idle periods; it never signals a child or modifies an active config.

## Integrate before target execution

Review and integrate the separate branches explicitly; this branch does not
silently merge them:

- Experiment Registry `c28450376687f1cf1eb7f8768b7677f78701bd87` supplies
  `turbo.experiment_registry`. Real event-driven execution refuses to launch if
  registry integration is absent or its outbox cannot be delivered.
- Research Inbox `d1c47bc0a82c061d4db5f58512e6a250f8e5f49f` supplies
  `turbo.research_inbox`. Optional import is planner context only.
- Diagnostic attempt isolation `1ec27cc` is required before real repeated S2/S3
  runs: base 389 reuses canary paths. Keep each hardware attempt's request/output
  distinct. This coordinator branch does not duplicate that separate fix.

No inference was run to implement this feature. All tests use synthetic clocks,
executors, records and mocked native entry points.

## Commands

Portable simulation, without models or API calls:

```sh
python scripts/autotune.py --dry-run --mock-llm --event-driven \
  --budget-minutes 30 --session-dir local/event-simulation
```

After integration/review, an explicitly authorized target run uses the existing
`autotune.py` arguments plus `--event-driven`. The frozen dataset remains
`development`; no heldout route is exposed. `--resume SESSION/session.json`
restores the persisted opt-in setting and original immutable session settings.

Read-only status or manual heartbeat:

```sh
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json --action heartbeat
```

Future decisions require a reason:

```sh
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json \
  --action reject --candidate CANDIDATE_ID --reason 'Unsupported by current runtime'
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json \
  --action reorder --candidate CANDIDATE_ID --priority 0.9 --reason 'Highest information value'
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json \
  --action repeat --candidate CANDIDATE_ID --reason 'Resolve observed variability'
python scripts/autotune_coordinate.py --state local/SESSION/coordination.json \
  --action research --inbox-root local/research-inbox
```

Research import does not create/admit candidates or jobs. A planner must translate
an explicitly reviewed idea into a supported candidate and pass the existing
static guard. No source text may issue executable commands through this interface.

## Decision and stage semantics

After every treatment, the existing stage gate runs immediately; event mode uses
one treatment per batch. S1 establishes liveness; S2 cheaply eliminates; S3 applies
the stronger diagnostic gate; S4 carries full development promotion evidence;
S5 confirms. The existing selector retains promotion authority. A bookkeeping
`PROMOTED` status does not certify energy or establish an overall winner.

All READY pool stages compete for the next slot, including S3 when the session
phase is still exploration. Phase influences the existing priority heuristic,
not permission to ignore ready work. Learned family statistics use the existing
`families` state. Scores and manual priorities are declared scheduling heuristics,
not measured performance or probability estimates.

The serious frontier contains at most four distinct hypothesis branches, keyed by
explicit `branch_id`, otherwise family, otherwise candidate ID. It may contain
multiple parameter points within a branch. Two to four is the intended working
range when enough eligible branches exist; the system does not fabricate a second
branch when only one is valid. Deferred candidates remain available. Combined
candidates require every named parent to have a confirmed individual promotion
from the existing selector; this policy is additional to static admissibility,
not a bypass of the supported search space.

Future rejection/reordering is checked again after a control completes and before
an unstarted treatment. Historical completed jobs are still replayed and processed
even if a later future decision rejects that candidate. Running config snapshots
are compared against launch intent and are never edited by the coordinator.

## Repeat policy and unknown evidence

A near-noise repeat requires at least two comparable control observations with
identical stage, control config hash, attempted count, case IDs/hashes and protocol.
No identity means unknown comparability, not zero noise. Additive identity metadata
is retained by diagnostic/archived observation adapters; scoring is unchanged.

For varying correctness, compare the candidate's absolute correct-count difference
with the observed control range. At equal stable correctness, compare latency only
when there are at least two matching-boundary control latencies. A substantial
speed improvement outside that observed range does not trigger a repeat merely
because correctness is equal. Missing latency remains unknown. These ranges are
repeat heuristics, not confidence intervals or invented promotion thresholds.

Only a surviving existing gate can request an automatic repeat. A rejected
invalid-output/quality gate cannot be turned into an advancement by noise logic.
Automatic near-noise repeats are bounded to two additional attempts per config and
stage; unresolved evidence then holds. Every observation stays in the journal.
Explicit operator repeat requests are separately reasoned future actions.

## Durability and hardware exclusion

The existing session lease serializes controllers. Coordination mutations have a
separate cross-process lock and atomic checkpoint. Durable launch intent precedes
execution. Completion is saved in the existing hardware journal before controller
postprocessing. A crash after a decision replays the same job-keyed decision,
without incrementing repeat counts or launching hardware again. Registry events
use stable event IDs for idempotent outbox retry; parent node IDs use the same
identity mapping as child snapshots.

A started/exceptional attempt with uncertain native completion **blocks resume**.
Do not delete intent to force a retry: independently reconcile native processes
and authoritative hardware evidence first. If the durable scheduler journal
already contains completion, recovery imports that exact observation. No timeout
or exception is converted into a fabricated successful observation.

All opt-in native workers own the hardware lock inside the actual native process,
not its parent. They first take a shared per-user machine slot beneath the system
temporary directory (`turbolab-hardware-<user hash>`), then the existing
`hardware-execution` lock under the archive root. Different new archive roots
therefore still share one event-driven hardware slot. Locks are OS-released on
process exit; a surviving native process retains them after controller death.
The S4/S5 tracker uses opt-in `child_hardware_lock=True`; normal tracker behavior
is unchanged. The wrapper source hash is captured and checked after execution.
No evaluator source bytes or parser/scoring behavior are changed.

Child-owned tracker mode refuses full datasets, custom commands and parent-scoped
energy capture. Parent-scoped energy could overlap a subsequent job after the
native child releases its lock, so this mode makes no energy qualification claim.
Ordinary external applications and legacy direct native processes do not acquire
the new machine slot: inspect existing hardware jobs before starting a session.
The existing archive-root lock still coordinates legacy tracker jobs using that
same root. All participants must use the coordinated execution protocol for a
cross-session single-job guarantee.

Heartbeat packets contain current immutable active intent, serious frontier,
future decisions, node observations and planner inbox. Observer failures are
recorded where writable and block the next launch; they never interrupt an active
measurement. Available registry metrics retain explicit timing/energy boundaries;
unknown or unbounded values stay null. RUNNING precedes launch, OBSERVED follows
completion, and all registry envelopes remain unqualified bookkeeping.
