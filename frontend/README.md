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

- Three responsive screens: machine identity, recorded configuration comparison, verified local-action finale.
- All ten recorded screening configurations and provisional configuration/evidence export.
- The Compare screen adds one compact QAIRT before/after finding beneath the original same-model tuning chart. Larger-model milestones remain available in Benchmark evidence; the main presentation labels the result experimental and does not name a qualified winner.
- The final screen runs one fixed public-fixture invoice task through the real opt-in MCP runner when the server is configured on the Latitude.
- The UI reports the physical file result, content hash, backend timing and unchanged exact-call verdict separately. It never turns a successful move into a broader quality pass.

## Live runner configuration

Run the frontend server from the same clean checkout as the native SDK/model configuration:

```powershell
$env:LOCAL_TURBO_DEMO_CONFIG = "local/qwen4b-cpu10-config.json"
npm --prefix frontend run dev
```

`LOCAL_TURBO_DEMO_CONFIG` resolves from the repository root. `LOCAL_TURBO_DEMO_PYTHON` can select the native ARM64 Python executable. Without a valid config, the finale remains visibly offline and the run endpoint returns 503; there is no scripted or recorded fallback. Every attempt writes a fresh ignored directory under `local/ui-demo-runs/`.

## Backend boundary

`GET /api/health`, `GET /api/recorded` and `GET /api/latest-results` serve recorded evidence. `GET /api/demo/status` reports only whether the fixed runner is ready. `POST /api/demo/invoice` launches `scripts/demo_invoice_mcp.py` with fixed model/task identities, a server-owned config path and a fresh server-owned output directory. The browser cannot provide paths, commands, prompts or model IDs. The response omits private device paths and returns only the verified move, safe configuration fields, timing scopes and the original exact-call flags.

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

Keep device addresses and credentials outside the browser and repository. The current endpoint is intentionally colocated with the Latitude runner; remote transport can be added behind the server without changing the browser contract. Never silently replace failed live runs with scripted answers.

`ux-spec.json` is the current versioned UX source. The initial file-task quality review is historical; the prompt comparison has five additional tests covering baseline identity, illustrative routing, sequential preview events, abort and unsupported prompts.
