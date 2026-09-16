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
- The Compare screen now adds a compact latest-device study sourced from the published QAIRT full runs and the 4B/8B model milestones. It keeps the original same-model tuning chart intact, labels the study experimental and does not name a qualified winner.
- The final screen compares **Default setup** with **Local Turbo**, using one shared prompt and launch button.
- **Speed** carries the recorded default and the selected settings for the same model. **Model routing** illustrates candidate roles for a quick explanation or reasoning question; no calibrated model choice is claimed.
- Two sequential scripted answers, equal animation pacing, stop/reset and stale-result protection. Per-answer clocks measure browser animation only; inference timings and answer quality remain unavailable, with no fabricated winner.

## What is not connected

The answer comparison is a preview. It does not call inference, execute a calibrated router, apply settings or grade answers. The single provider in `public/app.mjs` is `createPreviewComparisonProvider()` from `public/comparison.mjs`. The live request/result handoff is specified in [comparison-contract.md](comparison-contract.md); a live bridge and its rendering bindings are still needed.

The earlier `public/demo.mjs`, its tests and `task-contract.md` preserve the previous file-task adapter for reference. They are **not used by the current screen**. File operations are no longer the presentation workflow.

## Backend boundary

Implemented server endpoints remain read-only: `GET /api/health` reports recorded mode; `GET /api/recorded` reads sanitized `screen-01` records; `GET /api/latest-results` summarizes the published QAIRT, 4B and 8B evaluation artifacts without exposing task contents. No live execution endpoint is claimed. `public/data.mjs` normalizes recorded tuning evidence, `public/latest.mjs` validates the latest study, and `public/comparison.mjs` owns the prompt comparison preview.

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
