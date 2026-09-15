# Turbo MCP agent interface

A bounded Model Context Protocol server exposing the local inference tuner to
coding agents. Agents discover tools, resolve modes to measured models, run
single bounded inference requests, start tuning sweeps, apply validated
recommendations, and run verified secretary fixture tasks — with no shell, no
arbitrary file execution, and no network beyond loopback.

## Protocol

- JSON-RPC 2.0 over stdio, one message per line. Implements the official MCP
  lifecycle: initialize, notifications/initialized, tools/list, tools/call,
  ping (protocol version 2025-06-18). Server info: turbo-mcp v0.2.0;
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

All four endpoints (GET /api/status and /api/modes, POST /api/apply, /api/tune,
and /api/run) must be reachable on loopback for full functionality.

## Tools

### local_models
No arguments. Returns gateway health (runtime_available), installed models,
measured tuning profiles, the modes registry with a calibrated flag per mode
and its source (gateway registry or static config fallback), the current
recommendation, and tuning state. Call first to see which modes are usable.

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
default. Results include resolved_model, content, finish_reason, gateway
usage counts, and evidence (mapping_source, estimate_only, and the backend's
prompt_size_method label, e.g. approximate characters/3, not tokenizer counts).

### local_apply
Applies the gateway's validated recommendation for a mode to the runtime
config via /api/apply. Arguments: mode (required) and optional model_id.
Call after a sweep completes and local_models shows a recommendation for that
mode.

### local_tune
Starts a device sweep via /api/tune. Arguments: model_id (required, must
appear in local_models), optional objective and searchspace labels (bounded
strings passed to the gateway; the sweep executable itself is fixed). A sweep
pauses inference until it finishes.

### local_secretary
One verified secretary fixture task via /api/run. Arguments: mode (required),
prompt (required, 1..8000 chars), optional task_id. Returns the runtime config
that was applied, semantic correctness (passed), errors, usage, resolved
model, and total elapsed_s. This is the E2E verification primitive: agents run
the same task_id under different modes and compare passed and runtime_config.

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

Once MCP passes live verification against the gateway, a generic
OpenAI-compatible client note can be added here. No additional harness
dependencies are needed or included.

## Privacy and safety

- Loopback HTTP only; remote endpoints are disabled by construction and no
  tool accepts URLs.
- No shell, no subprocess, no file I/O beyond stdio; no state between requests
  beyond the initialization flag.
- No credential storage or logging of secrets; tool results echo only gateway
  responses.
- After models are installed locally, inference stays on device. The gateway
  binds to 127.0.0.1 by design.
