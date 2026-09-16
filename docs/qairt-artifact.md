# QAIRT artifact evidence

## Reproducible local inspection

```sh
python scripts/inspect_model_artifact.py /path/to/bundle
python scripts/inspect_model_artifact.py /path/to/bundle --expected-manifest local/artifact-manifests/PREVIOUS.json --output local/artifact-manifests/recheck.json
```

The command inventories every regular file with canonical relative POSIX paths, byte lengths, and SHA-256 hashes. Its inventory digest hashes canonical JSON of that mapping; it is **not interchangeable** with the existing evaluator's model hash. No timestamps or machine paths enter the reproducible inventory. It also extracts explicitly present configuration fields with their source filename and field path. Unknown quantization remains `null`; names such as `W4A16` or `Q4_0` are not parsed as evidence.

The default output is an exclusively created file under ignored `local/artifact-manifests/`. Existing files, output within the input bundle, symlinks/junctions, missing declared shards, and references escaping the bundle are rejected. Identical repeat inspection therefore requires a new explicit output filename if its default manifest already exists. `--expected-manifest` checks the inventory and digest without changing either artifact. JSON configuration reads accept UTF-8 BOMs and reject ambiguous duplicate keys or nonfinite values.

Inspection hashes files twice to detect ordinary concurrent changes. Keep the bundle quiescent during inspection. This is a file/configuration inventory, not proof that a driver loaded those bytes or that hardware executed a particular graph.

## Facts already retained in repository evidence

These are observations recorded by earlier runs, **not new hardware validation**:

- [Recorded runtime configuration](../eval/results/candidate_qairt-native-06-v1_runtime.json) retains `dialog.context.size=4096`, vocabulary 151936, BOS 151643 and EOS 151645.
- Its bundle sampler declares `seed=42`, `temp=0.8`, `top-k=40`, `top-p=0.95`. These are bundle defaults, not a claim that every request used those effective values. See [sampling provenance](qairt-sampling.md).
- It declares `part1_of_2.bin` and `part2_of_2.bin`, `tokenizer.json`, engine `n-threads=3`, backend `QnnHtp`, and `htp_backend_ext_config.json`.
- Retained HTP extension metadata declares `soc_model=60`, `dsp_arch=v73`, core 0, `perf_profile=burst`, RPC control latency 100, shared-buffer memory and weight sharing enabled. These are configuration declarations, not utilization measurements.
- The [initialization excerpt](../benchmarks/results/qairt-smoke-01/initialization-excerpt.txt) reports HTP v73, two shards, three context-length variants `[512,1024,4096]`, vocabulary 151936 and hidden dimension 1024. It does not establish supported runtime resizing or supply a per-graph execution trace.
- The [historical run manifest](../eval/results/candidate_qairt-native-06-v1_manifest.json) describes the deployment as an official W4A16 mixed-precision artifact. That manifest description is distinct from quantization derived from compiled bytes; the new inspector makes no such derivation.

## What remains unknown

Actual graph dispatch, effective sampler behavior, compiled-artifact internals, runtime context behavior, and candidate stop enforcement require Snapdragon validation. An inventory does not create a current correctness or energy baseline. Preserve historical reports and their fingerprints; use fresh comparable runs after implementation changes.
