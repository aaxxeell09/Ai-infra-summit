# Real-device results

## Screening: September 15, 2026

Actual Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB RAM, Windows 11 ARM64. Qwen3-0.6B Q4_0 SHA-256 `33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb`; official GenieX benchmark v0.6.1 ARM64. Model source revision `50968a4468ef4233ed78cd7c3de230dd1d61a56b` from `unsloth/Qwen3-0.6B-GGUF`.

[Screening manifest](screen-01/sweep.json) preserves commands, binary hash, timings and failures. `<TOOLS>` replaces the private installation directory; all numerical results are unchanged. Each cell contains three measured repetitions after one warmup, with 512 prompt tokens and 128 generated tokens, context 4096, temperature 0 and seed 42. KV resets between runs.

| Setting | Decode tok/s | Prefill tok/s | TTFT ms |
| --- | ---: | ---: | ---: |
| CPU default | 95.95 | 1578.30 | 324.61 |
| CPU 10 threads | 97.91 | 1583.34 | 323.69 |
| CPU 8 threads | 94.14 | 1586.79 | 323.06 |
| GPU | 66.38 | 1030.09 | 497.95 |
| NPU | 36.46 | 1235.16 | 414.72 |
| Hybrid | 38.43 | 1127.47 | 455.02 |

These are **screening observations**, not a confirmed speedup. The best observed decode result is approximately 2.0% above the default; paired confirmation and NPU operation-level diagnostics are reported below. Native results identify the resolved devices.

Memory is sampled benchmark-process peak working set. Energy comes from Windows Energy Meter counter deltas, in picowatt-hours converted to joules (`delta × 3.6e-9`). `SYS` is the channel name, not a wall-socket or NPU-only measurement. Full trial energy includes loading and warmup. Screening tokens/J is deliberately null because the native JSON does not report warmup token counts. Do not compare its average watts as decode-only power: initialization and trial durations differ.

The confirmation uses no in-process warmup so all generated tokens are accounted for, with five alternating default/tuned pairs. Its efficiency metric will include model loading, prefill and decoding across the full trial; it is not decode-only tokens/W.

## CPU confirmation: same model, five alternating pairs

[Confirmation manifest](confirm-01/sweep.json). Five trials per configuration, 15 repetitions per trial, no in-process warmup, cold KV before each repetition. Every measured repetition produced all 128 requested tokens: **9,600 generated tokens and 38,400 prefill tokens per configuration**. Default CPU resolves to 12 decode threads; the selected configuration uses 10. Batch/prefill threads remain at the runtime default in both legs.

| Metric | Default CPU | CPU, 10 decode threads | Observed difference |
| --- | ---: | ---: | ---: |
| Aggregate native decode tok/s | 75.86 | 88.65 | +16.9% |
| Aggregate native prefill tok/s | 1233.85 | 1331.84 | +7.9% |
| Median individual-run decode tok/s | 90.79 | 93.73 | +3.2% |
| Median individual-run TTFT, ms | 400.29 | 393.95 | −1.6% |
| Median process peak working set, MiB | 1526.68 | 1527.04 | Effectively unchanged |
| Pooled full-trial SYS tokens/J | 1.5043 | 1.5089 | +0.3%; no material efficiency gain established |

Aggregate throughput is total native tokens divided by summed native phase times, rather than an arithmetic mean of rates. Pooled efficiency is total generated tokens divided by summed measured SYS energy. It includes model loading, prefill and decode. Native decode throughput and full-trial energy therefore have different, explicitly stated measurement intervals.

**Variability matters.** Default trial medians were 95.24, 59.22, 91.97, 65.35 and 62.62 tok/s; selected trial medians were 97.64, 98.26, 93.09, 93.40 and 93.04. Median-of-trial-medians gives 65.35 versus 93.40 (+42.9%), but this is sensitive to how slowdown episodes fall within trials. We disclose it rather than use that larger number as the headline. Raw runs show dips in both legs. Their cause is unresolved; no temperature/clock trace or per-trial AC-state record was captured in this first confirmation. The next run records power state. Do not extrapolate the observed gain to every power/thermal condition or other models.

All counter conversions were independently checked. The audit prompted fixes to retain failed-trial energy evidence and label invalid counter deltas. See [energy review](../../docs/energy-review.md).

## NPU execution evidence

The separate default-auto diagnostic enabled `GGML_HEXAGON_PROFILE=1` and captured HTP0 operation records with device microseconds/cycles, including matrix multiplication and normalization. [Operation excerpts](dispatch/npu-ops.txt). This establishes actual Hexagon work for this model/runtime path. Profiling substantially reduces speed; its timings are excluded from the clean benchmarks.

The v0.6.1 [device resolver](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/src/device.cpp) maps empty/auto to the pinned NPU path. The default-auto comparison below keeps the strong default-CPU comparison above visible.

## Automatic placement versus selected CPU: battery-powered confirmation

[Manifest](confirm-auto-01/sweep.json). Five alternating pairs, five cold-KV repetitions per trial, no warmup, same model/hash and 512/128 tokens. All 25 repetitions per leg completed the full length (3,200 generated tokens per leg). Every start/end power snapshot reports battery operation.

| Metric | Default auto (HTP0 NPU) | Selected CPU (10 decode threads) |
| --- | ---: | ---: |
| Aggregate native decode tok/s | 36.36 | 97.19 |
| Aggregate native prefill tok/s | 1230.81 | 1547.58 |
| Median individual TTFT, ms | 416.48 | 321.13 |
| Median process peak working set, MiB | 1183.79 | 1527.06 |
| Pooled full-trial SYS tokens/J | 2.1089 | 1.3679 |

CPU decode is **2.67×** the default-auto rate on this fixed workload, while the NPU delivers **1.54×** the full-trial tokens/J and uses less process memory. This is a backend-selection result, not a new kernel claim. CPU uses 54% more measured full-trial SYS energy for the same output count. The energy interval includes loading, prefill and decode and does not establish decode-only power. The CPU-versus-CPU comparison above is the stronger baseline for thread tuning.

[Recommended modes](recommended.json) exports both choices with hashes, workload, power state and scope. These are measured performance profiles, not calibrated secretary-quality tiers.
