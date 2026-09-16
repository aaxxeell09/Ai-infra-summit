# Native backend and model routing in the demo

The live answer adapter uses the installed GenieX 0.6.1 SDK. It exposes
llama.cpp CPU, llama.cpp Adreno OpenCL, llama.cpp Hexagon HTP, and the native
Qualcomm QAIRT plugin. The frozen Secretary evaluation is unchanged.

## Two different comparisons

**Speed** keeps the pinned Qwen3-0.6B Q4_0 GGUF weights fixed. The default
lane uses CPU automatic threads; the selected lane applies the recorded CPU,
GPU or HTP configuration. Hybrid is not exposed by this adapter. The chart is
recorded screening evidence; the answers and their metrics are live.

**Model routing** uses `public-demo-v1`, an explicitly experimental task policy.
It requires `allow_uncalibrated: true` in the request. It does not claim a
calibrated quality level or choose a mathematically optimal configuration.

| Public prompt | Automatic route | Reason |
| --- | --- | --- |
| Quick explanation | Qwen3-0.6B, QAIRT NPU | Prefer the registered small Qualcomm bundle for a short answer |
| Multi-step schedule | Qwen3-4B, llama.cpp CPU/10 | Demonstrate delegation to a larger model; greater quality is a hypothesis |

Before inference, the quick policy checks registered files and SDK resolution
in this order: QAIRT, HTP, GPU, CPU. Skipped candidates and reasons are retained.
The schedule policy fails if its 4B route is unavailable. Manual selections fail
if unavailable. **Once inference starts, failures are surfaced without retry or
silent CPU fallback.** A user can select each route explicitly in the demo.

QAIRT uses its separately compiled bundle and compiled context. It is not the
same quantized artifact as the GGUF. Precision is labeled as the bundle's
`geniex.json` declaration (`w4a16` on the installed bundle), or null if unavailable.
Do not present the routed pair as a same-model optimization experiment.

## Identity, measurements and limits

Each job requires a clean committed application checkout and verifies the
recorded baseline weights and benchmark executable. The current SDK libraries
are fingerprinted before native execution. Routing also fingerprints the actual
selected model or full QAIRT bundle; GGUF demo models are pinned by SHA-256.
The runtime binding and selected configuration are exported with the result.

The backend identity, SDK resolved device and offload setting describe the
requested and resolved path. They are not a measurement of utilization or proof
that every operation used that accelerator. `dispatch_verified` stays false
unless separately established. No fabricated NPU utilization meter is shown.

Both lanes stream actual native text. Metrics include load+answer+unload time,
native TTFT excluding load, prefill/decode rates when reported, output length,
native profile, sampler disclosure and finish reason. Pair time also includes
identity checks and any prior resident-model unload. Energy and memory remain
null when this adapter does not measure them. Different answer lengths can
change timing; one pair establishes neither a speed nor a quality winner.

The policy is scoped to two public demo prompts. It is separate from
`turbo.router.plan_route`, which requires measured profiles and explicit quality
evidence for calibrated general routing. Extending the demo policy to arbitrary
requests requires task classification, calibration and correctness evaluation.

## API

`GET /api/live-comparisons/capabilities` lists supported same-model cells and
registered routes. File availability does not promise that model loading will
succeed. Native resolution and loading are checked under the exclusive gateway
lock when the job runs.

`POST /api/live-comparisons` accepts the existing v1 request. For routing,
`selected` is null and the routing object is:

```json
{"selection":"auto","policy":"public-demo-v1","allow_uncalibrated":true}
```

Explicit selections are `qwen06-qairt`, `qwen06-htp`, `qwen06-gpu`,
`qwen06-cpu` and `qwen4b-cpu`. A `route` event precedes the selected lane and
contains the decision and bound configuration. The final result repeats the
decision and each lane's actual native acknowledgement. Cancellation and unknown
execution must reconcile the same job ID before starting another job.

Presentation diagnostics are preserved separately from official evaluation
results. Do not use this two-prompt demonstration as evidence of passing the
unchanged Secretary quality gate.
