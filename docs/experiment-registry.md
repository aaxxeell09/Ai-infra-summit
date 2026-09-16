# Local experiment registry (v1)

The registry is an append-only planning and evidence index. It does not run models,
read datasets, score outputs, import archives, or certify measurements. A declared
`PROMOTED`, `CONFIRMED`, or `FINALIST` status remains bookkeeping: every envelope
has `qualified: false`. Existing tracker archives remain the measurement authority.
No overall winner is selected, including when energy is missing.

## API and full-snapshot schema

`turbo.experiment_registry.append_event(root, event)` returns the persisted envelope.
`read_events(root)` verifies and returns the complete ordered history.
`current_frontier(root)` returns each node's latest envelope except nodes declared
`REJECTED`, `PROMOTED`, or `CONFIRMED`; this is a status-based work list, not a ranking.

Each event is a complete node snapshot with these required fields:

- `node_id`: portable identifier; `parent_ids`: existing node IDs (a DAG).
- `config_hash`: full lowercase SHA-256; `code_sha`: full lowercase Git SHA-1.
- `protocol_version`, `hypothesis`: explicit nonempty strings.
- `stage`: `S1` through `S5`.
- `status`: `DISCOVERED`, `READY`, `RUNNING`, `OBSERVED`, `REPEAT_NEEDED`,
  `REJECTED`, `PROMOTED`, `COMBINATION_READY`, `CONFIRMED`, or `FINALIST`.
- `decision`, `decision_reason`: nonempty explanations supplied by the caller.

Optional fields:

- `event_id`: stable caller idempotency key. An identical retry returns the existing
  envelope; conflicting reuse fails. Callers should supply this for crash recovery.
- `evidence_paths`, `control_ids`: lists of strings. Paths are references only:
  existence, archive seals, contents and measurement qualification are not inferred.
- `repeat_count`: nonnegative integer, or `null` when unknown.
- `metrics`: `correctness`, `invalid_rate` (fractions in [0,1]), `latency_ms`,
  `ttft_ms`, `decode_tokens_per_second`, `energy_j`, `memory_bytes`.
  Every missing value is `null`, never an invented zero.
- `metric_boundaries`: a nonempty scope description for every supplied metric,
  e.g. generation-only median, total-process energy, or peak host RSS. No boundary
  is inferred from a field name. Energy here is descriptive, not commissioned proof.

A node's parent IDs, config/code hashes, protocol and hypothesis are immutable.
Create a child node for a changed treatment. Stage/status changes append snapshots;
there is deliberately no automatic status transition, qualification, combination,
promotion, causal inference, or threshold policy.

## CLI

Keep private input and registry files under ignored `local/`:

```sh
python scripts/experiment_registry.py --root local/experiment-registry append --event local/registry-event.json
python scripts/experiment_registry.py --root local/experiment-registry frontier
python scripts/experiment_registry.py --root local/experiment-registry history
```

Example **synthetic planning** input (replace hashes with actual identities):

```json
{
  "node_id": "candidate-001",
  "event_id": "candidate-001-discovered-v1",
  "parent_ids": [],
  "config_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "code_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "protocol_version": "diagnostic-planning-v1",
  "hypothesis": "Synthetic schema example only",
  "stage": "S1",
  "status": "DISCOVERED",
  "decision": "Await a permitted startup probe",
  "decision_reason": "No measurement has been collected"
}
```

## Persistence and limits

Each `events/000000000001.json` style record carries a sequence, UTC timestamp,
previous-record SHA-256, and its own SHA-256. Readers fail closed on gaps,
corruption, malformed records, and unsupported symlink event paths. The chain
checks integrity; it is not a signed audit log and cannot detect deletion of an
entire suffix without an external retained checkpoint.

An OS lock serializes readers/writers. Writers fsync a temporary file, atomically
publish a hard link **without replacing any existing destination**, then fsync the
directory where supported. Before publication, interrupted temporary files are
ignored; after publication, the complete record is visible. Stable `event_id`
retries recover an uncertain acknowledgement without duplicate records. Filesystems
without hard-link support fail closed; there is no unsafe overwrite fallback.
Windows directory fsync is unavailable in the shared helper, so sudden-power-loss
durability remains platform dependent. The OS releases the lock on process exit.

Tests use synthetic events, fake publication failure and concurrent local processes.
They launch no inference and inspect no historical or held-out experiment outputs.
