# QAIRT tune → apply → MCP, twice on the Latitude

**The integration loop works; the invoice task does not.** On clean application
commit `16d13138a61fd3f0e4bcbe5ae6bcb2271fb1b843`, the real Windows ARM64 SDK
completed two rounds through stdio MCP, loopback HTTP and native QAIRT inference.
The same service process tuned again after having loaded a model, avoiding the
previous SDK deinit/reinit crash. Each tune used two full 32-token trials.

| Round | Requested mode | Applied placement / threads / context | Arithmetic | Invoice |
| --- | --- | --- | --- | --- |
| 1 | Fast | NPU / 0 / 4096 | `5` | Failed action and final-state checks |
| 2 | Efficient | NPU / 0 / 4096 | `5` | Wrong source path; tool execution rejected |

Both modes select the **same single measured configuration** in this smoke.
Their differing answer lengths/times are not a speed–efficiency comparison.
Recommendations remain provisional and quality uncalibrated. The first invoice
output also contained malformed/multiple calls; the parser executed valid list
calls but the complete task failed. No real user files were touched.

The integration report retains every MCP response, applied config, runtime
manifest (51 executable/native-library files), token counts, tuner subprocess
telemetry, task verification and both failures. Two rounds took 17.241 and
13.380 seconds including tuning, validation, model loading and the requests;
this is integration timing, not an isolated inference latency benchmark.

Model: official Qwen3-0.6B QAIRT W4A16 release v0.62.2 on HTP v73. For component
hashes see `eval/results/candidate_qairt-native-06-v1_runtime.json`.
No competing inference or download process was active during the test.

Reproduction at the stated commit:

```powershell
python -X utf8 scripts/verify_tuner_loop.py --config local/qairt-loop-config.json --model-id qwen06-qairt --search-space local/qairt-loop-search.json --output local/qairt-mcp-loop-01 --rounds 2
```

Register the official bundle with plugin `qairt`, device `npu`, kind `llm`,
compiled context `[4096]`; configure the actual SDK root, benchmark executable,
and `tuner.prompt_file` using `benchmarks/results/qairt-tuner-smoke-01/prompt.txt`.
Search: devices `["npu"]`, threads `[0]`, contexts `[4096]`, nominal prompt tokens
64, generated tokens 32, repeats 2, warmup 0. The actual reported prompt count
is retained; it need not equal the nominal prompt axis.

Private paths in the published report use `${TOOLS}` and `${USER_HOME}`.
The invoice is the interactive demo fixture `t13`, not an additional official
50-case correctness run. The frozen dataset and historical baseline are untouched.
