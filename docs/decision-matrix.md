# Secretary energy decision matrix

Objective: minimize gross SYS joules per correct task, subject to correctness and latency limits.

Comparison: **NOT_ENOUGH_DATA**. Winner: **NOT ENOUGH DATA**.

| Config | Accuracy % | E2E latency ms | J/task | J/correct | Invalid | Clarify % | Peak RAM MB | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| llama_cpp_cpu | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED; gate=NOT_EVALUATED; move failures=UNAVAILABLE |
| llama_cpp_htp | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED; gate=NOT_EVALUATED; move failures=UNAVAILABLE |
| qairt_npu | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED; gate=NOT_EVALUATED; move failures=UNAVAILABLE |

## Selection policy

```json
{
  "min_accuracy_pct": null,
  "max_e2e_latency_ms": null,
  "latency_stat": "p95"
}
```

All tasks, including failures, contribute to total energy. J/correct task is undefined with zero successes. Latency excludes fixture preparation and final state comparison; parsing and execution are inside the measured boundary. p95 requires at least 20 samples.

Gross energy is the primary metric. Net energy is diagnostic only. Peak process RAM, available only when measured, is preserved in the JSON companion; it is not total system memory.

## Readiness and exclusions

- **llama_cpp_cpu**: No measured report supplied
  - Quality gate: Measured run unavailable
- **llama_cpp_htp**: No measured report supplied
  - Quality gate: Measured run unavailable
- **qairt_npu**: No measured report supplied
  - Quality gate: Measured run unavailable

## Modes

- FAST: NOT ENOUGH DATA
- BALANCED: NOT ENOUGH DATA
- EFFICIENT: NOT ENOUGH DATA

EFFICIENT minimizes J/correct task; FAST minimizes the configured latency statistic. BALANCED remains undefined until an explicit Pareto/tie policy is agreed. These are report recommendations, not routing changes.

Historical references are never promoted to a current baseline. No winner is issued without all three current comparable measurements, explicit thresholds and an approved correctness gate. Missing measurements remain unknown.

## Winners by objective

- lowest_joules_per_correct_task: NOT ENOUGH DATA
- lowest_latency: NOT ENOUGH DATA
- highest_accuracy: NOT ENOUGH DATA
- lowest_joules_per_task: NOT ENOUGH DATA
- best_eligible: NOT ENOUGH DATA

## Measurement provenance and summaries

Generated: 2026-09-16T00:54:57.732867+00:00

Generator: {"commit": "26bcc7be9e1d40877ce3de394742453ebc581f85", "source_sha256": "4cfd09b478e59ea7107e6e8f6bb0f514617994f2878de47aa99a6cb3e625e5f6", "dirty": true}

### llama_cpp_cpu

```json
{
  "provenance": null,
  "summary": null
}
```

### llama_cpp_htp

```json
{
  "provenance": null,
  "summary": null
}
```

### qairt_npu

```json
{
  "provenance": null,
  "summary": null
}
```
