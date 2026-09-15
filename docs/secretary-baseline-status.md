# Frozen evaluation status

The v2 baseline and two initial candidate reports are published under `eval/results/`. Their JSON is the unchanged Windows runner output, normalized only from CRLF to LF. Source hashes were checked against their application commits.

After publishing the required raw evaluation reports, the full test suite reports **230 passed, 1 skipped and one failed leakage-audit test**. `tests/test_eval_golden.py::GoldenTests::test_heldout_leakage_scan` finds held-out prompts in the official result JSON/Markdown files, which the runner intentionally writes for audit. It does not indicate that prompts were added to model inputs or optimization examples. The frozen protocol anticipated published audit reports appearing in this scan, but the test still asserts an empty result.

No scanner, test, dataset, expected answer or policy is changed here. Axel/Codex owns how to distinguish approved report artifacts from tuning leakage. Keep the audit finding visible rather than suppressing it or deleting required evidence. All other tests passed; native greedy and lifecycle regression tests passed independently.

See `eval/results/baseline_sampling_note.md` for the separate requested-versus-effective sampler issue. Existing reference results remain fixed; adapter changes are new candidates.
