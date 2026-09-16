# Native accelerator and routing rehearsals

Public answer demonstrations on the Latitude, through clean native commits `5434ec1` and `775bcea`. These are not frozen Secretary evaluations or controlled speedup trials. The frontend UI extension was not involved in these API rehearsals.

| Attempt | Result | Selected lane | Lane time (s) | Decode (tok/s) |
| --- | --- | --- | ---: | ---: |
| auto-default-1 | completed | qairt_npu | 13.159 | 83.32 |
| auto-default-2 | completed | qairt_npu | 5.984 | 83.14 |
| gpu-after-qairt-failure | failed | not reached | — | — |
| gpu-sdk-cleanup | completed | llama_cpp_gpu | 3.616 | 72.14 |
| htp-after-qairt | completed | llama_cpp_htp | 1.777 | 37.55 |

Lane time includes model creation, generation and destruction; pair time also includes identity checks, prior model unload and (from `775bcea`) SDK cleanup. No energy, utilization or answer-quality score is fabricated. Actual text, output-token count, TTFT, prefill, sampler, runtime binding, model hash and resolved backend are retained in every result.

**Failures matter:** the first QAIRT answer incorrectly says local AI requires the internet. The subsequent GPU pair failed in its default CPU lane with a model-load error; logs identified an HTP session-open failure after QAIRT. Commit `775bcea` deinitializes the SDK between jobs. A subsequent QAIRT → CPU/HTP sequence completed without that load failure. This single sequence is a regression rehearsal, not a reliability guarantee.

`auto-default-2` is a second default-sampler QAIRT run, despite its request ID containing `greedy`. The intended sampler deployment did not take place before that request. Its recorded application commit and generation fields are authoritative. The actual negative-temperature sampler change is in `d630669`, outside this evidence set.

QAIRT is a separate `w4a16` bundle declaration; GPU/HTP use the pinned Q4_0 GGUF. The registered-route policy is experimental and does not claim a speed/quality optimum. Resolution identifies NPU, HTP0 and GPUOpenCL; `dispatch_verified` remains false, with no utilization meter.

All five native attempts are included, including the failed job and the incorrect answer. JSON files preserve the serialized API responses; `publication.json` binds their bytes. Private client paths, SSH details and service configuration are omitted.

Reproduce on an exclusively available gateway from a clean checkout:

```sh
python scripts/demo_backend_routing.py --base http://127.0.0.1:8083 --case auto-quick --output local/new-unique-run
python scripts/demo_backend_routing.py --base http://127.0.0.1:8083 --case gpu --output local/another-unique-run
python scripts/demo_backend_routing.py --base http://127.0.0.1:8083 --case npu --output local/third-unique-run
```

Choose the matching source commit and private registered artifacts to reproduce its settings. Later code explicitly changes the QAIRT demo sampler and must be treated as a new configuration.
