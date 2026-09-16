# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 16d13138a61fd3f0e4bcbe5ae6bcb2271fb1b843
Candidate: qwen4b-cpu10-v2
Model: Qwen3-4B-Instruct-2507-Q4_0.gguf

Configuration:
```json
{
  "backend": "llama_cpp_cpu",
  "plugin": "llama_cpp",
  "device": "cpu",
  "threads": 10,
  "threads_batch": 0,
  "ubatch": 0,
  "n_batch": 0,
  "context": 4096,
  "max_tokens": 128,
  "grammar": false,
  "spec_type": "none",
  "draft_tokens": 8,
  "hardware_note": "Dell Latitude 7455, Snapdragon X Elite X1E80100, 32 GB; isolated CPU10 trial; model transfer completed before inference"
}
```
Task success: 37/50 (74.00%)
Failed tasks: 13
Tool / action / arguments: 74.00% / 74.00% / 92.00%
Clarification accuracy (expected-clarify cases): 15.384615384615385
Invalid output rate: 4.00%
Latency mean / median / p95 (ms): 5940.103 / 3430.061 / 26837.233

Quality gate: NOT_COMPARABLE

## Categories

- clarify_ambiguous_path: 0/3 (0.00%)
- clarify_conflicting_constraints: 0/1 (0.00%)
- clarify_missing_destination: 0/1 (0.00%)
- clarify_missing_file: 0/1 (0.00%)
- clarify_missing_path: 0/1 (0.00%)
- clarify_missing_query: 0/1 (0.00%)
- clarify_missing_source: 1/1 (100.00%)
- clarify_overwrite: 0/1 (0.00%)
- clarify_unsupported: 1/3 (33.33%)
- list: 3/3 (100.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 3/3 (100.00%)
- move: 3/3 (100.00%)
- move_exact_path: 1/1 (100.00%)
- move_paraphrase: 2/2 (100.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 6/6 (100.00%)
- read: 4/4 (100.00%)
- read_exact_path: 3/4 (75.00%)
- read_paraphrase: 1/2 (50.00%)
- search: 2/2 (100.00%)
- search_exact_query: 3/3 (100.00%)
- search_paraphrase: 2/2 (100.00%)

## Difficulty

- easy: 14/15 (93.33%)
- hard: 8/15 (53.33%)
- medium: 15/20 (75.00%)

## Expected action

- clarify: 2/13 (15.38%)
- list_files: 9/9 (100.00%)
- move_file: 8/8 (100.00%)
- read_file: 10/12 (83.33%)
- search_files: 8/8 (100.00%)

## Failed tests

### dev_005

Prompt: I need the plan for beta. The alpha plan is a distractor; read only the beta one from the inventory.

Failure: WRONG_ACTION

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "projects/beta/plan.md"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "search_files",
    "arguments": {
      "query": "beta plan.md"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"beta plan.md\"}}\n</tool_call>",
  "error": null
}
```
### dev_022

Prompt: Read the file for me.

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
  "raw_output": "Please specify which file you would like me to read. Provide the full workspace-relative path (including parent folders) of the file.",
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
      "path": "notes/meeting-notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"notes/meeting-notes.txt\"}}\n</tool_call>",
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
      "destination": "archive/transfer.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"archive/transfer.txt\"}}\n</tool_call>",
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
    "tool": "list_files",
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>",
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
  "raw_output": "I cannot delete files permanently as per safety and data preservation principles. However, I can assist in moving or archiving the file if needed. Would you like me to move `notes/draft.txt` to an archive folder instead?",
  "error": null
}
```
### dev_028

Prompt: Move budget.csv to archive/budget.csv.

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
      "path": "projects/alpha/budget.csv",
      "destination": "archive/budget.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"projects/alpha/budget.csv\", \"destination\": \"archive/budget.csv\"}}\n</tool_call>",
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
### heldout_003

Prompt: Read the meeting text file whose basename contains "(final)" in the inventory, not either meeting-notes file.

Failure: WRONG_ACTION

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
    "tool": "search_files",
    "arguments": {
      "query": "(final)"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"(final)\"}}\n</tool_call>",
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
    "tool": "search_files",
    "arguments": {
      "query": "plan.md"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"plan.md\"}}\n</tool_call>",
  "error": null
}
```
### heldout_012

Prompt: Append the line "Review complete" to notes/ideas.txt.

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
      "path": "notes/ideas.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"notes/ideas.txt\"}}\n</tool_call>",
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
  "status": "NOT_COMPARABLE",
  "reasons": [
    "Incompatible evaluator_sha256"
  ]
}
```
