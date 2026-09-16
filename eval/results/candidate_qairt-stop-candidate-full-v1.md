# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 728c6a2ad72917a8173f88cf647360bb83269c0a
Candidate: qairt-stop-candidate-full-v1
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
Task success: 29/50 (58.00%)
Failed tasks: 21
Tool / action / arguments: 62.00% / 62.00% / 80.00%
Clarification accuracy (expected-clarify cases): 7.6923076923076925
Invalid output rate: 8.00%
Latency mean / median / p95 (ms): 518.686 / 496.161 / 699.029

Quality gate: NOT_COMPARABLE

## Categories

- clarify_ambiguous_path: 0/3 (0.00%)
- clarify_conflicting_constraints: 0/1 (0.00%)
- clarify_missing_destination: 0/1 (0.00%)
- clarify_missing_file: 0/1 (0.00%)
- clarify_missing_path: 0/1 (0.00%)
- clarify_missing_query: 0/1 (0.00%)
- clarify_missing_source: 0/1 (0.00%)
- clarify_overwrite: 0/1 (0.00%)
- clarify_unsupported: 1/3 (33.33%)
- list: 3/3 (100.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 3/3 (100.00%)
- move: 3/3 (100.00%)
- move_exact_path: 1/1 (100.00%)
- move_paraphrase: 1/2 (50.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 5/6 (83.33%)
- read: 3/4 (75.00%)
- read_exact_path: 1/4 (25.00%)
- read_paraphrase: 0/2 (0.00%)
- search: 1/2 (50.00%)
- search_exact_query: 3/3 (100.00%)
- search_paraphrase: 2/2 (100.00%)

## Difficulty

- easy: 10/15 (66.67%)
- hard: 6/15 (40.00%)
- medium: 13/20 (65.00%)

## Expected action

- clarify: 1/13 (7.69%)
- list_files: 9/9 (100.00%)
- move_file: 7/8 (87.50%)
- read_file: 5/12 (41.67%)
- search_files: 7/8 (87.50%)

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
      "path": "data/ideas.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/ideas.txt\"}}\n</tool_call>",
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
### dev_012

Prompt: Search file contents for the substring "latency".

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "search_files",
    "arguments": {
      "query": "latency"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"latency\"}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"list_files\"}\n</tool_call>",
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
      "path": "docs/README.md"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/README.md\"}}\n</tool_call>",
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
      "query": "workspace files"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"workspace files\"}}\n</tool_call>",
  "error": null
}
```
### dev_026

Prompt: Delete notes/draft.txt permanently.

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
      "destination": "inbox/notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"inbox/notes.txt\"}}\n</tool_call>",
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
      "path": "data/budget.csv",
      "destination": "archive/budget.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"data/budget.csv\", \"destination\": \"archive/budget.csv\"}}\n</tool_call>",
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
### heldout_002

Prompt: Show the text of docs/guide-français.md.

Failure: PARSE_ERROR

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "docs/guide-français.md"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "The text of docs/guide-français.md is not available here. Please check the documents folder.",
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
      "query": "meeting-notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"meeting-notes.txt\"}}\n</tool_call>",
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
      "query": "Open plan.md"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"Open plan.md\"}}\n</tool_call>",
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
      "path": "archive/2025-summary.txt",
      "destination": "archive/chosen.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"archive/2025-summary.txt\", \"destination\": \"archive/chosen.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_015

Prompt: Read reports/final-results.csv exactly; do not substitute results.csv or old-results.csv if that exact path is absent.

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

## Comparison

```json
{
  "status": "NOT_COMPARABLE",
  "reasons": [
    "Incompatible evaluator_sha256"
  ]
}
```
