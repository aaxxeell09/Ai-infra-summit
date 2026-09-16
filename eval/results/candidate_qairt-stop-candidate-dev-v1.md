# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 728c6a2ad72917a8173f88cf647360bb83269c0a
Candidate: qairt-stop-candidate-dev-v1
Model: qwen3-06-qairt-x-elite

Configuration:
```json
{
  "backend": "qairt_npu",
  "plugin": "qairt",
  "device": "npu",
  "threads": 0,
  "context": 4096,
  "max_tokens": 128,
  "hardware_note": "Dell Latitude 7455, Snapdragon X Elite X1E80100, 32 GB; sequential isolated QAIRT stop ablation after 4B campaign",
  "stop_after_tool_call": true
}
```
Task success: 21/35 (60.00%)
Failed tasks: 14
Tool / action / arguments: 60.00% / 60.00% / 82.86%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 5.71%
Latency mean / median / p95 (ms): 514.269 / 504.778 / 659.771

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
- move_paraphrase: 0/1 (0.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 3/4 (75.00%)
- read: 2/3 (66.67%)
- read_exact_path: 1/3 (33.33%)
- read_paraphrase: 1/1 (100.00%)
- search: 2/2 (100.00%)
- search_exact_query: 2/2 (100.00%)
- search_paraphrase: 1/1 (100.00%)

## Difficulty

- easy: 8/10 (80.00%)
- hard: 4/11 (36.36%)
- medium: 9/14 (64.29%)

## Expected action

- clarify: 0/9 (0.00%)
- list_files: 6/6 (100.00%)
- move_file: 5/6 (83.33%)
- read_file: 4/8 (50.00%)
- search_files: 6/6 (100.00%)

## Failed tests

### dev_002

Prompt: Open reports/baseline.json and show its contents.

Failure: WRONG_ACTION

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "reports/baseline.json"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "search_files",
    "arguments": {
      "query": "reports/baseline.json"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/baseline.json\"}}\n</tool_call>",
  "error": null
}
```
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
      "query": "beta"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"beta\"}}\n</tool_call>",
  "error": null
}
```
### dev_019

Prompt: The old-results CSV in archive must stay where it is. Relocate the results CSV currently under reports to archive/results.csv.

Failure: WRONG_ACTION, WRONG_FINAL_STATE

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
    "tool": "search_files",
    "arguments": {
      "query": "results.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"results.csv\"}}\n</tool_call>",
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
  "raw_output": "Clarify.",
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
      "destination": "data/transfer.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"data/transfer.txt\"}}\n</tool_call>",
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
      "query": "search files in the workspace"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"search files in the workspace\"}}\n</tool_call>",
  "error": null
}
```
### dev_026

Prompt: Delete notes/draft.txt permanently.

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
      "path": "notes/draft.txt",
      "destination": "inbox/transfer.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"inbox/transfer.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_027

Prompt: Create notes/new.txt containing hello.

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
      "path": "budget.csv",
      "destination": "archive/budget.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"budget.csv\", \"destination\": \"archive/budget.csv\"}}\n</tool_call>",
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

Failure: PARSE_ERROR

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
    "tool": null,
    "arguments": {}
  },
  "raw_output": "The CSV file under \"data/sample.csv\" and the JSON file under \"data/sample.json\" are not the ones I want. Let me check out the files in the workspace.",
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
