# Overnight continuation — September 15–16

Stop starting work at **2026-09-16 09:00 America/Los_Angeles (16:00 UTC)**.
Save results and a morning handoff at the cutoff. Scheduled hourly continuation
is installed in the current task, ending at the cutoff. Pause that automation
when producing the final morning handoff.

## 15:22 UTC scheduled checkpoint — timeout evidence hardened

- Bounded SSH attempt at 15:22 UTC timed out; no further device probes or jobs
  were launched this wake. Local Tailscale reports Running, self online, no
  health errors, and the Latitude peer online/active. These status flags did
  not establish SSH reachability. Windows App showed the saved-device list,
  with no usable remote desktop visible; no fresh connection was attempted.
  Private Tailscale status is retained under `local/tailscale-status-1526.json`.
- Pushed `e901bfa`: the integration script preserves partial stdout/stderr bytes
  on feedback-MCP timeout, preserves launch failures and malformed replies, and
  validates JSON-RPC identities/result envelopes before accepting responses.
  Ten new tests plus ten existing binding tests pass. Leakage audit remains
  PASS_WITH_DISCLOSED_EXPOSURE with no new source matches/integrity errors/exposure.
  This does not alter the already queued Latitude run or any frozen semantics;
  it adds no new inference, quality or speed evidence.
- PR1 remains `204a9fb`. Teammate TurboLab branch is now `e4b30e1`; not merged.
  Flash reviewer Mill (`01a0aad0-3643-7a82-a385-65dfd59c7778`) completed its
  bounded read-only review. Owner verified the resume schema failure with an
  injected-clock reproduction and inspected outcome ingestion/deadline paths.
  See `docs/turbolab-review-e4b30e1.md`: hold integration pending fixes. The
  worker's stronger false-promotion claim was not established and is qualified
  explicitly. No branch edits, hardware work or teammate messages. No worker
  remains active.
- At the 16:00 UTC cutoff, start no experiment. Try one bounded recovery check,
  preserve any retrievable pending bound-MCP result and verify restoration if
  reachable. If unreachable, report remote cleanup/result status as unknown.
  Finish/stop only owned bounded local jobs and pause the heartbeat automation.

## 15:00 UTC checkpoint — narrow demo packaged, remote still unavailable

- Latest SSH checks at 14:56 and 14:58 UTC timed out. No new hardware jobs
  launched and no result assumed from the already scheduled bound MCP campaign.
  Follow the next scheduled reachability check; inspect existing processes/task
  status and retrieve both rounds before claiming tuner-to-task integration.
- Committed/pushed `78a8146`: four-slide editable PPTX at
  `demo/local-turbo-narrow-demo-v3.pptx`, validation receipt and three-minute
  runbook. Final PPTX was reimported, all four slides rendered and inspected;
  chart/workbook, package, layout and font checks passed. Native PowerPoint
  opening was not tested. The deck explicitly uses recorded evidence and keeps
  quality failures and frontend preview limitations visible.
- Fresh bounded Flash worker produced presenter CLI `eb70c1c`, integrated as
  `377ad5d`; owner review hardened missing/malformed/duplicate replies, task/model
  identity, verified 4B hash, ignored output containment and snapshot validation.
  Worker stopped after its initial implementation; owner completed the review.
  29 focused tests and 12 subtests pass, including replay of the committed public
  hardware response. This is local transport/verification testing, not a new
  successful hardware run. All original verifier fields remain unchanged.
  After committing clean source `3f61ed7`, an actual local MCP subprocess test
  with deliberately absent SDK/model returned three protocol replies and exit 1,
  transport_completed=true, ok=false and quality_qualified=false. This verifies
  the real error path without loading a model; private logs are retained under
  `local/presenter-transport-check-1520/`. No successful inference is implied.
- The CLI creates a fresh public t13 fixture through the real opt-in MCP server;
  it reports physical verification separately from exact-call grading and
  records broader MCP-process timing as well as inner timing scopes. Default
  service/MCP and frozen evaluation semantics are unchanged. It requires an
  explicit candidate flag, clean checkout and a fresh ignored `local/` output.
- GitHub PR1 frontend remains at `204a9fb`, unmerged and untouched. Teammate
  branch `claude/beautiful-mayer-gslb35` advanced to `33de023` with a substantial
  TurboLab implementation; review it before integration or hardware execution.
- Leakage audit remains PASS_WITH_DISCLOSED_EXPOSURE: no runtime-source match,
  archive-integrity error or unreviewed exposure. No new correctness/speed result.
- Next: retrieve `bound-mcp-1400/local/bound-mcp-loop-1400/integration.json`,
  validate native bindings/filesystem outcomes and gateway restoration. Rehearse
  the presenter CLI only after exclusive hardware is confirmed. If unreachable,
  use recorded evidence explicitly. Stop new experiments at 16:00 UTC, preserve
  pending results and pause the overnight automation. No worker remains active.

## 14:00 UTC checkpoint — fresh recommendation binding queued

- Pushedf1b8298 and3380a65: `verify_tuner_loop.py --feedback-mcp` now runs the
  existing MCP tune/apply/native smoke, exports its selected device/threads/context
  with model/plugin/SDK identities, unloads the resident model, then invokes the
  opt-in feedback MCP. CLI validates those bindings before model creation/fixture
  actions. Unbound batching/speculation/backend/cancellation overrides are rejected.
  Defaults and frozenv2 are unchanged.40focused tests passed; no new hardware
  success claim until the queued result is inspected. Grammar/task output budget
  remain explicit diagnostic controls, not calibrated benchmark workload settings.
- Task `Qualcomm-Bound-MCP-1400` uses clean checkout `bound-mcp-1400`, source
  `3380a652dda56b5389c84b2c545fc60645f566ff`, for two sequential rounds. CPU6/10,
  context4096,32generated benchmark tokens,2repeats; then selected Fast and, if
  available, Efficient. Both modes may select the same configuration. Results:
  `local/bound-mcp-loop-1400/integration.json`; supervisor status/log:
  `local/bound-mcp-1400-supervisor/`. Child900s watchdog, task17min. No overlapping
  jobs. Supervisor `overnight_bound_mcp_1400.py` restores the scheduled gateway.
- The gateway had exited between checkpoints (tasklastresult267014, exitfile-1;
  log only showed listening). Cause is unknown. Preserved original task XML as
  private `turbo-service-task-before-headless-1400.xml` and changed only its
  action to `run-turbo-service-headless-1400.py` via pythonw. That supervisor runs
  the existingroadmap-a8c3707 service with CREATE_NO_WINDOW and captured log,
  preserving prior task settings/config/power behavior. Check actual restoration
  and persistence next wake; do not claim the underlying exit cause is fixed.
- Teammate frontend branch advanced toff0faa6; PR1 remains open, no merge/edit.
  A read-only Flash review confirms latest metrics are wired but finale is still
  preview data, not the live service. Review's NOT_COMPARABLE warning refers to
  each artifact's historical-reference guard; it does not by itself invalidate
  a separately provenance-checked control/candidate pairing. Likewise inspect
  QAIRT native evidence before treating the generic dispatchflag as proof of no
  NPU use. No unsupported UI label changes or teammate messages were made.
- Independent Flash review completed with scoped approval and no blocker.
  Scope limitations: service-level controls beyond the selected axes are not
  propagated; the recommendation file is reread after apply, so this is an
  isolated integration check rather than an atomic signed export. Native
  model/SDK/config binding is checked before execution. No worker remains active.
  Clone preparation initially hit PowerShell NativeCommandError on redirected
  git progress output; the owned clone was inspected and recovered without
  deleting files, then its exact HEAD/clean state were asserted before launch.
  Next: verify both round bindings against actual native report, preserve final
  filesystem and exact-call grades separately, publish evidence, verify gateway.
  Finish remaining integration/presentation handoff within the16:00UTC cutoff.

## 13:00 UTC checkpoint — full 8B result and native MCP test

- Full50 8B result:38/50 (76%), moves8/8, clarify2/13, invalid2/50 (4%).
  Median recorded task12,946.676ms; mean inference19,896.854ms. No qualityPASS;
  NOT_COMPARABLE guard retained. `eval/results/qwen8b-full-1200/` holds the public
  report/config/command/telemetry; held-out row prompts/answers/arguments/output
  are omitted with explicit publication metadata. Complete original EXP-003
  archive is retained privately and passed integrity verification. No held-out
  answers were used for tuning. Energy remains diagnostic/uncommissioned.
- Two further4B constrained invoice runs moved the correct file, so three of
  three trials have matching final state. Every existing exact-call grade still
  fails. Loop times18.142/21.150/61.174seconds show substantial variation; no
  speedup or dependable latency claim. 20B canary passed and initial tool output
  parsed, but later output failed strict decoding; no move. All diagnostics are
  published in `benchmarks/results/grammar-repeats-1200/` without rescoring.
- The MCP worker's c1b9f2a was reviewed; request-name validation, model-ID type,
  timeout bytes, Windows headless/UTF8, lock race, child launch failures,
  absolute output path and duplicate aliases were fixed in38ee27a. Integrated
  as57bb9fb andbf0b317, pushed. Owner focused tests30passed. Worker's broader
  suite reported705passed/17subtests. No default MCP/service or frozen semantic
  dependency changed.
- New clean Latitude checkout `mcp-1300` is pinned to
  `bf0b317545564d2b59bd5c6b96b1cf78597df70a`. Initial bundle clone with --branchHEAD
  failed before changing hardware; default bundle clone succeeded. The actual
  MCP test runs as task `Qualcomm-MCP-1300`, with supervisor
  `overnight_mcp_1300.py`, 180s native child limit,240s MCP watchdog,6min task cap.
  It initializes MCP, lists tools, and delegates public invoice t13 to4B with
  grammar. Status/reply/wire in `mcp-1300/local/mcp-smoke-1300/`; full native
  reports in `mcp-1300/local/mcp-fixtures-1300/`. Gateway restoration is automatic.
- The real MCP test completed: isError=false, completed=true, five turns,
  matching final state and execution_ok=true; exact-call grade remainsfalse.
  Owner independently compared every file hash and checked both MCP payloads
  agree. Loop20.492s, broader diagnostic31.534s. Gateway restored/runtimeavailable.
  Published `benchmarks/results/feedback-mcp-1300/`; raw reply/status copied to
  main ignored `local/overnight-results-1300/mcp/`. This proves the fixture action
  through MCP, not a production qualityPASS.
  The opt-in wrapper currently takes a configured model/task, not a live mode
  or fresh tuner recommendation. Its config identity is recorded, but the full
  tune→apply→feedback→MCP loop and default product quality remain unfinished.
  Next step is binding a fresh measured export to this actual execution path,
  preserving honest verifier failure and external hardware exclusivity.
- Last results commit8685ac5; implementationbf0b317. Workers finished, no agent
  needs polling. Preserve the main checkout's edits. Stop by16:00UTC.

## 12:00 UTC checkpoint — larger models measured, milestone queued

- Both development archives completed and passed integrity verification at source
  `31bb6a1`. Results/configs/telemetry: `eval/results/large-model-dev-1100/`.
  8B:27/35 (77.14%), moves6/6, clarify1/9, invalid1/35, median recorded task9377.869ms.
  20B:0/35, all35 parse failures from Harmony-formatted outputs. Native generation
  works but the frozen Secretary protocol does not accept those outputs. Keep0/35;
  no post-hoc re-scoring. Neither has a quality PASS; NOT_COMPARABLE preserved.
  Full-process SYS energy is diagnostic/uncommissioned, not an efficiency claim.
- Original sealed archives are on Mac under main checkout's ignored
  `local/overnight-results-1200/experiments/`, and Latitude `grammar-1000/local/experiments/`.
  EXP-001 is8B development; EXP-002 is20B development. Reports include all failures.
- Service restoration was verified by actual native arithmetic returning5. It is
  paused again for task `Qualcomm-Milestone-1200`, which runs sequentially: unchanged
  full50 8B through the tracker (1200s child /1320s watchdog), two repeated4B
  grammar invoice diagnostics, then one20B grammar invoice diagnostic (180s each).
  Supervisor `overnight_milestone_1200.py`; state `grammar-1000/local/milestone-1200/status.json`.
  Task cap35min. All diagnostics use fresh public fixtures, never golden cases.
  Supervisor restores and smoke-tests the gateway. No overlapping hardware jobs.
- A second bounded Flash worker is coding an opt-in fixture-only MCP wrapper in
  `/Users/user/Documents/Qualcomm/worktrees/feedback-mcp-diagnostic`, branch
  `feat/feedback-mcp-diagnostic`, based on1512ef1. AgentID
  `01a0aa1b-1b8b-7c30-aeae-ded08df90fb2` (Gibbs). It owns only new
  `turbo/feedback_mcp.py`, `tests/test_feedback_mcp.py`, and
  `docs/feedback-mcp-diagnostic.md`; no hardware access, no default MCP/service or
  frozen semantics changes. It will commit locally, not push. Review before
  cherry-picking; do not assume completion, source cleanliness or real integration.
- Next: collect full50 aggregate/failure IDs without using held-out answers for
  tuning, keep original raw archives private and publish a clearly marked
  redacted handoff if necessary to avoid new held-out exposure. Inspect repeated
  public-fixture diagnostics. Review MCP wrapper and test it on actual hardware
  only after all queued jobs release the device. Stop by16:00UTC.

## 11:00 UTC checkpoint — actual move and larger-model queue

- The constrained 4B feedback diagnostic completed at clean source `31bb6a1`.
  It made three empty-result searches, listed files, then moved the invoice.
  Original contents are preserved at the destination, the source is absent,
  and every other file hash is unchanged. Existing verifier: **passed=false,
  calls_match=false, final_state_match=true, execution_ok=true**. Extra calls
  fail exact sequence scoring. This is a public-fixture diagnostic, not v2 or
  an accepted product/quality result. Evidence: `benchmarks/results/invoice-grammar-1000/`.
  Loop 18.142 s; broader diagnostic 29.702 s; no energy captured or speedup claim.
- A fresh Flash review supports these limited claims. The simple canary and
  observed actions do not cover every GBNF branch. Preserved grammar bytes have
  Windows CRLF; the report hashes the actual LF runtime string. Both hashes are
  documented. Future runs write exact UTF-8 bytes, fixing that artifact mismatch.
- The gateway was restored and `/api/status` reported native runtime available,
  all four registered artifacts available, and no tuner running. It is paused
  again for the sequential larger-model campaign.
- Read-only GGUF inspection found `qwen3` in the 8B artifact and `gpt-oss` in
  the 20B artifact. These metadata observations alone do not prove compatibility.
  Scheduled task `Qualcomm-Large-Dev-1100` now runs each model through the existing
  immutable experiment tracker, 35 development cases, CPU10/context4096, max128,
  no grammar/routing/speculation. Child timeout900 s; watchdog1020 s; task40 min.
  No overlapping jobs. Full-process energy remains diagnostic/uncommissioned.
- Inspect `grammar-1000/local/large-dev-1100/status.json` and its logs, plus
  `grammar-1000/local/experiments/`. Configs are private in the campaign folder;
  source stays pinned to clean `31bb6a1`. Archive every attempt and preserve
  unknown/unsupported outcomes. Supervisor restores and smoke-tests the service.
- Next wake: collect and verify these archives, then decide whether development
  evidence warrants a full unchanged 50-case milestone. Repeat the opt-in
  grammar diagnostic before proposing an MCP integration. Do not alter v2 or
  promote the single filesystem success to a quality PASS. Stop by16:00 UTC.

## 10:00 UTC checkpoint — grammar diagnostic and larger models

- Commit `31bb6a1` is pushed. An independent Flash/medium review found the
  diagnostic could exit successfully after a runtime error. That is fixed;
  effective loop limits are now passed explicitly and recorded. Focused tests:
  **33 passed**. The review's proposed dataset-selector concern was rejected:
  this standalone CLI only loads the public demonstration tasks.
- Both pinned downloads on the Latitude are complete and checksum-verified:
  Qwen3-8B Q4_K_M (5,027,784,512 bytes; SHA-256
  `120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4`)
  and gpt-oss-20b MXFP4 (12,109,566,624 bytes; SHA-256
  `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901`).
  Download success does not establish runtime support. Preflight architecture
  and quantization before attempting either model.
- A separate opt-in structured-output diagnostic uses a native exact-output
  grammar canary before any fixture action. The tool grammar is derived from
  current schemas; no fixture answers or filenames are embedded. This leaves
  the frozen evaluator, service and default behavior unchanged.
- Inspect scheduled task `Qualcomm-Grammar-1000` and checkout `grammar-1000`,
  pinned to `31bb6a1`. Supervisor: `local/feedback-supervisor/status.json`;
  result: `local/invoice-grammar-1000/diagnostic.json`. The child has a 180-second
  watchdog, and the supervisor requests gateway restoration on completion.
  Hardware is isolated from the now-completed downloads. Collect and publish
  the outcome next wake; no successful invoice task is claimed yet.
- Next priorities: inspect this diagnostic, verify gateway restoration, then
  preflight 8B/20B and use the existing experiment tracker for any formal run.
  Preserve all prior results and the unchanged quality gate. Stop by 16:00 UTC.

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

### 09:00 UTC checkpoint — native feedback works; syntax still fails

New opt-in diagnostic at `cd06b4215fbecdce7922afdc031148ece89c0908` uses a fresh
fixture, strict whole-response parsing and native tool-result messages. It is
not imported by service/MCP/frozen v2. Focused tests: 45 passed. See
`docs/secretary-feedback-diagnostic.md` for limits and methodology boundaries.

The Latitude ran the invoice example. After empty search results, its second
model turn acknowledged the tool result but produced a plain-text clarification.
Strict parsing rejected it; no move occurred; existing verification failed.
Raw diagnostic: `benchmarks/results/invoice-feedback-0900/`. Do not repair the
text or call this a v2 improvement. Service restoration was requested.

Current background job: `Qualcomm-Large-Downloads-0900`, using the existing
bounded range downloader with pinned 8B and 20B artifacts. Private queue is
`local/large-download-queue.json` on the Mac; copied to Windows as
`QualcommTools/large-download-queue-0900.json`. Download root/status:
`QualcommTools/models/large-download-status.json`. Existing parts are reused;
final files require exact size and SHA-256. Prior status was backed up. Worker
deadline is six hours, task cap 375 minutes, both before the 16:00 UTC cutoff.
Do not launch another download or benchmark concurrently without inspecting
this status. These downloads do not establish architecture/runtime support.

Next: verify transfer progress and gateway; use a real restrictive grammar
canary before any constrained-output feedback trial. Keep this opt-in diagnostic
separate from the frozen protocol and product defaults. The Flash route's prior
quota reset was reported around 09:38; at the next hourly checkpoint a single
fresh bounded review may be appropriate, without account rotation or paid fallback.

### 08:00 UTC checkpoint — six trials complete; 4B integration queued

Six rotated development trials completed and their seals verified after transfer.
Control: 45/105 attempts correct; stop: 58/105. Mean inference 788.680 versus
516.741 ms. Stop invalid rate remains 9.52%; all six trials have 0/9 clarification
success. Provenance-qualified measurements are not product qualification.
Public evidence and exact boundaries: `eval/results/qairt-repeats-0700.md`.
Private original archives/status are under the main Mac checkout's
`local/overnight-results-0800/`. Energy remains diagnostic, not comparable.

Gateway restoration completed. Actual HTP inference answered arithmetic correctly
but failed the only-number formatting instruction. Preserve that limitation.

Current hardware owner: `Qualcomm-4B-MCP-0800`, pinned clean Windows checkout
`roadmap-33c7edd`, source `33c7edd8f2013a5963d99cc321703efa3967408d`.
The driver uses console-free normal Python so MCP has working stdio without an
interactive window. Its MCP child also requests CREATE_NO_WINDOW on Windows.
Twenty-nine MCP tests passed before dispatch; the smoke now rejects dirty source.

The bounded integration runs `scripts/verify_tuner_loop.py` for model `qwen4b`,
two rounds, demo task `t13`. Tuner axes: CPU threads 6/10, context 4096, prefill
128, output 32, two repeats, no warmup; each sweep has a 240-second budget.
This is an integration smoke, not an official correctness/performance campaign.
Inspect `roadmap-33c7edd/local/mcp-0800-supervisor/status.json` and
`local/qwen4b-mcp-loop-0800/integration.json`. The supervisor limits the whole
run to 780 seconds and requests restoration of the existing service afterward.
Do not overlap inference or modify its source/config while running.

Next: preserve the two-round result; verify actual task state and applied model/
SDK identity. A successful invoice example does not erase the failed 50-case gate.
If tuning fails, preserve its reason rather than fabricating a recommendation.

The integration finished before this checkpoint ended: both rounds completed,
both applied CPU10/context4096, and both invoice tasks failed. Evidence is in
`benchmarks/results/qwen4b-mcp-loop-0800/`. The model requested literal search
`hexagon invoice`, received no matches, and the one-shot Secretary ended without
another inference turn or a move. This identifies a missing agent feedback loop
in addition to search/intent errors. Do not patch frozen search/parser semantics
or score this as success. Any multi-turn harness should be a separate opt-in
diagnostic contract until its versioned methodology is agreed. The service
restoration was requested; verify reachability next wake. No benchmark remains
active from the 08:00 campaign.

### 07:00 UTC checkpoint — recovery complete; balanced repeats queued

Both recovery campaigns completed. Full 4B scored 37/50 (74%), 4% invalid,
mean inference 5,940.103 ms. QAIRT control/stop scored 20/50 versus 29/50;
mean inference 810.762 versus 518.686 ms; invalid 34% versus 8%. No quality
PASS. Full details: `eval/results/overnight-0700-results.md`. Five completed
reports and telemetry are published unchanged and backfilled into verified
historical-diagnostic archives in this worktree's ignored `local/experiments/`.

Origin advanced through `a8c3707`; fast-forwarded without touching the dirty
main Mac checkout. Its experiment tracker, provenance fixes and diagnostics
passed 675 tests and 17 subtests here. The frozen data remain unchanged.

Current hardware owner is task `Qualcomm-QAIRT-Repeats-0700`, windowless Python,
clean Windows checkout `roadmap-a8c3707`. Status/plan/logs are under
`local/repeats-0700/`; immutable EXP archives are under that checkout's
`local/experiments/`. It runs six development-only trials through the committed
tracker, three per treatment with rotated order, one at a time. Child timeout
300 s; supervisor 360 s; campaign stops before 09:00 UTC. Do not overlap it.

The previous gateway returned HTTP 200 after recovery. It is paused for these
repeats. The wrapper now uses `roadmap-a8c3707` (previous wrapper backed up).
The campaign will restore it and save an actual arithmetic inference response
as `local/repeats-0700/gateway-smoke.json`. Inspect that response before claiming
success. The deployed code includes the QAIRT directory availability fix.

Next: collect/verify the six archives; analyze development-only repeatability;
verify restored gateway/MCP and pursue a correct task. Do not silently modify
the frozen prompt/parser/tool schema to address clarification failures; the
new `OWNER_DECISIONS_REQUIRED.md` records those versioned-methodology decisions.

### 06:00 UTC checkpoint — recovery is active

The 4B upload completed and both hashes match. Development result is published
under `eval/results/candidate_qwen4b-cpu10-dev-v1.*`: 25/35 correct, all six moves,
zero of nine clarifications, 5.71% invalid outputs, mean inference 6,756.383 ms.
See `eval/results/qwen4b-development-note.md` for scope, failures and telemetry.

Both original campaign processes exited with `0xC000013A` before the full 4B
result or any QAIRT result was saved. Their old status files are stale. No Python
inference processes remained when checked; origin of termination is unknown.
One bounded recovery was launched using `pythonw.exe` to avoid console coupling:

- Task `Qualcomm-Overnight-4B-Recovery-0600`: full candidate
  `qwen4b-cpu10-v2`, unchanged clean `16d1313`, output/status under
  `roadmap-16d1313/local/qwen4b-recovery-0600/`. Deadline 08:00 UTC.
- Task `Qualcomm-Overnight-QAIRT-Recovery-0600`: same four QAIRT trials, clean
  `728c6a2`, output/status under `roadmap-728c6a2/local/qairt-stop-recovery-0600/`.
  Waits for that recovery, then restores the service. Deadline 09:00 UTC.
- Both new tasks were observed Running. Do not restart the old campaigns or
  overlap these jobs. If this recovery is also interrupted, inspect the cause
  rather than blindly repeating it. Original partial logs remain private.
- The QAIRT model-directory availability bug is fixed locally and covered by a
  focused status test. Deploy the resulting commit only after current campaigns
  finish; do not alter their pinned clean checkouts.

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
