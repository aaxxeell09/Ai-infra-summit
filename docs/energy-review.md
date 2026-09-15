# Energy review — benchmark/energy audit (worktree review/benchmark-energy)

Scope: committed scripts/sweep.py, turbo/telemetry.py, docs/benchmark-protocol.md at e87c800, plus raw screen-01 and confirm-01 results. Method-only audit; no new features.

## Verified correct

- Units: Energy Meter Energy is picowatt-hours. Delta 1.541409184e9 pWh x 3.6e-9 = 5.5490730624 J; / 1.0019639 s = 5.538 W. All screen/confirm energy_j and average_power_w values reproduce from the stored raw counter reads with this factor. The 44-trillion raw SYS increment is a cumulative lifetime counter, consistent with a continuous meter, not a per-call figure.
- Counter chain: each cell's energy_before equals the previous cell's energy_after across both screen-01 and confirm-01; no gap or overlap between trials. Deltas are positive and sane; no reset or stale read observed in either run.
- Headers/ctypes: PdhOpenQueryW, PdhAddEnglishCounterW, PdhCollectQueryData, PdhGetRawCounterValue are correct signatures for 64-bit Windows and were validated on the actual Latitude machine. RawCounter layout (status, FILETIME, FirstValue, SecondValue, dwCount) is correct for PDH_RAW_COUNTER; only FirstValue is used, which is valid for these cumulative counters. GetProcessMemoryInfo/PROCESS_MEMORY_COUNTERS_EX usage is correct.
- Baseline label: cpu-t0 log resolves n_threads=12 (default) and tuned leg n_threads=10. Honest pairing as designed.
- t/J definition in code: full-trial SYS energy (load + prefill + decode) over all generated tokens, warmup excluded from numerator only when --warmup 0. Label matches implementation.

## Bugs found and fixed (minimal patch, this worktree)

- Failed/timeout cells lost their paired energy_before/energy_after (they were only stored inside the target-exists branch). Now always recorded in the cell row, so failed trials keep their energy evidence.
- A counter reset or missing SYS delta silently produced energy with no SYS channel and a stale validity reason. Now the row records sys_delta_valid and tokens_per_joule_reason switches to an explicit "counter delta missing or reset" message.

## Known limitations (record, do not overclaim)

- GPU 10.8 W and NPU 16.7 W screen figures are full-trial averages over 44.3 s and 19.1 s walls that include compile/init; the CPU 53.7 W figure sits over a 7.98 s wall. Wall ranges are not comparable efficiency claims until confirm-phase matched durations exist.
- Thermal/drift unresolved. Confirm-01 shows 40-66 tok/s dips in both legs (deeper in 12-thread legs) and slow trials use less power (33-41 W) than fast ones (55-57 W). Distribution reporting, no robust 2%-gain claim. Record power state per trial; do not exclude bad baselines post hoc.
- -t N changes decode threads only; n_threads_batch stays 12 in the native logs. t/J includes prefill at 12 threads in both legs.
- Rails are separate; SYS is not wall power and rails overlap (do not sum).

## Acceptance checklist for the next confirmation

- [ ] AC status recorded at sweep start and each trial start/end (power_state in sweep.json and every cell row).
- [ ] Same model/runtime SHA-256 as prior runs; native JSON present for every completed cell.
- [ ] warmup=0, r=15, identical parameters both legs; alternating pairs preserved in sweep order.
- [ ] complete_length_runs = 15 per cell; any early-EOS run disclosed, never silently dropped.
- [ ] Per-cell energy_before/energy_after present even for failed/timeout cells; counter chain continuity checked across cells.
- [ ] sys_delta_valid true for every t/J number published; any reset trial re-run, not repaired.
- [ ] Report median + spread of per-trial decode tps and per-trial t/J; both legs' distributions shown including slow trials.
- [ ] Thermal caveat stated whenever trial-to-trial dips appear; no causal thermal claim without per-trial clock/thermal telemetry.

