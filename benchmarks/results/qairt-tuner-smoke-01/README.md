# QAIRT tuner command smoke on the Latitude

Source provenance correction: the original smoke did not record its application
commit or dirty status. The later access check found that checkout still pointed
to an older Git bundle, so the earlier `718140c` clean-checkout attribution cannot
be established. Preserve the command/output evidence without that attribution.
The fresh `qairt-mcp-loop-01` run explicitly verifies clean commit `16d1313`.
Model/runtime component identities
are recorded in `eval/results/candidate_qairt-native-06-v1_runtime.json`.

The corrected tuner passed a declared QAIRT shard, native `-c 0`, NPU placement
and zero llama.cpp threads. Both 32-token repetitions completed at full length.
Median decode was **84.998 tokens/s**, median TTFT **28.355 ms**. This is a tiny
single-cell command-path smoke, with no comparator, quality qualification or
speedup claim. Both runs and the exact generated command are retained.

The native report counts **128 prompt tokens**, although the nominal `-p` axis
was 64. With a text prompt, the axis is not the measured tokenizer count; QAIRT
can include graph padding. Its reported prefill number is tokens / TTFT and is
not an independent prefill measurement.

The cell captured **50.617 J SYS** over its full subprocess, including model
loading. Memory and counter details remain in `record.json`. These values do
not establish warm-task efficiency. No other inference/download job was active
at launch; unlike the earlier prompt-parity diagnostic, this cell was isolated.

At this commit, QAIRT service mode export was still rejected, as retained in
`recommendation_error`. Commit `efd5100` adds QAIRT export/apply and SDK binding;
the first integration launch was blocked by the offline Latitude. After access
returned, a new checkout pinned to `16d1313` completed both rounds; see
`../qairt-mcp-loop-01/`. Both invoice tasks still failed.

Paths are replaced with `${TOOLS}` / `${USER_HOME}` placeholders. Numeric results
and stored hashes are unchanged. To reproduce, register this official bundle as
`Variant(..., plugin="qairt", kind="llm", compiled_contexts=(4096,))`, use
`SearchSpace(devices=("npu",), threads=(0,), contexts=(4096,), prompt_tokens=64,
gen_tokens=32, repeats=2, warmup=0)`, and call `run_tuning` with the supplied
`prompt.txt` and the Windows ARM64 v0.6.1 SDK benchmark executable.
