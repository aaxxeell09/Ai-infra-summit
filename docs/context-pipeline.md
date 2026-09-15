# Context optimization pipeline

`turbo/context_pipeline.py` reduces selected tool-result payloads in a message
array before they are sent to a model. It is a local, stdlib-only, offline
module: no tokenizer downloads, no hosted APIs, no installs. Exact recovery of
any reduced payload is always available through the existing
`turbo/context.py` `ContextStore` (SHA-256 keyed).

## Guarantees

- Only `role="tool"` messages whose tool name is in `Policy.tools` or whose
  `tool_call_id` is in `Policy.call_map` are touched. System, user and
  assistant messages keep their original object references, byte-for-byte.
- `tool_call_id` and `name` on tool messages are never modified.
- Every applied reduction stores the exact source text in the store and embeds
  a `raw_ref` in the envelope. Lossy modes are labeled with `"lossy": true`
  and a `mode` string. Small payloads where the envelope would not save
  characters are skipped (`applied: false`).
- The module never counts tokens. All accounting is in characters. The
  `break_even` helper refuses token inputs that are not measured by a real
  tokenizer and rejects negative values.
- The recovery tool schema and executor (`RECOVERY_TOOL_SCHEMA`,
  `execute_recovery`) are opt-in. The pipeline never appends tools or schemas
  to caller message arrays.
- `stable_prefix_fingerprint` hashes the history up to the first tool result.
  Because non-tool history is never rewritten, the fingerprint is unchanged by
  optimization, which supports KV-prefix reuse comparisons.

## Reduction modes

- `field_projection`: deterministic JSON projection for list-of-object
  (search-result) shapes. Policy names the fields to keep; the module also
  always keeps path-like keys (`path`, `file`, `filepath`, `name`, `id`),
  numeric values, and negation keys (`negated*`, `not_*`, `inverted*`,
  `exclud*`). Key order is preserved, so output is deterministic.
- `compressor`: an optional local hook callable. If `cost_budget_chars` is
  set, inputs longer than the budget skip the hook (a cheap precheck, not a
  timeout: the module never promises to kill a running hook). Negative
  budgets disable the hook. Hook exceptions fall back to the pre-hook text.
- `preview`: truncation to `preview_chars`, available only with explicit
  `preview_opt_in`. Intended for arbitrary non-JSON output.
- `rtk_label`: RTK-inspired command-output labeling, ours and not the actual
  RTK binary (`context-pipeline/command-output`). Configured per call through
  `call_map[tool_call_id]`; the exit code and the full failure text are
  preserved verbatim, and raw recovery still applies.

## Usage sketch

```python
from turbo.context import ContextStore
from turbo.context_pipeline import Policy, optimize_messages

store = ContextStore(root)
policy = Policy(tools=frozenset({"search_units"}),
                fields={"search_units": ["snippet"]},
                call_map={"call_1": {"exit_code": 1}},
                rtk_label=True)
result = optimize_messages(messages, store, policy)
send(result["messages"])  # records: raw_ref/mode/lossy/saved_chars/elapsed_s
```

## Cost break-even

`break_even(input_tokens_saved, prefill_usd_per_mtok, overhead_usd,
prefix_loss_usd)` returns net USD saved. It raises on `None` (unmeasured) or
negative inputs. Token counts must come from a tokenizer measurement;
character counters are never converted into token claims.

## Caveman prose (opt-in)

`caveman_prose_instruction()` returns instruction text the caller may add for
the model to compress its own generated prose. It excludes JSON, code and
exact-value fields and never rewrites the user prompt; the module itself does
not modify prose.

## Measurable ablations

Each mode can be ablated independently by toggling the policy flags and
comparing `saved_chars` records and prefix fingerprints. A learned compressor
(e.g. LLMLingua-2) can be evaluated through the same `compressor` hook as an
external, local process. That route is **UNVERIFIED** in this repo: it
requires an external dependency and no hosted API or installation was used or
performed here. Keep it behind the hook until measured locally.

## Integration note

The parent runtime SDK supports prefix reuse and raw timings; the recorded
`elapsed_s` per result and the stable fingerprint are the integration points.
Device-side confirmation is still pending, so nothing here assumes that SDK.