# First measured candidate comparison

Same Qwen3-0.6B Q4_0 weights, GenieX 0.6.1, application and frozen evaluator `ccd1e00`. Only auto placement/default threads changed to CPU/10 decode threads. Both runs used AC power, Balanced mode and an exclusive inference workload.

| Metric | Untuned reference (auto → HTP0) | CPU/10 candidate |
|---|---:|---:|
| Correct tasks | 30/50 (60%) | 33/50 (66%) |
| Tool/action accuracy | 70% | 72% |
| Argument accuracy (all cases) | 82% | 84% |
| Clarification correct | 0/13 | 0/13 |
| Invalid output rate | 6% | 8% |
| Mean inference latency | 1209.531 ms | 853.287 ms |
| Median inference latency | 1147.561 ms | 853.103 ms |
| P95 inference latency | 1500.174 ms | 986.358 ms |
| Mean task latency with fixture execution/scoring | 1269.193 ms | 908.726 ms |
| Peak process working set | 1219.406 MiB | 1575.742 MiB |
| Full-run SYS energy | 1382.694 J | 3201.876 J |
| Quality gate | Fixed reference | **FAIL** |

Observed mean inference ratio: **1.4175×**, or **29.45% lower latency**; median is 25.66% lower. Accuracy improves by 6 points, with no recorded critical move/clarify regression. However, the frozen policy also requires invalid outputs ≤2%, and this candidate produces 8%; it is **not an accepted optimization**. Both configurations fail all expected clarification cases. These results do not establish a dependable general secretary.

The frozen comparator additionally reports the 2-point invalid-output increase as exceeding 2 because the computed floating-point value is `2.0000000000000004`. This numerical boundary issue is recorded for Axel/Codex; the evaluator is untouched, and the absolute 8% > 2% failure independently rejects the candidate.

Energy spans loading, warmup, all inference, fixture execution, scoring and report generation. It is neither inference-only nor wall-plug energy; the SYS counter is a named meter channel. Tokens/J is intentionally unavailable because the frozen runner omits warmup token counts. This is one full 50-case run per configuration, not a repeated paired timing experiment. Candidate outputs differ, so task latency improvement is distinct from fixed-length native decode throughput.

Full failures and outputs: [baseline](baseline.md), [CPU/10](candidate_cpu-t10-v2.md). JSON and telemetry are adjacent; candidate metadata carries the exact command and config. Preserve the baseline and golden data.
