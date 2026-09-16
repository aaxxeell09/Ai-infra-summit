# UNO Q native inference admission smoke

GenieX 0.6.1's Linux ARM64 CPU SDK successfully loaded SmolLM2-360M-Instruct Q8_0 on the actual Arduino UNO Q ABX00162 and generated two different answers. The process exited zero. This is CPU inference, with no claim of GPU/NPU execution.

| Prompt | Output | TTFT | Decode | Exact requested format |
| --- | --- | ---: | ---: | --- |
| Reply with exactly the word hello. | Hello, this is a helpful assistant. | 1835.518 ms | 7.546501 tokens/s | FAIL |
| What is two plus three? Reply with just the number. | 2 + 3 = 5 | 2060.241 ms | 7.515770 tokens/s | FAIL |

The SDK ran with two CPU threads, context 512, maximum output 16, no warmup, fresh KV per prompt and thinking disabled. Both generated answers ended at EOS. The SDK reports 39/44 actual prompt tokens and 8/7 generated tokens; `n_prompt=512` is an unused default when the prompt file is supplied. The aggregate combines different prompts and must not be used as a controlled throughput comparison. Verbose diagnostic logging was enabled. No memory peak or energy was measured.

The command, exact model/SDK archive hashes, outputs and limitations are in `provenance.json`; `benchmark.json` retains the SDK report with the private model path reduced to a basename. Create a UTF-8 `smoke-prompts.txt` containing those prompts separated by a line consisting only of `---`, then run the recorded command with `$SDK` and `$MODEL` pointing to the verified local artifacts.

This admits the board as a technically demonstrated CPU inference target. It does not make this model eligible for Secretary tasks, establish reliable structured output, or demonstrate a laptop speedup. A serving endpoint and physical policy-controller integration remain separate work.
