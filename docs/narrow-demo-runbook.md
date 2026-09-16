# Local inference tuning with verified agent actions

Use this as a short technical demonstration. The invoice run and the QAIRT
experiment are separate pieces of evidence. Do not imply the invoice ran on
QAIRT or that stopping generation increased native decode tokens per second.

## Three-minute sequence

**Opening, 20 seconds.** “We measure local inference configurations on a
Snapdragon laptop, then connect local models to agent tools. This is a technical
prototype; the broader correctness gate still fails.” Show the Latitude and name
the actual runtime/model for each segment.

**Invoice, 60–90 seconds.** “An MCP client delegates this public test-fixture task
to the local 4B model: find the invoice draft and move it to the invoices folder.”
Run the live entrypoint only after reachability and hardware exclusivity are
verified. Show the original tool replies, source/destination and content hash.
Every unrelated file must retain its hash. The task acts on a fresh synthetic
workspace, not a person's real files. The recorded MCP run took 20.492 seconds in
the feedback loop, excluding model loading; do not call this full MCP latency.

Say the result precisely: “The requested filesystem change is verified. The
existing exact-call check fails because the model used extra search/list calls.”
Keep both flags visible. A successful command exit is not a quality PASS.

**QAIRT, 50 seconds.** Show the repeated development result: mean inference
788.680 ms with standard generation and 516.741 ms with first-tool-call stopping,
a 34.48% observed reduction. The same 35 unique development prompts were repeated
three times per treatment, with sequential balanced order. This is shortening
unnecessary output, not a new faster kernel or increased native decode speed.
The mean of block task medians fell 10.11%; that is a different timing statistic.
No cold end-to-end, statistical-significance or energy-efficiency claim follows.

**Close, 20 seconds.** “The action works in this bounded fixture; the remaining
work is reliable clarification and broader task quality.” All QAIRT repeat blocks
failed the quality gate. The 8B full result is 38/50 with 2/13 clarification success.
The latest combined tuner→MCP run must remain pending until its actual report is
retrieved and verified. Do not claim a production-ready secretary.

## Live preparation on the Latitude

Use a clean committed checkout with the private, verified 4B native config at
`local/qwen4b-cpu10-config.json`. It must point to the verified model and installed
SDK. Ensure no tuner, evaluation campaign, model download/hash job or other native
inference process is running. Stop the existing gateway for this isolated demo;
if its known service child remains listening, reconcile it before proceeding.
Do not launch a second copy after an uncertain timeout.

The one-command presenter entrypoint is implemented and locally tested. A successful
hardware run of this new entrypoint remains pending; the underlying MCP path has
recorded hardware evidence. Run:

```powershell
python -X utf8 scripts/demo_invoice_mcp.py --enable-candidate --config local/qwen4b-cpu10-config.json --output local/live-invoice-demo-001
```

Use a new output directory for every attempt. Preserve failures and logs.
The command talks to the real opt-in MCP server; it does not simulate model text.
Inspect `summary.json` and the original report. Require `file_move.verified=true`
for the physical-action claim; `ok` and exit zero describe transport/runtime
completion only. The unchanged exact-call verdict remains separate. The summary
also checks the verified 4B weights hash and records native identity/config.
MCP-process timing includes launch, model loading and child exit; the reported
feedback-loop timing has a narrower scope. Restore the normal gateway afterward and verify its status separately.
This entrypoint does not assert that a fresh tuner recommendation was applied.

The existing standalone server command, already verified on hardware, is:

```powershell
python -X utf8 -m turbo.feedback_mcp --enable-candidate --model qwen4b=local/qwen4b-cpu10-config.json --output-root local/mcp-fixtures-demo
```

Call `local_feedback_diagnostic` with `model_id=qwen4b`, `task_id=t13` after MCP
initialization. The default service/MCP remain separate from this opt-in path.

## Recorded fallback

If the laptop is unreachable, explicitly say “recorded hardware evidence” and
show these committed artifacts. Do not animate preview responses as live inference
or silently fall back to a recorded result after a live failure.

- [Actual MCP response and native report](../benchmarks/results/feedback-mcp-1300/result.json)
- [MCP evidence and timing scope](../benchmarks/results/feedback-mcp-1300/README.md)
- [All constrained repeats, including 20B failure](../benchmarks/results/grammar-repeats-1200/README.md)
- [Six QAIRT development blocks](../eval/results/qairt-repeats-0700.md)
- [8B full milestone and failed cases](../eval/results/qwen8b-full-1200/README.md)

The frontend's comparison finale is still labelled preview. Its animation clock
is not model latency. Use the deck and evidence files for this narrow sequence
until a real provider is wired and independently validated.
