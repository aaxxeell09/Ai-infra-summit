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

These are **screening observations**, not a confirmed speedup. The best observed decode result is approximately 2.0% above the default; paired confirmation is running. Native results identify the resolved devices. NPU operation-level dispatch evidence is a separate diagnostic still pending.

Memory is sampled benchmark-process peak working set. Energy comes from Windows Energy Meter counter deltas, in picowatt-hours converted to joules (`delta × 3.6e-9`). `SYS` is the channel name, not a wall-socket or NPU-only measurement. Full trial energy includes loading and warmup. Screening tokens/J is deliberately null because the native JSON does not report warmup token counts. Do not compare its average watts as decode-only power: initialization and trial durations differ.

The confirmation uses no in-process warmup so all generated tokens are accounted for, with five alternating default/tuned pairs. Its efficiency metric will include model loading, prefill and decoding across the full trial; it is not decode-only tokens/W.
