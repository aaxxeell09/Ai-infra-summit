# Timing boundaries at the overnight infrastructure revision

Frozen timers remain unchanged. Source references: eval/run_secretary_eval.py::execute, eval/secretary_adapter.py::PreparedFixture, turbo/native.py::_chat_locked, turbo/service.py::completion/secretary.

| Timer | Includes | Excludes | Comparable with |
|---|---|---|---|
| latency_ms | instruction/message construction, reset, template, native generation, native result wrapping | scoring/execution, fixture work | same inference-request boundary |
| task_latency_ms, no energy protocol | inference, score, two temporary fixture copies, golden execution, actual action, snapshot audit | model load and pre-run warmup | same uninstrumented evaluator protocol |
| task_latency_ms, energy protocol | inference/score/actual execution plus final audit | prepared copies/golden execution, load/warmup | same instrumented protocol only |
| warm_task_latency_ms | inference request, score and actual tool | setup/golden/final audit/load | warm_task_v1 |
| native timings.total | geniex_llm_generate wall time | reset/template, outside PDH calls | same native generation boundary |
| native ttft/prompt/decode | backend profile values | may differ semantically by plugin | versioned plugin definitions, not guessed kernel phases |
| service completion elapsed_s | apply/identity, load if needed, chat | HTTP transport, outer fixture work | same service residency/identity policy |
| service secretary elapsed_s | fixture creation, completion, action, verification | HTTP transport | labelled demo task boundary |
| client observed TTFT | first content receipt after HTTP request | none of prior network wait | same streaming protocol; chunks not tokens |

```mermaid
flowchart LR
 A[Load] --> B[Warmup] --> C[Prepare copies and golden]
 C --> D[Prompt/reset/template] --> E[Native generation] --> F[Score + actual action] --> G[Filesystem audit]
```

The energy-instrumented warm-task timer spans D–F; native timer only E. Uninstrumented task timer includes C as called within execution. Historic labels must stay attached to historical data. QAIRT prompt_time is a TTFT proxy in pinned wrapper source, not separately timed prefill. No speedup claim may mix these scopes.
