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
Keep each scheduled Astra checkpoint to roughly ten minutes; use bounded scripts
for transfers and hardware jobs, then yield. This is an operating limit, not a
provider billing cap. Flash was quota-exhausted; Claude Code authentication was
unavailable. Do not silently switch accounts or purchase capacity.

## Verified checkpoint

- Offsite Tailscale SSH is reachable again. Keep-awake processes on both machines
  expire at 16:00 UTC. Mac needs power, an open lid and Codex running.
  The Windows SSH child initially exited after disconnect; it was replaced by
  Task Scheduler task `Qualcomm-Overnight-Awake-20260916`, verified Running from
  a subsequent SSH session. The old keep-awake task is preserved.
- GitHub includes integration checkpoint `728c6a2`, merging Axel's descriptive
  backend comparator and opt-in QAIRT first-tool-call callback cancellation.
  The merged code passed 158 focused tests. No golden dataset was changed.
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
- The normal loopback service remains stopped during isolated benchmarks. Its
  wrapper now points to clean checkout `roadmap-728c6a2`, with a fresh private
  service config registering 0.6B, 1.7B, 4B and the QAIRT bundle. The original
  wrapper and config are preserved. The QAIRT campaign restores the scheduled
  service after releasing hardware, then checks `/api/status`; verify actual
  inference separately. Fresh recommendations must be generated before using
  tuned modes. Keep rejection of old profiles visible.

## Already queued — inspect before launching anything

Both campaigns run as Windows scheduled tasks, so SSH disconnects do not cancel
them. Helpers and state are private, ignored artifacts, not another evaluator.
They invoke the existing `scripts/observe_secretary_eval.py`, which observes the
unchanged evaluation runner with a 600-second child timeout. Campaigns add a
660-second observer watchdog and terminate only their own process tree on timeout.
No inference runs concurrently with the model upload or another queued benchmark.

1. `Qualcomm-Overnight-4B-20260916` waits for the final verified model file,
   independently checks its size/hash, asserts clean source `16d1313`, then runs
   `qwen4b-cpu10-dev-v1` (35 cases) and `qwen4b-cpu10-v1` (50 cases). It stops if
   there is no valid report, a timeout, or every case fails execution. Status and
   results: `roadmap-16d1313/local/qwen4b-evaluation/`. It refuses duplicate output.
   Campaign ends by 07:00 UTC; artifact wait reserves time for both runs.
2. `Qualcomm-Overnight-QAIRT-20260916` waits until the first campaign is complete
   or failed, then runs control/candidate development and full evaluations from
   clean source `728c6a2`. Names are `qairt-stop-{control,candidate}-{dev,full}-v1`.
   The sole candidate difference is `stop_after_tool_call: true`. Status/results:
   `roadmap-728c6a2/local/qairt-stop-evaluation/`. Campaign deadline is 08:00 UTC.
   It restores the service only after the prior campaign has released hardware.

Read each directory's `campaign-status.json`, then the reports and native logs.
Do not treat exit code 2 as missing results: the unchanged runner uses it for
failed or non-comparable candidates. Preserve those findings. Native cancellation
must be observed in actual outputs/profiles, not inferred from the option.

Mac private helper copies: `overnight_4b_campaign.py` and
`overnight_qairt_campaign.py`. They are bounded dispatch wrappers. Public candidate
manifests describe the committed configurations and exact runner commands.

## Next bounded work

1. Collect the already queued 4B and QAIRT ablation results. Preserve native logs,
   verify captured provenance, redact private paths and publish complete evidence.
   Keep the historical `NOT_COMPARABLE` guard when evaluator provenance differs.
2. Compare development failures and native stopping behavior before selecting
   another candidate. Do not infer a hardware-only speedup across model artifacts.
3. Verify the restored gateway, actual inference and MCP. The current status
   endpoint tests model paths with `is_file()`, so a registered QAIRT directory
   can incorrectly appear unavailable; fix this display/availability issue with
   a focused test before claiming complete QAIRT frontend integration.
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
