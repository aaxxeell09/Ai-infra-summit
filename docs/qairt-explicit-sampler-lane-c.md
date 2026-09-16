# QAIRT explicit sampler — Lane C diagnostic v1

**Base:** `c866c48f0d12219d8cf38187c71769623143c0c8`. **Protocol:** `qairt-explicit-sampler-diagnostic-v1`. **Status:** implemented diagnostic request/ABI path and synthetic tests; **real execution blocked because effective-sampler readback is unavailable**. No Lane A admission, tracker qualification, benchmark result or performance claim follows.

## Evidence and exact mapping

The target is owner-described as GenieX 0.6.1, QAIRT 2.45, official Qualcomm Qwen3-0.6B, plugin `qairt`, NPU. No installed target SDK/library was available for direct inspection in this worktree. Tagged upstream sources were inspected read-only; they do not certify the installed DLLs.

The unchanged Python path is `NativeModel.chat` → `_chat_locked` → `geniex_SamplerConfig` → `geniex_GenerationConfig.sampler_config` → `geniex_llm_generate`. Its normal defaults send temperature 0, top-p 1, top-k 0 and seed -1. Python only directly exposes temperature; top-k=1 via `greedy_zero` is restricted to llama.cpp and does not enable a QAIRT control.

[GenieX's public C header](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/include/geniex.h) defines float32 temperature/top-p and signed-int32 top-k/seed. Its generation output provides text and profile data, not effective sampler values. [The QAIRT generation wrapper](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/src/llm.cpp) passes the public sampler to the adapter before pipeline generation.

[The tagged sampler adapter](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/include/sampler_config_utils.h) gives nonzero caller values precedence; zero defers to bundle/plugin defaults. It casts seed to unsigned, so -1 becomes 4294967295 rather than proving random-seed behavior. Negative temperature has a source-documented greedy sentinel, but this diagnostic does not expose it or claim installed-runtime enforcement.

| Diagnostic field | Public ABI field | Explicit diagnostic range | Native mapping shown in source |
|---|---|---|---|
| `temperature` | float32 `temperature` | finite `0 < x <= 2` | Nonzero literal; zero is not an explicit greedy request |
| `top_p` | float32 `top_p` | finite `0 < x <= 1` | Nonzero literal |
| `top_k` | int32 `top_k` | `1..2147483647` | Nonzero literal; candidate 1 narrows to one candidate |
| `seed` | int32 `seed` | `1..2147483647` | Positive value survives unsigned conversion |

These are **source-supported ABI inputs**, not runtime-verified controls. Float32 conversion is recorded; values that underflow to zero are rejected. Missing/extra keys, booleans, nonfinite numbers and sentinel values are rejected. `top_k=1` plus fixed positive seed is a candidate hypothesis, not a determinism guarantee. Controls such as penalties/min-p, negative-temperature sentinel, grammar and stop sequences are not exposed by this minimal protocol.

## Fail-closed implementation

`LaneCQairtSamplerModel` is a separate subclass. Its proxy replaces the sampler pointer only for its own generation call and forwards through the real public `geniex_llm_generate` ABI. The existing model implementation still handles disabled thinking, template construction, reset, generation, output allocation cleanup and profiling. The original runtime/pointer are restored even on errors. Default `NativeModel`, frozen runner/parser/scoring and benchmark configuration allowlists are unchanged.

There are **no trusted native readback implementations registered**. Without one, model construction refuses before load, and the CLI does not initialize the SDK. There is no `--effective-values` file or user-attestation bypass. The CLI writes a new ignored local diagnostic record with requested values, planned ABI values, `abi_submitted=null`, `effective_native=null`, zero completed repeats and status `BLOCKED_EFFECTIVE_READBACK_UNAVAILABLE`.

The subclass has an integration point for an audited future native readback provider. After each generation, it must obtain the actual sampler used for that same generation and compare it against the exact ABI-normalized request. Missing or mismatched values raise before output acceptance; the repeat harness records the failed attempt and stops. Synthetic tests register an explicit fake provider only inside the test process. Their metadata says `synthetic_contract_only` and never populates `effective_native`.

To unblock the real path, an audited SDK/plugin instrumentation change must expose sampler values **after fallback resolution and before/at the actual sampler**, bound to the same model and generation. It must also bind runtime version and binary identity. A request echo, bundle JSON, source-derived expectation, or pre-adapter log is insufficient. This work does not invent that native API or modify the DLL. If the only trustworthy readback becomes available after generation, mismatched output must remain failed evidence. Timing that includes readback overhead must remain diagnostic and separately labeled.

## Five-repeat determinism diagnostic

The harness uses one model instance, one identical prompt, five sequential calls and reset=true each time. It compares raw UTF-8 bytes exactly: capitalization, punctuation and whitespace matter. `semantic_correctness` remains null; equal output is not proof of a correct action. A failed readback produces no determinism conclusion.

The owner reported an existing five-repeat target test returning `hello`, `Hello.`, `HELLO`, `hello`, `hello`, with logs showing 0/1/0/-1 for temperature/top-p/top-k/seed. That is owner-reported nondeterminism, not a new measurement by this branch. The log's position relative to sampler fallback is not established; the values match the current Python ABI request and must not be relabeled verified post-adapter values.

### Exact target command

Run from this branch's repository root with the existing private QAIRT base config. No dataset or heldout option exists:

```powershell
python -X utf8 scripts/qairt_sampler_diagnostic.py --config local/qairt-secretary.json --temperature 0.8 --top-p 1.0 --top-k 1 --seed 42 --repeats 5 --prompt "Say hello in one short word." --output local/sampler-diagnostics/topk1-seed42-v1.json
```

**Current expected outcome: exit code 3, a blocked diagnostic JSON, and no model load or inference.** This command cannot yet produce five target outputs. Use a fresh output filename; existing evidence is never overwritten. The candidate explicitly changes several sampling inputs and makes no single-variable causal claim.

A future hardware run requires the audited readback capability, one hardware owner, verified target artifacts and separate approval to promote any result beyond Lane C. Do not add these keys to the frozen runner, run heldout tuning, infer an efficiency winner, or treat the canary as a qualified experiment.
