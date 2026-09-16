# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 728c6a2ad72917a8173f88cf647360bb83269c0a
Candidate: qairt-stop-control-dev-v1
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
  "stop_after_tool_call": false
}
```
Task success: 14/35 (40.00%)
Failed tasks: 21
Tool / action / arguments: 40.00% / 40.00% / 51.43%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 45.71%
Latency mean / median / p95 (ms): 862.656 / 601.355 / 1881.938

Quality gate: NOT_COMPARABLE

## Categories

- clarify_ambiguous_path: 0/2 (0.00%)
- clarify_conflicting_constraints: 0/1 (0.00%)
- clarify_missing_destination: 0/1 (0.00%)
- clarify_missing_path: 0/1 (0.00%)
- clarify_missing_query: 0/1 (0.00%)
- clarify_overwrite: 0/1 (0.00%)
- clarify_unsupported: 0/2 (0.00%)
- list: 1/2 (50.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 2/2 (100.00%)
- move: 1/2 (50.00%)
- move_exact_path: 0/1 (0.00%)
- move_paraphrase: 0/1 (0.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 1/4 (25.00%)
- read: 1/3 (33.33%)
- read_exact_path: 0/3 (0.00%)
- read_paraphrase: 1/1 (100.00%)
- search: 2/2 (100.00%)
- search_exact_query: 2/2 (100.00%)
- search_paraphrase: 1/1 (100.00%)

## Difficulty

- easy: 6/10 (60.00%)
- hard: 2/11 (18.18%)
- medium: 6/14 (42.86%)

## Expected action

- clarify: 0/9 (0.00%)
- list_files: 4/6 (66.67%)
- move_file: 2/6 (33.33%)
- read_file: 2/8 (25.00%)
- search_files: 6/6 (100.00%)

## Failed tests

### dev_002

Prompt: Open reports/baseline.json and show its contents.

Failure: INVALID_OUTPUT

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
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/baseline.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"reports/baseline.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/baseline.json\"}}\n</tool_call>",
  "error": null
}
```
### dev_004

Prompt: Read inbox/Read Me.txt, preserving the spaces and capitalization in its path.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "inbox/Read Me.txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"inbox/Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"inbox/Read Me.txt\"}}\n</tool_call>",
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
### dev_006

Prompt: Read the JSON file in config whose name refers to runtime, rather than settings.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "config/runtime.json"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"config/runtime.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"runtime\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Are you sure about reading the JSON file named 'runtime' instead of 'settings'?\"}}",
  "error": null
}
```
### dev_007

Prompt: Show a recursive inventory of the entire workspace.

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "list_files",
    "arguments": {},
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "Clarify: Please provide a file or directory path to search for contents.",
  "error": null
}
```
### dev_018

Prompt: Move inbox/receipt.txt to archive/receipt.txt.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "inbox/receipt.txt",
      "destination": "archive/receipt.txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/receipt.txt\", \"destination\": \"archive/receipt.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"archive/summary.txt\", \"destination\": \"archive/receipt.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"archive/transfer.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_019

Prompt: The old-results CSV in archive must stay where it is. Relocate the results CSV currently under reports to archive/results.csv.

Failure: INVALID_OUTPUT

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
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\"}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"query\": \"results.csv\"}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"path\": \"archive/old-results.csv\", \"destination\": \"reports/results.csv\"}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"path\": \"archive/sample.csv\", \"destination\": \"archive/results.csv\"}\n</tool_call>",
  "error": null
}
```
### dev_020

Prompt: Move inbox/Read Me.txt to archive/Read Me.txt. Keep its capitalization and spaces.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "inbox/Read Me.txt",
      "destination": "archive/Read Me.txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/Read Me.txt\", \"destination\": \"archive/Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"archive/2025-summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"archive/README.md\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Do you want me to move the file 'inbox/Read Me.txt' to the archive?\"}}\n</tool_call>",
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
  "raw_output": "clarify",
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
      "query": "all files in the workspace"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"all files in the workspace\"}}\n</tool_call>",
  "error": null
}
```
### dev_026

Prompt: Delete notes/draft.txt permanently.

Failure: INVALID_OUTPUT

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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"inbox/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Do you want to delete notes/draft.txt permanently?\"}}\n</tool_call>",
  "error": null
}
```
### dev_027

Prompt: Create notes/new.txt containing hello.

Failure: INVALID_OUTPUT

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
  "raw_output": "<tool_call>\n{\"name\": \"tools\", \"arguments\": {\"tool\": \"list_files\", \"query\": \"notes/new.txt\"}}\n</tool_call>",
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

Failure: INVALID_OUTPUT

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
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"docs/README.md\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/setup.md\"}}\n</tool_call>",
  "error": null
}
```
### dev_030

Prompt: Read reports/summary.txt after first listing all files in the workspace. Return only the first action.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "list_files",
    "arguments": {},
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"reports/summary.txt\"}}",
  "error": null
}
```
### dev_032

Prompt: The receipt must stay in inbox. Move the transfer text file from inbox to archive/transfer.txt, then list all workspace files. Return only the first action.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "inbox/transfer.txt",
      "destination": "archive/transfer.txt"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"archive/transfer.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"archive\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Are there any specific formatting or language requirements for the transfer file?\"}}\n</tool_call>",
  "error": null
}
```
### dev_033

Prompt: Move notes/draft.txt to archive/draft.txt, but keep notes/draft.txt in its original location too. Do not change either requirement.

Failure: INVALID_OUTPUT

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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"archive/draft.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"The destination is 'archive/draft.txt', but the source is 'notes/draft.txt'. Are you moving all files from the source to the destination or keeping them in their original location?\"}}\n</tool_call>",
  "error": null
}
```
### dev_034

Prompt: Move inbox/summary.txt to reports/summary.txt without replacing any existing file.

Failure: INVALID_OUTPUT

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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/summary.txt\", \"destination\": \"reports/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Is there any existing file named reports/summary.txt in the workspace that needs to be moved?\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"summary.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_035

Prompt: Read the CSV sample under data; the JSON sample is not the one I want.

Failure: INVALID_OUTPUT

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
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"data\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Is the file in the data folder?\"}}\n</tool_call>",
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
