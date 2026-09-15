# Benchmark protocol

The primary question is whether the Latitude generates tokens faster than the default configuration on identical weights and quantization. A separate experiment tests whether routing and context reduction complete local secretary tasks faster at comparable correctness.

## Controlled inference comparison

Use native ARM64 Python and GenieX v0.6.1 ARM64 on the Latitude. Pin model revision and SHA-256. Record runtime SHA-256, bundled llama.cpp version, CPU, OS, RAM, AC state and power plan. Stop competing inference services. Mac-side network latency is not device latency.

Screen CPU default and 2/4/6/8/10/12 threads plus GPU, NPU and hybrid. Shuffle screening order with seed 42. Use 512 random prompt tokens, 128 generated tokens, 4096 context, temperature 0, seed 42, one warmup and three measured repetitions. Reset KV each repetition. Retain early EOS, failures and timeouts. Verify resolved devices and logs rather than relying on requested flags.

Confirm the selected configuration using five alternating default/tuned pairs. Report median and spread. If output lengths differ, disclose them and add a matched workload before claiming a fixed-length decode gain. This establishes performance against the measured default, not all open-source runtimes; that broader claim requires an independently tuned upstream llama.cpp baseline.

## Separate experiments

| Experiment | Changed | Metric |
| --- | --- | --- |
| Native tuning | Threads or backend; same weights and workload | Native decode tokens/s |
| Speculation | N-gram strategy and draft length | Decode tokens/s; accepted draft tokens |
| Prefix reuse | Cold reset versus retained matching prefix | TTFT and prefill time |
| Context reduction | Tool-output representation | Total time including compression |
| Routing | Selected local model | Correct tasks/s and latency |
| Concise output | Prose budget | Generated tokens and total time |

Native profiles measure device throughput. Streaming HTTP timings are client-observed; chunks may contain multiple tokens. Never count chunks as tokens. Missing token usage means throughput is unknown. Prefix reuse is not free new-token prefill. Answer replay is not inference speed.

## Secretary evaluation

Use disposable files. Score tool name, arguments and filesystem state, not plausible prose or valid JSON alone. Include negation, similar filenames, missing information and required clarification. Hold out paraphrases from development. Count retries and fallback latency. A schema-valid answer can still be wrong.

For context reduction, count its own time, final serialized prompt, recovery calls and cache effects. Preserve exact paths, numbers, dates and negation or provide explicit raw recovery. Character savings are not token savings.

No final device result has been accepted yet. Inspect raw results and runtime configuration before publishing numbers; retain failed trials.
