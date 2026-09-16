# Final browser routing rehearsal

All six attempts immediately preceding presentation freeze are retained, including cancellation, truncation and incorrect answers. These are public-prompt diagnostics, not the frozen Secretary benchmark. Model output is unmodified. Source commits, artifact/runtime hashes and generation controls are in each result.

- Original 128-token schedule attempt (493311a7): both outputs truncated.
- Two original QAIRT explanation attempts (da6ce7a4, 535f2327): completed, but failed the requested two-sentence format.
- Cancelled attempt (525461bd): no completed lanes.
- Shared concise instruction, QAIRT explanation (9f9c35d5): completed. CPU 2.15 s lane time; QAIRT 4.34 s, 30.60 ms native TTFT, 82.26 decode tokens/s. QAIRT still returned one sentence. Different artifact/sampler/output length; not an end-to-end speedup claim.
- Shared concise instruction and 384-token budget, 4B schedule (cee46e9c): complete but incorrect. CPU answered 15:05 and 4B answered 13:35; the required latest start is 13:05 when all preparation finishes before 14:00. Do not present this as a successful reasoning demo.

Presentation recommendation: demonstrate the local QAIRT explanation and real backend routing/metrics. The larger-model route is connected but correctness remains unresolved. Energy and utilization were not measured.
