# TurboLab pilot persistence and recovery

This change repairs startup routing and orchestration durability. It does not
change the frozen Secretary evaluator, fixtures, expected actions, model
configuration, quality thresholds, or existing result archives. Tests use fake
subprocesses and fake later-stage executors; no hardware inference was run.

## Root causes

- `startup_probe_executor` explicitly passed `runner=None`, replacing the probe
  helper's previous default callable. The helper then attempted to call `None`.
  It now selects `subprocess.run` when the injected runner is `None`.
- Sessions were only saved at normal completion. An early executor exception
  could therefore leave no session checkpoint at all.
- Candidate stage pools and complete observations lived only in local variables.
  A resumed session could neither reconstruct the funnel nor know which exact
  work had completed. Controls also bypassed the scheduler's ownership guard.
- Resume passed the wrong shape to `Budget.restore`: `elapsed_s` without the
  required schema, instead of the supported `elapsed_seconds` field.

## Durable boundaries

Before any advisor request or hardware work, the session writes an atomic initial
checkpoint. It records the exact development-only settings needed by `--resume`.
A new run refuses to overwrite an existing session; choose a new session directory
or resume the existing one. A separate operating-system session lock surrounds
loading, execution and recovery writes. A second controller for the same session
is rejected, including a concurrent `--resume` process.

Each stage batch persists its ordered candidates, selected subset, control
configuration and unique batch identity before launching work. Each control or
candidate then checkpoints a `started` job before entering its executor. When an
executor returns, the complete observation and stage bookkeeping are atomically
checkpointed before returning to funnel postprocessing. Static rejections are
also checkpointed as they are recorded.

Hardware ownership uses one nonblocking scheduler mutex and the existing queue
claim. Controls follow the same path. Exceptions release the claim and local
mutex. They produce an explicitly unqualified failure journal entry, preserving
exception class, message, traceback and candidate/stage identity. Configured
credential values are redacted. A crash never becomes a made-up result row or
successful stage outcome. Attempt counts include failed/uncertain launches;
completed-stage counts remain separate.

Postprocessing is transactional with respect to session state: on an exception,
its in-memory changes are rolled back to the pre-processing snapshot. Resume
replays complete persisted observations into the funnel without repeating their
hardware calls. Pending stage pools, confirmations and full-development
observations remain durable across restarts.

## Recovery policy

The CLI exits nonzero on an unexpected failure and prints the absolute recovery
checkpoint and a concrete `--resume` command. It keeps the failure journal in the
checkpoint. Original control/configuration, subset sizes, seed, deadlines,
backend and diagnostic/dry-run choices are restored from that checkpoint.

- **Completed job:** replay its saved observation; never automatically relaunch.
- **Caught executor failure:** retain the terminal unqualified failure and skip
  that failed treatment on resume. Other pending work can continue. A deliberate
  retry of that treatment should use a new session so its failure remains visible.
- **Failed control:** block the batch and any candidate promotion. A missing or
  failed control never becomes a fabricated baseline; inspect the failure and
  start a new session for a deliberate retry.
- **Uncertain in-flight job (`started` after abrupt process death):** refuse to
  relaunch automatically. Inspect the child process and existing artifacts first.
  The software cannot establish exactly-once execution across an OS/process crash
  between child completion and the parent's durable write. Manual reconciliation
  is required; never delete or relabel the job merely to make resume proceed.

A write failure leaves the previous atomic checkpoint intact. If storage remains
unwritable, the newest in-memory evidence cannot be guaranteed durable; the last
readable checkpoint and any tracker archive remain the evidence. No recovery
operation rewrites a sealed experiment archive.

## Windows pilot and resume

From the isolated pilot checkout, after installing the intended Python/runtime
and confirming the private candidate configuration exists:

```powershell
$env:PYTHONUTF8 = '1'
python -X utf8 scripts/autotune.py `
  --control-config local/qairt-single-action.json `
  --control-name qairt-control --split development `
  --backend qairt_npu --budget-minutes 10 `
  --archive-root local/experiments-pilot-recovery `
  --session-dir local/autotune-pilot-recovery `
  --s2-cases 8 --s3-cases 18 --canary-seed pilot-20260916 `
  --stage-limit 1 --timeout 600 --mock-llm
```

Use the actual private configuration filename if it differs from the example.
The directory above must be new. To continue that exact session:

```powershell
python -X utf8 scripts/autotune.py --resume local/autotune-pilot-recovery/session.json
```

The mock advisor is not a model inference benchmark; real local stage execution
still requires Snapdragon hardware. Portable tests prove orchestration behavior,
not device liveness, model compatibility or performance.
