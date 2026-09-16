# Descriptive three-backend comparison

`eval/compare_backends.py` reads existing Secretary result JSON files. It runs no inference, changes no benchmark files and selects no overall winner. Energy measurements are optional for reporting correctness and inference latency.

## Use existing reports

The committed CPU, HTP reference and QAIRT reports currently contain all 50 cases. Select their 35 explicitly labeled development cases without rewriting them:

```powershell
python eval/compare_backends.py --cpu eval/results/candidate_cpu-t10-v2.json --htp eval/results/baseline.json --qairt eval/results/candidate_qairt-native-06-v1.json --dataset dev --output local/comparisons/three-backends-dev.md
```

The command creates Markdown and a JSON companion. Omit `--output` to print JSON. Existing output files are never overwritten. For dedicated development reports, supply those paths with the same options. `--dataset all` (default) compares every row in each supplied file.

Selecting development rows preserves each input's original `dataset_sha256`; it does not pretend a full-suite hash describes a new dataset. The report includes the selected IDs and `case_sha256`, source case count, input filename and SHA-256. Exact prompt text and model output are not copied into the comparison.

## Independent statuses

- `correctness_latency_comparable`: all three measured reports have valid rows, expected backend identities, matching benchmark/protocol/scope, dataset/fixture/action-schema/system-prompt/evaluator hashes, warmup policy and exact selected case IDs/hashes.
- `energy_comparable`: additionally satisfies the existing decision table's strict energy provenance and raw SYS-counter validation. This includes matched measurement signatures and commits. Missing energy never becomes zero and does not block the correctness/latency report.

The existing committed QAIRT result has different evaluator hashes from the CPU/HTP reports. Its metrics can be displayed, but these reports are explicitly **not comparable under the provenance check**. No override rewrites that evidence. The report remains useful for diagnosing current observations; a controlled rerun on the Snapdragon is needed for matched evidence.

An application commit difference alone does not block descriptive correctness/latency comparison when evaluator and methodology match. Config, generation settings, model hashes and environment differences are explicitly disclosed as treatments or caveats. This is a configuration comparison, not proof of a hardware-only speedup. QAIRT and GGUF artifacts need not have the same hash. Backend selection/resolution is not proof of hardware dispatch; any recorded dispatch verification remains visible. Legacy reports lacking `inference_backend` require `config.plugin` plus consistent per-case `selected_device`; the command never invents backend identity from its argument slot.

## Metrics and boundaries

Metrics are recomputed from recorded case flags, not trusted from cached summaries. No output is rescored and no golden answer is changed:

- Success count / total and accuracy percentage include failures.
- Invalid output rate is the fraction of cases marked `invalid_output`.
- Clarification accuracy uses `no_action_correct` on cases whose expected tool is `clarify`, matching the existing summarizer. With no clarification cases, it is unavailable.
- Mean, median and nearest-rank p95 use `latency_ms`. This is the model inference request interval, before scoring and fixture execution; it is not full task latency. p95 is unavailable below 20 samples. Missing, negative or nonfinite latency blocks comparability instead of silently dropping observations.

The JSON and Markdown include backend identity, evaluator/dataset hashes, all selected case IDs/hashes, model/config/generation provenance and explicit incompatibility reasons. There is no overall winner, mode recommendation or official correctness gate from this tool, even when energy is present. Use the existing `eval/decision_table.py` with approved reference, thresholds and matched energy evidence for a separate energy decision.

## Tests

```powershell
python -m pytest tests/test_compare_backends.py -q
```

Tests cover no-energy comparison, provenance mismatches, case changes, invalid values, legacy identity, existing report incompatibility, development filtering, metric denominators, p95, generation treatments, independent energy checks and refusal to overwrite outputs. Hardware is only needed to collect new measurements.
