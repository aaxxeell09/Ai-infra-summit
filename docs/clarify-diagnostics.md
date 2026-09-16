# Clarification diagnostics: development evidence and bounded candidates

## Scope and evidence boundary

This workflow reads existing **development-only** result JSON and exports separate
candidate descriptions. It runs no inference, executes no file action, repairs no
model output, and changes no frozen prompt, schema, parser, evaluator, golden
answer or fixture. Candidate exports are proposals, not qualified measurements.
All input rows must be validated as development rows before analysis; reject a
mixed/full/heldout report rather than filtering forbidden rows out afterward.

The reviewed historical evidence is exactly
`eval/results/qairt-repeats-0700/candidate_EXP-001.json` through
`candidate_EXP-006.json`: 35 development rows per report. EXP-001/004/005 have
`stop_after_tool_call=false`; EXP-002/003/006 have it true. **Every report has 0/9
successful clarification cases.** This is descriptive evidence for this campaign,
not proof that every QAIRT configuration behaves identically.

The owner's current 19/35 versus 18/35, five clarification failures, and two S2
clarification failures are newer owner-reported observations. Their corresponding
raw reports are unavailable here. Do not assign those counts to historical case
IDs, infer a causal improvement, or silently replace their denominator with nine.

## What the nine development cases require

| Case | Required decision | Historical observed failure |
|---|---|---|
| dev_022 | Ask which file to read: path missing | Usually prose such as `Clarify.`; one report selects `list_files` |
| dev_023 | Ask which of two meeting-notes basenames | Chooses a path, invents a path, or searches instead of asking |
| dev_024 | Ask for move destination | Invents a destination |
| dev_025 | Ask for search query | Prose about tools or an invented query |
| dev_026 | Clarify unsupported permanent deletion | Substitutes move, prose, or move followed by clarification |
| dev_027 | Clarify unsupported file creation | Substitutes list/move or emits an unsupported write tool |
| dev_028 | Ask which of two budget basenames | Selects/invents a source, sometimes also changes destination |
| dev_033 | Resolve mutually incompatible move/keep-original requirements | First action is move; some controls later emit clarification |
| dev_034 | Resolve move into existing destination with no replacement | First action is move; some controls later emit clarification |

Missing `question` is a useful diagnostic category, but it is **not an observed
explanation** for these 54 historical clarification failures. Keep zero observed
counts visible rather than claiming a schema-field failure was measured.

The offline classifier reproduces the following counts across those 54 rows.
Labels overlap and must not be summed as independent failures:

| Diagnostic label | Rows |
|---|---:|
| Valid parsed action fails to clarify | 34 |
| Malformed or noncontract output | 20 |
| First parsed tool is not clarify | 45 |
| Multiple parsed actions | 11 |
| Plain prose with no structured invocation | 9 |
| Clarification appears after a different first action | 5 |
| Unbalanced tool-call tags | 2 |
| Missing/empty question in a parsed clarify call | 0 |
| Reported length stop | 0 |

These labels diagnose existing text; they do not replace archived success,
execution or final-state results. `WRONG_FINAL_STATE` can be the consequence of
an already-wrong move that changed the copied fixture, rather than a separate
parser defect. The diagnostic does not execute any tool or rewrite any output.

A stopping candidate can remove trailing calls after a wrong first move. It
cannot turn that first move into clarification. In dev_033, trailing clarification
in a control is evidence that clarification language appeared somewhere, not a
successful safe decision. No diagnostic should take the final/best call and
re-score it as the model's answer.

## Existing contracts explain the distinction

- `SecretaryAdapter.instructions()` says “at most four” tool calls, whereas the
  Secretary evaluation expects exactly one action. This is a concrete instruction
  mismatch worth a separate prompt candidate; the frozen prompt stays unchanged.
- `turbo/service.py::parse_calls` supports tagged JSON, JSON fences and raw JSON.
  Tags alone are not the correctness criterion. Plain `Clarify.` has no structured
  tool invocation. Parsing may find multiple calls, while the adapter requires one.
- `turbo/secretary.py::TOOLS` requires `clarify.arguments.question`; execution
  requires a nonempty string. Golden `expected.arguments={}` means scoring does
  not require one exact question wording. It does **not** authorize an empty
  argument object as a valid invocation.
- The current clarification description emphasizes genuine ambiguity. Missing
  required arguments, unsupported operations, conflicting constraints and an
  overwrite prohibition are distinct reasons to ask rather than improvise.

These observations justify experiments, not edits to v2 semantics. A future
versioned prompt/schema experiment needs separate identity and explicit owner
approval before any official benchmark-path change.

## Candidate 1: explicit single-action clarification instruction

**MECHANISM:** Export a separate prompt variant that requests exactly one tool
call; before selecting a file operation, check for missing required information,
multiple possible source paths, unsupported capability, incompatible constraints,
and prohibited overwrite. If clarification is needed, emit only `clarify` with a
nonempty question. Give a generic structured example without a development
filename, case ID or expected answer. Do not append this to the frozen prompt in
place or treat output rewriting as prompting.

**FILES_CHANGED:** Diagnostic implementation
`turbo/clarify_diagnostic.py`, CLI `scripts/clarify_diagnostic.py`, associated tests,
this document; export under ignored `local/`. Frozen adapter/service unchanged.

**WHY_IT_MIGHT_HELP:** Directly addresses prose-only clarification, implicit
argument invention, and the four-versus-one mismatch seen in the evidence.

**RISKS:** More input tokens and latency; unnecessary clarification on valid
requests; model may still select a wrong first action. The change affects prompt
identity, so comparison must retain the original control and its hashes.

**CASES_AFFECTED:** All nine clarification cases; all 26 other development cases
must also be checked for unnecessary clarification and success regression.

**HOW_TO_DIAGNOSTICALLY_TEST:** Export only now. An explicitly authorized future
runner may compare unchanged control versus this single change on development
cases, using unchanged scoring, exact raw output retention, balanced repeated
order and all-attempt latency accounting. Report both clarification and normal
operation results; do not promote a nine-case-only win.

**WHY_IT_CANNOT_LEAK_HELDOUT:** Export uses a generic rule and development evidence
only; no heldout loader, prompts, case IDs, results or oracle lookup is needed.

## Candidate 2: clarify tool description only

**MECHANISM:** Export a schema-description variant explaining that clarification
also covers missing arguments, unsupported operations, conflicts and prohibited
overwrite; require one nonempty question and no preceding file action. Keep tool
name, argument keys/types and required fields unchanged. Do not combine with the
prompt candidate for the first comparison.

**FILES_CHANGED:** Same separate diagnostic/export files as candidate 1; never
mutate `turbo/secretary.py::TOOLS` or the frozen action-schema identity in place.

**WHY_IT_MIGHT_HELP:** Makes the existing tool's intended selection conditions
clearer at the point where the model sees tool descriptions.

**RISKS:** This is still an input-schema-description change, not a free parser
fix. Extra tokens may affect latency; overuse of clarify can reduce normal-task
success. Missing-question failures were not observed, so no benefit is established.

**CASES_AFFECTED:** Especially dev_022/024/025/026/027/033/034; ambiguous paths
023/028 and the 26 non-clarification cases remain regression checks.

**HOW_TO_DIAGNOSTICALLY_TEST:** Export the alternate description with its own
hash; future authorized development-only paired diagnostic, unchanged evaluator,
original outputs and precise latency boundary. Compare this variant independently
before considering combinations.

**WHY_IT_CANNOT_LEAK_HELDOUT:** Generic capability wording and development-only
analysis; no heldout data or per-case expected-answer mapping enters the variant.

## Candidate 3: narrow basename-collision shadow detector

**MECHANISM:** In a separate shadow diagnostic, recognize only an entire `Read BASENAME.` or `Open BASENAME.` request
when the inventory contains more than one exact matching
basename. Emit a diagnostic flag and candidate paths. It does not choose a path,
construct an executable action, override a model response or change scores.
Qualified full paths must not be treated as ambiguous merely because their basename
is duplicated. Destination text alone must not count as source ambiguity.

**FILES_CHANGED:** Separate diagnostic/export implementation and tests only;
fixture inventory is read-only. No production routing or executor changes.

**WHY_IT_MIGHT_HELP:** Separates a concrete, mechanically detectable ambiguity
from the model's unsupported source choice in dev_023. Move parsing is
deliberately excluded from this small implementation.

**RISKS:** Natural-language extraction is narrow and incomplete. False positives
are possible with quoted filenames, negation, destination references or names
embedded in larger strings. This cannot solve missing information, unsupported
operations, contradictions or overwrite constraints. Report flags as shadow
observations, never corrected model success.

**CASES_AFFECTED:** Only dev_023 is flagged by the implemented detector. dev_028 remains
unhandled because move parsing is excluded. All other development cases and synthetic explicit-path/unique-basename/destination-only examples are
negative controls; do not hardcode those case IDs into detection logic.

**HOW_TO_DIAGNOSTICALLY_TEST:** Run the shadow detector without inference or
execution; inspect collision flags and candidates, including synthetic negative
controls. Any future production interception is a separate versioned design
requiring owner review, not an implementation detail of this diagnostic.

**WHY_IT_CANNOT_LEAK_HELDOUT:** Operates on the provided development request and
existing inventory with a generic exact-basename rule, without golden answers or
heldout access.

## Token limits and ordering

Increasing `max_tokens` can rescue a genuinely truncated structured answer, but
adds a larger generation budget and may allow more unwanted trailing calls. The
54 archived clarification rows report `eos` or `user`, with no `length`
stop observed in this campaign. This is not evidence that a shorter cap would be
safe; it may cut off the question or closing JSON/tag. Missing termination
metadata in other reports must remain unknown. Prose, invented arguments and a wrong first action occur independently
of whether a later continuation is cut off. Keep token-cap changes separate from
prompt/schema changes and preserve available termination metadata. Do not disable
thinking; it is already disabled.

Start with existing-result taxonomy and exports, then review candidates. No
inference is authorized by this document. No overall winner can be selected from
these diagnostics, and they do not establish energy comparability.

## Diagnostic CLI

```sh
python scripts/clarify_diagnostic.py --diagnostic-only \
  --result eval/results/qairt-repeats-0700/candidate_EXP-001.json \
  --output local/clarify-diagnostics/control.json
```

Repeat `--result` for additional development-only reports. Use
`--export-candidate prompt`, `schema`, or `ambiguity-shadow` to export the selected
proposal. Preserve existing reports and use fresh output paths. Input validation
must reject foreign/heldout/mixed case IDs before emitting case-level analysis.
The output is a diagnosis of historical evidence, not a new benchmark result.
