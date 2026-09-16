# Tuner → applied configuration → native task through MCP

The previously queued Latitude integration run finished at 14:11 UTC on
September 16, 2026. Its complete artifacts were retrieved at the 16:00 UTC cutoff;
no new experiment was launched to obtain this result.

**Both rounds applied a measured recommendation and completed the requested
physical invoice move through MCP. Both existing exact-call checks still fail.**
This is a public-fixture integration diagnostic, not a frozen Secretary quality
PASS, paired speed comparison or demonstrated energy-efficiency improvement.

| Round / selected mode | Actual configuration | Feedback loop | Broader diagnostic | Whole round |
|---|---|---:|---:|---:|
| 0 / Fast | llama.cpp CPU, 10 threads, context 4096 | 19.347 s | 30.296 s | 67.893 s |
| 1 / Efficient | llama.cpp CPU, 6 threads, context 4096 | 26.577 s | 37.521 s | 65.536 s |

Device: Latitude 7455, Snapdragon X Elite, 32 GB. Model:
Qwen3-4B-Instruct-2507 Q4_0, SHA-256
`e0ba675d86ab277c61701c6793659b2ae801d95e3be791464c321e6fbf613be2`.
Runtime: GenieX 0.6.1 / llama.cpp CPU. Clean application source:
`3380a652dda56b5389c84b2c545fc60645f566ff`.

## Independently checked

- Each saved recommendation matches the configuration returned by MCP apply.
- The native diagnostic confirms the same model, SDK binding, plugin, device,
  threads and context; the owner independently rechecked those identities.
- Both arithmetic smoke responses are `5`.
- Both invoice runs move `drafts/hexagon-invoice.md` to
  `invoices/2026/hexagon-invoice.md`, preserving its bytes and all 11 other files.
  Every copied final-workspace file was independently hashed and compared with
  the native report, not just the report's success flag.
- Original MCP wire payloads match their embedded reports and verifier fields.
  `final_state_match=true` and `execution_ok=true`; `passed=false` and
  `calls_match=false`. These grades are retained without rescoring.

## Measurement boundaries

The feedback loop covers model calls, tools and loop checks, excluding loading
and fixture creation. The broader diagnostic additionally covers artifact
hashing, model loading, grammar canary, fixture creation, verification and model
destruction. Whole-round time includes tuning, apply, arithmetic and the MCP
feedback diagnostic. These are different scopes, not interchangeable latencies.

Each round independently tunes two thread counts (6 and 10), with two measured
repeats and no warmup, before applying its mode. Native profiles show **25 actual
prompt tokens and 32 generated tokens**, despite the nominal prompt-token axis
being 128 because a prompt file was supplied. All four tuning trials and native
logs are retained. Do not describe this as a 128-token prefill workload.

“Efficient” names the exploratory full-trial tokens/J objective. Meter resolution
is not commissioned, task-level energy was not captured, and neither mode is
quality-qualified. This single sequential observation per mode does not establish
a causal speedup, repeatability, or an efficiency winner. Grammar and the task
output budget are separate diagnostic controls beyond the bound tuning axes.

## Reproduction and artifacts

With exclusive hardware, the same installed SDK/weights, and the recorded private
service config/search axes, the original command was:

```powershell
python -X utf8 scripts/verify_tuner_loop.py --config local/mcp-config.json --model-id qwen4b --search-space local/mcp-search.json --output local/bound-mcp-loop-1400 --rounds 2 --feedback-mcp
```

Use a fresh output path for another attempt. `feedback-config-*.json` preserve the
actual exported native configurations, with `${QUALCOMM_TOOLS}` placeholders.
`integration.json` holds the full tune/apply/inference/MCP transcript; `tuning/`
holds trials and recommendations; `feedback-*/` holds native diagnostic reports.
`publication.json` records original/published hashes and independent checks.
Original bytes and duplicate public fixture contents are retained privately.
Private directory prefixes were redacted, including nested JSON strings/keys.

## Gateway restoration failed

The supervisor records a failed attempt to restart `Qualcomm-Turbo-Service`.
At the cutoff the task was disabled, no Python/native benchmark process was
observed, and port 8083 had no listener. The service was not verified restored.
A later read-only SSH call failed after retrieval; access remains unreliable.
The standalone presenter CLI added later is separately locally tested and still
needs its own successful hardware rehearsal.
