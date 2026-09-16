# Constrained feedback diagnostic: invoice moved, existing verifier failed

Clean source `31bb6a178638eda96c33fe3b9f0bbd4ec97c3ebe`, GenieX 0.6.1 llama.cpp
CPU/10 threads, Qwen3-4B-Instruct-2507 Q4_0, on the Latitude 7455. This is the
separate opt-in public demonstration diagnostic, **not secretary-eval-v2**.
No frozen prompt, golden data, parser, scoring or executor was changed.

The restrictive native grammar canary returned its exact required literal. The
five subsequent tool calls were valid without output repair: three searches
returned no matches, list_files returned the workspace inventory, then move_file
moved the requested invoice to the correct destination. The original file SHA-256
is present at the destination; the source is absent; all other file hashes match.

Unchanged demo verification reports:

- `passed: false`
- `calls_match: false`
- `final_state_match: true`
- `execution_ok: true`

The extra search/list calls fail its expected-call sequence. The successful
filesystem result must not be presented as an overall verifier PASS, a frozen
50-case correctness result, or a production-ready Secretary. This is one
stochastically sampled diagnostic; repeatability remains unmeasured. It is not
wired into the default service or MCP. No speedup is attributed to grammar.

The feedback loop took **18.142 s**, covering model calls, tool execution and
loop checks, excluding fixture creation and model load. The broader diagnostic
took **29.702 s**, including artifact hashing, model load, canary, fixture,
feedback, verification and model destruction; it excludes initial argument/Git
reads, final serialization and SDK shutdown. No energy was captured.

Exact command, from a clean source checkout with private artifact paths:

```powershell
python -X utf8 scripts/run_secretary_feedback.py --enable-candidate --config local/qwen4b-cpu10-config.json --task-id t13 --constrain-tools --output local/invoice-grammar-1000
```

The JSON preserves requested configuration, SDK/model identities, canary,
native outputs/profiles, messages, action results and before/after snapshots.
The CLI flag `--constrain-tools` determines this treatment: `grammar_enabled`
is true. The original configuration's legacy `grammar: false` field is retained
but is not read by this standalone CLI. Private device path prefixes were
redacted, with the private original's SHA-256 recorded. The emitted GBNF is
included. Windows wrote CRLF line endings in this original artifact; the report
hashes the LF grammar string passed to the runtime. Its LF-normalized hash
matches the report. The preserved file-byte SHA-256 is
`26b18a9647048ee3af76aaf322ea187e03d936b61a553ae7292ebe8a924e486c`.
New diagnostic runs write exact UTF-8 bytes to eliminate this difference.

The existing loopback gateway was restored and reported a native runtime plus
all four registered model artifacts available at the next checkpoint. Larger
model development tests run separately and sequentially after this diagnostic.

Independent Flash review confirmed the fixture outcome and bounded opt-in scope.
Its full-grammar coverage caution remains valid: the simple canary plus these five
valid actions does not exercise every escape/Unicode branch or every tool rule.
No engine compile-only API was established, so a proposed compile-only check was
not claimed or implemented. Existing strict decoding remains the final per-action
check. The review did not qualify the model or change scoring.
