# Demo deck: tuner-demo.pptx

Eight-slide demo deck for the local inference tuner. Design: charcoal (#2B2E2A), white and lime (#A8D129), Helvetica Neue, 16:9. All numbers come from the accepted on-device benchmark evidence; nothing is illustrative.

## Files

- `tuner-demo.pptx` — the deck. Slide 4, 5 and 6 contain native, editable bar charts with embedded data workbooks (data snapshots, not links to external files).
- `deck-source.mjs` — the build script. Run it with the Codex bundled Node runtime and `@oai/artifact-tool` (presentations skill): `RUNTIME_NODE build-deck.mjs` from a directory where `node_modules` links to the bundled runtime packages. It writes `candidate.pptx`; finalize with the presentations-skill finalizer to produce a validated output.
- `previews/tuner-demo-slide-*.png` — per-slide PNG renders for quick review (1920x1080).

## Slide map and evidence

1. **Cover** — problem statement. Device and model identity on the slide.
2. **Problem** — backend choice is guesswork. Note: NPU used 54% less full-trial energy despite slower decode. Source: `benchmarks/results/README.md`, screening table.
3. **Architecture** — sweep runner, ranking/recommendation, loopback gateway, MCP server plus verified secretary. Carries the LIVE FLOW UNDER INTEGRATION disclosure: the chained tune-apply-verify-MCP flow has not passed end to end. Sources: `docs/tuner-api.md`, `docs/agent-interface.md`, `docs/secretary-evaluation.md`.
4. **Measured result** — aggregate native decode 36.36 (NPU default auto) vs 97.19 tok/s (CPU, 10 decode threads), 2.67x, battery, Qwen3-0.6B Q4_0, 512/128 tokens, five alternating pairs. Source: `benchmarks/results/confirm-auto-01/sweep.json` via `recommended.json`. Backend selection, not a new kernel.
5. **Energy trade-off** — full-trial SYS tokens/J 2.1089 (NPU) vs 1.3679 (CPU), 1.54x; interval includes load, prefill and decode. Source: `confirm-auto-01` pooled energy, conversion audit in `docs/energy-review.md`.
6. **Honest baseline** — the stronger CPU-vs-CPU comparison: aggregate 75.86 -> 88.65 tok/s (+16.9%), median individual run +3.2%, with disclosed variability and unresolved slowdown dips. Source: `benchmarks/results/confirm-01/sweep.json`. Shown so the 2.67x headline is not mistaken for kernel tuning.
7. **Demo flow** — tune, apply, verify (secretary fixtures), MCP; repeats the live-flow-under-integration status.
8. **Roadmap** — larger-model routing, optional UNO Q worker, power-state recording, QAIRT bundles; honest-boundaries box (one device, one model, one workload; no superiority or 100%-support claims; no invented quality scores).

Speaker notes on every slide carry the route, measurement caveats and citations.

## Regenerating

The PPTX is the committed artifact. `deck-source.mjs` is kept so the deck can be regenerated or restyled; the finalizer output was validated (8 slides, package integrity, layout, font policy, native chart checks).
