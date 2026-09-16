# Live answer comparison adapter

The presentation can opt into the actual local GenieX runtime with
`live_comparison_enabled: true` in the private gateway configuration. The default
remains disabled. This is a demo adapter, separate from Axel's optimization loop
and the frozen Secretary evaluation.

The two public frontend prompts run sequentially on the recorded Qwen3-0.6B
Q4_0 weights. The default lane explicitly uses CPU and automatic threads; the
selected lane uses the selected recorded CPU thread count. This does not call
`Engine.apply('baseline')`, whose automatic backend placement is different.
GPU/NPU and uncalibrated model routing are rejected by this adapter.

Every request validates the recorded model hash, benchmark-executable hash,
source-manifest hash and complete selected parameter record. Before loading it
also checks the installed files, current native SDK identity and clean Git
checkout. Each lane uses a fresh model and KV cache, no warmup, 128-token limit,
requested temperature zero and the SDK's default seed. These natural-language
prompts have different token counts and generation controls from the recorded
synthetic sweep; the result records the actual controls and token counts.
GenieX's zero-temperature default behavior is disclosed in each native result.

One engine lock serializes the pair with other gateway inference. An active tuner
prevents launch. Cancellation is requested through the job API and checked by
the native token callback; it becomes terminal only after native cleanup.
Loading or a stalled native call may delay cancellation. A second request must
wait for reconciled terminal status. There is no kill-and-retry guess.

Endpoints:

- `GET /api/live-comparisons/capabilities`
- `POST /api/live-comparisons` with `local-turbo.comparison-request.v1`
- `GET /api/live-comparisons/<request_id>` for correlated events/results
- `POST /api/live-comparisons/<request_id>/cancel` with `{}`

Each request and terminal result is retained beneath the private gateway data
folder in `live-comparisons/<request_id>/`. Repeating the same ID in a running
server returns its state; altered inputs with the same ID are rejected. After a
restart, an existing output directory prevents accidental replay.

Native TTFT excludes loading. Lane total time includes loading, generation and
unloading. Pair total includes identity checks and unloading the previous
resident model, but excludes browser/network transport. Actual generated token
counts and native decode rates remain separate. Energy and memory are null when
not measured. Completed first-lane output survives second-lane failure. No single
pair chooses a winner or establishes a quality/speedup claim.

The frontend proxy keeps the target address server-side. Its opt-in connection
and user-facing labels are documented in `frontend/README.md`. Hardware and
browser rehearsal evidence must be saved before claiming that path verified.
