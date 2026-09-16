# Opt-in tool-feedback diagnostic

`turbo/secretary_loop.py` is a separate fixture-only experiment, disabled unless
explicitly enabled. The service, router, MCP tools and frozen evaluator do not
import it. Version: `secretary-feedback-diagnostic-v1`.

The previous invoice smoke ended after an unsuccessful search. This diagnostic
passes each actual tool result into the next model turn using native assistant
`tool_calls` and matching tool-message IDs. It uses the same tool schemas and
executor, but a separately versioned one-action-per-turn instruction and strict
whole-response decoder. It is **not an identical secretary-eval-v2 protocol**.

Limits: a newly created synthetic fixture only; six turns by default (maximum
eight); one successful file move; repeated identical actions on unchanged state
stop; no action executes after the deadline. The CLI uses 128 output tokens per
turn and a 90-second loop budget. An external process supervisor is required for
blocked native calls. Malformed JSON, duplicate keys, extra envelopes/suffixes,
unknown tools and unsafe path spellings are rejected without repairing output.
Existing sandbox traversal and overwrite checks still apply. No shell tool exists.

`DONE` records a model claim, not success. A successful move records
`mutation_executed_awaiting_verification`. Existing demo verification is reported
unchanged, including exact-call and full-state checks. Extra legitimate search
steps can fail the original exact-call check even if final state matches; retain
both values. No overall quality PASS, new benchmark or threshold is created.

Run only from clean committed source, using private native configuration:

```powershell
python -X utf8 scripts/run_secretary_feedback.py --enable-candidate --config local/qwen4b-cpu10-config.json --task-id t13 --output local/feedback-diagnostic
```

The CLI records native responses/profiles, messages, actions/results, before/after
file hashes, model/SDK identity, configuration, source and timing boundaries.
Original outputs remain untouched. There are no model-specific answer rules or
held-out prompts in the implementation. Production adoption and any formal
quality comparison require the versioned-methodology decision recorded in
`OWNER_DECISIONS_REQUIRED.md`.

## Optional constrained-output canary

`--constrain-tools` adds a separate GBNF treatment. It first asks the native
runtime for an unrelated response while a grammar permits only `CANARY_OK_731`.
If the returned text is not that exact literal, no fixture actions are attempted.
The raw canary result is saved. Passing that canary establishes the restrictive
path on that runtime/model for this run; it does not prove the full tool grammar
or semantic intent. The subsequent real output and strict decoder remain the
acceptance check for each action.

The full grammar is derived from the existing required-string tool schemas and
permits exactly one envelope or DONE. It does not encode filenames, expected
answers or a preferred tool. It constrains format, while the strict decoder and
sandbox still validate arguments. Native output is never repaired. Grammar text
and SHA-256 are saved with the diagnostic. The default remains unconstrained.

GBNF syntax follows the primary [llama.cpp grammar examples](https://github.com/ggml-org/llama.cpp/blob/master/grammars/json.gbnf);
the installed GenieX v0.6.1 path must pass the native canary rather than being
assumed compatible with current upstream. This uses upstream constrained decoding,
not a new inference-kernel optimization.
