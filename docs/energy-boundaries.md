# Energy boundaries

| Scope | Boundary | Interpretation |
|---|---|---|
| full_process_energy | before launching evaluator child → after child exit | includes validation/hashes/load/warmup/cases/copies/audit/serialization; cold/setup included |
| warm_suite_block (future commissioned run) | after load/warmup → after whole case workload | only valid when every attempted case belongs to same block and exact scope retained |
| cold_load | runtime/model initialization | startup diagnostic, not warm inference |
| warm_task_v1 | prepared fixture → request/score/actual tool finish | final audit excluded; subsecond readings may be unresolved |
| inference | around native generate | excludes Python template/reset, cannot stand in for task energy |
| platform/runtime idle | repeated quiet windows before/after resident model | baseline stability diagnostic |
| gross | raw positive SYS difference ×3.6e-9 | primary numerator, all attempts included |
| net | gross − stable runtime idle power×duration | diagnostic; negative net remains unavailable |

Observed update gap, requested polling interval, declared protocol resolution and true hardware resolution are separate facts. Approximately1second gaps do not validate precise0.5second per-task joules. Store raw PDH source timestamps/status/type and host collection bounds, without claiming actual hardware cadence from synthetic tests.

Qualified imports must validate retained protocol/idle/warmup/power/runtime/counter evidence, not merely valid=true. Historical full-process records may be displayed as diagnostic counter-derived energy but do not acquire new commissioning or power observations retroactively. Windows active scheme is not the power-mode overlay; observed overlay remains null until a reliable observation exists.
