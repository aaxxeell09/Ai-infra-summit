# Local inference tuning with verified agent actions

Use [the four-slide presentation](../demo/local-turbo-demo-v5.pptx)
for this short technical demonstration. The invoice run and the QAIRT
experiment are separate pieces of evidence. Do not imply the invoice ran on
QAIRT or that stopping generation increased native decode tokens per second.

## Preferred live frontend sequence

Use Ilan's **Machine → Compare → In action** design with the opt-in live
connection described in [the frontend README](../frontend/README.md).
The rehearsal used frontend `86eb559` and native gateway `410931f`.
[Original downloaded and device results](../benchmarks/results/live-ui-1720/README.md)
match. The frozen quality benchmark remains unchanged.

1. Show Machine, then Compare. Explain that the chart is recorded native
   screening evidence. Select CPU/10 for the rehearsed path.
2. Continue to the demo and click **Run on Latitude**. Both answers come from
   real local inference, sequentially, with exact configuration acknowledgements.
3. Explain the separate metrics: load+answer+unload, native TTFT excluding load,
   and native decode rate with actual output-token counts. One pair is not a
   confirmed speedup; the metrics can favor different configurations.
4. Download the result. Use slides 2–3 for the separate verified MCP file action
   and repeated QAIRT study. Label these as recorded evidence unless separately
   rehearsing the invoice command below with exclusive device access.

The QAIRT card in the frontend and slide 3 describe different recorded studies:
the complete candidate comparison and repeated development blocks respectively.
Do not mix their sample counts or calculate a cross-study speedup.

## Three-minute invoice sequence

**Opening, 20 seconds.** “We measure local inference configurations on a
Snapdragon laptop, then connect local models to agent tools. This is a technical
prototype; the broader correctness gate still fails.” Show the Latitude and name
the actual runtime/model for each segment.

**Invoice, 60–90 seconds.** “An MCP client delegates this public test-fixture task
to the local 4B model: find the invoice draft and move it to the invoices folder.”
Run the live entrypoint only after reachability and hardware exclusivity are
verified. Show the original tool replies, source/destination and content hash.
Every unrelated file must retain its hash. The task acts on a fresh synthetic
workspace, not a person's real files. The latest presenter rehearsal took
21.791 seconds in the feedback loop and 48.634 seconds from MCP process launch
through exit, including model loading. Do not confuse these timing scopes.

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
The combined tuner→MCP run is now verified for two public-fixture rounds;
see [the recovered evidence](../benchmarks/results/bound-feedback-mcp-1400/README.md).
Fast applied CPU/10 and Efficient CPU/6; both moved the invoice correctly, while
both exact-call checks failed. These single observations do not establish a
speed or efficiency winner. Slide 2 in the v5 deck shows the two verified rounds.
Do not claim a production-ready secretary.

## Live preparation on the Latitude

Use a clean committed checkout with the private, verified 4B native config at
`local/qwen4b-cpu10-config.json`. It must point to the verified model and installed
SDK. Ensure no tuner, evaluation campaign, model download/hash job or other native
inference process is running. Stop the existing gateway for this isolated demo;
if its known service child remains listening, reconcile it before proceeding.
Do not launch a second copy after an uncertain timeout.

The one-command presenter entrypoint completed on the Latitude at clean commit
`da59974`: [hardware rehearsal and original replies](../benchmarks/results/presenter-mcp-1645/README.md).
The gateway was restored afterward and answered a real inference request. Run:

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
- [One-command presenter rehearsal](../benchmarks/results/presenter-mcp-1645/README.md)
- [Tuner → exact applied configuration → MCP, two modes](../benchmarks/results/bound-feedback-mcp-1400/README.md)
- [MCP evidence and timing scope](../benchmarks/results/feedback-mcp-1300/README.md)
- [All constrained repeats, including 20B failure](../benchmarks/results/grammar-repeats-1200/README.md)
- [Six QAIRT development blocks](../eval/results/qairt-repeats-0700.md)
- [8B full milestone and failed cases](../eval/results/qwen8b-full-1200/README.md)

With the live connection configured, the CPU Speed finale uses actual device
results and has been browser-rehearsed. With no connection configured, it remains
a labelled preview whose animation clock is not model latency. Failed live runs
never silently fall back to preview. Live routing and GPU/NPU answer comparisons
remain unavailable in this adapter.
