# Local Turbo demo UI

Three screens: **Machine → Compare → In action**. Local-only, dependency-free Node.js 20+ server and browser ES modules.

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:4173. Set `PORT` to change the port. The server binds to loopback only. Refresh the browser after source edits; restart the server after editing `server.mjs`. No dependency installation or build is required.

```sh
npm run check
npm test
```

## What works

- Three responsive screens, hash navigation and browser history, reduced-motion support.
- All ten actual recorded screening configurations, ranking by generation speed, prefill speed or TTFT.
- Selection details, provisional configuration export, raw evidence inspection/download.
- Deterministic in-memory move and clarification scenarios with reset/replay. These are explicitly simulated and never call a model or touch user files.
- Explicit unavailable/error states; no fabricated metrics or silent sample fallback.

## What is not connected

There is no live Latitude connection, benchmark execution, model loading, filesystem executor, or quality grader in this frontend. “Compare configurations” displays recorded results and an animation; it does not start a benchmark. Configuration export downloads a JSON recommendation, not an applied device setting. The task screen sends the selected model/configuration into a task-provider contract. Its default preview provider records that context but does not execute it. The injectable live provider requires configuration application, matching result identity and task evidence before rendering success; see [task contract](task-contract.md).

## Backend boundary

The only implemented frontend-server endpoints are:

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | Reports recorded mode and `live_backend: false`. |
| `GET /api/recorded` | Reads the existing sanitized `benchmarks/results/screen-01` manifest and companion files. Returns `local-turbo.recorded.v1`. Missing/corrupt data returns 503. |

`public/data.mjs` translates these backend records into view data. `public/app.mjs` renders the view; `public/demo.mjs` owns isolated examples, the request/result contract and the injectable live task provider. Add the real bridge behind a separate provider rather than fetching directly from components.

### Recorded response

```js
{
  schema_version: 'local-turbo.recorded.v1',
  mode: 'recorded',
  source: 'benchmarks/results/screen-01',
  manifest_sha256: '...',
  device: { name, processor, chipset, ram_gb, gpu, platform },
  runtime: 'GenieX 0.6.1',
  manifest: /* existing turbo.sweep.v1 */,
  reports: { /* cell ID -> existing native schema 4 JSON, or null */ }
}
```

The device identity is repository-provided target metadata, not detection of the preview's host. The model and runtime hashes, trial settings and timings come from the records. The manifest hash is computed from the file bytes when serving.

| UI value | Existing source |
| --- | --- |
| Model and identity | `manifest.model_name`, `model_sha256`, `runtime_sha256` |
| Requested backend | Manifest `command` flag `--device` |
| Reported device | Companion `device_id`; null means not reported |
| Threads and workload | Companion `params`, validated against command flags |
| Generation | `agg.decode_tps.median` |
| Prompt processing | `agg.prefill_tps.median` |
| First response, ms | `agg.ttft_ms.median` (not raw run `ttft_us`) |
| Peak process memory | `telemetry.peak_working_set_mb`, divided by 1024 for GiB |
| Failures | Manifest `status`, `exit_code`; missing reports and inconsistent trials also remain visible |

Rank only completed, full-length comparable trials with valid provenance. Keep ties. Current ranking is a metric-specific recorded comparison, **not a call to `turbo.policy.choose`** and not quality-calibrated model routing. Do not use the `bench.v1` client-observed measurements in this native chart without a separate explicit normalization and timing-source label.

### Integration still to agree with backend owner

No endpoints below are claimed to exist. The live provider will need these capabilities:

1. Read target/runtime health and locally available model identities, including supported configurations.
2. Start one bounded calibration job and receive queued/running/completed/failed cell events plus original result records. Support cancellation and reconnects without restarting a benchmark.
3. Return a recommendation with objective, rejected candidates, provenance, confirmation and measured-quality status. Preserve `estimate_only` for router latency predictions.
4. Apply a selected configuration and report whether application succeeded before executing a task.
5. Execute a request inside disposable fixtures, returning snapshot-bound tool actions, clarification, before/after inventories, correctness verdict with grading evidence, retries and real task time. A valid tool schema alone is not a correctness verdict.

Use relative URLs through the local frontend server for the bridge. Keep addresses and credentials outside public code. Do not silently change data modes when a live request fails. Never infer NPU dispatch from its requested flag or a reported device ID alone. Energy and power need their own explicitly scoped views; do not mix full-process SYS energy with decode-only speed.

`ux-spec.json` is the versioned screen/state specification for continued design iteration.

## UX quality check

The final screen is the end of the demonstration: same model and selected settings, request, visible workspace result, then optional run evidence. It does not jump back to the start after completion. Preview has no invented latency or model-quality verdict. Changing the selected configuration clears the previous task outcome.

The request/result and error paths are covered by Node tests; browser checks cover the three-screen flow, selection handoff, both scenarios, reset and evidence. See [quality review](quality-review.md).
