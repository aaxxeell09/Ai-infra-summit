# Qwen3-8B full milestone — 38/50, no quality PASS

Clean application `31bb6a178638eda96c33fe3b9f0bbd4ec97c3ebe`; EXP-003 in the
Latitude `grammar-1000` checkout's immutable tracker. Unchanged frozen50 cases:
35 development and15 held-out. Model Qwen3-8B Q4_K_M, SHA-256
`120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4`;
GenieX0.6.1 llama.cpp CPU10, context4096, max128, default batching, fresh KV,
no grammar, routing or speculation. Temperature0 is requested; SDK zero values
still select default sampling, as recorded in every row.

- Overall/tool/action: **38/50 (76%)**; arguments94% all-case.
- Clarification:2/13 (15.38%). Moves8/8; invalid output2/50 (4%).
- Mean/median/p95 inference:19,896.854 /12,808.861 /39,356.446 ms.
- Mean/median/p95 recorded task:19,992.707 /12,946.676 /39,431.437 ms.
- Full-process SYS energy:31,161.686 J;820.044 J/correct including failed cases.
  **Diagnostic, uncommissioned; not a qualified energy comparison.**

Recorded task timing uses the evaluator boundary, not user-facing cold end-to-end.
No speedup is claimed. Historical comparison remains **NOT_COMPARABLE** due to
incompatible evaluator hash. The4% invalid rate exceeds the unchanged2% quality
limit; no accepted candidate or routing admission follows from this result.

Failures: `dev_022`, `dev_023`, `dev_024`, `dev_025`, `dev_026`, `dev_027`,
`dev_028`, `dev_034`, `heldout_003`, `heldout_010`, `heldout_012`, `heldout_015`.
Category results remain in result.json. Held-out content was not used to tune.

Reproduce from the clean source with the matching private paths restored:

```powershell
python -X utf8 scripts/experiment_tracker.py run --name qwen8b-cpu10-full-reproduction --dataset all --config local/qwen8b-config.json --change "Different model deployment; CPU10 context4096; unchanged frozen full milestone workload" --hypothesis "Prespecified full-50 milestone for 8B development candidate; no heldout tuning or causal speedup claim" --timeout 1200 --capture-full-process-energy
```

Original sealed archive integrity was verified after retrieval. Published files
retain existing formats plus an explicit publication record and original hash.
Private paths are redacted. Held-out prompts, expected actions, actual arguments
and raw outputs are omitted from the public copy to avoid additional exposure.
This copy does not replace the complete private archive for revalidation. All
aggregate metrics, per-category failures, row IDs/status/timing and source/model
identities remain available. The original baseline and all old results are intact.
