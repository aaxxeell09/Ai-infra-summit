# SECRETARY OFFICIAL BASELINE

Henry confirmed this **explicitly untuned reference** on 2026-09-15. A separate historical pre-optimization Secretary deployment was not established; this is the agreed fixed reference for future candidates.

- Application and unchanged golden evaluator: `ccd1e00327fe5cabe875acec166e7d9831c1cfe0` (`secretary-eval-v2`); clean `evidence/official-reference-v2` checkout on the Latitude.
- Model: `Qwen3-0.6B-Q4_0.gguf`, SHA-256 `33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb` (unsloth/Qwen3-0.6B-GGUF revision `50968a4468ef4233ed78cd7c3de230dd1d61a56b`).
- Runtime: native Windows ARM64 GenieX 0.6.1, `llama_cpp`; requested `auto`, resolved `HTP0` on all 50 cases. This is SDK placement evidence, not a per-case NPU-utilization measurement.
- Device: Dell Latitude 7455, Snapdragon X Elite X1E80100, 32 GB RAM; AC power, Balanced plan; no competing inference workload.
- Config: 4096 context; default decode/batch threads, batch and microbatch (`0`); temperature 0; max 128 tokens; no grammar, speculative decoding or routing; fresh KV each case; one untimed development warmup. Native sampler seed is `-1`, top_p=1, top_k=0, min_p=0, repetition_penalty=1, presence/frequency penalties=0, thinking disabled. Greedy temperature does not imply cross-backend bitwise output identity.
- Correctness: **30/50 (60%)**; tool/action **70%**; all-case argument **82%**; expected-clarify **0/13 (0%)**. There are 20 failed tasks and zero model execution exceptions. All raw outputs, reasons and final-state checks are retained below and in `baseline.json`.
- Inference latency: mean **1209.531 ms**, median **1147.561 ms**, p95 **1500.174 ms**. Includes templating/generation; excludes model loading and fixture/scoring. Mean task latency including fixture execution/scoring is **1269.193 ms**.
- Full-run telemetry: peak process working set **1219.406 MiB**; SYS energy **1382.694 J** over **72.464 s** (mean **19.081 W**). Includes loading, warmup, all 50 cases, validation and scoring. Tokens/J is unavailable because warmup tokens are not recorded. See `baseline_telemetry.json`; do not treat these as inference-only or wall-plug energy.

## Reproduction

Install the same Python 3.14.6 ARM64 runtime and GenieX package; `baseline_runtime.json` pins the actual DLL hashes. Place the hashed model and SDK at local paths. Windows **must use Python UTF-8 mode** so the frozen accented fixture filename is decoded correctly. No frozen benchmark files were edited.

At the exact application commit, create ignored `local/official-reference-config.json` from the `config` object in `baseline.json`, adding the real `sdk_dir` and `model_path`. The native adapter sets `GENIEX_PLUGIN_PATH` and DLL search directories itself. Put Git on PATH. Record the confirmed commit and canonical config hash in the ignored approval file as required by the frozen runner; the original attestation is retained in `baseline_manifest.json`.

```powershell
$env:PYTHONUTF8 = '1'
python -X utf8 eval/run_secretary_eval.py --dataset all --candidate-name secretary-untuned-auto-v2 --config local/official-reference-config.json --baseline-approval local/official-reference-approval.json --freeze-baseline --output-dir local/official-reference-v2
```

The output directory must not exist. Keep these committed reference results fixed. Future serious candidates use the same frozen runner, fixtures, prompts, scoring and quality policy: at most 3 accuracy points lost and no critical move/clarify regression. Benchmark ownership remains Axel/Codex.

---

# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: ccd1e00327fe5cabe875acec166e7d9831c1cfe0
Candidate: secretary-untuned-auto-v2
Model: Qwen3-0.6B-Q4_0.gguf

Configuration:
```json
{
  "device": "auto",
  "threads": 0,
  "threads_batch": 0,
  "ubatch": 0,
  "n_batch": 0,
  "context": 4096,
  "max_tokens": 128,
  "grammar": false,
  "plugin": "llama_cpp",
  "spec_type": "none",
  "draft_tokens": 8,
  "hardware_note": "Dell Latitude 7455; Snapdragon X Elite X1E80100; 32 GB RAM; Windows ARM64; ac; Balanced power plan verified before launch; exclusive inference workload. User-designated untuned reference, not a recovered historical pre-optimization deployment."
}
```
Task success: 30/50 (60.00%)
Failed tasks: 20
Tool / action / arguments: 70.00% / 70.00% / 82.00%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 6.00%
Latency mean / median / p95 (ms): 1209.531 / 1147.561 / 1500.174

Quality gate: REFERENCE

## Categories

- clarify_ambiguous_path: 0/3 (0.00%)
- clarify_conflicting_constraints: 0/1 (0.00%)
- clarify_missing_destination: 0/1 (0.00%)
- clarify_missing_file: 0/1 (0.00%)
- clarify_missing_path: 0/1 (0.00%)
- clarify_missing_query: 0/1 (0.00%)
- clarify_missing_source: 0/1 (0.00%)
- clarify_overwrite: 0/1 (0.00%)
- clarify_unsupported: 0/3 (0.00%)
- list: 3/3 (100.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 3/3 (100.00%)
- move: 3/3 (100.00%)
- move_exact_path: 1/1 (100.00%)
- move_paraphrase: 0/2 (0.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 4/6 (66.67%)
- read: 4/4 (100.00%)
- read_exact_path: 3/4 (75.00%)
- read_paraphrase: 0/2 (0.00%)
- search: 2/2 (100.00%)
- search_exact_query: 3/3 (100.00%)
- search_paraphrase: 2/2 (100.00%)

## Difficulty

- easy: 13/15 (86.67%)
- hard: 6/15 (40.00%)
- medium: 11/20 (55.00%)

## Expected action

- clarify: 0/13 (0.00%)
- list_files: 9/9 (100.00%)
- move_file: 6/8 (75.00%)
- read_file: 8/12 (66.67%)
- search_files: 7/8 (87.50%)

## Failed tests

### dev_003

Prompt: Read the ideas text file from the supplied file inventory. I only need its contents, not a directory listing.

Failure: WRONG_ARGUMENT, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "notes/ideas.txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "data/sample.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_019

Prompt: The old-results CSV in archive must stay where it is. Relocate the results CSV currently under reports to archive/results.csv.

Failure: WRONG_SOURCE, WRONG_DESTINATION, EXECUTION_ERROR, WRONG_FINAL_STATE

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "reports/results.csv",
      "destination": "archive/results.csv"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "archive/old-results.csv",
      "destination": "reports/results.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"archive/old-results.csv\", \"destination\": \"reports/results.csv\"}}\n</tool_call>",
  "error": null
}
```
### dev_022

Prompt: Read the file for me.

Failure: FAILED_TO_CLARIFY

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "archive/2025-summary.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"archive/2025-summary.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_023

Prompt: Read meeting-notes.txt.

Failure: FAILED_TO_CLARIFY

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "docs/meeting-notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/meeting-notes.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_024

Prompt: Move inbox/transfer.txt.

Failure: FAILED_TO_CLARIFY, WRONG_FINAL_STATE

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "inbox/transfer.txt",
      "destination": "workspace"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"workspace\"}}\n</tool_call>",
  "error": null
}
```
### dev_025

Prompt: Search the workspace files.

Failure: FAILED_TO_CLARIFY

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "search_files",
    "arguments": {
      "query": "search"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"search\"}}\n</tool_call>",
  "error": null
}
```
### dev_026

Prompt: Delete notes/draft.txt permanently.

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "None of the functions provided can be used to delete notes/draft.txt permanently.",
  "error": null
}
```
### dev_027

Prompt: Create notes/new.txt containing hello.

Failure: FAILED_TO_CLARIFY, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "notes/new.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"notes/new.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_028

Prompt: Move budget.csv to archive/budget.csv.

Failure: FAILED_TO_CLARIFY, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "data/sample.csv",
      "destination": "archive/2025-summary.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"data/sample.csv\", \"destination\": \"archive/2025-summary.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_029

Prompt: Eventually I want a complete workspace inventory. Before that, read the setup Markdown document under docs. Return only the first action.

Failure: WRONG_ACTION

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "docs/setup.md"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "list_files",
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>",
  "error": null
}
```
### dev_031

Prompt: Before choosing any file to read, search file contents for the literal substring "throughput". Do not substitute "latency". Return only the first action.

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "search_files",
    "arguments": {
      "query": "throughput"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<search_files query=\"throughput\">",
  "error": null
}
```
### dev_033

Prompt: Move notes/draft.txt to archive/draft.txt, but keep notes/draft.txt in its original location too. Do not change either requirement.

Failure: FAILED_TO_CLARIFY, WRONG_FINAL_STATE

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "notes/draft.txt",
      "destination": "archive/draft.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"archive/draft.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_034

Prompt: Move inbox/summary.txt to reports/summary.txt without replacing any existing file.

Failure: FAILED_TO_CLARIFY, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "inbox/summary.txt",
      "destination": "reports/summary.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/summary.txt\", \"destination\": \"reports/summary.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_035

Prompt: Read the CSV sample under data; the JSON sample is not the one I want.

Failure: WRONG_ARGUMENT

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "data/sample.csv"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "data/sample.json"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>",
  "error": null
}
```
### heldout_003

Prompt: Read the meeting text file whose basename contains "(final)" in the inventory, not either meeting-notes file.

Failure: WRONG_ARGUMENT, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "notes/meeting (final).txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "data/meeting-notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/meeting-notes.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_009

Prompt: Move the PNG file under assets to archive/photo.png. Leave the SVG where it is.

Failure: WRONG_DESTINATION, WRONG_FINAL_STATE

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "assets/photo.png",
      "destination": "archive/photo.png"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "assets/photo.png",
      "destination": "archive/photomove.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"assets/photo.png\", \"destination\": \"archive/photomove.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_010

Prompt: Open plan.md.

Failure: FAILED_TO_CLARIFY

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "list_files",
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>",
  "error": null
}
```
### heldout_011

Prompt: Move a file to archive/chosen.txt.

Failure: FAILED_TO_CLARIFY, WRONG_FINAL_STATE

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "move_file",
    "arguments": {
      "path": "data/sample.csv",
      "destination": "archive/chosen.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"data/sample.csv\", \"destination\": \"archive/chosen.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_012

Prompt: Append the line "Review complete" to notes/ideas.txt.

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "None of the provided functions can append lines to files. However, you can use the \"read_file\" tool to read a file and then use the \"write_file\" tool to write to a file. Here's how you can do it:\n\n1. Read the file \"notes/ideas.txt\" to get the content.\n2. Append \"Review complete\" to the file.\n3. Write the updated content back to the file.\n\nIf you need clarification, I can provide more details.",
  "error": null
}
```
### heldout_015

Prompt: Read reports/final-results.csv exactly; do not substitute results.csv or old-results.csv if that exact path is absent.

Failure: FAILED_TO_CLARIFY, EXECUTION_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "clarify",
    "arguments": {},
    "clarification_required": true,
    "should_act": false
  },
  "actual": {
    "tool": "read_file",
    "arguments": {
      "path": "reports/final-results.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"reports/final-results.csv\"}}\n</tool_call>",
  "error": null
}
```

## Comparison

```json
{
  "status": "REFERENCE",
  "reasons": []
}
```
