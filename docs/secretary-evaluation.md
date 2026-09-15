# Secretary correctness evaluation

## What exists (inspected application commit f8f27ccb520e7a4cc1eca0a062fe4742e28a76b2)

There is **no `turbo/secretary.py`, file executor, Secretary CLI/API or complete secretary workflow** in this revision. Do not describe the benchmark below as end-to-end Secretary correctness.

Actual components:
- `turbo/action_codec.py`: `ActionCodec.from_files()` builds a sorted unique inventory, `instructions()` declares ONE compact JSON action, `decode(text, snapshot_digest=...)` expands the action and validates representation. `grammar()` optionally constrains generation. The SHA-256 inventory identity prevents expanding symbols against a changed inventory.
- `turbo/native.py`: `NativeRuntime(sdk_dir)`, `NativeModel(runtime, path, device=..., threads=..., context=...)`, then `model.chat(messages, max_tokens=..., temperature=0, reset=True, grammar=...)`. Returns text, native profile, timing, resolved device, SDK version and config. Model calls are serialized. SDK bindings are version-pinned by the existing module.
- `turbo/policy.py`: independent measured-profile selection by decode speed or estimated latency, subject to context/quality tiers. No Secretary caller integrates this router in this revision. This evaluation uses an explicit native configuration and records route/route accuracy as null.
- `turbo/context.py`: local raw-output recovery and context reduction. Not wired into these first-action trials.
- Existing benchmarks and `scripts/sweep.py` measure runtime performance. Their throughput results are not semantic correctness results. Existing tests cover codecs, native layout, policy, context and benchmark parsing; 42 passed before this change on the Mac.

### Actual action contract

| Compact output | Decoded tool | Arguments |
|---|---|---|
| `{"r":FILE_ID}` | read_file | path |
| `{"l":"DIRECTORY"}` | list_files | path |
| `{"s":"QUERY"}` | search_files | query |
| `{"m":[FILE_ID,"DESTINATION"]}` | move_file | source, destination |
| `{"q":"QUESTION"}` | clarify | nonempty question |

There is no separate operation nested inside a tool: tool accuracy and action accuracy are two labels for the same selection in this schema. There are no email/calendar/reminder/delete/send/draft operations, tool-execution result schema or direct text-answer action.

```
Fixture inventory + user prompt
  → existing ActionCodec.instructions() as system message
  → existing NativeModel.chat() with explicit model/device configuration
  → ONE compact JSON action
  → existing ActionCodec.decode()
  → deterministic expected tool/arguments/no-action checks
  → results JSON and Markdown (NO file operation execution)
```

This is an evaluation entrypoint composed from real primitives, not a new production Secretary implementation. If Henry publishes Secretary, add a separately versioned adapter/protocol and freeze a new comparable baseline rather than claiming this benchmark already tested its executor or routing.

## Dataset and expected behavior

50 synthetic human-reviewable prompts, with a fixed committed inventory of 30 illustrative path strings. No actual personal files are read or changed. `secretary_dev.json` contains 35 development cases; `secretary_heldout.json` contains 15 held-out cases. Split is curated by case ID and committed, not randomly reselected. Both contain action coverage and difficult examples. Held-out is public and labelled; it is not a secret dataset and scores do not establish broad generalization.

Coverage: reads, lists, searches, moves, exact paths, paraphrases, missing information, ambiguous filenames, unsupported/destructive requests, overwrite ambiguity, and explicitly requested FIRST actions of multi-step instructions. Read/write and move/new-destination distinctions use the actual operations. Calendar/date reasoning, draft-versus-send and full multi-tool completion are not supported and are not fabricated.

Every case has id, split, category, prompt and `expected: {tool, arguments, clarification_required}`. Clarification expects a nonempty question and no file action, not exact wording. This measures choosing clarification, not whether its question is helpful. Unsupported requests expect clarify under the limited available action vocabulary; that is a benchmark policy, not evidence that Secretary already implements safe refusal.

Paths preserve case and internal spaces, normalize Windows separators and leading `./`, and do not collapse `..` or Unicode differences. Search queries match exactly. Required arguments are checked; irrelevant generated wording is not. Missing/invalid output is failure, never credited as successful no-action. There are no timestamps in this workload because no date-aware operation exists.

## Run commands

No additional Python packages are required for dataset/scoring tests. Actual measurements require native Windows ARM64, the compatible pinned GenieX SDK and real model files. Copy `eval/config.example.json` to ignored `local/secretary-config.json` and replace paths/settings with the actual configuration. Example paths are placeholders, not verified installation instructions. Do not put private paths or credentials in public configuration.

Validate all cases without loading any model:

```sh
python eval/run_secretary_eval.py --dataset all --candidate-name validation --validate-only
python -m unittest discover -s tests -v
```

Freeze the first real action-intent baseline on the Latitude (all 50 cases):

```sh
python eval/run_secretary_eval.py --dataset all --candidate-name reference --config local/secretary-config.json --freeze-baseline --output-dir local/reference
```

Repeated development checks against that reference use ONLY the matching 35 baseline rows:

```sh
python eval/run_secretary_eval.py --dataset development --candidate-name cpu-tuned-v1 --config local/secretary-config.json --baseline local/reference/baseline.json --output-dir local/secretary-eval
```

For a serious final candidate, run all 50 with the same command and `--dataset all` plus a new candidate name. Output filenames are unique; an existing baseline or candidate is never overwritten. Outputs default to ignored `local/` to allow review before public publication. After checking privacy and validity, commit the real reference JSON/Markdown to `eval/results/` in place of the explicit unmeasured marker. Do not replace it silently on future optimization runs.

The runner stores source commit, branch/dirty flag, source/evaluator hashes, dataset/fixture hashes, timestamp, model-file hash, runtime version, config without private paths, safe OS/Python metadata, generation policy, native per-case profiles, failures and latency. For a model directory/bundle the model hash is currently unavailable: supply a separately reviewed bundle manifest before claiming identical weights. Hardware note must record power and competing load manually. Requested/resolved device is not proof of actual NPU dispatch; attach Henry's execution evidence separately. No CPU/NPU work is run on this Mac and reported as Latitude speed.

One untimed warmup uses the first development case. Each measured case resets context; the model stays loaded. Wall-clock case latency includes prompt templating/generation and native work, excludes model loading and deterministic scoring. Mean/median include failures; count is explicit; p95 uses nearest-rank only for at least 20 samples. Raw native TTFT, decode speed and token counts are preserved, not inferred from streaming chunks. This runner does not invent NPU utilization, power or token counts. Native timeouts/process supervision remain the caller's responsibility: abort a hung run, do not publish it as a completed baseline.

## Metrics and quality gate

Overall task success requires correct tool/action, required arguments and clarification/no-action behavior. Report all-prompt tool/action/argument rates, clarification/no-action rate, argument rate restricted to non-clarify expectations, latency and category failures. Tool/action metrics are identical by design for this codec.

`eval/quality_policy.json` provides editable engineering defaults:
- maximum overall accuracy drop: 3 percentage points;
- maximum per-category accuracy drop: 10 percentage points;
- no previously correct critical clarification or move case may regress (plus configured critical categories).

These are provisional tolerances, not scientific truths. With 50 cases, each error is 2 points; small categories make the category gate strict. Show every category regression even if the total score improves. A poor baseline is not proof of useful absolute quality even if a candidate passes a relative gate.

PASS requires every condition above. FAIL lists reasons and failed cases. Missing/invalid baseline yields NOT_EVALUATED; incompatible fixture/protocol/evaluator/generation settings or case expectations yield NOT_COMPARABLE, never PASS. Development subsets compare their exact case hashes against only those baseline rows; a development pass is not a held-out pass. Repeated tests of held-out cases must not guide routine tuning.

Runtime changes, grammar experiments and model variants are recorded separately. Preserve same weights/quantization for native runtime speed claims. Comparing changed model weights can support a quality/latency tradeoff, not same-model acceleration. Do not interpret fewer generated syntax tokens as greater decode throughput.

## Frozen reference status

`eval/results/baseline.json` records the clean pre-evaluation application commit, not measured values. Baseline is **not measured**: this Mac has no verified native Latitude runtime/config or authenticated SSH session, and `turbo/secretary.py` is absent. No existing throughput report is substituted for correctness.

The historical application commit is frozen by SHA and source hashes. Henry may continue working, but a later run on changed application code must be identified by its actual commit and cannot be retroactively called the original baseline. To measure the historical reference, run these evaluation files against that recorded application revision in an isolated checkout; preserve Henry's live work. Full Secretary baseline requires its implementation and a new protocol.

## Team workflow

Henry owns device/performance optimization. We own task fixtures, deterministic scoring and correctness gates. Product/demo work is outside this change.

For a serious candidate Henry provides name, commit, what changed, reason for anticipated improvement and exact private run configuration. Run development checks during tuning; run the full benchmark for serious candidates. Compare to the fixed reference, examine category regressions and report PASS/FAIL. Tiny internal experiments do not each require 50 cases. Coordinate exclusive laptop measurement windows so competing jobs do not contaminate latency. No automatic runtime optimization or router modification is introduced here.

## Verification of this change

After integrating remote main through `9d5012c`, all 71 tests passed with pytest (including 10 new evaluation tests); unittest discovery passed 59 class-based tests. The new remote context-pipeline tests require pytest, installed only in the ignored local virtual environment. Dataset validation passed for all 50 cases. Independent bounded code review found no blocking issue in the declared first-action scope. The requested external Fable/Claude review was unavailable: no Claude executable is installed on this Mac. No native model results were produced by these synthetic tests.
