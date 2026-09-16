# Native QAIRT execution roadmap

Updated 2026-09-15 after Qualcomm feedback. One convincing measured demo is the delivery target. The frozen `secretary-eval-v2` tasks, fixture, expected actions and scoring remain unchanged.

## Verified starting point

- Application checkout: `0611729a120351aec405a90b4316dbf85a7b9ce1`, branch `main`; no tracked changes before this documentation update. The pre-existing untracked `web/` prototype is preserved.
- Target: Dell Latitude 7455, X1E80100, 12 Oryon cores, 32 GB RAM, Windows 11 Pro ARM64 build 26200.
- Installed CLI: GenieX 0.6.1; QAIRT 2.45; llama.cpp runtime revision `0eadefe`.
- `geniex model list` detects Snapdragon X Elite CRD compatibility and lists `qualcomm/Qwen3-0.6B` as an LLM.
- Cached official model metadata reports QAIRT context variants 512/1024/4096, prompt-processor sequence length 128 and minimum QNN 2.45.0. These catalog values do not yet identify which graphs the downloaded bundle contains.
- `geniex pull qualcomm/Qwen3-0.6B --model-hub aihub` started an approximately 760 MB download. Completion, precision, bundle checksum and actual execution are pending.
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
