# Turbo MCP agent interface

A bounded Model Context Protocol server exposing the local inference tuner to
coding agents. Agents discover tools, resolve modes to measured models, run
single bounded inference requests, start tuning sweeps, apply validated
recommendations, and run verified secretary fixture tasks — with no shell, no
arbitrary file execution, and no network beyond loopback.

## Protocol

- JSON-RPC 2.0 over stdio, one message per line. Implements the official MCP
  lifecycle: initialize, notifications/initialized, tools/list, tools/call,
  ping (protocol version 2025-06-18). Server info: turbo-mcp v0.3.0;
  declared capability: tools.
- No prompts, resources, sampling, or roots. Tool inputs are validated against
  the JSON Schema in tools/list before execution; failures return isError
  results with a machine-readable error field, not protocol crashes.
- Endpoint: the gateway base URL defaults to http://127.0.0.1:8080 and may be
  overridden only to another loopback address via the TURBO_BASE_URL env var.
  Non-loopback scheme/host combinations are rejected at construction.

## Prerequisite

The MCP server is a client of the existing local gateway (turbo/service.py).
Start the gateway first, from the parent checkout:

    cd /Users/user/Documents/Qualcomm/Ai-infra-summit
    python3 -m turbo.service --config local/config.json

These endpoints (GET /api/status and /api/modes, POST /api/apply, /api/tune,
and /api/run) must be reachable on loopback for full functionality; GET
/api/tasks is also used to validate local_secretary task_id selectors.

## Launch and use sequence

1. Start the gateway (see Prerequisite) and confirm it answers GET /api/status
   on loopback.
2. Register the MCP server with your client using configs/mcp.example.json
   (stdio command, repo root as working directory). Optionally set TURBO_BASE_URL
   to a different loopback address.
3. Initialize: send initialize with protocolVersion 2025-06-18, wait for the
   result, then send notifications/initialized. Before this handshake the
   server rejects tools/call with a JSON-RPC error.
4. Call local_models and read modes.<name>.available and model_id before other
   tools. Choose a mode whose available=true (measured point exists).
5. local_run for generic inference; local_apply to switch the runtime config to
   a mode's validated recommendation; local_tune to sweep (pauses inference
   until done; GET /api/status tuning block reports progress).
6. local_secretary for verified fixture runs. Exactly one of prompt or task_id.

This sequence is verified by the focused test suite: unit tests over fixtures
captured from the real parent gateway, plus stub-dylib integration tests that
boot the real parent Engine over loopback HTTP and drive a piped stdio MCP
subprocess (read endpoints and /api/apply only; no inference, no tune, no
hardware calls). Latitude end-to-end on-device verification has not been run.

## Tools

### local_models
No arguments. Returns gateway health (runtime_available), installed models,
measured tuning profiles, the current recommendation, tuning state, and a modes
object keyed fast/efficient/balanced. Each mode entry carries:

- available and model_id: true plus the resolved id only when a measured point
  exists for that mode (see Modes and calibration honesty).
- performance_calibrated: mirrors available (a measured point exists); it says
  nothing about output quality.
- quality_calibrated: the recommendation scope's quality_calibrated flag;
  false unless the sweep explicitly verified quality.
- source: "gateway" or "static_config_fallback" when available, else null.

Call first to see which modes are usable.

### local_run
One bounded generic inference request via /v1/chat/completions.

| argument   | type    | required | bounds                        |
|------------|---------|----------|-------------------------------|
| mode       | string  | yes      | fast \| efficient \| balanced |
| messages   | array   | yes      | 1..64 text-only messages      |
| max_tokens | integer | no       | 1..2048, default 256          |
| model      | string  | no       | explicit model id; overrides the mode mapping |
| task_id    | string  | no       | caller correlation id, echoed back |

Mode resolution reads the gateway /api/modes registry; unmapped modes return
available=false with the registry's reason and never substitute an unmeasured
default. Results include available, mode, resolved_model, route, task_id,
content, finish_reason, usage (gateway counts), estimate_only,
prompt_size_method (an approximate label, not tokenizer counts), and evidence
(mode, requested_model, mapping_source: gateway, static_config_fallback, or
explicit_request; resolved_model).

### local_apply
Applies the gateway's validated recommendation for a mode to the runtime
config via /api/apply. Arguments: mode (required) and optional model_id.
Call after a sweep completes and local_models shows a recommendation for that
mode. Returns applied, mode, model_id, runtime (the applied device, threads,
and context), evidence, elapsed_s, and gateway_response.

### local_tune
Starts a device sweep via /api/tune. Arguments: model_id (required, must
appear in local_models), optional objective (one of fast, efficient, balanced,
decode, prefill), and an optional search_space object with exact gateway axes
(unknown keys are rejected before the request; the sweep executable itself is
fixed). A sweep pauses inference until it finishes. Accepted axis keys:

| key             | type              | notes             |
|-----------------|-------------------|-------------------|
| devices         | array of strings  | nonempty          |
| threads         | array of integers | nonempty          |
| contexts        | array of integers | nonempty          |
| prompt_tokens   | integer           | >= 1              |
| gen_tokens      | integer           | >= 1              |
| warmup          | integer           | >= 0              |
| repeats         | integer           | >= 1              |
| batch           | integer or null   | >= 0              |
| ubatch          | integer or null   | >= 0              |
| energy_channel  | string or null    | nonempty when set |
| temperature     | number            |                   |
| seed            | integer           |                   |

The gateway merges the object over its own defaults, so omitted axes keep the
gateway defaults. Returns accepted, requested, gateway_response, elapsed_s.

### local_secretary
One verified secretary fixture task via /api/run. Arguments: mode (required)
and exactly one of prompt (1..8000 chars, non-blank) or task_id (gateway
gold-fixture selector matching tNN, e.g. t13; verified against GET /api/tasks
before the run; task_id alone runs and grades the stored prompt). Exactly-one
is enforced server-side. Returns available, mode, task_id, resolved_model,
content, result (tool-call outcomes), passed, errors, verification, usage,
runtime_config (the applied runtime config), elapsed_s (full task timing:
fixture creation, profile validation, model load if cold, inference, tool
execution and verification), gateway_elapsed_s, and gateway_response. This is the E2E
verification primitive: agents run the same task_id under different modes and
compare passed and runtime_config.

## Modes and calibration honesty

The gateway's approved-modes registry is the single source of truth for mode
to model mapping. The server keeps a static fallback mapping only for gateways
that predate /api/modes, and labels any such result mapping_source=
static_config_fallback. A mode with no eligible measured model returns
available=false; the server never presents an uncalibrated default as a
calibrated choice and never invents model ids.

## Agent integration

Reference configs/mcp.example.json for the generic stdio command shape
(command + args launching python3 -m turbo.mcp_server from the repo root).
Adapt the exact registration syntax to your MCP client's own documentation;
this repo does not assert any specific client's config format.

The gateway also exposes an OpenAI-compatible /v1/chat/completions endpoint;
the MCP server is the agent-facing wrapper for it, and a direct
OpenAI-compatible client note can be added here once live verification
against the gateway has been run. No additional harness dependencies are
needed or included.

## Privacy and safety

- Loopback HTTP only; remote endpoints are disabled by construction and no
  tool accepts URLs.
- No shell, no subprocess, no file I/O beyond stdio; no state between requests
  beyond the initialization flag.
- No credential storage or logging of secrets; tool results echo only gateway
  responses.
- After models are installed locally, inference stays on device. The gateway
  binds to 127.0.0.1 by design.
