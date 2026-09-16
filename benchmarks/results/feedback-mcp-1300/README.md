# Real MCP feedback diagnostic on the Latitude

Clean source `bf0b317545564d2b59bd5c6b96b1cf78597df70a`. A real stdio MCP
client initialized the opt-in server, listed its tool, then invoked
`local_feedback_diagnostic` with `model_id=qwen4b`, `task_id=t13`.
This launched actual GenieX0.6.1 llama.cpp CPU10 inference with the4B Q4_0 model,
context4096 and constrained output; no fake runtime or canned response was used.

The MCP tool returned `isError=false`, `completed=true` and preserved:

- `passed=false`, `calls_match=false`
- `final_state_match=true`, `execution_ok=true`

The invoice's original content hash appears at its requested destination, its
source is absent, and every other file hash is unchanged. The five-turn loop
took20.492seconds; the broader diagnostic interval was31.534seconds. The latter
includes hashing/load/canary/fixture/verification/destruction, not final
serialization or SDKshutdown. Neither metric measures the entire MCP roundtrip.
No energy was captured. This is one public-fixture diagnostic, not a frozen
quality PASS or a complete production Secretary. Extra calls still fail the
existing verifier. No repair or rescoring occurred.

Exact server command from the clean checkout:

```powershell
python -X utf8 -m turbo.feedback_mcp --enable-candidate --model qwen4b=local/qwen4b-cpu10-config.json --output-root local/mcp-fixtures-1300
```

The startup allowlist selects a fixed recorded native configuration. A fresh
recommendation is not yet bound to this diagnostic execution path, and the
normal MCP/service remain unchanged. That linkage is the next integration step.
The gateway was stopped for exclusivity and restored afterward; its native
runtime reported available.

`result.json` contains the MCP structured result and complete nested native
report. Before publication, its structured payload was verified identical to
the text content payload. Private device roots were redacted and the original
wire-reply hash retained. Source/model/SDK/configuration identities and original
file snapshots are preserved. Original wire and stderr remain in private local
storage. The wrapper's180second child limit and outer240second watchdog were
not reached.
