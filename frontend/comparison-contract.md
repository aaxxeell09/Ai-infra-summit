# Prompt comparison finale

Status: **interactive preview implemented; live bridge pending**. No file operations. `comparison.mjs` exports the request builder, lane descriptions and scripted provider. The UI supports two fixed examples; it does not pretend to answer arbitrary edited prompts.

## Current preview

`createComparisonRequest(snapshot, selectedRow, metric, mode, promptId, requestId)` returns `local-turbo.comparison-request.v1`, the shared prompt, sequential execution, recorded default configuration and, in speed mode, the selected same-model configuration. In routing mode the selected model is null and routing explicitly has `pending_calibration` status. Candidate role names are editorial examples, not real model IDs or classifier decisions.

`createPreviewComparisonProvider().execute(request, {signal, onEvent})` emits `start`, `text` and `complete` events for the default lane followed by the turbo lane. Text chunks are animation fragments, never token counts. It returns `local-turbo.comparison-result.v1` with null timing, output-token counts, winner and speedup; quality is `not_evaluated`. Both lanes use the same scripted answer and animation pace. Abort ends the preview; resets and changed selections discard stale results.

## Live integration requirements

Implement a separate provider and update the view's preview-specific labels and metric bindings together. Do not simply replace the scripted text while leaving candidate names, timing placeholders or preview status in place. No live HTTP endpoints are currently implemented.

Before execution, finalize the request with exact prompt hash, generation limits, seed/temperature, warmup/cache policy, execution order and source evidence. Confirm the requested and effective model/hash, runtime/hash, quantization, backend, threads and context for each lane. Do not send recorded synthetic benchmark token counts as the actual token counts of a natural-language prompt.

- **Speed:** same weights/quantization and equivalent workload controls. Never report shorter output as faster native decoding. If the user selected the default row, identify the comparison as identical settings rather than claiming an optimization.
- **Routing:** choose from measured model profiles with separately calibrated quality/context requirements. Preserve the selected profile, rejection reasons and estimation status. `turbo.policy.choose()` consumes requirements; it does not infer them automatically from arbitrary prompts.
- Execute sequentially on the Latitude to avoid resource contention. Alternate order for repeated confirmation trials. Include model-loading and routing overhead in end-to-end results with a stated scope.
- Each lane returns actual answer, effective configuration acknowledgement, finish reason, provider token counts, TTFT, total time, native decode speed only if available, timing source/scope, retries/fallbacks, error and evaluated quality status/evidence. Keep missing metrics null.
- Correlate all events/results with the request and lane. Preserve completed first-lane evidence if the second fails. No silent preview fallback. Cancellation/timeout must reconcile device job status before retrying.
- One pair supports an observation, not a confirmed tuning-speedup claim. Model switching is a routing experiment, not a same-model tuning gain.

## Demo control hardware

The user confirms Arduino UNO Q is part of the demo hardware. A physical launch button or completion display can feed the same comparison controller after its role and bridge are confirmed. The current preview does not claim that hardware connection. Page one's graphic is unchanged by this iteration.
