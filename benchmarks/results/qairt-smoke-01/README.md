# Native QAIRT admission smoke

The actual Latitude generated `5` for an arithmetic prompt through the GenieX 0.6.1 QAIRT plugin after the native ABI correction in `14b009a`. It subsequently generated a file-tool response and `Pineapple` for two other inputs. These are prompt-dependent native outputs, not mocks.

The loaded artifact is the official Qualcomm Qwen3-0.6B GENIEX_QAIRT W4A16 package for Snapdragon X Elite, release v0.62.2. Downloaded ZIP: 641,390,179 bytes, locally recorded SHA-256 `92543e1eadb175d3c6ee2b0a05656690f49db9d6e5911d18f39af2f517471415`. Archive CRC validation passed. No upstream SHA-256 was available to compare; do not call the download upstream-checksum-verified.

The installed bundle exposes two compiled shards and CL512/1024/4096 variants. The runtime recognized HTP v73, applied its HTP power vote and completed inference. The excerpt preserves initialization evidence. No per-graph trace or hardware utilization counter was captured, so `dispatch_verified` remains false in generic API output; the requested device alone is not treated as proof.

For a representative Secretary request, CPU and QAIRT rendered exactly the same 2,924-character prompt: SHA-256 `50bf2ebac5ebc83b4391678f80960f8e5ed91df6048a07b54b686df20bf1a9e1`. Both retained the system instruction, five tool names/descriptions and closed thinking prefix. Their reported token counts were 683 and 684: the QAIRT diagnostic logged first-turn BOS insertion. This is byte-level prompt parity, not an assertion that token IDs or numerical weights match.

**These timing fields are diagnostic only.** The parity run overlapped another evaluation. The arithmetic run generated only two tokens. Neither establishes a representative speedup, stability, power efficiency or Secretary quality. QAIRT `prompt_time` equals its TTFT proxy in the pinned source; its prefill speed is not independently timed prefill. Do not chart it as directly equivalent to llama.cpp's measured prompt time.

A diagnostic that deinitialized and reinitialized the bridge in one process aborted in ggml's exception-handler assertion on Windows. Keeping one initialized runtime while closing individual model handles allowed the CPU→QAIRT sequence to complete. Service tuning now preserves that initialized bridge; isolated benchmark runs use fresh processes.

Sources: [official artifact/model card](https://huggingface.co/qualcomm/Qwen3-0.6B), [tagged QAIRT adapter](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/src/llm.cpp). These external sources identify the stack and measurement semantics; the JSON files contain this machine's observations.
