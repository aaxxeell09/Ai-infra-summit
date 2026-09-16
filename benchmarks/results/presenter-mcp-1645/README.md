# Presenter command: verified on the Latitude

One public-fixture rehearsal on September 16, 2026, 16:40:58–16:42:15 UTC,
including gateway restoration. Clean application commit
`da599746336ea092310a9978195c6b70bfb19f3c`.

The one-command presenter invoked the real stdio MCP server and Qwen3-4B
Instruct-2507 Q4_0 through GenieX 0.6.1, llama.cpp CPU, 10 threads, context 4096.
It moved `drafts/hexagon-invoice.md` to `invoices/2026/hexagon-invoice.md`.
The copied workspace was independently hashed: the invoice contents match and
all 11 surrounding files are unchanged. Five model turns were recorded.

| Check / measurement | Result |
| --- | --- |
| Actual file move | Verified |
| Original exact-call check | Failed; preserved unchanged |
| Broader correctness qualification | Not established |
| Feedback loop, excluding model load and fixture creation | 21.791 s |
| MCP process launch through exit, including model load | 48.634 s |
| Gateway recovery | Actual subsequent completion returned `5` |

This is one presentation rehearsal, not an official benchmark or a speedup
comparison. It uses a fixed configuration; the separate
[bound tuner → MCP evidence](../bound-feedback-mcp-1400/README.md) verifies
recommendation application. No energy-efficiency claim follows from this run.

Exact command from the committed checkout, with the machine's private config:

```powershell
python -X utf8 scripts/demo_invoice_mcp.py --enable-candidate --config local/qwen4b-cpu10-config.json --output local/live-presenter-1645
```

Use a fresh output directory for another attempt. Follow the
[runbook](../../../docs/narrow-demo-runbook.md), including exclusive hardware use.
The original directory must not be overwritten.

[summary.json](summary.json) records the model/SDK hashes, native settings,
timing boundaries and both verdicts. MCP replies and the native diagnostic are
preserved alongside it. [publication.json](publication.json) binds raw and
published artifact hashes; only private path prefixes were replaced. Duplicate
public fixture bytes remain private, with their hashes and independent check
recorded. The supervisor's actual recovery response is preserved separately;
it is not part of the invoice timing.
