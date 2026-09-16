# Overnight continuation — September 15–16

Stop starting work at **2026-09-16 09:00 America/Los_Angeles (16:00 UTC)**.
Save results and a morning handoff at the cutoff. Scheduled hourly continuation
is installed in the current task, ending at the cutoff. Pause that automation
when producing the final morning handoff.

## Guardrails and ownership

Preserve the main Mac checkout: it has uncommitted reversions affecting 16 files.
The active branch is `fix/latitude-resume-evidence`, in the sibling worktree
`latitude-resume-16d1313`. Do not restore, stash, stage or overwrite the main
checkout's edits. Fetch and check PRs before pushes; preserve human frontend work.
Only one hardware benchmark runs at a time. No fake load or indefinite loops.
No paid fallbacks, purchases, quota resets, account rotation or recursive agents.
Use at most two bounded Flash/medium workers if their quota is available; stop
attempting an exhausted route. Keep Astra work focused on decisions, integration
and consequential review. Do not repeatedly scan history or unchanged files.

## Verified checkpoint

- Offsite Tailscale SSH is reachable again. Keep-awake processes on both machines
  expire at 16:00 UTC. Mac needs power, an open lid and Codex running.
- `benchmarks/results/qairt-mcp-loop-01/` contains the successful two-round
  tune/apply/native-inference/MCP lifecycle test at clean source `16d1313`.
  Arithmetic passed; both invoice tasks failed. No accepted Secretary demo yet.
- The Windows test checkout is `%LOCALAPPDATA%\QualcommTools\roadmap-16d1313`.
  Its remote is a Git bundle, not a live GitHub tracking remote. Update using an
  explicitly pinned new bundle or add a distinct GitHub remote; always assert
  HEAD and clean status before recording results.
- The older standalone tuner smoke lacked a captured application hash. Its
  previous clean-commit attribution was corrected; retain numeric evidence.
- Mac has verified Qwen3-4B-Instruct-2507 Q4_0: 2,375,773,280 bytes,
  SHA-256 `e0ba675d86ab277c61701c6793659b2ae801d95e3be791464c321e6fbf613be2`.
  One bounded transfer to the Latitude is active; check its status before retrying.
  Private status/log/helper files remain in the main checkout's ignored `local/`:
  `upload-4b-overnight-status.json`, `upload-4b-overnight.log`,
  `upload-4b-supervisor.pid`, `upload_4b_overnight.py`, `remote.py`.
  Successful verification leaves the model under `%LOCALAPPDATA%\QualcommTools\models`.
- The normal loopback service remains stopped after isolated benchmarks. Restore
  it after the next short model/evaluation jobs, preferably from verified code
  without overwriting private config. Keep old profile rejection visible.

## Next bounded work

1. Preserve/commit this integration evidence and exact reproduction details.
2. Verify 4B arrival, hash and free memory; run a short CPU10 generation check.
3. Run development correctness using the existing runner from clean source.
   For a serious candidate, preserve its unchanged full 50-case result. Keep
   the historical `NOT_COMPARABLE` guard when evaluator provenance differs.
4. Choose between stronger-model admission and generic production grammar based
   on development failures. Any grammar trial needs a real restrictive canary;
   the frozen runner currently rejects grammar, so coordinate adapter changes
   rather than bypassing it. No held-out-answer rules or edits to golden data.
5. Restore the live loopback service, verify actual inference and MCP. Then move
   to the remaining roadmap: larger/smaller routing, context work and acknowledged
   Arduino mode control. The UNO Q CPU smoke exists but did not pass exact output.

Axel owns golden data, scoring and methodology. The preserved official reference
is 30/50; native QAIRT full run is 23/50 and not qualified. Do not manufacture a
quality PASS, a speedup between different quantizations, or warm-task energy
from full-process counters. All benchmark logs and failures remain reviewable.
