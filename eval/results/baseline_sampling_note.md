# Sampling provenance clarification (baseline preserved)

The official baseline JSON and its results remain unchanged. Its `temperature: 0` records what the adapter requested, not proof of effective greedy decoding.

The [tagged GenieX v0.6.1 llama_cpp source](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/llama_cpp/src/params.cpp#L160-L170) replaces zero temperature with 0.8, zero top-k with 40, and zero min-p with 0.05. Our original adapter passed those zeros and seed -1. The inferred effective configuration is therefore sampling with runtime-default randomness, not the intended greedy policy. This is a source-based inference for the pinned release; the installed SDK does not expose its post-default sampler through the wrapper. Observed repeated outputs varied, but variation alone cannot identify its cause.

The baseline and first two candidates all use the unchanged original adapter at `ccd1e00`, so preserve them as measured runs of that implementation. One run per configuration does not isolate backend effects from stochastic output variation. The 60% → 66% result is an observed difference, not evidence that CPU placement inherently improves task quality.

A separate `greedy-topk1-cpu-v2` candidate changes only the production adapter's greedy request handling: for `llama_cpp` and requested temperature zero, pass `top_k=1`. This constrains selection to one highest-ranked token even when the SDK substitutes its temperature default. Positive-temperature requests and QAIRT are unchanged. Model/backend numerical differences can still change the selected token. This is an adapter workaround, not a rebuilt GenieX binary or a novel decoding algorithm.

The frozen dataset, scorer, system instructions, fixtures, output cap and existing reference results are not changed. The candidate must run through the same correctness gate. Any proposed upstream change should distinguish explicit zero from absent/default configuration and be reviewed against the API's compatibility contract.
