# Optional QAIRT first-tool-call stop

## Verified supported path

The pinned GenieX **v0.6.1 QAIRT wrapper rejects native stop sequences** (`GenerationConfig.stop_count > 0`) with `GENIEX_ERROR_COMMON_PARAM_NOT_SUPPORTED`. Do not pass `stop=["</tool_call>"]` to that plugin. The supported exposed mechanism is the native token callback returning false.

Primary source inspection:

- [GenieX QAIRT stop-list rejection](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/src/llm.cpp#L220-L223).
- [GenieX forwards callback cancellation](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/src/llm.cpp#L242-L256).
- GenieX v0.6.1 pins `geniex-qairt-plugin` at `551f576fd6bf6ecec2f33674f018c80bd2e358d1`. Its [pipeline appends each decoded piece before invoking the callback](https://github.com/qualcomm/geniex-qairt-plugin/blob/551f576fd6bf6ecec2f33674f018c80bd2e358d1/core/src/pipeline/llm_pipeline.cpp#L212-L223). Returning false stops generation; [the reason becomes `user`](https://github.com/qualcomm/geniex-qairt-plugin/blob/551f576fd6bf6ecec2f33674f018c80bd2e358d1/core/src/pipeline/llm_pipeline.cpp#L275-L279).

The underlying pipeline has additional stop-sequence machinery, but the exposed v0.6.1 QAIRT ABI refuses that configuration. No SDK rebuild or invented supported flag is used here.

## Candidate configuration

The new NativeModel option is **`stop_after_tool_call: true`**, QAIRT-only and false by default. `configs/qairt-single-action.example.json` is a path-neutral example. For a real comparison, copy the existing *working* private QAIRT configuration to `local/qairt-single-action.json`, preserving SDK path, artifact and every other setting, then add:

```json
"stop_after_tool_call": true
```

Use UTF-8 without BOM for evaluation configuration files. Do not overwrite the original configuration. The option is supported by the existing Secretary runner (both ordinary and instrumented execution) and the existing smoke helper through NativeModel. No production UI mode or model routing behavior is changed.

The callback searches for literal `</tool_call>` in streaming bytes, retaining only a small tail to handle split markers. It immediately returns false when the closing tag is complete, and continues returning false if the SDK invokes it again. External caller callbacks still receive the original chunks. A new matcher is created on each request.

**Native text is never sliced, reconstructed, repaired or forgiven.** The closing marker and any suffix already emitted in that completing piece remain in native `full_text`. If the piece already contains another action, the unchanged single-action evaluator must reject it. Missing markers, malformed JSON and invalid actions remain failures. Native token counts and profiling remain unmodified. `enable_thinking=False` is already present and remains unchanged.

Per-case `generation_control` records whether the option was enabled, the callback mechanism, delimiter detection, callback count after cancellation and `native_text_modified=false`. These fields show what was requested/observed; they do not prove deployed SDK cancellation until hardware verification. The full configuration hash records this candidate setting. Native stop_count remains zero because QAIRT rejects stop lists.

## Future Snapdragon comparison

Run baseline and candidate on the same clean current commit and the same deployed SDK/artifact, sequentially:

```powershell
python eval/run_secretary_eval.py --dataset dev --candidate-name qairt-stop-control-dev --config local/qairt-secretary.json --output-dir local/qairt-stop
python eval/run_secretary_eval.py --dataset dev --candidate-name qairt-stop-candidate-dev --config local/qairt-single-action.json --output-dir local/qairt-stop
```

The control must omit the option or set it to false. Retain both JSON/Markdown records. Existing historical quality-reference fingerprint checks remain active; these commands do not manufacture a new official baseline. Compare success, invalid outputs and inference latency, keeping any failures. For the current CPU/HTP/QAIRT descriptive report use [compare_backends](three-backend-comparison.md).

On the target confirm: the complete first closing marker survives, `generation_control.delimiter_seen=true`, native `profile.stop_reason=user` when stopped, and no continued callbacks/extra generated action. A marker may not be generated on every prompt; report those cases. Cancellation happens at a decoded-piece boundary, so it cannot undo text already produced in that piece. Check baseline and candidate memory/token/timing profiles without guessing a speedup.

No new Snapdragon inference was performed for this change. Only pinned source inspection and fake-SDK tests establish the implementation path; the deployed DLL behavior and actual accuracy/latency remain to be measured.

## Tests

```powershell
python -m pytest tests/test_qairt_single_action.py tests/test_native.py tests/test_backend_identity.py tests/test_secretary_eval.py -q
```

Synthetic tests cover every split within the marker, UTF-8 fragments, default-off behavior, exact native full_text/token retention, same-piece multiple calls rejected by the original parser, missing markers, ignored cancellation, invalid configuration and runner option propagation.
