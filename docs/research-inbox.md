# Offline Research Inbox

The inbox records research findings and human triage. It does not import the
optimizer, launch hardware, call a provider, inspect benchmark cases, or change
any evaluation protocol. All examples below are synthetic.

## Finding schema

Supply a JSON object with nonempty text fields:

- `finding_id`: unique portable slug
- `title`, `technique`, `mechanism`
- `source`: citation or provenance text; storing it does not verify its claims
- `stack_compatibility`: compatibility assessment, including uncertainty
- `expected_impact`, `confidence`: each `HIGH`, `MED`, or `LOW`
- `implementation_cost`: descriptive estimate
- `hardware_cost_estimate`: optional descriptive estimate, omitted or null when unknown; stored as null

Impact and confidence are assessments, never measured performance claims. New
findings start at `LOW_PRIORITY` with reason "Unclassified; explicit triage required
before planner" and cannot appear in READY exports.

## CLI

```sh
python scripts/research_inbox.py --inbox local/research-inbox add --file local/finding.json
python scripts/research_inbox.py --inbox local/research-inbox list
python scripts/research_inbox.py --inbox local/research-inbox classify synthetic-1 NEW_EXPERIMENT --reason "Synthetic technique merits a separate development experiment"
python scripts/research_inbox.py --inbox local/research-inbox export-ready --output local/research-ideas.json
```

Classification statuses:

- `NEW_EXPERIMENT`
- `SUPPORTS_EXISTING_EXPERIMENT`
- `ALREADY_TESTED`
- `NOT_AVAILABLE`
- `LOW_PRIORITY`
- `REQUIRES_PROTOCOL_OR_CODE_CHANGE`

Classification requires a reason. For supporting/tested findings, include the
existing experiment reference in that reason; this is descriptive provenance,
not automatic verification of the referenced archive.

## Persistence and deduplication

Immutable numbered JSON events live under `events/`. Additions and classification
changes append events under a cross-platform process lock. Each event is fsynced
and atomically published with an exclusive hard link; no existing event is
rewritten. An interrupted unpublished temporary file is ignored. Publication
requires a filesystem supporting hard links (normal local NTFS/APFS/ext4); an
unsupported filesystem fails rather than downgrading to a partial write.

Listing projects the latest classifications from the journal. Invalid sequences
or malformed records fail closed. This is an application append-only journal,
not a tamper-proof audit service against manual file changes.

Duplicate technique + mechanism + stack assessments are normalized for Unicode,
case, whitespace and trailing prose punctuation. Numeric signs and operators
are preserved; `seed=-1` and `seed=1` stay distinct. A duplicate returns the original finding ID
without an event. Changes in wording beyond this narrow normalization are not
silently merged; semantic deduplication needs review. Different stacks or
mechanisms remain distinct. Reusing an ID with different contents is rejected.
A duplicate source is not added to the original event; retain corroboration in
classification reasons or a distinct finding with a genuinely different mechanism.

## READY means a planning idea

The exclusive export includes only findings explicitly classified
`NEW_EXPERIMENT`. Its schema is `research-ideas-v1`, with `status: READY`,
`executable: false` and `scope: development_planning_only`. Exports cannot be
written inside the inbox or overwrite an existing output.

This is intentionally not the campaign planner's executable/configured plan
format. A reviewer must supply a control, concrete candidate configuration,
single-variable hypothesis, compatibility evidence and repetition protocol to
the existing offline planner. No direct import into the hardware queue exists.
Protocol/code changes remain outside READY until implemented and independently
reviewed. No heldout access or benchmark modifications are needed for triage.
