# 4B two-round tuner/apply/MCP integration

Clean source `33c7edd8f2013a5963d99cc321703efa3967408d` completed both rounds on the Latitude. CPU threads 6 and 10 were measured; Fast and Efficient each applied CPU10/context4096 in their respective sweeps. Model/SDK binding and real native inference survived both cycles. Mode labels are exploratory, not quality-qualified product policies.

**Both invoice tasks failed.** Each produced a search with no matching results and no move. The existing one-shot Secretary does not feed that tool result back into another model turn. Successful lifecycle execution is not successful task execution. The same measured configuration was applied in both rounds; no mode speedup or efficiency benefit is claimed. SYS tokens/J differed substantially across short full-process trials, so those rankings require confirmation.

The preserved integration record contains native results, tuning cells, applied runtime and final-state verification. Private user-path prefixes were redacted; measurement values and failures were retained. This is an integration smoke, not the frozen 50-case benchmark.

Command:

```powershell
python -X utf8 scripts/verify_tuner_loop.py --config local/mcp-config.json --model-id qwen4b --search-space local/mcp-search.json --output local/qwen4b-mcp-loop-0800 --rounds 2
```

Search: CPU threads 6/10, context4096, nominal prefill128, output32, repeats2, warmup0. Shared service configuration supplied a prompt file; the recorded prompt hash and actual native token counts are authoritative. Each sweep budget was240 seconds. Existing frozen prompt/parser/executor and demo golden task were unchanged.
