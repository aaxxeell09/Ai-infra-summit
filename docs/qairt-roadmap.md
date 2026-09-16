# Native QAIRT execution roadmap

Updated 2026-09-15 after Qualcomm feedback. One convincing measured demo is the delivery target. The frozen `secretary-eval-v2` tasks, fixture, expected actions and scoring remain unchanged.

## Verified starting point

- Application checkout: `0611729a120351aec405a90b4316dbf85a7b9ce1`, branch `main`; no tracked changes before this documentation update. The pre-existing untracked `web/` prototype is preserved.
- Target: Dell Latitude 7455, X1E80100, 12 Oryon cores, 32 GB RAM, Windows 11 Pro ARM64 build 26200.
- Installed CLI: GenieX 0.6.1; QAIRT 2.45; llama.cpp runtime revision `0eadefe`.
- `geniex model list` detects Snapdragon X Elite CRD compatibility and lists `qualcomm/Qwen3-0.6B` as an LLM.
- Cached official model metadata reports QAIRT context variants 512/1024/4096, prompt-processor sequence length 128 and minimum QNN 2.45.0. These catalog values do not yet identify which graphs the downloaded bundle contains.
- Official GENIEX_QAIRT W4A16 release v0.62.2 is downloaded and imported. ZIP is 641,390,179 bytes; SHA-256 `92543e1eadb175d3c6ee2b0a05656690f49db9d6e5911d18f39af2f517471415` is locally recorded, not compared against an upstream checksum. Two shards and CL512/1024/4096 variants loaded successfully on HTP v73. See `benchmarks/results/qairt-smoke-01/`.
- The Python adapter now passes a shard file and native `n_ctx=0`, while recording/asserting the compiled context. Model load and prompt-dependent generation work; per-graph traces and matched task-energy results remain pending.
- A representative CPU/QAIRT rendered prompt was byte-identical, including system/tool semantics and disabled thinking. QAIRT reported one additional BOS token. The parity diagnostic overlapped another evaluation and supplies no performance comparison.
- Clean QAIRT development run: 14/35 (40%), zero model errors, 42.86% invalid outputs, 0% clarification. The historical-reference gate is NOT_COMPARABLE because Axel’s newer runner has different provenance. The full unchanged run is now recorded: 23/50 (46%), 34% invalid outputs, 1/13 clarification, zero model errors. Mean inference 786.338 ms, median 533.529 ms, p95 1753.166 ms; mean total task latency 826.204 ms. No settings changed between development and full runs. See `eval/results/candidate_qairt-native-06-v1*`.
- QAIRT full-process telemetry: SYS 760.735 J over 54.045 s (14.076 W), peak process working set 2674.465 MiB. This includes initialization, warmup, fixture execution and scoring; it is not warm-task energy and establishes no efficiency gain against the historical reference.
- Baseline is 30/50, CPU10 is 33/50, and 1.7B CPU10 is 34/50. Both candidates fail the quality gate. See the committed `eval/results/` records; no accepted new candidate is implied here.

## Sequence and acceptance

| Gate | Work | Evidence required |
| --- | --- | --- |
| Access | Tailscale unattended, SSH, bounded awake job; reconnect after Mac changes network | Fresh authenticated connection, not an existing LAN socket; desktop access tested separately |
| Artifact | Finish official 0.6B QAIRT download without replacing GGUF | Source/version, exact precision, chipset/context, all bundle file hashes and byte sizes |
| Smoke | Two different bounded prompts through `qairt` | Prompt-dependent outputs, plugin/device identity, observed Hexagon execution, fallback status stated honestly |
| Backend | Register `llama_cpp_cpu`, `llama_cpp_htp`, `qairt_npu` or equivalent runtime+device identities | Native configuration reaches inference; compiled context is not silently treated as a tunable GGUF context |
| Quality | Development first, then frozen full 50 cases for serious candidate | Same runner/scoring, exact application commit/config/command; invalid output, clarify and critical move regressions retained |
| Compare | Three deployment variants | Task/inference/TTFT/prefill/decode, token counts, memory and energy scope; changed QAIRT quantization disclosed |
| Demo | Tune → apply → correct task → repeat through MCP | Exported identity matches runtime; real sequential inference replaces scripted preview; frontend and hardware show acknowledged applied settings |
| Optimize | One supported QAIRT knob after its baseline works | Hypothesis, one config change, paired trials, predeclared success/kill criteria and rollback |

## Parallel ownership

- Main hardware owner: remote access, download/load/dispatch proof and isolated Latitude runs. No competing laptop inference workers during a timed cell.
- Runtime-binding worker: model/runtime fingerprint, stale-profile rejection, measured energy eligibility, exact apply.
- QAIRT source worker: official artifact and installed-version compatibility evidence; no independent hardware jobs.
- Arduino worker: verified device eligibility, mode API acknowledgement and bounded controller smoke. On-board inference is a later admission test.
- Grammar worker: production five-action constraints as a separate experiment. Do not mix into the first QAIRT run or bypass the frozen evaluator's grammar rejection.
- Human frontend owner: presentation design. Integrate their contract and PRs; preserve explicit recorded/scripted labels until real inference is connected.

## Follow-up queue from Henry's V2 synthesis

Keep CPU10 as a reference and possible FAST mode. Output validity and clarification remain unresolved product problems. After the clean QAIRT comparison, test generic production grammar and mechanically provable preconditions separately, then batch/prefill threads at fixed decode threads. Recheck requested versus effective sampling: the existing zero-temperature caveat remains authoritative.

Prefix/KV reuse, local context reduction, n-gram speculation, larger-model routing and kernel work remain separate ablations. No novel-kernel, universal speedup or 45-TOPS utilization claim follows from enabling QAIRT. Never turn held-out answers into routing or precondition rules. Coordinate any candidate-adapter methodology change with Axel; preserve the reference.

## Result handoff

Commit each serious candidate and JSON/Markdown under `eval/results/`, with exact model artifact identity, application/runtime hashes, command, power/background state, workload/token counts, lifecycle boundaries and failures. Missing telemetry stays unavailable. Recommendations follow measured correctness/latency/energy trade-offs; QAIRT is not declared the winner in advance.

## Updated decision after the complete QAIRT dossier

The supplied dossier identifies useful checks, not measured improvements. Preserve the three different deployment identities and report QAIRT prefill as a TTFT-derived proxy unless lower-level instrumentation measures it independently. Before a speed claim, run fresh-process stability checks and capture active graph selection where the installed runtime exposes it.

The first QAIRT development result makes output reliability the next optimization target. After preserving the as-shipped full run, test deterministic sampling and a production five-action grammar as separate candidates. Coordinate the evaluator’s current grammar rejection with Axel; do not silently bypass it. If valid outputs still fail semantically, prioritize 1.7B QAIRT before power-profile micro-tuning. Keep CPU10 as the latency reference, with its failed quality gate visible.

For a qualified model, the first narrow energy experiment is clock-keeper on/off, followed separately by HTP profile and RPC polling. Live-session KV and canonical-prefix restoration need semantic parity before speed tests. Runtime graph selection is already present; changing VTCM, graph compilation, or quantization requires a new artifact and a separate experiment.
