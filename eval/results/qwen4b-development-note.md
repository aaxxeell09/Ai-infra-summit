# Qwen3-4B instruction candidate — development screening

Measured on the Latitude at clean application commit
`16d13138a61fd3f0e4bcbe5ae6bcb2271fb1b843`, using the unchanged 35 development
cases of `secretary-eval-v2`. Configuration and model SHA-256 are recorded in
`candidate_qwen4b-cpu10-dev-v1.json` and the previously committed candidate manifest.
The 2,375,773,280-byte model was verified on both machines before inference.

| Metric | Observed |
|---|---:|
| Correct tasks | 25/35 (71.43%) |
| Move cases | 6/6 |
| Clarification cases | 0/9 |
| Invalid outputs | 2/35 (5.71%) |
| Mean inference latency | 6,756.383 ms |
| Median inference latency | 4,691.478 ms |
| p95 inference latency | 23,922.892 ms |
| Mean complete task latency | 6,839.597 ms |
| Peak working set | 3,833.918 MiB |
| Sampled peak private memory | 4,928.188 MiB |

The broader `clarification_no_action_accuracy` field includes ordinary action
cases; it is not the 0/9 clarification-only score. All nine clarification prompts
failed. Two produced natural-language responses instead of a tool call; others
invented missing information, selected ambiguous paths, or attempted unsupported
operations through another tool. The remaining failure selected search instead
of reading the requested file. Preserve the unchanged scorer's interpretation.

SYS measured 10,089.423 J over 263.683 s (38.263 W average). This interval covers
the full evaluator process, including loading, hashing, warmup and scoring; it
is not warm-task energy or NPU-only power. Tokens/J is unavailable because the
untimed warmup token count is missing. AC power remained connected. Timing
outliers are retained; this is a single development run, not a stabilized speed
claim. Native profiles are preserved for investigation.

The historical-reference comparison is **NOT_COMPARABLE** because evaluator
fingerprints differ. The 5.71% invalid-output rate also exceeds the frozen 2%
absolute ceiling. This candidate is not admitted as a reliable Secretary.

The following full-suite run was interrupted before producing a result. Both
scheduled Python campaign processes exited with `0xC000013A`
([Microsoft NTSTATUS reference](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55)).
The initiating cause is unknown; no full-suite score or telemetry is inferred
from incomplete logs. A single bounded recovery uses `pythonw.exe`, a new output
directory and candidate name `qwen4b-cpu10-v2`. It does not rerun or overwrite this
completed development measurement. QAIRT trials remain sequential after it.

Private user-path prefixes were replaced with placeholders before publication;
recorded hashes, metrics, model outputs and comparisons were preserved.

Reproduce the completed run from the pinned commit after filling the three
private configuration fields described in the manifest:

```powershell
python -X utf8 scripts/observe_secretary_eval.py qwen4b-cpu10-dev-v1 dev --config local/qwen4b-cpu10-config.json --output-dir local/qwen4b-evaluation
```

Use a fresh output directory for a repeat; existing results are never overwritten.
