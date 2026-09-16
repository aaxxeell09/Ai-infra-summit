# Adversarial tracking-infrastructure audit

Red-team audit of the experiment tracking, provenance, KPI, energy, archival and
campaign infrastructure. The goal was to invalidate the system, not to confirm it.

## 1. Executive summary

The tracking layer is unusually disciplined. Every attack aimed at the three primary
KPIs failed: raw case rows always beat lying top-level metrics, failed tasks stay in the
energy numerator, missing energy never becomes zero, latency boundaries never silently
mix, and the archive seal detected 26 of 29 mutation attempts (the 3 undetected ones are
byte-level formatting of the checksum manifest itself, with no semantic effect). An
independent KPI and energy reimplementation, written without importing production code,
reproduced every published number in `eval/results/` exactly.

Two defects are nevertheless capable of producing a wrong, sealed, internally consistent
experimental conclusion:

* **TRK-001** Historical import binds telemetry to a result by **filename only**. A
  demonstration mispaired two runs and published `238.095 J/correct` where the true
  value was `16.667 J/correct`, a 14x error, in a sealed archive whose checksums all
  verify. The telemetry file names its own experiment in `candidate_name`; the tracker
  never reads it. **No live mispair exists in the repository today.**
* **TRK-002** Nothing prevents two `run()` supervisors from measuring **at the same time
  on the same machine**. Three concurrent runs were demonstrated overlapping in wall
  time. Both archives would look clean, complete and qualified while their latency and
  energy are mutually contaminated. `AGENTS.md` requires one hardware job at a time; the
  tracker does not enforce it.

Both are fixed in Phase 2. Three further gaps (campaign plan not bound to execution,
incomplete frozen-provenance comparison, energy accepted with no counter-resolution
guard) are documented; two of the three are fixed, one is left as an owner decision.

No frozen benchmark file, no historical result and no archived evidence was modified.
No inference was executed.

## 2. Scope

In scope: `turbo/experiments.py`, `turbo/experiment_analysis.py`, `turbo/campaign_plan.py`,
`turbo/json_io.py`, `turbo/runtime_identity.py`, `turbo/telemetry.py`,
`scripts/experiment_tracker.py` and the five sibling report scripts,
`eval/report_validation.py`, `eval/decision_table.py`, `eval/leakage_audit.py`,
`eval/energy_measurement.py`, `eval/validate_dataset.py`, `scripts/observe_secretary_eval.py`,
the eight named test modules, and every tracked artifact under `eval/results/`.

Out of scope: frozen Secretary semantics (prompt, parser, scoring, fixtures, golden
labels), product thresholds, BALANCED policy, and any hardware measurement.

## 3. Exact audited revision

```
commit        3498f7d0a989f1e02ed03d116ec0a38b020067c1
branch        claude/beautiful-mayer-gslb35 (fast-forwarded to origin/main)
worktree      clean (git status --porcelain=v2 empty) at audit start
tracked files 371, all byte-identical at audit start and audit end of Phase 1
test baseline 704 passed, 1 skipped, 17 subtests passed
frozen hashes dataset 643c036e..., fixture 69ec2946..., inventory 423d6cc7...,
              action_schema 3a1c425e..., system_prompt e977a9fe...
```

`local/` does not exist in this checkout. **There are no live `EXP-*` archives to audit.**
All archive behaviour below was exercised against synthetic archives in temporary
directories. No claim is made about archives that may exist on the Snapdragon.

## 4. Architecture

```
                         scripts/experiment_tracker.py  (CLI: run | backfill | backfill-known | ledger | verify)
                                            |
        +---------------------+-------------+--------------+-------------------+
        |                     |                            |                   |
   turbo.experiments.run  turbo.experiments.backfill  turbo.experiments.ledger  verify
        |                     |                            |
        |                     +-- report_metadata / sampling_evidence
        |                     +-- reserve -> initialize -> finish -> seal
        |
        +-- git_state          (commit, branch, dirty, status, diff HEAD --binary)
        +-- capture_environment(allowlisted OS + git/node/npm versions only)
        +-- artifact_identity  (model dir/file and SDK dir: per-file sha256 manifest)
        +-- captured_runner_identity (evaluator + application source sha256, legacy model hash)
        +-- eval.validate_dataset.validate()  -> frozen benchmark hashes
        +-- reserve            (archive_lock 'allocation' -> EXP-NNN_slug)
        +-- initialize         (manifest, config BYTES snapshot, argv, git evidence, environment)
        +-- subprocess.Popen   (new session / new process group; stdout+stderr to FILES)
        +-- capture_block      (optional PDH SYS counters around the whole child)
        +-- eval.report_validation.backend_identity_errors
        +-- finish -> kpis -> seal -> ledger

   read-only consumers (never mutate archives):
   turbo.experiment_analysis.{load_archive, summary, campaign, case_comparison, error_analysis}
   scripts/{render_experiment_summary, analyze_experiment_campaign,
            analyze_experiment_errors, compare_experiment_cases}.py
   turbo.campaign_plan.{plan, verify_plan, write_plan}  (offline, launches nothing)
```

Functions that can allocate an EXP ID: `reserve` only. Write an archive: `initialize`,
`finish`, `backfill`. Seal: `seal` only. Verify: `verify`. Rebuild the ledger: `ledger`
/ `_ledger`. Backfill: `backfill` / `_backfill`. Compute primary KPIs: `kpis` only
(re-derived and compared on every `load_archive`). Compute energy: `block_energy` only.
Capture git: `git_state`. Capture environment: `capture_environment`. Capture artifact
identity: `artifact_identity`, `captured_runner_identity`, `runtime_identity`. Execute a
child: `run`. Kill a child: `stop_child`. Copy raw results: `run` (`write_bytes`) and
`_backfill` (`write_bytes`). Create campaign plans: `campaign_plan.plan`. Compare runs:
`experiment_analysis.{compatibility, summary, campaign, case_comparison}`. Render human
output: `experiments._ledger`, `experiment_analysis.markdown`, `finish` (KPI.txt).

## 5. Data flow

```
config.json (bytes)
   |  read once, hashed, and COPIED into the archive
   v
archive/config.json  <--- the child is invoked with --config pointing HERE, not at the original
   |
   v
child evaluator --output-dir archive/runner-output
   |
   v
candidate_*.json  (exactly one required; 0 or 2+ -> status=failed, no evidence attached)
   |  byte-for-byte copy
   v
archive/result.json ---> kpis() ---> archive/kpi.json + archive/KPI.txt + manifest.primary_kpis
   |                        ^
   |                        |
archive/telemetry.json -----+  (block_energy: raw SYS pWh delta only)
   |
   v
seal -> artifact-hashes.sha256 (every file except itself)
   |
   v
ledger (rebuildable index; verify() re-run per archive, KPIs blanked on integrity failure)
   |
   v
summary / campaign / case comparison / error analysis  (load_archive re-derives KPIs and
                                                        refuses if they differ from kpi.json)
```

The archived config snapshot being the file the child actually executes against is the
single most important property here, and it holds.

## 6. Threat model

Trusted: the local operator and the machine. `--root` is operator-chosen and is followed
through symlinks by design. Filesystem administrators can modify archives; the seal
detects it, it does not prevent it. There is no signer identity, only tamper evidence.

Untrusted: the contents of result and telemetry JSON, historical files offered to
backfill, checksum manifests, experiment names, change and hypothesis free text, and
child process output. All of these were attacked.

Not defended against, by design and stated: a root-privileged attacker, a malicious
operator, and concurrent unrelated system load.

## 7. Evidence model

Authority hierarchy, confirmed in code and by experiment:

1. `result.json` raw case rows (byte-identical copy of the child's output)
2. `telemetry.json` raw PDH counters
3. derived per-experiment KPIs (`kpi.json`, `KPI.txt`, `manifest.primary_kpis`)
4. `EXPERIMENT_LEDGER.{csv,md}` (rebuildable index, never evidence)
5. human reports (`summary`, `campaign`, `docs/CURRENT_STATUS.md`)

Verified: a report whose top-level `metrics` claimed 34/35 while its rows contained 20/35
produced `success_rate_pct = 57.1429`. Raw rows win. The hierarchy is documented in
`docs/experiment-protocol.md`; it is now also enforced by `load_archive` re-deriving KPIs
and refusing any archive where `kpi.json` disagrees.

## 8. EXP lifecycle

`reserve` (locked) -> `initialize` (manifest, status=incomplete) -> child -> `finish`
(KPIs, status, notes) -> `seal` -> `ledger`. Statuses observed: `incomplete`, `failed`,
`timeout`, `completed_diagnostic`, `completed_qualified`, `historical_diagnostic`, plus
the ledger-only `integrity_failure`.

IDs are never reused: the index is `max(existing)+1` computed under an OS lock, counting
files and symlinks as well as directories. An abandoned archive keeps its ID forever and
the next attempt gets a new one. Confirmed under 20, 50 and 100 concurrent allocators:
100/100 unique, zero errors, zero collisions.

## 9. KPI lifecycle

`kpis()` is the only implementation. `load_archive` recomputes it and compares to the
stored `kpi.json`, so a hand-edited KPI file is rejected even before the checksum is
considered. An independent reimplementation (section 35) agrees on all 11 historical
reports.

## 10. Energy lifecycle

`EnergyMeter.sample()` before `Popen`, again after `wait`, then `block_energy` converts
`(after_pWh - before_pWh) * 3.6e-9`. The scope is the **whole evaluator child process**
and is labelled `full_process_energy`. `energy_qualification` is hardcoded
`diagnostic_uncommissioned` and `energy_comparable` hardcoded `False` for everything the
tracker produces; `experiment_analysis.energy_identity` refuses anything that is not
`commissioned` + `warm_task_v1`. No tracker output can therefore enter a qualified energy
comparison or a Pareto front today.

## 11. Provenance lifecycle

Bound per run: git commit / branch / dirty / status / binary diff, config bytes, model and
SDK per-file sha256 manifests (pre and post), evaluator and application source hashes
(pre and post), frozen benchmark hashes, environment allowlist, argv, and the resolved
absolute artifact paths. `GENIEX_QAIRT_LIB` is refused outright. Pre/post comparison
flags `artifact_changed_during_run`, `runner_sources_changed` and
`source_changed_during_run`, any of which blocks qualification.

## 12. Crash and recovery lifecycle

Injected at nine points. Results in section 33. Unsealed archives are always reported
`Archive incomplete: checksum manifest absent`; a half-written checksum manifest is
detected and cannot be re-sealed; `finish` refuses a sealed archive; `initialize` refuses
a non-empty directory; `atomic` leaves no temp debris and preserves the previous file on
`ENOSPC` or on an interrupt between fsync and rename. `KeyboardInterrupt` and `SystemExit`
are deliberately not caught by `run`'s `except Exception`, so an interrupted run leaves an
incomplete (never falsely complete) archive after its `finally` block stops the child.

## 13. Concurrency lifecycle

Allocation, backfill and ledger use three distinct OS-level locks acquired in one
direction only (backfill -> allocation -> ledger), so no deadlock is constructible. Locks
are released by the OS on process exit, so a stale lock file never blocks work
permanently. **Gap TRK-002: there is no lock around hardware execution itself.**

## 14. Backfill lifecycle

Identity is `sha256(result bytes) + sha256(telemetry bytes)`, not a filename. Re-importing
the same file is idempotent; the same bytes under a different name deduplicate to the
original archive; different bytes create a new archive; an existing archive that has been
tampered with causes a refusal rather than silent reuse; an abandoned (unsealed) archive
with the same fingerprint is left untouched and a new ID is allocated. Everything imported
is `historical_diagnostic` and cannot be upgraded. Counter probes receive no task KPIs.
**Gap TRK-001: telemetry is chosen by filename convention only.**

## 15. Ledger lifecycle

Deleting both ledger files and rebuilding reproduced byte-identical CSV and Markdown and
identical row objects. Corrupting the CSV and rebuilding reproduced identical rows.
Rebuilding never touched an archive. Incomplete and integrity-failed archives are listed
with their KPI cells blanked, not hidden.

## 16. Campaign lifecycle

`plan()` is deterministic (cyclic rotation, no randomness), requires at least 3
repetitions, enforces exactly one changed JSON field per candidate (numeric type changes
included: `1` and `1.0` count as different), and `verify_plan` rebuilds the whole schedule
and re-reads every config file, so a tampered plan or a drifted config is refused.
Position balance is exact when repetitions are a multiple of the treatment count and
differs by at most one otherwise, as documented. **Gap TRK-003: the campaign analyser has
no link to a plan.**

## 17. Human-report lifecycle

`manifest.json`, `kpi.json`, `KPI.txt`, `EXPERIMENT_LEDGER.csv`, `EXPERIMENT_LEDGER.md`
and the rendered summary were compared for four synthetic experiments including a
zero-correct and a perfect run. All six artifacts agreed on every value. Missing values
print `UNAVAILABLE`, never `0.000`. `markdown()` escapes `|` and newlines. The word
"winner" appears only as "**No overall winner.**"; "best", "optimal", "fastest" and "most
efficient" do not appear. **Gap TRK-007: the CSV export does not neutralise leading
`=`, `+`, `-`, `@`.**

## 18. Frozen-data protection

`validate()` runs on every `run()` and aborts on any frozen-hash drift. All 371 tracked
files were sha256-listed at Phase 0 and re-listed at the end of Phase 1: identical. The
full test suite leaves the worktree clean. `eval/leakage_audit.py` pins reviewed
historical exposure by content hash and fails closed on any new or changed exposure; it
exits 0 today with `unreviewed_exposure: []`.

## 19. Windows-specific behaviour

Not executable in this Linux environment; assessed by inspection.

* Locking uses `msvcrt.locking(LK_NBLCK, 1)` at offset 0 with a matching unlock, mirroring
  the POSIX `flock` path. Same-process reacquisition on a second handle will block until
  the 30 s deadline on both platforms; no code path does this.
  `test_two_processes_cannot_hold_the_same_archive_lock` now proves the mutual exclusion
  on whatever platform runs it, using two plain subprocesses and no tracker code, so a
  Windows failure would separate a broken mutex from a raced harness. See section 19a.
* `stop_child` uses `taskkill /PID <pid> /T /F` with `CREATE_NEW_PROCESS_GROUP`, the
  Windows analogue of the POSIX `killpg` that was demonstrated to kill grandchildren.
  Unverified on Windows.
* `command.txt` / `reproduce.txt` use `subprocess.list2cmdline` on Windows and
  `shlex.join` elsewhere. The POSIX form round-trips exactly through `shlex.split`.
* `parse_json` accepts a UTF-8 BOM, which Windows editors and `Out-File` produce.
* Child commands already use `-X utf8`.
* Archive names are `EXP-NNN_slug`; slugs are `[A-Za-z0-9][A-Za-z0-9_-]{0,95}`, so
  `CON`/`NUL`/`AUX` can only appear as a suffix of a longer name and are harmless, and
  trailing dots and spaces are rejected. Worst-case archive basename is 104 characters.

### 19a. Windows CI follow-up on the Phase 2 fixes

The first Phase 2 push was red on `windows-latest` only (Ubuntu and macOS green), at
733 passed / 5 skipped, failing exactly two of the new audit-regression tests. Both were
defects in the tests, not in the fixes.

**TRK-002 test race.** The original test waited for `root/.hardware-execution.lock` to
appear and then slept 0.5 s. `archive_lock` opens its lock file *before* calling
`msvcrt.locking` or `flock`, so file existence never proved acquisition. Under
multiprocessing spawn on Windows CI the holder had not necessarily acquired when the
contender started, so no `TimeoutError` was raised. The heuristic is replaced by an
explicit post-acquisition handshake: the holder writes a marker only from inside the
lock, and the parent waits for that marker. The holder and contender are now ordinary
subprocesses rather than a `multiprocessing.Pool`, and the contender records its outcome,
exception cause and errno as JSON so a future red run is self-diagnosing. A new
tracker-independent test, `test_two_processes_cannot_hold_the_same_archive_lock`, asserts
that a second process is refused while the first holds the lock and acquires once it is
released. It also asserts the lock file exists throughout, keeping the reason the old
heuristic was invalid visible in the test itself.

**TRK-008 platform contract.** The original test spied on `os.open` for `O_DIRECTORY`,
which is absent on Windows, so the spy recorded nothing. Rather than force a POSIX
assertion to pass, the contract is now explicit (option A of the follow-up):

> `fsync_directory` is a POSIX durability improvement. Windows has no portable
> directory-fsync primitive, so it is a documented no-op there and the durability of a
> replacement rests on `os.replace` / `MoveFileExW` alone. It returns `True` only when a
> directory entry was actually flushed, and never raises.

Both platforms now assert something real: POSIX must return `True`, Windows must return
`False`, `atomic` and `seal` must call it with the right directory on both, and a
dedicated test proves that atomic replacement is still correct and leaves no debris when
the flush is unsupported. No Windows-specific flush primitive was introduced, because
TRK-008 is P2 and a fragile implementation would be worse than a documented limitation.

**Durability guarantee, stated plainly:** on POSIX, a replaced manifest or ledger survives
a power loss once `atomic` returns. On Windows the replacement is atomic but the directory
entry may not be durable, so a power loss can revert it to the previous version. It cannot
corrupt it, and a sealed archive whose manifest reverted fails `verify` rather than
reading as valid.

## 20. Cross-platform behaviour

`artifact_identity` uses POSIX-normalised relative paths and sorted entries, so a model
directory hashes identically on both platforms. `captured_runner_identity` deliberately
reproduces the evaluator's platform-native directory hash for `model_sha256` and keeps the
portable `artifact.posix.v1` manifest separate; this is the correct split and is
documented in the code. Archive checksum manifests record POSIX relative paths. An archive
created on a case-sensitive filesystem containing both `A.json` and `a.json` could not be
restored on Windows; no code produces such names.

## 21. Security findings

No shell is ever used: `command.json` is an argv array and a payload of
`; touch X ; $(touch X) \`touch X\` && calc | echo` in `--change` and `--hypothesis`
created no file and was stored verbatim. Checksum-manifest entries that are absolute, use
`..`, a drive letter, a backslash, a colon or a NUL are refused, and every verified target
is re-checked with `resolve().is_relative_to(archive)`, so a malicious manifest cannot read
outside the archive. Experiment names cannot escape the root. `parse_json` rejects
duplicate keys, NaN, Infinity, invalid UTF-8 and trailing data. Environment capture
allowlists OS and three tool versions and records no environment variables, hostname,
user or network address. Remaining items: TRK-007 (CSV formula injection) and TRK-013
(the archive root is followed through a symlink, which is the stated trust boundary).

## 22. Reproducibility findings

An archive contains everything needed to re-derive its own KPIs and to state what was
run: argv, config bytes, commit, diff, model and SDK content hashes, frozen benchmark
hashes and raw child output. It does **not** contain the model weights or the SDK
binaries, by design. Identity is therefore reproducible; artifact availability is not
guaranteed. Six months later, a reader can prove which bytes were used and can detect
substitution, but cannot reconstruct the artifacts from the archive alone. This is the
correct trade-off and is stated in `docs/experiment-protocol.md`.

## 23. Statistical findings

`stats()` uses `statistics.stdev` (sample standard deviation, n-1), reports `n=1` as
`stddev=None`, suppresses CV when the mean is not positive, and requires at least 20
samples for a nearest-rank p95. The campaign report labels the column "Sample SD".
Pooled energy statistics are emitted only when every member of a group has an identical
and qualified energy signature, which is currently impossible, so `stats([None, ...])`
returns all-None rather than a fabricated figure.

The one real campaign in the repository, `eval/results/qairt-repeats-0700`, was
recomputed independently from its six raw reports and six telemetry files. It is a
correctly balanced two-treatment, three-repetition stop ablation whose execution order
(A,B / B,A / A,B) matches the cyclic rotation `campaign_plan.plan` produces:

```
stop_after_tool_call=false  positions 1,4,5   success mean 42.857  SD 2.857  CV 0.067
                                              median task 628.295 ms  SD 41.663
                                              J/correct 39.131 / 41.737 / 51.757 (diagnostic)
stop_after_tool_call=true   positions 2,3,6   success mean 55.238  SD 3.299  CV 0.060
                                              median task 564.787 ms  SD 2.504
                                              J/correct 25.762 / 27.331 / 29.553 (diagnostic)
```

The published `qairt-repeats-0700_campaign.json` reports exactly these group means
(42.857142857142854 and 55.23809523809524 success; 628.2946666666667 and 564.787 ms), two
groups, zero ungrouped attempts, zero integrity failures and `overall_winner: null`. Its
pooled energy statistic is `None` even though all six raw J/correct values exist and the
two treatments do not overlap on either success or energy. That suppression is the system
working as designed: diagnostic block energy is never pooled into a campaign statistic, no
matter how clean the separation looks. There is no significance test and none
is claimed. No "best run" selection exists anywhere: `min`/`max` appear only inside
`stats` and in the Pareto helper, which is gated behind qualified energy.

## 24. Test-quality findings

704 tests pass, 1 skipped, in 15 s. 32 of 43 test modules use temporary directories; the
worktree is clean after a full run. No test requires the network, a real model or the
Snapdragon except the single skipped parent-checkout integration test. Campaign planning
is deterministic so no seeding is required. The adversarial regression tests added in
Phase 2 are listed in section 38.

## 25. Documentation consistency

`docs/kpi-definitions.md`, `docs/timing-boundaries.md`, `docs/energy-boundaries.md` and
`docs/experiment-protocol.md` match the implementation on every claim checked, including
the explicit warning that `median_e2e_ms` is a storage field and not permission to call a
timer user-facing E2E. Two drifts: `docs/CURRENT_STATUS.md` states 674 tests where 704
now pass, and it tabulates EXP-001..EXP-006 which do not exist in this checkout (it is
explicitly a snapshot of `bcfd1c7`, 30 commits behind). Both of its published energy
figures were independently re-derived from raw counters and are correct (section 36).

## 26. Findings table

| ID | Sev | Category | File | Function | Fixed |
|---|---|---|---|---|---|
| TRK-001 | P0 | energy attribution | scripts/experiment_tracker.py, turbo/experiments.py | backfill-known, backfill | yes |
| TRK-002 | P0 | concurrency | turbo/experiments.py | run | yes |
| TRK-003 | P1 | campaign integrity | turbo/experiment_analysis.py | campaign | no (owner) |
| TRK-004 | P1 | frozen provenance | turbo/experiments.py | run | yes |
| TRK-005 | P2 | provenance binding | turbo/experiments.py | run | no (owner) |
| TRK-006 | P2 | energy resolution | turbo/experiments.py | block_energy | no (owner) |
| TRK-007 | P2 | human report safety | turbo/experiments.py | _ledger | yes |
| TRK-008 | P2 | durability | turbo/experiments.py | atomic, seal | yes |
| TRK-009 | P2 | TOCTOU | turbo/experiments.py | artifact_identity | no (mitigated) |
| TRK-010 | P3 | misleading evidence | turbo/experiments.py | block_energy | yes |
| TRK-011 | P3 | validation gap | turbo/experiments.py | run | no |
| TRK-012 | P3 | validation gap | turbo/experiments.py | run | no |
| TRK-013 | P3 | trust boundary | turbo/experiments.py | reserve | no (documented) |
| TRK-014 | P3 | ledger labelling | turbo/experiments.py | _ledger | no |
| TRK-015 | P3 | documentation | docs/CURRENT_STATUS.md | n/a | no (owner) |
| TRK-016 | P3 | naming | turbo/experiments.py | kpis | no (owner) |

## 27. P0 findings

### TRK-001 Telemetry is bound to a result by filename only

* **File / function**: `scripts/experiment_tracker.py::main` (`backfill-known`),
  `turbo/experiments.py::backfill`.
* **Issue**: `backfill-known` selects telemetry as
  `source.stem + '_telemetry.json'` or `label + '-telemetry.json'` and passes whichever
  exists. Nothing checks that the telemetry belongs to that result. Seven of the eleven
  telemetry files in `eval/results/` declare `candidate_name` and the full child argv
  including `--candidate-name`; both are ignored.
* **Why it matters**: the pairing determines the numerator of
  `gross_sys_j_per_correct_task`, which is published in `KPI.txt`, `kpi.json`, the ledger
  and `docs/CURRENT_STATUS.md`. A wrong pairing yields a wrong, sealed, fully verifiable
  archive.
* **Reproduction**: two synthetic runs, A with 21/35 correct and 350 J, B with 10/35 and
  5000 J, with their `_telemetry.json` files swapped. `backfill-known` produced
  `EXP-001_candidate_expA ... J=5000.0 J/cor=238.095` while the telemetry inside declared
  `candidate_name='expB'`. True value 16.667.
* **Impact**: 14x error on the primary energy KPI.
* **Historical data affected**: **no**. All eleven current pairings were checked and are
  correct.
* **Safe fix**: yes, implemented. **Hardware needed**: no. **Benchmark semantic risk**:
  none.

### TRK-002 No hardware execution mutex

* **File / function**: `turbo/experiments.py::run`.
* **Issue**: `run` takes the allocation lock only for the few milliseconds of `reserve`.
  Nothing serialises the child execution.
* **Why it matters**: `AGENTS.md` requires one hardware job at a time. Two overlapping
  Secretary runs on the Snapdragon contend for CPU, NPU and memory bandwidth. Both
  archives record a clean commit, matching hashes and complete case sets, so both can
  reach `completed_qualified` while their latency and energy are contaminated. Nothing in
  the recorded evidence reveals it. This is the definition of "appears reproducible when
  it is not".
* **Reproduction**: three `run()` calls in a multiprocessing pool against one root, each
  with a 2 s synthetic child. All three start timestamps precede all three end
  timestamps; EXP IDs were correctly unique.
* **Impact**: silently invalid latency and energy for every affected run.
* **Historical data affected**: unknown, cannot be determined from archives.
* **Safe fix**: yes, implemented as an exclusive lock held for the whole supervised
  execution. **Hardware needed**: no to implement, yes to observe contention.
  **Benchmark semantic risk**: none.

## 28. P1 findings

### TRK-003 Campaign analysis is not bound to a campaign plan

`turbo/experiment_analysis.campaign(paths)` takes archive paths only. It never reads a
plan, never reports planned versus attempted versus completed, and never checks run order,
block index or the plan's config byte hashes against the archives. A plan of six runs of
which five completed produces a report saying `total_attempts=5` with no indication that
one is missing. Integrity failures and ungrouped attempts are retained and visible, so a
run that *failed* is not hidden; a run that was never executed, or whose archive was
removed, is invisible.

Not fixed: matching archives to plan rows requires a naming convention that is an owner
decision. Recommended shape in section 39.

### TRK-004 Frozen provenance comparison is incomplete

`run()` compares only `benchmark_version`, `fixture_sha256`, `action_schema_sha256` and
`system_prompt_sha256` against `validate()`. `inventory_sha256` is produced by `validate()`
and used in `experiment_analysis.IDENTITY` but is never compared, and `protocol_version`
is never compared against the runner's `PROTOCOL` constant. A report declaring a wrong
`inventory_sha256` or an invented `protocol_version` produced no reason in the adversarial
matrix. `dataset_sha256` is deliberately and correctly compared against the selected split
rather than against `validate()`, avoiding the 35/50 hash ambiguity. Fixed.

## 29. P2 findings

* **TRK-005** `generation_protocol` is recorded but not bound. A report declaring
  `max_tokens 256, temperature 0.7, reset false` produced no reason and could reach
  `completed_qualified`. Downstream `signature()` includes it in IDENTITY, so two runs
  with different protocols are refused comparison, which contains the damage. Left to the
  owner because binding it changes which runs qualify.
* **TRK-006** `block_energy` only applies the "at least ten counter intervals" guard when
  `declared_counter_resolution_s` is present, and `--counter-resolution` is optional. A
  50 ms block with no declared resolution yielded a confident `350.0 J` and
  `35.0 J/correct`. Mitigated by the unconditional `diagnostic_uncommissioned` label.
  Left to the owner because requiring a resolution changes the CLI contract.
* **TRK-007** `EXPERIMENT_LEDGER.csv` writes `change` and `notes` raw. A change string of
  `=cmd|' /C calc'!A0` is written unescaped and would be interpreted by a spreadsheet.
  The Markdown ledger correctly escapes `|`. Fixed in the CSV export only; JSON and
  Markdown keep the raw text.
* **TRK-008** `atomic()` fsyncs the temporary file before `os.replace` but never fsyncs
  the containing directory, and `seal()` fsyncs the checksum manifest but not the
  directory. After a power loss the rename or the new directory entry can be lost. The
  previous file content is never corrupted, so the failure mode is "reverts", not
  "garbage". Fixed on POSIX; on Windows the flush is a documented no-op and the
  durability guarantee is explicitly reduced. See section 19a.
* **TRK-009** `artifact_identity` hashes a tree with no post-hash re-check, unlike
  `runtime_identity` which re-reads its signature and raises "Native SDK changed while
  being fingerprinted". A model mutated during the pre-hash and reverted before the
  post-hash would go unnoticed. Mitigated by the pre/post comparison in `run` for any
  change that persists. Documented, not fixed.

## 30. P3 findings

* **TRK-010** An invalid (negative or non-finite) `declared_counter_resolution_s` reports
  `Block shorter than ten declared counter intervals`, which is not the actual reason.
  Fixed.
* **TRK-011** A row's `split` field is not cross-validated against the frozen dataset.
  Relabelling a development row as `heldout` produced no reason at run time. It cannot be
  used to inject a genuine heldout case, because case IDs and hashes are checked against
  the selected split; the only effect is that downstream development-only diagnostics
  refuse the archive, which is fail-closed.
* **TRK-012** `branch` and `model_label` are recorded but not compared with the supervisor
  or with `model_sha256`. Cosmetic: the content hashes are bound.
* **TRK-013** `reserve` follows a symlinked `--root`. This is the stated trust boundary;
  documented, not changed.
* **TRK-014** A reserved directory with no manifest at all is listed with
  `qualification=None` rather than `unqualified_integrity_failure`, unlike every other
  broken archive. Its note correctly says "Manifest absent or malformed".
* **TRK-015** `docs/CURRENT_STATUS.md` states 674 tests (now 704) and tabulates archives
  absent from this checkout. It is explicitly a `bcfd1c7` snapshot.
* **TRK-016** The stored key `median_e2e_ms` overstates its scope. `docs/kpi-definitions.md`
  already says so explicitly and `KPI.txt` prints `MEDIAN_TASK` with a `LATENCY_SCOPE`
  line, so the human surface is correct. Renaming the stored key is a schema change and an
  owner decision.

## 31. Adversarial tests executed

| Area | Cases | Outcome |
|---|---|---|
| EXP allocation, hostile directory contents | 10 | all safe, no reuse |
| EXP slug injection | 24 | all path escapes refused, no name escaped the root |
| Concurrent allocation | 20 / 50 / 100 processes | 100% unique IDs, 0 errors |
| Archive mutation | 29 | 26 detected; 3 are manifest formatting with no semantic effect |
| Crash and partial write | 9 | all fail closed |
| Qualification matrix, wave 1 | 24 | none qualified; 22 produced a specific reason |
| Qualification matrix, wave 2 | 21 | none qualified; blind spots recorded as TRK-004/005/011/012 |
| KPI adversarial inputs | 40+ | no fake zero, no boundary mixing, no type confusion |
| Energy missingness | 20 | zero fake zeros |
| Backfill identity | 5 | idempotent, dedup by bytes, tamper refused |
| Ledger rebuild | 3 | byte-deterministic, archives untouched |
| JSON strictness | 12 | duplicates, NaN, Inf, bad UTF-8, trailing data all refused |
| Injection | 2 | no shell execution, no CSV escape (TRK-007) |
| Child behaviour | 4 | 105 MB stdout, grandchild kill, two candidates, timeout |
| Human/machine consistency | 4 experiments x 6 artifacts | all agree |
| Cross-platform lock proof | 2 independent processes, tracker-free | second process refused, acquires after release |

## 32. Synthetic corruption tests

Edited, deleted, added, renamed and nested files; file replaced by directory; file
replaced by a symlink with identical content; hardlink to an external file mutated after
sealing; truncated, emptied, garbled, CRLF, blank-line, no-trailing-newline and
extra-whitespace checksum manifests; duplicate, absolute, traversal, drive-letter,
backslash, uppercase-hash and short-hash manifest entries; manifest itself replaced by a
symlink; archive root replaced by a symlink; manifest status and experiment_id falsified.
All semantically meaningful mutations were detected. The hardlink case is worth stating
plainly: archive immutability rests on content hashes, not on filesystem permissions, and
external mutation of a hardlinked file is detected as `Hash mismatch`.

## 33. Crash simulations

Crash before seal, mid-seal (truncated manifest), zero-byte manifest, `finish` on a sealed
archive, `initialize` into a non-empty directory, `ENOSPC` inside `atomic`, interrupt
between fsync and rename, file added after seal, and a ledger over a mixed set of sealed,
unsealed, tampered and manifest-less archives. No crash produced an archive that appears
complete. A half-written manifest cannot be re-sealed, so the archive stays permanently
flagged rather than silently repaired. Temp debris was never left behind.

## 34. Concurrency simulations

100 concurrent `reserve` calls: 100 unique IDs. Lock ordering (backfill -> allocation ->
ledger) admits no inversion, so no deadlock is constructible. OS locks release on process
death, so a stale lock file cannot block work. Three concurrent `run()` supervisors
overlapped in wall time, which is TRK-002.

## 35. KPI independent recomputation

A separate implementation that does not import `turbo.experiments` recomputed success
rate, correct and attempted counts, latency boundary selection, median, p95 and mean from
raw rows for all eleven reports in `eval/results/`. It agreed with both the production
`kpis()` and the reports' own top-level `metrics` in every case. No duplicate case IDs, no
mixed or unknown splits, no dirty run. Dev runs have exactly 35 development rows; full
runs have exactly 35 development plus 15 heldout.

## 36. Energy independent recomputation

From raw picowatt-hour counters, without production helpers:

```
candidate_qairt-native-06-v1   SYS delta 760.734968 J over  54.045 s (14.076 W)
                               declared 760.7349677916  match  -> 23 correct -> 33.075433 J/correct
candidate_qwen4b-cpu10-dev-v1  SYS delta 10089.423458 J over 263.683 s (38.263 W)
                               declared 10089.4234579  match   -> 25 correct -> 403.576938 J/correct
```

Both match `docs/CURRENT_STATUS.md` to the published precision. Both scopes are correctly
declared "Complete evaluator child process". Neither is warm-task energy, and neither is
marked comparable anywhere.

All twenty historical reports reachable by `backfill-known` were re-derived the same way;
none disagreed with its own archive. The six `qairt-repeats-0700` J/correct values are in
section 23.

## 37. Remaining risks

1. TRK-003: a campaign can silently be short a run.
2. TRK-005 and TRK-006: a run can qualify with an unbound generation protocol, and block
   energy can be derived with no resolution evidence. Both are contained by
   `energy_comparable=False` and by comparison-time signature checks, not by run-time
   refusal.
3. Windows behaviour of the lock, the process-tree kill and the new hardware mutex is
   reasoned, not executed.
4. The archive binds artifact identity, not artifact bytes. Long-term reproduction depends
   on the model and SDK still existing.
5. Background system load is neither detected nor recorded. Exclusivity is an operator
   claim.
6. The tracker cannot distinguish workload families. Everything in the ledger is assumed
   to be a Secretary evaluation; an MCP or microbenchmark import would need an explicit
   `workload_kind` field before it could safely share the ledger.

## 38. Safe fixes performed

Six fixes, all in `turbo/experiments.py`, with `tests/test_tracking_audit_regression.py`
(33 tests) reproducing each finding. They are delivered as one commit because they touch
the same module and splitting them would have published intermediate states that do not
pass their own tests; every finding ID, its fix and its test are named below.

| Finding | Change | Regression test |
|---|---|---|
| TRK-001 | `telemetry_identity` / `telemetry_binding`; `backfill` refuses telemetry that names a different candidate than the result, or than the source file it was offered as a companion of; the manifest records `telemetry_binding` | `test_backfill_refuses_mismatched_telemetry_identity`, `test_backfill_refuses_foreign_telemetry_when_the_result_names_nothing`, `test_backfill_accepts_and_records_matching_telemetry_identity`, `test_backfill_accepts_companion_matching_the_source_label`, `test_backfill_marks_legacy_telemetry_binding_unverified`, `test_telemetry_identity_reads_recorded_child_argv` |
| TRK-002 | `run` holds an exclusive `hardware-execution` lock for the whole supervised execution, acquired before `reserve` so a refused run allocates no EXP ID; new `execution_lock_timeout`; the CLI reports `TimeoutError` cleanly | `test_second_concurrent_run_is_refused`, `test_run_releases_the_execution_lock` |
| TRK-004 | `frozen_provenance_errors` compares `inventory_sha256` and the runner `PROTOCOL` in addition to the previous four keys | `test_wrong_inventory_hash_blocks_qualification`, `test_wrong_protocol_version_blocks_qualification`, plus a new `protocol_version` case in the existing `test_run_qualification_checks_captured_identity` matrix |
| TRK-007 | `csv_safe` prefixes formula-leading cells in the CSV export only; row objects, JSON and Markdown keep the raw text | `test_csv_ledger_neutralises_formula_prefix`, `test_csv_formula_prefixes_are_neutralised`, `test_csv_safe_leaves_ordinary_values_untouched` |
| TRK-008 | `fsync_directory` after `os.replace` in `atomic` and after writing the checksum manifest in `seal`, tolerating platforms that refuse it | `test_atomic_and_seal_fsync_parent_directory`, `test_atomic_survives_a_platform_that_refuses_directory_fsync` |
| TRK-010 | an invalid declared counter resolution now reports `Invalid declared counter resolution` | `test_invalid_counter_resolution_reports_its_real_reason`, `test_short_block_still_reports_the_interval_reason`, `test_valid_resolution_still_accepts_a_long_block` |

False-negative check: `backfill-known` over the real `eval/results/` tree imports all 20
historical reports with zero integrity failures. Seven are classified
`declared_identity_match`, nine `unverified_filename_only` (legacy telemetry that declares
no identity), three `no_telemetry`, one probe. No previously importable report is refused.

Suite after the fixes: 737 passed, 1 skipped, 17 subtests. Frozen dataset validation and
the leakage audit both exit 0. Every file under `eval/` and `benchmarks/` is byte-identical
to its Phase 0 hash.

## 39. Owner decisions required

1. **TRK-003** Should `analyze_experiment_campaign.py` accept `--plan` and report
   planned / attempted / completed / missing? Recommended matching key: the tracker
   `--name` equals the plan `treatment` name, plus the plan's `config_byte_sha256` equal
   to the archived `config.json` hash. This changes the campaign report schema.
2. **TRK-005** Should `run()` refuse to qualify a report whose `generation_protocol`
   differs from the config-derived expectation (`max_tokens` from config, `temperature 0`,
   `reset true`)? This would newly unqualify runs.
3. **TRK-006** Should `--counter-resolution` become mandatory whenever
   `--capture-full-process-energy` is used? This changes the CLI contract.
4. **TRK-016** Should the stored key `median_e2e_ms` be renamed to
   `median_task_latency_ms` with a schema version bump?
5. **GF** Should the manifest gain an explicit `workload_kind` before any non-Secretary
   workload is imported?
6. `docs/CURRENT_STATUS.md` refresh (test count, and whether EXP-001..006 exist on the
   Snapdragon).

## 40. Final readiness verdict

| Dimension | Verdict |
|---|---|
| Experiment allocation | READY |
| Archive immutability | READY |
| Crash recovery | READY |
| Concurrency (allocation / ledger / backfill) | READY |
| Concurrency (hardware execution) | READY WITH CAVEATS (fixed in Phase 2, unverified on Windows) |
| KPI correctness | READY |
| Latency semantics | READY |
| Energy math | READY |
| Energy commissioning | NOT READY (by design: nothing is commissioned yet) |
| Provenance | READY WITH CAVEATS (TRK-005) |
| Model identity | READY |
| Runtime identity | READY WITH CAVEATS (TRK-009) |
| Dataset integrity | READY |
| Backfill | READY (after TRK-001 fix) |
| Ledger | READY |
| Campaign planning | READY |
| Campaign analysis | READY WITH CAVEATS (TRK-003) |
| Windows compatibility | READY WITH CAVEATS (reasoned, not executed) |
| CI | READY |
| Documentation | READY WITH CAVEATS (TRK-015) |
| Hardware qualification | NOT READY (no hardware access in this environment) |

This is not a statement that the system is safe in every dimension. It is a statement of
what was attacked, what held, and what did not.

## Appendix A: fifty red-team questions

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Two tracker processes allocate the same EXP ID? | NO | 100 concurrent allocators, 100 unique |
| 2 | Sealed archive altered without verify noticing? | NO (semantically) | 26/29 mutations detected; 3 are manifest byte formatting only |
| 3 | Incomplete archive appear complete? | NO | unsealed and partial-manifest both reported incomplete |
| 4 | Failed task disappear from the success denominator? | NO | `total_tasks` counts all rows; type-checked booleans |
| 5 | Failed-task energy disappear from J/correct numerator? | NO | block energy is authoritative; 350/21 verified |
| 6 | Missing energy become zero? | NO | 20 missingness cases, zero fake zeros |
| 7 | 35-case run mislabelled 50-case? | NO | `expected_count` plus per-case id/hash map |
| 8 | Top-level lying metrics override raw rows? | NO | 20/35 rows beat a 34/35 claim |
| 9 | Wrong telemetry attached to a result? | **YES** | TRK-001, demonstrated 14x error |
| 10 | Old telemetry attached to a new experiment? | NO for `run` (fresh output dir); **YES** for import | TRK-001 |
| 11 | Dirty run become qualified? | NO | `dirty` blocks qualification and is cross-checked |
| 12 | Model change during a run without detection? | NO for persistent change | pre/post `artifact_identity`; TRK-009 for revert-in-window |
| 13 | Runtime libraries change during a run? | NO | SDK directory is hashed pre and post |
| 14 | Git HEAD change during a run? | NO | `source_changed_during_run` |
| 15 | Ignored config/model changes escape provenance? | NO | config bytes archived, model and SDK hashed independently of git |
| 16 | Timeout leave a model process running? | NO on POSIX, UNKNOWN on Windows | grandchild killed via `killpg`; `taskkill /T /F` not executed |
| 17 | SSH disconnect produce a falsely completed experiment? | NO | supervisor death leaves the archive unsealed |
| 18 | Ledger corruption affect original evidence? | NO | rebuild is byte-identical, archives untouched |
| 19 | Backfill invent historical provenance? | NO | ingestion time and measurement time are separate fields |
| 20 | Summary disagree with raw rows? | NO | six artifacts agreed across four experiments |
| 21 | Campaign analysis silently drop timeouts? | NO | retained as ungrouped or integrity failures |
| 22 | Campaign analysis cherry-pick the best run? | NO | no selection code exists |
| 23 | Full-process energy labelled warm-task? | NO | scope is set by the producer and re-checked |
| 24 | Incomparable energy pooled? | NO | pooling requires one identical qualified signature |
| 25 | NPU request reported as verified dispatch? | NO | `verified_consistent` requires an explicit `dispatch_verified=true` |
| 26 | Heldout cases enter optimization diagnostics? | NO | error analysis and case comparison refuse non-development rows |
| 27 | Archive path traversal escape the root? | NO | 24 hostile slugs, all refused or contained |
| 28 | Malicious checksum manifest read outside the archive? | NO | absolute, `..`, drive, backslash, colon, NUL all refused |
| 29 | Command or hypothesis input cause shell execution? | NO | argv arrays only; payload stored verbatim |
| 30 | Windows behaviour differ materially from Linux? | PARTIALLY | locking and process-tree kill are analogous but unexecuted |
| 31 | Stale lock permanently block work? | NO | OS locks release on process exit |
| 32 | Crash reuse an EXP ID? | NO | index is max+1 over all entries including files |
| 33 | `backfill-known` create duplicates? | NO | content fingerprint dedup, verified idempotent |
| 34 | Historical data silently rewritten? | NO | 371 tracked files byte-identical before and after Phase 1 |
| 35 | Regenerated ledger produce different KPI values? | NO | byte-identical CSV and MD on rebuild |
| 36 | Raw and declared energy disagree yet be accepted? | NO | `math.isclose(rel_tol=1e-7)` or refusal |
| 37 | Zero-correct cause divide-by-zero or zero energy? | NO | `J/correct = None`, `gross_sys_j` retained |
| 38 | Bool pass numeric validation because bool is int? | NO | `finite()` uses `type(v) in (int, float)` |
| 39 | NaN or Infinity enter machine-readable evidence? | NO | `parse_json` refuses them, `allow_nan=False` on write |
| 40 | Duplicate JSON keys change interpretation? | NO | refused at parse time |
| 41 | Hard links undermine archive immutability? | NO | external mutation detected as a hash mismatch |
| 42 | Symlink or junction redirect archive writes? | PARTIALLY | a symlinked `--root` is followed; stated trust boundary (TRK-013) |
| 43 | Huge stdout deadlock the child? | NO | 105 MB written to a file handle in 0.8 s |
| 44 | Grandchild survive a timeout? | NO on POSIX, UNKNOWN on Windows | marker file stopped advancing |
| 45 | Report output overwrite an input? | NO | exclusive create, refuses output inside a source archive |
| 46 | Verifier tricked by Unicode or path normalization? | NO | a name that does not resolve to a file fails closed |
| 47 | Experimental state lost if the disk fills? | NO | `ENOSPC` preserved the previous file and left no debris |
| 48 | Partially written checksum manifest accepted? | NO | inventory mismatch, and re-sealing is refused |
| 49 | Campaign control link point to an invalid archive? | NO | `run` verifies the control archive and its measured report |
| 50 | Human-facing "ready" status exceed the evidence? | NO | `CURRENT_STATUS.md` claims are conservative and were re-derived |
