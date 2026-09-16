# Local Turbo — mandatory engineering rules

## Objective and evidence

Optimize the local Snapdragon Secretary for **success / median task latency / gross SYS J per correct task**. Decode tokens/s and tokens/J are diagnostics, not product success or efficiency. State every timing/energy boundary. Missing energy is null, never zero. Requested NPU placement is not proof of exclusive NPU dispatch. Thinking is already disabled.

## Frozen benchmark

secretary-eval-v2: **35 development / 15 held-out / 50 full milestone cases**. Do not tune on held-out. Never alter datasets, golden answers/rationales, manifest, fixture inventory/bytes/names, `benchmarks/secretary_tasks.json`, or existing files under `eval/results/` and `benchmarks/results/`.

Do not change v2 prompt/scoring/parser/executor semantics in place. Semantic dependencies include eval/scoring.py, secretary_adapter.py, validate_dataset.py, quality_policy.json, runner logic, service.parse_calls, secretary.execute_tool/TOOLS/snapshot. Record defects, add separate diagnostics, propose a versioned future path in OWNER_DECISIONS_REQUIRED.md. Never repair model text after generation to inflate scores.

## Every experiment is an archive

- Official experiments must use `scripts/experiment_tracker.py`; no bypass benchmark runs.
- Commit code first. Qualified measurement requires clean Git state, bound artifacts and complete evidence. Dirty diagnostics require explicit `diagnostic_dirty`; never promote them.
- Every attempt gets a unique EXP ID under ignored `local/experiments/`; never overwrite or reuse one, even after failure.
- Record hypothesis, exact change, control EXP ID (or baseline/no causal claim), config snapshot, command, git status/diff, identities, requested/effective sampler where observable, raw outputs/logs/counters and all failures.
- Preserve originals when backfilling. Unknown historical facts stay unknown; ingestion machine state is not historical provenance.
- Include energy of **all attempts**, including incorrect tasks, in J/correct. Zero correct tasks => undefined, not zero.
- Counter update gaps are not certified hardware resolution. Short task deltas may be unavailable; use sufficiently long scoped blocks. Full-process energy is not warm-task energy.
- One hardware job at a time; inspect existing jobs before launch. Use bounded timeouts, keep every attempt and balance repeated treatment order.
- No overall winner without comparable evidence and owner-defined quality/latency thresholds. Do not invent thresholds or replace historical baseline.

## Collaboration and checkpoints

Proceed autonomously on authorized safe work; log owner-dependent decisions and continue independent work. Use bounded independent agents with disjoint ownership; one hardware owner. Run focused tests before each coherent commit, broad tests at milestones. Inspect diff/status and preserve other contributors' edits. Fetch/check open PRs before pushes; never force push or delete unknown work. Frontend design belongs to collaborators; use existing contracts.

Keep private configs, device addresses, credentials, models and raw private logs under ignored local/. Never commit secrets or large models. Core inference remains offline. Preserve user power settings. Keep claims measured and scope limitations explicit.

Detailed methodology: [experiment protocol](docs/experiment-protocol.md). Prior operating context: [historical agent instructions](docs/agent-operating-context.md); current rules above take precedence. Use genuine authenticated review tools only; never rotate accounts, extract tokens, reset quota or use paid fallback silently.
