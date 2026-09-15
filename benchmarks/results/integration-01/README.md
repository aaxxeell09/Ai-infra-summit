# Latitude tuner and MCP integration smoke

Application `8ec23e2`, GenieX 0.6.1, Qwen3-0.6B Q4_0 on the Latitude.
This is an integration check, **not** a new official correctness baseline or
paired performance confirmation. Frozen evaluation results remain under
`eval/results/`.

The running HTTP service accepted `tune-request.json`, executed both native
trials and exported `recommended.json`. The actual stdio MCP client then
applied each mode and ran the same invoice task (`t13`) on the laptop.

| Mode | Applied configuration | Screening decode | Screening prefill | Screening TTFT | Full-trial SYS tokens/J |
| --- | --- | ---: | ---: | ---: | ---: |
| Fast | CPU, 10 threads, context 4096 | 97.211 tok/s | 1581.760 tok/s | 324.116 ms | 1.454 |
| Efficient | NPU, 10 threads requested, context 4096 | 32.612 tok/s | 1615.152 tok/s | 317.372 ms | 1.508 |

Three repetitions per configuration, 512 synthetic input tokens, 128 generated
tokens, fresh KV, no warmup, AC power. Energy includes model loading, prefill
and decode for each whole process. These short screening results are provisional;
the narrow energy difference needs paired confirmation. CPU/NPU placement is
reported by the runtime; this run did not collect a fresh operation trace.

Both invoice attempts **failed**. CPU invented `notes/hexagon-invoice.md`; NPU
invented `docs/hexagon-invoice.md`. The correct source was in `drafts/`.
The file tool rejected the missing sources and the final-state checks failed.
Measured whole-task times were 1.791 s and 2.221 s respectively, with different
generated outputs. They are not a speedup claim for correct tasks.

A subsequent simple `t01` task passed its exact action, execution and final-state
checks over HTTP in 1.809 s and subsequently through actual MCP in 0.707 s
(the latter reused a resident model). This does not repair the invoice failure or qualify
the model against the full frozen suite. The sampler retains the reference's
zero-as-default behavior; see `eval/results/baseline_sampling_note.md`.

## Evidence and reproduction

- `record.json`, `recommended.json` and `trial-*/result.json`: native trial
  measurements, telemetry, source hashes and commands.
- `mcp-exchanges.json`: initialization, discovery, real apply acknowledgements
  and both failed task results; JSON text payloads decoded for inspection.
- `task-t01-fast.json` and `task-t01-mcp.json`: successful simple HTTP and MCP
  tasks, with full checks. Background model downloads had started by these
  diagnostic calls; these task timings are not isolated benchmark measurements.
- `manifest.json`: source and scope. Absolute installation paths use
  `${QUALCOMM_TOOLS}` placeholders. Private raw transport and native logs were
  retained outside Git.

With the pinned runtime and model configured, start `python -m turbo.service
--config local/config.json --port 8083`, post `tune-request.json` to `/api/tune`,
wait until `/api/status` reports completion, then launch
`python -m turbo.mcp_server` with `TURBO_BASE_URL=http://127.0.0.1:8083`.
After MCP initialization, call `local_apply` then `local_secretary` with
`task_id=t13` for each mode. The recorded requests contain the exact arguments.

Remaining gaps: runtime DLL identity validation is being strengthened; the
teammate frontend and Arduino have not been connected to this live flow.
Correct invoice execution and an accepted full-suite candidate remain required.
