# QAIRT sampling: requested and effective values

The first full QAIRT result requests temperature zero. This is **not evidence
of greedy sampling**. Qualcomm's version-pinned
[QAIRT sampler adapter](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/include/sampler_config_utils.h)
treats zero as a sentinel that defers to the bundle, then plugin defaults. The
official artifact we used declares temperature 0.8 and top-k 40.

Our existing ctypes adapter additionally sends top-p 1.0 and seed -1. The
QAIRT wrapper casts the seed to an unsigned integer; do not describe that as
the bundle seed 42 or assume random-seed behavior without inspecting the lower
sampler. The published runtime record retains the actual bundle configuration.

The metadata now marks zero-temperature fallback for both llama.cpp and QAIRT.
No sampler setting changed in this correction, and historical reports remain
untouched. A future deterministic QAIRT experiment must explicitly record its
sampler fields and verify repeated outputs before making a reproducibility claim.

The same version-pinned adapter forwards inline grammar, with precedence over a
grammar file. That supports preparing a GBNF experiment, but does not prove
the installed binary enforces it. Run a deliberately restrictive canary first.
The [QAIRT generation wrapper](https://github.com/qualcomm/GenieX/blob/v0.6.1/sdk/plugins/qairt/src/llm.cpp)
rejects public stop sequences and exposes cancellation through its callback.
It also derives prompt time from TTFT; reported prefill throughput is a proxy.

Keep these ablations separate: default sampling, explicit deterministic
sampling, production action grammar, then validated structural cancellation.
The frozen runner currently rejects its grammar option. Coordinate a candidate
adapter extension with Axel before official evaluation; do not enable grammar
implicitly in the native layer or modify expected actions.
