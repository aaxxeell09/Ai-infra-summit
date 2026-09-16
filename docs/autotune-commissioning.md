# TurboLab target commissioning

This path commissions scheduler costs. It does **not** qualify task energy,
select winners, change the frozen evaluator, or establish universal determinism.
No model is loaded by importing the module or by the default CLI path.

## Plan, then explicitly execute on the target

```powershell
python scripts/autotune_commission.py --config local/qairt-secretary.json
# Only on the Snapdragon, after committing clean code and checking running jobs:
python scripts/autotune_commission.py --config local/qairt-secretary.json --execute --resume
```

Default output: `local/autotune/commissioning.json`. Use `--output` for a new
independent commissioning. `--step resident`, `--step s1`, `--step s2`, and
`--step dev35` can be supplied independently or repeatedly. `--timeout` bounds
each target child/tracker request; it is a declared limit, not a measured cost.

Optional `--changed-config local/qairt-candidate.json` measures model close and
reload in the same process. The model, SDK and backend must remain identical;
only the explicitly supplied configuration changes. This does not claim a
configuration can be applied without a reload. Supply it before the resident
step succeeds; to commission another change, use a new output file.

S1 uses the existing backend smoke. S2 uses the existing diagnostic canary with
exactly eight development cases and fixed seed label `commissioning-v1`.
The resident probe uses only the first development case. Five additional
requests use the unchanged tools, reset behavior and scoring path; exact raw
output equality is an observation for those five requests only. Thinking stays
disabled by the native layer. Full development wall time uses the existing
experiment tracker with `--dataset dev`; the tracker archive is linked.

## Evidence and recovery

Every metric has `value`, `unit`, `source` (`measured`, `declared`, or
`unavailable`), UTC timestamp, backend, full configuration SHA256, artifact
identity and a combined model/configuration SHA256. Missing values are null.
Cold load means a fresh process including SDK initialization and model creation;
it does not mean the operating system file cache was flushed. Wall times include
the wrapper/probe process costs stated in each metric boundary.

Attempt directories under `local/autotune/commissioning-attempts/` retain request
snapshots, commands, PID, stdout/stderr, raw results and failures. Successful
steps are skipped on resume; failed steps get new attempt directories. An
interrupted `running` attempt blocks default resume because a native child may
survive. Check the target's running jobs first, then use
`--resume --acknowledge-interrupted`; the abandoned record remains untouched.
The JSON summary is mutable/rebuildable; attempt result files are exclusive.

Diagnostics hold the **same** `hardware-execution` OS mutex as the tracker,
under the experiment archive root. The diagnostic worker owns it for its native
lifetime, so controller death does not release the lock while that worker is
still running. dev35 relies on the tracker's own mutex; no nested lock is taken.
Use the same `--archives-root` as all other target workers. The API callbacks
never acquire the hardware mutex.

Proposer/critic latency is unavailable unless an API integration explicitly
supplies `TargetRunner(api_probe=callable)`. That callback receives the phase,
attempt directory and timeout and must enforce the timeout. No credentials,
provider defaults or mock latency are invented; the separate API branch may
supply this callable later. The CLI records absent integration as unavailable.

## Scheduler consumption

At startup, TurboLab validates commissioning against the control configuration,
model and SDK artifacts. Recorded S1, S2-eight-case and dev35 wall times replace
the temporary 180-second budget estimate for their corresponding stages.
They are **control reference estimates** for new candidates, never measured
candidate costs. S3 remains unavailable until separately commissioned; existing
explicitly declared fallback remains labeled. Config/model/SDK mismatch rejects
the record. Dry runs do not read target commissioning or load models.

Target validation still required: real loading, reload behavior, same-process
reuse, five-repeat outputs, target wall times, Windows locking and cancellation.
Portable tests inject execution; none are evidence of Snapdragon performance.
