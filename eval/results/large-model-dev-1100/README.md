# Larger-model development results on the Latitude

Clean application `31bb6a178638eda96c33fe3b9f0bbd4ec97c3ebe`, GenieX 0.6.1,
llama.cpp CPU, 10 threads, context4096, max128 generated tokens, default batching,
no grammar/routing/speculation, fresh KV per case. The existing immutable tracker
ran the unchanged **35 development cases** sequentially. Both original sealed
archives passed integrity verification after retrieval. No held-out cases were
used to choose these trials.

| Observed metric | Qwen3-8B Q4_K_M | gpt-oss-20b MXFP4 |
|---|---:|---:|
| Correct / attempted | 27/35 (77.14%) | 0/35 (0%) |
| Tool/action accuracy | 77.14% | 0% |
| All-case argument accuracy | 97.14% | 0% |
| Clarification correct | 1/9 | 0/9 |
| Move correct | 6/6 | 0/6 |
| Invalid output | 1/35 (2.86%) | 35/35 (100%) |
| Mean inference latency | 15,701.380 ms | 12,336.373 ms |
| Median inference latency | 9,274.730 ms | 7,744.678 ms |
| P95 inference latency | 38,305.226 ms | 34,818.622 ms |
| Median recorded task latency | 9,377.869 ms | 7,744.813 ms |
| P95 recorded task latency | 38,410.431 ms | 34,818.739 ms |
| Median native prefill speed | 95.143 tokens/s | 136.063 tokens/s |
| Median native decode speed | 16.536 tokens/s | 30.443 tokens/s |
| Full-process SYS energy (diagnostic) | 20,167.805 J | 14,095.180 J |
| Full-process SYS J/correct (diagnostic) | 746.956 | Undefined: zero correct |

These are different model deployments and output lengths, not a causal hardware
or native-speedup comparison. Profile medians summarize per-case profiles; they
are not aggregate-throughput measurements. The recorded task boundary is the
frozen evaluator's boundary, not user-facing cold end-to-end time. Energy covers
the entire evaluation child process, including loading, warmup and failed cases.
The meter remains **diagnostic_uncommissioned**; no efficiency winner is selected.

Both reports retain **NOT_COMPARABLE** against the historical reference because
the evaluator hash differs. `completed_qualified` means clean, complete measurement
provenance; it is not a quality PASS. Neither model is admitted to task routing.

The 8B failures are `dev_022`, `dev_023`, `dev_024`, `dev_025`, `dev_026`,
`dev_027`, `dev_028`, and `dev_034`, all clarification categories. Applicable
argument accuracy on the 26 action cases is100%; that does not compensate for
failing to ask required questions or attempting an overwrite. Its invalid rate
also exceeds the frozen2% limit. A full50 milestone is queued without changing
this configuration or examining held-out answers for tuning.

All35 20B outputs failed parsing. Captured text uses Harmony channel/tool markers
and function arguments rather than the frozen parser's accepted action envelope.
Native loading/generation worked; the Secretary integration failed. The record
remains **0/35**. An independent Flash review agreed that protocol mismatch is a
major cause; its suggested offline re-scoring was rejected as evidence of actual
execution. A separate opt-in constrained diagnostic is queued; it cannot repair
or replace this result. No20B full-suite run is justified yet.

Model SHA-256 identities:

- 8B: `120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4`
- 20B: `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901`

Reproduce from that clean application source with the matching private artifact
paths restored in the published configuration copies:

```powershell
python -X utf8 scripts/experiment_tracker.py run --name qwen8b-cpu10-dev-reproduction --dataset dev --config local/qwen8b-config.json --change "Different model deployment; CPU10 context4096; unchanged frozen development workload" --hypothesis "Measure runtime compatibility and development correctness for larger local model; no causal speedup claim" --timeout 900 --capture-full-process-energy
python -X utf8 scripts/experiment_tracker.py run --name gptoss20b-cpu10-dev-reproduction --dataset dev --config local/gptoss20b-config.json --change "Different model deployment; CPU10 context4096; unchanged frozen development workload" --hypothesis "Measure runtime compatibility and development correctness for larger local model; no causal speedup claim" --timeout 900 --capture-full-process-energy
```

Published JSON follows the existing result/KPI/telemetry formats. Private device
path roots are replaced with `${QUALCOMM_TOOLS}`; each object includes its
original file SHA-256 and publication note. Original immutable archives and raw
stdout/stderr remain in ignored local storage; published redacted copies are not
the original sealed archives. The gateway was restored afterward and an actual
native request returned `2 + 3 = 5` before the next isolated campaign began.
