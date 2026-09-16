# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 728c6a2ad72917a8173f88cf647360bb83269c0a
Candidate: qairt-stop-control-full-v1
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
Task success: 20/50 (40.00%)
Failed tasks: 30
Tool / action / arguments: 42.00% / 42.00% / 54.00%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 34.00%
Latency mean / median / p95 (ms): 810.762 / 524.575 / 1965.833

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
- clarify_unsupported: 0/3 (0.00%)
- list: 3/3 (100.00%)
- list_exact_path: 1/1 (100.00%)
- list_paraphrase: 3/3 (100.00%)
- move: 1/3 (33.33%)
- move_exact_path: 0/1 (0.00%)
- move_paraphrase: 1/2 (50.00%)
- move_rename: 1/1 (100.00%)
- multistep_first_action: 3/6 (50.00%)
- read: 1/4 (25.00%)
- read_exact_path: 0/4 (0.00%)
- read_paraphrase: 0/2 (0.00%)
- search: 1/2 (50.00%)
- search_exact_query: 3/3 (100.00%)
- search_paraphrase: 2/2 (100.00%)

## Difficulty

- easy: 8/15 (53.33%)
- hard: 3/15 (20.00%)
- medium: 9/20 (45.00%)

## Expected action

- clarify: 0/13 (0.00%)
- list_files: 8/9 (88.89%)
- move_file: 3/8 (37.50%)
- read_file: 2/12 (16.67%)
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
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/receipt.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"inbox/README.md\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"config/runtime.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"runtime.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"config/runtime.json\", \"destination\": \"archive/2025-summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"please check if the JSON file in config/runtime is the one to search for\"}}",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/receipt.txt\", \"destination\": \"archive/receipt.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"archive/transfer.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"docs/meeting-notes.txt\", \"destination\": \"archive/meetings.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_019

Prompt: The old-results CSV in archive must stay where it is. Relocate the results CSV currently under reports to archive/results.csv.

Failure: PARSE_ERROR

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
  "raw_output": "<tool_call>\n{\"name\": \"list_files\"}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\"}\n,{\"path\": \"archive/old-results.csv\", \"destination\": \"reports/archive/results.csv\"}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\"}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\"}\n,{\"query\": \"old-results CSV\"}\"\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/Read Me.txt\", \"destination\": \"archive/Read Me.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"archive/runtime.json\", \"destination\": \"archive/runtime.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"data/sample.json\", \"destination\": \"archive/data.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"docs/setup.md\", \"destination\": \"docs/setup.md\"}}\n</tool_call>",
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
  "raw_output": "Clarify: What file would you like to read?",
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
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/README.md\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"query\": \"meeting-notes.txt\"}}",
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
      "destination": "summary.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"summary.txt\"}}\n</tool_call>",
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
      "query": "all files"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"all files\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"inbox/draft.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/ideas.txt\", \"destination\": \"inbox/ideas.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/meeting (final).txt\", \"destination\": \"inbox/meeting.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Are you sure? If you want to delete notes/draft.txt",
  "error": null
}
```
### dev_027

Prompt: Create notes/new.txt containing hello.

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
  "raw_output": "<tool_call>\n{\"name\": \"tools\", \"arguments\": {\"tools\": [\"create_note\", {\"path\": \"notes\", \"content\": \"hello\"]}}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\", \"destination\": \"archive/transfer.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"archive/2025-summary.txt\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/draft.txt\", \"destination\": \"archive/draft.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"archive/2025-summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"notes/draft.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"path\": \"archive/notes/draft.txt\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/summary.txt\", \"destination\": \"reports/summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"arguments\": []}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"clarify\", \"arguments\": {\"question\": \"Is there any other file in the workspace that might conflict with moving to reports/summary.txt?\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"sample.csv\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"sample.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"archive/2025-summary.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>",
  "error": null
}
```
### heldout_001

Prompt: Retrieve the contents of reports/latency.csv.

Failure: WRONG_ACTION

Expected vs actual:
```json
{
  "expected": {
    "tool": "read_file",
    "arguments": {
      "path": "reports/latency.csv"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": "search_files",
    "arguments": {
      "query": "reports/latency.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"reports/latency.csv\"}}\n</tool_call>",
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
  "raw_output": "No text of docs/guide-français.md. Let me know if you need that information.",
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
  "raw_output": "{\"name\": \"search_files\", \"arguments\": {\"query\": \"meeting-notes.txt\"}}",
  "error": null
}
```
### heldout_008

Prompt: Both projects have a budget. Move only the alpha budget to archive/alpha-budget.csv; leave beta untouched.

Failure: INVALID_OUTPUT

Expected vs actual:
```json
{
  "expected": {
    "tool": "move_file",
    "arguments": {
      "path": "projects/alpha/budget.csv",
      "destination": "archive/alpha-budget.csv"
    },
    "clarification_required": false,
    "should_act": true
  },
  "actual": {
    "tool": null,
    "arguments": {}
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"projects/alpha/budget.csv\", \"destination\": \"archive/alpha-budget.csv\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"projects/alpha/budget.csv\", \"destination\": \"archive/alpha-budget.csv\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"projects/beta/budget.csv\", \"destination\": \"archive/beta-budget.csv\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"archive/2025-summary.txt\", \"destination\": \"archive/chosen.txt\"}}\n</tool_call>\n<tool_call>\n{\"name\": \"list_files\", \"arguments\": {\"parameters\": {}}}",
  "error": null
}
```
### heldout_012

Prompt: Append the line "Review complete" to notes/ideas.txt.

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
      "path": "notes/ideas.txt",
      "destination": "notes/ideas.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"notes/ideas.txt\", \"destination\": \"notes/ideas.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_015

Prompt: Read reports/final-results.csv exactly; do not substitute results.csv or old-results.csv if that exact path is absent.

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
  "raw_output": "<tool_call>\n{\"name\": \"list_files\", \"arguments\": {}}",
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
