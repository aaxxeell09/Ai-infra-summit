# Secretary correctness audit

Scope: one Secretary action plus isolated fixture execution; not full multi-turn routing workflow.

Benchmark: secretary-eval-v2
Status: measured
Application commit: 41260c438e64a1da1107e2d3ba88236886314993
Candidate: greedy-topk1-cpu-v2
Model: Qwen3-0.6B-Q4_0.gguf

Configuration:
```json
{
  "device": "cpu",
  "threads": 10,
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
Task success: 29/50 (58.00%)
Failed tasks: 21
Tool / action / arguments: 70.00% / 70.00% / 78.00%
Clarification accuracy (expected-clarify cases): 0.0
Invalid output rate: 8.00%
Latency mean / median / p95 (ms): 823.220 / 845.590 / 933.759

Quality gate: FAIL

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
- read_exact_path: 2/4 (50.00%)
- read_paraphrase: 0/2 (0.00%)
- search: 2/2 (100.00%)
- search_exact_query: 3/3 (100.00%)
- search_paraphrase: 2/2 (100.00%)

## Difficulty

- easy: 13/15 (86.67%)
- hard: 5/15 (33.33%)
- medium: 11/20 (55.00%)

## Expected action

- clarify: 0/13 (0.00%)
- list_files: 9/9 (100.00%)
- move_file: 6/8 (75.00%)
- read_file: 7/12 (58.33%)
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
      "path": "data/ideas.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/ideas.txt\"}}\n</tool_call>",
  "error": null
}
```
### dev_005

Prompt: I need the plan for beta. The alpha plan is a distractor; read only the beta one from the inventory.

Failure: WRONG_ARGUMENT

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
    "tool": "read_file",
    "arguments": {
      "path": "data/sample.json"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>",
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
      "path": "data/sample.csv",
      "destination": "reports/results.csv"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"data/sample.csv\", \"destination\": \"reports/results.csv\"}}\n</tool_call>",
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
      "path": "data/sample.json"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"data/sample.json\"}}\n</tool_call>",
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
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"inbox/transfer.txt\"}}\n</tool_call>",
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
      "query": "workspace"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"search_files\", \"arguments\": {\"query\": \"workspace\"}}\n</tool_call>",
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
  "raw_output": "None of the provided functions can delete a file. The available functions are: list_files, read_file, search_files, move_file, and clarify.",
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
    "tool": "read_file",
    "arguments": {
      "path": "notes/draft.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"notes/draft.txt\"}}\n</tool_call>",
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

Failure: WRONG_ARGUMENT

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
      "path": "docs/meeting-notes.txt"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/meeting-notes.txt\"}}\n</tool_call>",
  "error": null
}
```
### heldout_009

Prompt: Move the PNG file under assets to archive/photo.png. Leave the SVG where it is.

Failure: WRONG_SOURCE, WRONG_FINAL_STATE

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
      "path": "assets/logo.svg",
      "destination": "archive/photo.png"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"move_file\", \"arguments\": {\"path\": \"assets/logo.svg\", \"destination\": \"archive/photo.png\"}}\n</tool_call>",
  "error": null
}
```
### heldout_010

Prompt: Open plan.md.

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
      "path": "docs/open-plan.md"
    }
  },
  "raw_output": "<tool_call>\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"docs/open-plan.md\"}}\n</tool_call>",
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
  "raw_output": "None of the provided functions can append a line to a file.",
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
  "status": "FAIL",
  "reasons": [
    "Invalid output rate exceeds absolute limit",
    "Invalid output rate increase exceeds policy",
    "read_exact_path: category accuracy drop exceeds policy"
  ],
  "accuracy_delta_points": -2.0,
  "category_regressions": [
    {
      "category": "read_exact_path",
      "drop_points": 25.0,
      "failures": [
        "dev_005",
        "dev_035"
      ]
    }
  ],
  "median_latency_change_pct": -26.314156720209215,
  "baseline_metrics": {
    "total_prompts": 50,
    "task_success": 30,
    "task_accuracy": 60.0,
    "tool_accuracy": 70.0,
    "action_accuracy": 70.0,
    "argument_accuracy": 82.0,
    "clarification_no_action_accuracy": 72.0,
    "argument_applicable_prompts": 37,
    "argument_accuracy_applicable": 81.08108108108108,
    "avg_task_latency_ms": 1269.1927,
    "median_task_latency_ms": 1205.3384999999998,
    "avg_latency_ms": 1209.53102,
    "median_latency_ms": 1147.5610000000001,
    "p95_latency_ms": 1500.174,
    "latency_samples": 50,
    "errors": 0,
    "categories": {
      "clarify_ambiguous_path": {
        "total": 3,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_023",
          "dev_028",
          "heldout_010"
        ]
      },
      "clarify_conflicting_constraints": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_033"
        ]
      },
      "clarify_missing_destination": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_024"
        ]
      },
      "clarify_missing_file": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "heldout_015"
        ]
      },
      "clarify_missing_path": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_022"
        ]
      },
      "clarify_missing_query": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_025"
        ]
      },
      "clarify_missing_source": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "heldout_011"
        ]
      },
      "clarify_overwrite": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_034"
        ]
      },
      "clarify_unsupported": {
        "total": 3,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_026",
          "dev_027",
          "heldout_012"
        ]
      },
      "list": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "list_exact_path": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "list_paraphrase": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move_exact_path": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move_paraphrase": {
        "total": 2,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_019",
          "heldout_009"
        ]
      },
      "move_rename": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "multistep_first_action": {
        "total": 6,
        "task_success": 4,
        "task_accuracy": 66.66666666666667,
        "failures": [
          "dev_029",
          "dev_031"
        ]
      },
      "read": {
        "total": 4,
        "task_success": 4,
        "task_accuracy": 100.0,
        "failures": []
      },
      "read_exact_path": {
        "total": 4,
        "task_success": 3,
        "task_accuracy": 75.0,
        "failures": [
          "dev_035"
        ]
      },
      "read_paraphrase": {
        "total": 2,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_003",
          "heldout_003"
        ]
      },
      "search": {
        "total": 2,
        "task_success": 2,
        "task_accuracy": 100.0,
        "failures": []
      },
      "search_exact_query": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "search_paraphrase": {
        "total": 2,
        "task_success": 2,
        "task_accuracy": 100.0,
        "failures": []
      }
    },
    "failed_tasks": 20,
    "invalid_output_rate": 0.06,
    "parse_failure_rate": 0.06,
    "clarification_prompts": 13,
    "clarification_accuracy": 0.0,
    "difficulties": {
      "easy": {
        "total": 15,
        "task_success": 13,
        "task_accuracy": 86.66666666666667
      },
      "hard": {
        "total": 15,
        "task_success": 6,
        "task_accuracy": 40.0
      },
      "medium": {
        "total": 20,
        "task_success": 11,
        "task_accuracy": 55.0
      }
    },
    "actions": {
      "clarify": {
        "total": 13,
        "task_success": 0,
        "task_accuracy": 0.0
      },
      "list_files": {
        "total": 9,
        "task_success": 9,
        "task_accuracy": 100.0
      },
      "move_file": {
        "total": 8,
        "task_success": 6,
        "task_accuracy": 75.0
      },
      "read_file": {
        "total": 12,
        "task_success": 8,
        "task_accuracy": 66.66666666666667
      },
      "search_files": {
        "total": 8,
        "task_success": 7,
        "task_accuracy": 87.5
      }
    }
  },
  "candidate_metrics": {
    "total_prompts": 50,
    "task_success": 29,
    "task_accuracy": 58.0,
    "tool_accuracy": 70.0,
    "action_accuracy": 70.0,
    "argument_accuracy": 78.0,
    "clarification_no_action_accuracy": 72.0,
    "argument_applicable_prompts": 37,
    "argument_accuracy_applicable": 78.37837837837837,
    "avg_task_latency_ms": 877.37612,
    "median_task_latency_ms": 889.0725,
    "avg_latency_ms": 823.22004,
    "median_latency_ms": 845.59,
    "p95_latency_ms": 933.759,
    "latency_samples": 50,
    "errors": 0,
    "categories": {
      "clarify_ambiguous_path": {
        "total": 3,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_023",
          "dev_028",
          "heldout_010"
        ]
      },
      "clarify_conflicting_constraints": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_033"
        ]
      },
      "clarify_missing_destination": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_024"
        ]
      },
      "clarify_missing_file": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "heldout_015"
        ]
      },
      "clarify_missing_path": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_022"
        ]
      },
      "clarify_missing_query": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_025"
        ]
      },
      "clarify_missing_source": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "heldout_011"
        ]
      },
      "clarify_overwrite": {
        "total": 1,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_034"
        ]
      },
      "clarify_unsupported": {
        "total": 3,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_026",
          "dev_027",
          "heldout_012"
        ]
      },
      "list": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "list_exact_path": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "list_paraphrase": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move_exact_path": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "move_paraphrase": {
        "total": 2,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_019",
          "heldout_009"
        ]
      },
      "move_rename": {
        "total": 1,
        "task_success": 1,
        "task_accuracy": 100.0,
        "failures": []
      },
      "multistep_first_action": {
        "total": 6,
        "task_success": 4,
        "task_accuracy": 66.66666666666667,
        "failures": [
          "dev_029",
          "dev_031"
        ]
      },
      "read": {
        "total": 4,
        "task_success": 4,
        "task_accuracy": 100.0,
        "failures": []
      },
      "read_exact_path": {
        "total": 4,
        "task_success": 2,
        "task_accuracy": 50.0,
        "failures": [
          "dev_005",
          "dev_035"
        ]
      },
      "read_paraphrase": {
        "total": 2,
        "task_success": 0,
        "task_accuracy": 0.0,
        "failures": [
          "dev_003",
          "heldout_003"
        ]
      },
      "search": {
        "total": 2,
        "task_success": 2,
        "task_accuracy": 100.0,
        "failures": []
      },
      "search_exact_query": {
        "total": 3,
        "task_success": 3,
        "task_accuracy": 100.0,
        "failures": []
      },
      "search_paraphrase": {
        "total": 2,
        "task_success": 2,
        "task_accuracy": 100.0,
        "failures": []
      }
    },
    "failed_tasks": 21,
    "invalid_output_rate": 0.08,
    "parse_failure_rate": 0.06,
    "clarification_prompts": 13,
    "clarification_accuracy": 0.0,
    "difficulties": {
      "easy": {
        "total": 15,
        "task_success": 13,
        "task_accuracy": 86.66666666666667
      },
      "hard": {
        "total": 15,
        "task_success": 5,
        "task_accuracy": 33.333333333333336
      },
      "medium": {
        "total": 20,
        "task_success": 11,
        "task_accuracy": 55.0
      }
    },
    "actions": {
      "clarify": {
        "total": 13,
        "task_success": 0,
        "task_accuracy": 0.0
      },
      "list_files": {
        "total": 9,
        "task_success": 9,
        "task_accuracy": 100.0
      },
      "move_file": {
        "total": 8,
        "task_success": 6,
        "task_accuracy": 75.0
      },
      "read_file": {
        "total": 12,
        "task_success": 7,
        "task_accuracy": 58.333333333333336
      },
      "search_files": {
        "total": 8,
        "task_success": 7,
        "task_accuracy": 87.5
      }
    }
  },
  "invalid_output_delta_points": 2.0000000000000004,
  "compared_prompts": 50,
  "policy": {
    "max_accuracy_drop_points": 3,
    "max_category_drop_points": 10,
    "critical_categories": [
      "ambiguous",
      "unsupported",
      "destructive",
      "move"
    ],
    "critical_tools": [
      "clarify",
      "move_file"
    ],
    "max_invalid_action_rate": 0.02,
    "max_invalid_action_increase_points": 2,
    "max_clarification_drop_points": 0
  }
}
```
