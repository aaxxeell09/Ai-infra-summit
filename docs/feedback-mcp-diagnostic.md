# Feedback diagnostic MCP wrapper (opt-in, fixture-only)

`turbo/feedback_mcp.py` is a minimal stdio MCP server that exposes exactly one
tool, `local_feedback_diagnostic`. Each call runs the committed
`scripts/run_secretary_feedback.py` in a fresh subprocess with
`--enable-candidate --constrain-tools`, a mapped config path, the requested
demo `task_id`, and a unique output directory, via argv with no shell and a
180 s timeout. It is a diagnostic transport, not a production service, and it
performs no rescoring, repair, or quality claims.

## Starting the server

```sh
python -m turbo.feedback_mcp \
  --enable-candidate \
  --model qairt-secretary=local/qairt-secretary.json \
  --output-root local/feedback-mcp-runs
```

- `--enable-candidate` is required; the server refuses to start without it,
  mirroring the script's own guard.
- `--model NAME=PATH` builds the startup allowlist (repeatable). `NAME` is the
  only model identifier a client may pass; `PATH` must be an existing config
  file and is never accepted at call time. Use private configs under the
  ignored `local/` tree.
- `--output-root` is the startup output root; every invocation creates a fresh
  timestamped subdirectory, and all raw report artifacts there are preserved,
  including on timeout or failure.

## Tool contract

`local_feedback_diagnostic` takes only `task_id` (a public demo fixture id,
validated against the task list) and `model_id` (from the startup allowlist).
Paths, commands, prompts, and workspace are never accepted as call arguments.
Concurrent invocations are rejected; one diagnostic runs at a time.

The result returns the raw `diagnostic.json` record verbatim, including the
original `existing_demo_verification` values, plus model/sdk/source/timing
identity (`version`, `git_commit`, `model_sha256`, `sdk_identity`,
`grammar_enabled`, `grammar_canary`, `diagnostic_elapsed_s`, `timing_scope`).
A `passed: false` verification with `final_state_match: true` is preserved
exactly as the script reported it. Timeout and nonzero exits surface as
`isError` results with the stderr tail; partial artifacts stay on disk.

## Hardware exclusivity

Exclusivity is external to this process. The operator must stop the Turbo
gateway and all other model jobs on the device before starting this server;
the wrapper cannot enforce that and does not try.

## Known limitations

- Diagnostic only: no quality qualification, no experiment tracker EXP ID,
  and no tuning conclusions may be drawn from its output.
- 180 s hard timeout per invocation; long cold loads may be cut off, with
  partial artifacts preserved.
- Single-process concurrency lock only; it cannot see other processes.
- The wrapper relies on the committed script's own clean-git guard and
  task-id validation; it does not duplicate them beyond the allowlist and
  task-id checks.
- MCP surface is minimal (initialize / tools/list / tools/call / ping) with
  line-delimited JSON framing; it is not hardened for untrusted clients.
