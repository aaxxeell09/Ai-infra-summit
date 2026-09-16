# Local Turbo demo UI

Three screens: **Machine → Compare → In action**. Local-only, dependency-free Node.js 20+ server and browser ES modules.

The header uses a typographic `localturbo` wordmark in a locally bundled Manrope variable font; the matching `lt` favicon is derived from the same letterforms. The font was converted to WOFF2 from the [Google Fonts Manrope source](https://github.com/google/fonts/tree/main/ofl/manrope) (source TTF SHA-256 `d0639be45d0af36e798172419d7bd173c4bd4f29e2b76cbb69db1d11bf8b0a40`) and retains its [SIL Open Font License](licenses/Manrope-OFL.txt). The interface font remains the local system sans serif.

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

- Three responsive screens: machine identity, recorded configuration comparison, prompt/answer finale.
- All ten recorded screening configurations and provisional configuration/evidence export.
- The Compare screen adds one compact QAIRT before/after finding beneath the original same-model tuning chart. Larger-model milestones remain available in Benchmark evidence; the main presentation labels the result experimental and does not name a qualified winner.
- The final screen compares **Default setup** with **Local Turbo**, using one shared prompt and launch button.
- **Speed** carries the recorded default and the selected settings for the same model. **Model routing** illustrates candidate roles for a quick explanation or reasoning question; no calibrated model choice is claimed.
- Optional real sequential answers on the Latitude, with applied configuration acknowledgements, native metrics, cancellation and result export. Without the live connection configured, an explicitly labelled scripted preview remains available.

## Live scope

The Speed comparison can call actual inference and apply the recorded CPU settings using `public/live-comparison.mjs`. The [browser rehearsal](../benchmarks/results/live-ui-1720/README.md) verifies that path. Routing, GPU/NPU answer comparisons and answer-quality grading remain unavailable. See [comparison-contract.md](comparison-contract.md) and the opt-in instructions below.

The earlier `public/demo.mjs`, its tests and `task-contract.md` preserve the previous file-task adapter for reference. They are **not used by the current screen**. File operations are no longer the presentation workflow.

## Backend boundary

Recorded endpoints remain read-only: `GET /api/recorded` reads sanitized `screen-01` records and `GET /api/latest-results` summarizes the published studies. The optional `/api/live-comparisons` proxy connects the native gateway; `GET /api/health` reports whether that connection is configured. `public/data.mjs` normalizes recorded tuning evidence, `public/latest.mjs` validates the latest study, and the comparison providers keep preview and live results explicit.

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

### Live integration

See [comparison-contract.md](comparison-contract.md). Keep device addresses/credentials on the local server. Configuration tuning must use identical model weights; multi-model routing is a separate experiment. Never silently replace failed live runs with scripted answers.

`ux-spec.json` is the current versioned UX source. The initial file-task quality review is historical; the prompt comparison has five additional tests covering baseline identity, illustrative routing, sequential preview events, abort and unsupported prompts.

## Opt-in live answer demo

The native gateway now supports the final screen's two public prompts using the
recorded 0.6B weights and CPU settings. Enable `live_comparison_enabled: true` in
its private config, then start this frontend with a local gateway or SSH tunnel:

```sh
LOCAL_TURBO_LIVE_URL=http://127.0.0.1:18083 PORT=4180 node server.mjs
```

The URL stays in the Node process. With no URL configured the labelled preview
remains available. A configured but unreachable live device is an error; it never
silently substitutes scripted answers. Invalid non-loopback/credential URLs
prevent startup. The existing visual design is preserved.

Choose **Speed** and a **CPU configuration**, then **Run on Latitude**. Both
answers come from sequential native inference with the selected model/config
acknowledged. The live view shows lane load+answer+unload time, native TTFT,
actual output-token counts and native decode rate. It does not use browser
animation time as inference latency. Recorded charts remain recorded charts.
Routing and GPU/NPU answer comparisons are not enabled by this adapter.

Stop requests cancellation and waits for native cleanup. Unknown execution
retains its request ID in session storage; **Check device status** reconciles it
before another run. First-lane evidence survives second-lane failure. Download
the complete result for configuration hashes, generation policy and timing
scopes. Different answer lengths and uncontrolled sampling remain visible;
one pair does not establish a confirmed speed or quality win.
