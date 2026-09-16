# Live frontend rehearsal on Snapdragon

The teammate's **Machine → Compare → In action** UI was exercised in a real
browser, using frontend commit `86eb559` and the Latitude gateway at clean
commit `410931fb03e8d50977da52128ba5a8b9c81a4d49`.

The browser selected the recorded CPU/10 configuration, clicked **Run on
Latitude**, displayed two actual native answers and downloaded the result.
The downloaded JSON was checked against the result saved on the device: it
matches exactly, with the provider's terminal `status` and `error` fields added.
Original bytes and SHA-256 digests are preserved in `publication.json`.

Both lanes use Qwen3-0.6B Q4_0, GenieX 0.6.1, llama.cpp CPU, context 4096,
fresh models/KV, no warmup and the same public prompt. The request and result
retain the model hash, SDK identity, source identity and generation policy.

| Observed measurement | CPU automatic threads | CPU 10 threads |
| --- | ---: | ---: |
| Lane load + answer + unload | 2.586 s | 1.719 s |
| Native TTFT, excluding model load | 754.436 ms | 851.661 ms |
| Generated tokens | 23 | 25 |
| Native decode rate | 160.022 tok/s | 141.511 tok/s |

Use the full JSON for unrounded values. Pair time was 10.096 s, including
identity checks and prior-model unload, excluding browser/network transport.
Memory and energy were not captured. Neither answer followed the requested
two-sentence format; answer quality is explicitly **not evaluated** by this
adapter. This is evidence that the live UI reaches the selected configuration,
not a correctness PASS or a confirmed speedup. The selected configuration was
faster in this lane-time observation but had slower native TTFT and decode;
output lengths differ and the samples are unreplicated.

The first integration launch exposed Git's Windows CRLF conversion in the
source-manifest hash and was rejected before inference. Commit `410931f` accepts
exact bytes or CRLF-to-LF conversion only; model and runtime binary hashes remain
exact. The failed request and the subsequent direct-API preflight are retained
privately under the owner's ignored `local/live-answer-rehearsal/`.

This screen's live **Speed** path supports CPU settings. Model routing, GPU/NPU
answer comparisons and broad task-quality qualification remain separate work.
The QAIRT chart elsewhere in the frontend comes from a different recorded study.
