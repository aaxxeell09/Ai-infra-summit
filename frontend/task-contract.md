# Previous file-task integration contract

Superseded for the presentation UI by [comparison-contract.md](comparison-contract.md). Retained as a backend reference; the current In action screen does not use this adapter.

Status: **frontend adapter implemented; device bridge not connected**. This is a view-facing contract, not an assertion that HTTP endpoints exist. Keep credentials and device addresses on the local server.

## Wiring

`public/app.mjs` creates `createPreviewTaskProvider()` in one place. Replace that with `createLiveTaskProvider(deviceBridge)` once the backend implements the two operations below. The same three screens and result rendering remain in use. Add a local server bridge and its static asset route explicitly; do not point the browser directly at a private device address.

The selected metric and configuration are passed to `createTaskRequest`. This includes cell ID, exact model and runtime hashes, plugin, requested device and the full recorded parameters. Preview carries this identity without claiming it was applied. Changing selection clears prior task results.

### 1. `bridge.prepare(request, { signal })`

Before starting inference:

- Verify the exact selected model, runtime, plugin, device and parameters. If unsupported, fail explicitly; never silently substitute another model or configuration.
- Apply the settings and acknowledge their effective values.
- Create a fresh, disposable `budget-files.v1` fixture: `budget-final.csv`, `budget-draft.csv`, and `meeting-notes.md` in Workspace; Presentation empty. Return authoritative file metadata in the view shape used by `initialFiles()`.
- Return `{session_id, snapshot_id, fixture_id, configuration_applied: true, effective_configuration, files}`. `effective_configuration` must match the request identity and parameters. The UI displays “Applied on the device” only after this acknowledgement.

This is a backend attestation, not independent proof of NPU computation. Preserve reported device and operation-level dispatch evidence separately in the run result.

### 2. `bridge.run(requestWithSessionAndSnapshot, { signal })`

Own the complete chain: model inference → decoded intent/action → protected file execution or clarification → postcondition checks → result. Execute only within the disposable fixture with traversal, symlink and overwrite protections. No arbitrary shell from model output.

Return `local-turbo.task-result.v1` with:

| Field | Meaning |
| --- | --- |
| `mode` | `live` |
| `request_id`, `session_id` | Exact correlation with this request and prepared session |
| `before_snapshot_id`, `after_snapshot_id` | Snapshot-bound result; before must match preparation |
| `effective_configuration` | Exact acknowledged model/runtime hashes, cell, plugin, device and parameters |
| `status` | `completed`, `clarification` or `failed` |
| `message` | Plain-language observed outcome; rendered as text, never HTML |
| `model_output` | Actual model output for inspection; no replayed example |
| `action`, `clarification` | Returned action or clarification question; null when absent |
| `files` | Authoritative after-inventory; never optimistically moved by the browser |
| `quality` | `{status: 'passed' | 'failed' | 'not_evaluated', checks: [{name, passed}]}` |
| `task_time_s`, `ttft_ms` | Measured values or null |
| `timing_source`, `timing_scope` | Clock/provider and exact interval definitions; both required to display numeric timings |

A passing quality verdict requires explicit `intent`, `action` and `file_postconditions` checks. The adapter also rejects a claimed successful move whose final inventory differs from the prepared inventory with only the requested file moved. For clarification, no action or changed inventory is accepted. Valid JSON alone is not a passing task. An explicit `quality.status: "not_evaluated"` renders “Checks pending.” Missing quality status or a passing verdict without its required checks is rejected. Backend semantic evaluation remains necessary; frontend checks do not replace it.

Include additional evidence in the result for its expandable inspector/export: reported device, dispatch proof/status, raw provider token counts, finish reason, retries, failures/fallbacks, tool execution time, inference time, before inventory, and capture timestamps. Do not count stream chunks as tokens or mix client-observed task timing with the recorded native benchmark chart.

## Lifecycle and errors

Live: idle → preparing → running → completed / clarification / failed. Preview: idle → playing preview → example outcome. The preview never calls the bridge. Device failures never switch into preview.

The UI bounds waiting to two minutes and discards late responses. `AbortSignal` stops waiting and should propagate to the backend, but does not establish that device execution was cancelled or undone. Navigating away is blocked during an active live request. On timeout, the UI reports unknown execution status. The bridge must reconcile outstanding jobs before accepting another preparation, use request IDs for idempotency, and never blindly replay a possibly executed action. Every new run uses a fresh isolated fixture; resetting the view never claims to undo real files.

## Existing backend gap

`turbo.bench.run_completion()` returns `bench.v1` inference text, usage, transport/completion status and client-observed timings. It does not apply/verify device-thread settings, execute file actions or grade intent. `ActionCodec.decode()` validates and expands the representation; it is not a semantic quality verdict. Those responsibilities must be implemented in the device bridge before connecting this provider.

## Acceptance

Run the real model on the Latitude with one selected configuration; show the correct final-file move and preserved draft. Then run the ambiguous scenario and show clarification with unchanged files. Demonstrate a failed check, unavailable metric, configuration mismatch and disconnected device without any synthetic success. Unit tests use test doubles to validate adapter behavior; they are not hardware measurements.
