# Durable canary artifact identity

Base: `389c2e8a8d073254e18c5c213a1f574ca79930df`.
No inference, benchmark semantic changes, dataset changes or historical archive edits.

## Verified failure mechanism

The old executor chose `<candidate_id>-<stage>.json`. Repeated controls retain
`CONTROL-S2-<config hash>`, so the second batch chose the same filename.
The diagnostic script performs generation before its exclusive `open('x')` write.
Consequently that launch could consume hardware time and then fail to save. This
is an orchestration collision, not evidence of a model failure. The previously
failed pilot and its session remain untouched.

## Identity and reservation

The scheduler attaches a copy-only execution identity `{session_id, job_id, stage}`
to S2/S3 invocations. This is persisted in the started job before execution. It
never changes the candidate/configuration hash, treatment or original pool item.

Canaries use:

```
<canaries>/jobs/<sha256(canonical execution identity)>/<candidate_id>-<stage>.json
```

The job directory is exclusively created **before** invoking the subprocess.
`request.json` records job identity, candidate ID, unchanged comparison config
hash, full config hash, stage, subset size, seed and artifact paths. It is written
exclusively and flushed/fsynced. A pre-existing directory, reservation or output
blocks launch. Existing config snapshots are checked instead of silently reused
when different. The diagnostic script still writes its result with `open('x')`.

Both control and candidate canaries retain their existing leaf filenames and
measurement/scoring behavior; durable invocations now have an additional directory.
Direct executor callers without durable job metadata retain the old flat output
name, with an exclusive `.attempt.json` reservation before launch. A second call
using that identity is refused, even if its first launch failed without an output.
Intentional new attempts must use distinct durable jobs, not delete reservations.

Successful and failed returned observations point to the request/output artifacts.
A failure may have no output file; its artifact path is a destination, not a claim
that evidence exists. Reservations contain intent, never invented observations.

## Resume

Completed jobs return their stored observation without entering the executor.
A different candidate/configuration/stage cannot be rebound to a completed job ID.
Failed and uncertain attempts retain the existing recovery policy and are not
silently relaunched. A crash after reservation but before output leaves that
reservation occupied. A new session is required for the previously failed target
pilot; this change does not rewrite or repair its historical evidence.

This addresses process crashes and normal atomic checkpoint recovery. Filesystem,
power-loss and persistent disk-error guarantees remain those of the underlying
storage; directory entries are not explicitly fsynced on all operating systems.

## Target retry (not executed by this work)

Use a clean checkout of this branch, the existing private config, and unused
session/archive directories. Confirm there is no competing hardware job.

```powershell
$env:PYTHONUTF8 = '1'
python -X utf8 scripts/autotune.py `
  --budget-minutes 10 --backend qairt_npu --split development `
  --control-config local/qairt-single-action.json --control-name qairt-control `
  --session-dir local/autotune-pilot-canary-id-v1 `
  --archive-root local/experiments-pilot-canary-id-v1 `
  --mock-llm --s2-cases 8 --s3-cases 18 --canary-seed pilot-20260916 `
  --stage-limit 1 --timeout 600
```

Resume only this new session if appropriate:

```powershell
python -X utf8 scripts/autotune.py --resume local/autotune-pilot-canary-id-v1/session.json
```

Portable tests use exclusive-writing fake subprocesses and the real batch/router/
canary/checkpoint paths. They prove separation, attribution, no overwrite, stale
artifact refusal, failed/uncertain-job handling and completed replay. They do not
validate Snapdragon inference, speed or quality.
