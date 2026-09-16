# Owner decisions required

No item below blocks unrelated engineering. Defaults remain unchanged.

1. **Product thresholds:** minimum success rate and maximum task latency are still undefined. Which threshold and exact timing boundary should qualify FAST/EFFICIENT? No numeric default invented.
2. **BALANCED:** choose explicit policy after comparable quality/latency/energy data exists. No arbitrary weights.
3. **Frozen parser defect A01:** malformed extra tool envelopes can be ignored. Approve a separately versioned future strict parser/evaluation contract; v2 remains unchanged.
4. **Semantic provenance closure A02 / dirty historical gate A04:** approve a future versioned qualification contract including imported parser/executor dependencies and clean candidate gate. Tracker can enforce clean measurement independently without changing v2 scoring.
5. **Reference roles:** approve a campaign control/reference distinct from immutable historical baseline before official energy qualification. Never replace original baseline.
6. **Schema/prompt/grammar/routing evaluation:** any candidate requiring frozen prompt/TOOLS/scoring modification needs a new explicit protocol; do not present it as identical v2.
7. **Held-out exposure:** existing archives expose prompts to developers. Keep15 held-out cases out of optimization; no silent redefinition/replacement.

## From the adversarial tracking audit (TRACKING_AUDIT.md, revision 3498f7d)

8. **Campaign plan binding (TRK-003):** should `analyze_experiment_campaign.py` accept
   `--plan` and report planned / attempted / completed / missing? Today a campaign that is
   short a run reports statistics over the remaining runs with no indication one is
   missing. Suggested matching key: tracker `--name` equals the plan `treatment` name and
   the plan `config_byte_sha256` equals the archived `config.json` hash. This changes the
   campaign report schema, so it was not done unilaterally.
9. **Generation protocol binding (TRK-005):** should `run()` refuse to qualify a report
   whose `generation_protocol` differs from the config-derived expectation
   (`max_tokens` from config, temperature 0, reset true)? A report declaring
   `max_tokens 256, temperature 0.7` currently produces no reason. Binding it would newly
   unqualify runs, so it is an owner call.
10. **Mandatory counter resolution (TRK-006):** should `--counter-resolution` become
    required whenever `--capture-full-process-energy` is used? Without it the
    ten-interval guard never applies and a 50 ms block yields a confident joule figure.
    This changes the CLI contract.
11. **KPI key naming (TRK-016):** should the stored key `median_e2e_ms` be renamed to
    `median_task_latency_ms` with a schema version bump? `docs/kpi-definitions.md`
    already warns that the name overstates its scope.
12. **Workload kind (GF):** should the manifest gain an explicit `workload_kind`
    (secretary_eval, energy_probe, mcp_diagnostic, microbenchmark) before any
    non-Secretary result is imported? The ledger currently assumes every archive is a
    Secretary evaluation.
13. **Status refresh (TRK-015):** `docs/CURRENT_STATUS.md` states 674 tests where 739 now
    pass and tabulates EXP-001..006, which do not exist in a fresh checkout. Confirm
    whether those archives exist on the Snapdragon before the document is refreshed.
