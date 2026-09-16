# Secretary prefix and cache evidence

Evidence: STATIC_CODE_EVIDENCE, source inspected during the overnight sprint.

The frozen adapter builds 407 UTF-8 bytes of instructions plus 606 inventory bytes (30 paths), totaling 1,013 bytes. Canonical diagnostic serialization of the tool schema is 1,319 bytes. This is **not a token count** and is not claimed to reproduce the backend chat template. System, tools, inventory and user token counts remain unknown until the actual tokenizer/template is measured.

Reproduce without reading heldout prompts:

```sh
python scripts/inspect_secretary_prefix.py --output local/new-prefix-report.json
```

The existing native API exposes `reset=False`, but the frozen runner explicitly resets each case. A persistent session is not proven to implement correct reusable-prefix caching. Disabling reset can accumulate previous requests/answers and contaminate independent cases. Do not change it in v2 or claim a speedup. A versioned candidate needs runtime capability evidence, identical prompt equivalence, isolation checks, bounded context growth and controlled task/energy measurements.

No prefix optimization was applied and no hardware tokenizer was available.
