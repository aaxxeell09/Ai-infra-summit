# Provenance impact of reporting and input hardening

The Secretary evaluator runner now accepts strict UTF-8 JSON with an optional UTF-8 BOM for private configuration, quality policy, baseline approval, and imported baseline files. It rejects duplicate keys, nonfinite numbers, and non-object roots. Reading does not rewrite file bytes. Frozen datasets and fixture loading are unchanged.

Each case additionally retains the runtime's `sampling` metadata. This records available sampler evidence; a requested temperature of zero alone does not establish greedy decoding. No timer boundaries, parser rules, scoring rules, golden actions, or fixture contents change in this infrastructure update.

## Evaluator fingerprint changes

The evaluator fingerprint includes the runner's source bytes. These infrastructure-only edits therefore change `evaluator_sha256` even though scoring semantics remain unchanged. Historical results remain immutable and retain their original fingerprints. Do not replace historical fingerprints, relabel old runs as current, or remove fingerprint checks to make a comparison pass.

Results produced before and after this update cannot claim an identical-evaluator comparison. The descriptive report can display their measured metrics and incompatibility reasons; a current comparable set requires fresh runs under the same committed runner and protocol. A new official baseline also requires the existing approval procedure. No new hardware results are provided by this update.

## Backend identity consistency

Descriptive reporting now checks configuration, top-level backend identity, and per-case device/runtime evidence for contradictions. Known CPU versus NPU/GPU contradictions block comparability instead of trusting a top-level label. Legacy reports can still identify their backend through their plugin and consistently selected devices. `dispatch_verified=false` remains an absence of verified dispatch evidence; it is not evidence that NPU dispatch did not occur.

## Hardware follow-up

Fresh CPU, llama_cpp HTP, and QAIRT measurements require the Snapdragon target. Energy commissioning, actual power-mode observation, counter cadence, and stop-candidate runtime behavior still require hardware validation. Unit-test evidence is not a hardware performance measurement.
