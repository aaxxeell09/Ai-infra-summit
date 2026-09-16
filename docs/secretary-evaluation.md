# Golden Secretary correctness evaluation

## Actual implementation inspected

The real `turbo/secretary.py` and `turbo/service.py` arrived in shared main `06aeed3` during this task. The existing evaluation was adapted before publication; no runtime/performance code was changed.

Production `Engine.secretary()` creates its 12-file fixture, builds inventory-aware messages, invokes `Engine.completion()` with `secretary.TOOLS`, parses one to four tool calls through `service.parse_calls()`, executes them with `execute_tool()`, and grades labelled demo tasks using exact calls and final state. Its existing 13 tasks remain untouched in `benchmarks/secretary_tasks.json`.

Production `Engine.completion()` applies a selected mode/model, loads the native model, calls `NativeModel.chat()`, and reports model, route, applied configuration, text and profile. `policy.py`, `catalog.py` and context modules are separate performance components; this task changes none of them.

Our versioned golden evaluation tests **one requested action plus actual fixture execution**, using the production tool schema, parser and executor. It uses a larger 30-file synthetic fixture to test distractors and ambiguity. It invokes the same native model API directly with an explicit configuration and `tools=TOOLS`; it does not exercise Engine's mode routing, multi-turn loops or automatic context reduction. Those require a separately versioned adapter/benchmark. Routing metrics remain null, not claimed successes.

```
Fixed synthetic inventory + prompt (never golden answers)
  → Secretary system instructions + real TOOLS
  → existing NativeModel.chat() with explicit config
  → real service.parse_calls() + strict schema validation
  → actual action and arguments
  → real execute_tool() in a disposable fixture copy
  → deterministic golden action/arguments + final filesystem comparison
  → JSON and Markdown correctness audit
```

### Actual production action space

| Tool | Meaning | Required arguments | Optional | Use / avoid |
|---|---|---|---|---|
| read_file | Read a text file | path | none | Read identified existing file; clarify ambiguous identity |
| list_files | Recursively list ALL files | none | none | Full inventory; no directory-filter argument exists |
| search_files | Case-insensitive content substring search | query | none | Search text contents; not filename search or semantic retrieval; PDF files excluded |
| move_file | Move/rename a file | path, destination | none | Full relative filenames; refuses overwrite/escape; executor creates destination parents |
| clarify | Ask a question | question | none | Missing essential info, ambiguous/conflicting/unsupported request; not a guessed file action |

Outputs are generated tool calls: `{"name":"read_file","arguments":{"path":"docs/example.md"}}`, optionally wrapped in `<tool_call>` tags. Executor returns `{ok,result,error}`. One tool name is one action: tool/action accuracy are the same decision. Required question wording is unconstrained beyond nonempty text.

ToolWire `action_codec.py` still exists, unchanged for historical comparisons. Its compact `r/l/s/m/q` schema is **not** the production Secretary schema: notably its list path and move source fields differ. Version 2 uses the real production schema and is not directly comparable to ToolWire v1. No calendar/email/date/send/draft/delete capabilities are invented.

## Golden dataset: secretary-eval-v2

- Exactly **50** committed questions: **35 development / 15 held-out**.
- **15 easy / 20 medium / 15 hard** (development 10/14/11; held-out 5/6/4).
- Action distribution: read 12, list 9, search 8, move 8, clarify 13.
- Coverage: direct actions, paraphrases, filename inference, exact path discrimination, nested directories, distractors, read/search and list/search distinctions, moves/renames, missing arguments, ambiguous filenames, overwrite ambiguity, unsupported/destructive requests, missing files, conflicting constraints, and explicit first steps of multi-action requests.

Difficulty is predefined by reasoning required, not by observing model failures. v1 was introduced in `0470a28`; v2 strengthens fixtures, intent cases, explanations and metrics **before any model baseline was measured**. Some golden prompts changed. Old files are preserved in Git. Never compare v1 and v2 as the same exam.

`eval/fixtures/files.json` fixes the 30 path symbols. `eval/fixtures/secretary_workspace/` materializes every path with synthetic, deterministic contents (valid JSON/CSV/SVG/PNG where relevant). Similar reports, draft/final names, nested paths and distractors create deliberate ambiguity. No personal data is used. Actions execute only in independently copied temporary fixtures; the original golden fixture remains unchanged. The model sees the file inventory, not hidden fixture contents or expected answers; questions require no unknown timestamps/content metadata.

Golden item schema:

```json
{
  "id": "stable-case-id",
  "split": "development",
  "category": "read",
  "difficulty": "easy",
  "prompt": "A predefined task",
  "expected": {
    "tool": "read_file",
    "arguments": {"path": "an/existing/fixture/path"},
    "should_act": true,
    "clarification_required": false
  },
  "rationale": {"kind": "explicit"}
}
```

This illustrates the shape, not an extra executable test. For clarify, arguments are empty, should_act=false, clarification_required=true; wording need not match. Rationales include explicit instructions, unique filename match, multiple existing candidates, missing arguments, nonexistent file, occupied destination, unsupported capability and conflicting constraints.

### Validation and leakage

`validate_dataset.py` checks IDs, nonempty prompts, schema, fixed split/difficulty counts, real fixture files, source paths, directory paths, unoccupied destination and existing parent, golden encode/decode against **the production Secretary tools**, rationale evidence and committed hashes. Changing the production tool schema or benchmark system instructions invalidates the manifest until deliberately reviewed/versioned. Every golden action is also executed on temporary fixtures during validation. No output from a candidate determines an expected answer.

It checks that ambiguity candidates exist and unique filename matches identify one target. Natural-language intent still requires human review when authoring the benchmark; this validator does not pretend to prove English ambiguity automatically. Missing/conflicting requests carry explicit authored rationale. Actual executor behavior is checked on isolated fixture copies.

`--check-leakage` searches tracked and unignored working files for held-out prompt text (including decoded JSON), excluding its canonical dataset file. No duplicate held-out text was found at construction. This exact-text check cannot detect paraphrase leakage. The set is public in Git: do not use it as tuning examples. Future audit reports may legitimately reproduce prompts; the scanner reports those locations for review, rather than deleting files.

## Deterministic scoring and audit

Each record includes ID/category/difficulty/prompt, full expected behavior, raw output, decoded actual tool/action/arguments, individual booleans, should_act, latency, native profile and failure reasons. Model execution errors remain failures and are counted in denominators.

Overall success requires correct action, semantically important required arguments, correct action-vs-clarification behavior, successful execution and matching final filesystem state. Normalize path separators and leading `./` only. Preserve case, source, destination, interior spaces, and `..` differences. Exact queries are used for search. Clarification needs a valid clarify action with a nonempty question, not exact wording; this tests the decision to ask, not usefulness of the question. A malformed response is not credited as abstention.

Failure taxonomy: WRONG_ACTION, WRONG_SOURCE, WRONG_DESTINATION, WRONG_ARGUMENT, FAILED_TO_CLARIFY, UNNECESSARY_CLARIFICATION, INVALID_OUTPUT, PARSE_ERROR, MODEL_ERROR, TIMEOUT, EXECUTION_ERROR, WRONG_FINAL_STATE. Failures may have multiple argument reasons. No subjective text scoring or LLM judge is introduced.

Reports include total/passed/failed, overall accuracy, action/tool/argument accuracy, argument accuracy on applicable non-clarify cases, clarification accuracy on expected-clarify cases, all-case clarification/no-action accuracy, invalid-output and parse-failure rates, category/action/difficulty accuracy, mean/median latency and nearest-rank p95 for >=20 samples. Smaller samples report p95 unavailable. Inference latency includes generation/templating, excludes model loading and scoring. task_latency_ms separately includes scoring, fixture copies and real execution; failed attempts remain in averages and error counts are explicit. One untimed development prompt warms the model; reset=True isolates every measured question.

Native profile counters and timings are preserved per case for later speed-quality plots. No streaming chunks are counted as tokens; no replay/shorter text is credited as higher decode speed. Future graphs can join Henry's measured throughput by candidate/config/commit, not by an invented accuracy value. Route and routing accuracy are null because the explicit native configuration adapter does not exercise Engine routing.

## Commands

### Validate the frozen golden dataset (no model required)

```sh
python eval/validate_dataset.py --check-leakage
python eval/run_secretary_eval.py --dataset all --candidate-name validation --validate-only
```

### Configure actual Latitude execution

Copy `eval/config.example.json` to ignored `local/secretary-config.json`. Supply the real SDK directory and model path, requested device, threads/context, output cap and other supported settings. Record actual hardware/power/background load in hardware_note. Example paths are placeholders, not installed locations. Defaults are test settings, **not Henry's official baseline**.

`NativeRuntime` uses the version-pinned native SDK, and `NativeModel.chat()` returns the actual text and profile. Model file SHA-256 is captured. Directory model bundles currently lack a full weight hash and cannot become an accepted official baseline. No model files, private addresses or host paths are committed.

### Confirm the official original baseline with Henry

Henry must explicitly identify the original model/weights, backend/runtime, config and application commit. After confirmation, put these fields in ignored `local/baseline-approval.json`:

```json
{
  "status": "confirmed",
  "confirmed_by": "Henry",
  "application_commit": "EXACT_CURRENT_APPLICATION_COMMIT",
  "config_sha256": "HASH_OF_CONFIRMED_CONFIG"
}
```

Get the commit and canonical config hash:

```sh
git rev-parse HEAD
python -c "import json; from pathlib import Path; from eval.scoring import digest; print(digest(json.loads(Path('local/secretary-config.json').read_text())))"
```

This is a recorded team attestation, not cryptographic proof of Henry's identity. Do not fill it in on Henry's behalf without confirmation. The tracked pending baseline manifest is deliberately not accepted by this guard.

Freeze all 50 cases:

```sh
python eval/run_secretary_eval.py --dataset all --candidate-name reference --config local/secretary-config.json --baseline-approval local/baseline-approval.json --freeze-baseline --output-dir local/reference
```

It requires a clean committed working tree and writes baseline.json, baseline.md and baseline_manifest.json. Existing outputs are never overwritten. Execution errors or unverified model identity produce an invalid baseline, never an accepted reference. A poor but technically valid score remains poor; do not change its golden labels to improve the score.

### Run future candidates

```sh
python eval/run_secretary_eval.py --dataset dev --candidate-name cpu-tuned-v1 --config local/secretary-config.json --baseline local/reference/baseline.json --output-dir local/secretary-eval
```

Use a unique candidate name each time; use `--dataset heldout` or `--dataset all` for serious evaluations. Development runs compare only their matching 35 baseline rows, not a 35/50 aggregate. The full baseline is immutable. Review real results before publishing from ignored local/ into eval/results/.

Compare previously saved runs:

```sh
python eval/compare_runs.py local/reference/baseline.json local/secretary-eval/candidate_cpu-tuned-v1.json
```

### Quality gate

Editable `eval/quality_policy.json` defaults:
- Overall accuracy may drop at most 3 percentage points.
- Category accuracy may drop at most 10 points.
- No previously successful clarification or move case may regress.
- Invalid output fraction <=0.02, increase <=2 percentage points.
- Clarification accuracy drop <=0 points.

These are engineering starting tolerances, not scientific truths. With small categories the category rule is deliberately strict. Report every regression, even if aggregate accuracy improves. Speed improvements are Henry's separate responsibility: this PASS is a correctness gate, not proof of speedup.

Absent or unapproved baseline, dirty reference or a candidate file used as reference => NOT_EVALUATED. Different benchmark/protocol/fixture/action schema/evaluator/generation policy or changed case expectations => NOT_COMPARABLE. Valid comparison => PASS or FAIL with baseline/candidate values, deltas, failed categories and critical cases. Changing max output length requires a new comparable reference; model/runtime candidates are recorded as different experiments.

## Provenance, baseline status and workflow

Metadata includes actual Git commit, branch, dirty flag, evaluator/source hashes, benchmark version, dataset/fixture/inventory/action-schema hashes, config hash, model hash/label, runtime version, requested settings, per-case resolved device and native timing, timestamp, safe environment metadata and reproducible command shape. Private config paths are redacted in the public command; the private config plus its hash is needed to rerun. Source/fixture changes during a run invalidate publication. Requested/resolved device does not alone prove NPU dispatch; attach Henry's measured evidence separately.

**No official model baseline has been run in this task.** The historical code observation at f8f27cc is not Henry's baseline approval. `eval/results/baseline.json`, baseline.md and baseline_manifest.json explicitly mark the official baseline unmeasured/pending. Blockers: original configuration confirmation, real SDK/model paths, verified device session, and the explicitly confirmed original application commit. This measures single-action Secretary correctness with real isolated execution, not the full routed multi-step Engine.secretary workflow.

Henry supplies candidate name, commit, what changed, why faster, exact command, model and runtime/backend/config. We run the same golden exam, inspect failure taxonomy/categories and report the gate. Serious candidates get a complete run; tiny experiments do not need 50 cases. Coordinate an exclusive measurement window on the laptop. Do not change runtime or model optimization logic in this workstream.

If a golden answer is objectively wrong, document why, bump the benchmark version/manifest and rerun every compared configuration. Never silently adjust labels after seeing failures.

## Tests

```sh
python -m pytest tests -q
```

The repository's newer context tests require pytest; dataset validation and the runner otherwise use the standard library plus the existing native runtime. Evaluation tests use synthetic outputs only and are not model accuracy measurements. Tests cover fixture/schema/rationale validity, strict scoring, clarification, unknown/invalid actions, failure reasons, metric denominators, subset comparison, incompatible versions, audit output and gates. No production runtime/performance module is changed. The production 13-case task set is preserved.

### Verification of this update

152 tests and 5 subtests passed on the development Mac, including 22 evaluation tests; all 50 golden cases validate and the held-out exact-text scan found no duplicates outside the canonical dataset. Synthetic test outputs are not model results. A bounded independent review checked scoring/provenance; its two baseline-approval findings were fixed. External Fable/Claude review is unavailable on this Mac because the Claude executable is absent.


### September 15 integration findings for benchmark ownership

The first native QAIRT full result is committed as `qairt-native-06-v1` (23/50).
Its comparison returns `NOT_COMPARABLE` because the newer runner changes
`evaluator_sha256` relative to the immutable baseline. Agree on a provenance
migration or a matched reference run before an official candidate gate; the
application must not weaken this guard or replace the old baseline.

The full unit suite also exposes an existing issue in `leakage()`: it scans saved
`eval/results/` reports, including `baseline.json`, and treats their required
failed-prompt evidence as held-out leakage. The test needs an owner-approved
scope that distinguishes archived evaluation evidence from application inputs.
The scanner, golden prompts, fixture, expected actions and scoring are unchanged
in this integration. This issue remains visible rather than being suppressed.
