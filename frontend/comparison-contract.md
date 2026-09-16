# Prompt comparison finale

Status: **live CPU Speed path verified in the browser on the Latitude**; [rehearsal evidence](../benchmarks/results/live-ui-1720/README.md). Model routing and GPU/NPU answer comparisons remain unavailable. No file operations. `comparison.mjs` exports the request builder, lane descriptions and scripted provider; `live-comparison.mjs` supplies the opt-in native provider. The UI supports two fixed examples, not arbitrary edited prompts.

## Current preview

`createComparisonRequest(snapshot, selectedRow, metric, mode, promptId, requestId)` returns `local-turbo.comparison-request.v1`, the shared prompt, sequential execution, recorded default configuration and, in speed mode, the selected same-model configuration. In routing mode the selected model is null and routing explicitly has `pending_calibration` status. Candidate role names are editorial examples, not real model IDs or classifier decisions.

`createPreviewComparisonProvider().execute(request, {signal, onEvent})` emits `start`, `text` and `complete` events for the default lane followed by the turbo lane. Text chunks are animation fragments, never token counts. It returns `local-turbo.comparison-result.v1` with null timing, output-token counts, winner and speedup; quality is `not_evaluated`. Both lanes use the same scripted answer and animation pace. Abort ends the preview; resets and changed selections discard stale results.

The view also keeps independent browser animation clocks: start on each lane’s `start`, freeze on `complete`, and exclude time spent queued. They are labelled **Animation time**, stored outside provider results, and never used to compute a winner or speedup. Stopping or changing examples clears them.

## Live integration requirements

The separate live provider updates the view's labels and metric bindings. `/api/live-comparisons` creates the native job, a request-ID endpoint polls its state, and a cancel endpoint requests native cleanup. The requirements below remain the integration contract; the current narrow implementation supports CPU Speed only.

Before execution, finalize the request with exact prompt hash, generation limits, seed/temperature, warmup/cache policy, execution order and source evidence. Confirm the requested and effective model/hash, runtime/hash, quantization, backend, threads and context for each lane. Do not send recorded synthetic benchmark token counts as the actual token counts of a natural-language prompt.

- **Speed:** same weights/quantization and equivalent workload controls. Never report shorter output as faster native decoding. If the user selected the default row, identify the comparison as identical settings rather than claiming an optimization.
- **Routing:** choose from measured model profiles with separately calibrated quality/context requirements. Preserve the selected profile, rejection reasons and estimation status. `turbo.policy.choose()` consumes requirements; it does not infer them automatically from arbitrary prompts.
- Execute sequentially on the Latitude to avoid resource contention. Alternate order for repeated confirmation trials. Include model-loading and routing overhead in end-to-end results with a stated scope.
- Each lane returns actual answer, effective configuration acknowledgement, finish reason, provider token counts, TTFT, total time, native decode speed only if available, timing source/scope, retries/fallbacks, error and evaluated quality status/evidence. Keep missing metrics null.
- Correlate all events/results with the request and lane. Preserve completed first-lane evidence if the second fails. No silent preview fallback. Cancellation/timeout must reconcile device job status before retrying.
- One pair supports an observation, not a confirmed tuning-speedup claim. Model switching is a routing experiment, not a same-model tuning gain.

## Demo control hardware

The user confirms Arduino UNO Q is part of the demo hardware. A physical launch button or completion display can feed the same comparison controller after its role and bridge are confirmed. The current preview does not claim that hardware connection. Page one's graphic is unchanged by this iteration.
