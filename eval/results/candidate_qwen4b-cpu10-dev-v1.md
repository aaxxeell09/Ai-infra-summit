# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 16d13138a61fd3f0e4bcbe5ae6bcb2271fb1b843
Candidate: qwen4b-cpu10-dev-v1
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
Task success: 25/35 (71.43%)
Failed tasks: 10
Tool / action / arguments: 71.43% / 71.43% / 91.43%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 5.71%
Latency mean / median / p95 (ms): 6756.383 / 4691.478 / 23922.892

Quality gate: NOT_COMPARABLE

## Categories

- clarify_ambiguous_path: 0/2 (0.00%)
- clarify_conflicting_constraints: 0/1 (0.00%)
- clarify_missing_destination: 0/1 (0.00%)
- clarify_missing_path: 0/1 (0.00%)
- clarify_missing_query: 0/1 (0.00%)
- clarify_overwrite: 0/1 (0.00%)
- clarify_unsupported: 0/2 (0.00%)
- list: 2/2 (100.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 2/2 (100.00%)
- move: 2/2 (100.00%)
- move_exact_path: 1/1 (100.00%)
- move_paraphrase: 1/1 (100.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 4/4 (100.00%)
- read: 3/3 (100.00%)
- read_exact_path: 2/3 (66.67%)
- read_paraphrase: 1/1 (100.00%)
- search: 2/2 (100.00%)
- search_exact_query: 2/2 (100.00%)
- search_paraphrase: 1/1 (100.00%)

## Difficulty

- easy: 9/10 (90.00%)
- hard: 6/11 (54.55%)
- medium: 10/14 (71.43%)

## Expected action

- clarify: 0/9 (0.00%)
- list_files: 6/6 (100.00%)
- move_file: 6/6 (100.00%)
- read_file: 7/8 (87.50%)
- search_files: 6/6 (100.00%)

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
  "raw_output": "I need more information to proceed. Could you please specify which file you would like me to read?",
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
  "raw_output": "I cannot delete files permanently as that would require operations beyond the available tools. However, I can help you move or archive the file if you'd like an alternative. Would you like me to move it instead? If so, to where?",
  "error": null
}
```
### dev_027

Prompt: Create notes/new.txt containing hello.

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
      "destination": "notes/new.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"notes/new.txt\"}}\n</tool_call>",
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

## Comparison

```json
{
  "status": "NOT_COMPARABLE",
  "reasons": [
    "Incompatible evaluator_sha256"
  ]
}
```
