# Model coverage catalog: scope, sources and selection

Date: September 15, 2026. Target device: Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB RAM, Windows ARM64, GenieX v0.6.1 with the llama.cpp and QAIRT plugins. Machine-readable entries live in [configs/model-catalog.json](../configs/model-catalog.json); this page records the reasoning and the rules the loader enforces.

## What the catalog is and is not

The catalog is an offline planning artifact. `turbo/catalog.py` (stdlib only) loads, validates and filters entries; nothing in that path starts inference, spawns a runtime or contacts the network. The CLI reads a local file and prints rows: `python3 turbo/catalog.py --state downloaded` (add `--json` for machine output).

"unverified" is the maximum backend status any entry may carry today. It means: a named official source for the pinned file lists the model for that runtime version (typically the GenieX v0.6.1 `bench-models.json` QDC matrix), but the file has not been measured on our laptop. Nothing in the catalog claims hardware testing. NPU entries additionally require on-device dispatch diagnostics before "supported"; a requested NPU flag alone is not evidence, per [docs/research.md](research.md). A QAIRT "supported" would further require the bundle to match chipset and compiled context. The validator rejects "supported" outright until a measurement justifies it.

## Pinned sources

Every entry records the official model card, the quantization repo, the HF revision hash, per-file SHA-256 (from HF LFS metadata), exact bytes and license. Sizes and hashes come from the HF API at catalog-build time; a mismatch on download invalidates the row.

## Entries and why they were selected

**Qwen3-0.6B Q4_0 (downloaded, 382,156,480 B).** The actual measured weights are from `unsloth/Qwen3-0.6B-GGUF`, revision `50968a4468ef4233ed78cd7c3de230dd1d61a56b`, SHA-256 `33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb`. CPU/GPU/NPU/hybrid completed; benchmark manifests preserve the evidence. Secretary tool quality remains separate. This is not the different ggml-org blob in the upstream benchmark matrix.

**Qwen3-1.7B Q4_0 (downloading, 1,056,782,912 B).** The parent task is fetching it; hash matches unsloth/Qwen3-1.7B-GGUF at revision `d7f544e`, the repo the v0.6.1 bench matrix pins for this tier. Instruction-tuned. No duplicate download.

**Qwen3-4B-Instruct-2507 Q4_0 (downloading, 2,375,773,280 B).** Same pattern: unsloth repo, revision `a06e946`, hash verified against the HF API; pinned cpu/npu in the v0.6.1 bench matrix. Instruction-tuned (non-thinking 2507 refresh).

**SmolLM2-360M-Instruct Q8_0 (candidate, 386,404,992 B).** The very-small dense instruction slot. There is no official Q4_0 GGUF: the HuggingFaceTB GGUF repo publishes Q8_0 only, so Q8_0 is what the catalog pins. Instruct here means SFT + DPO per the model card; function calling is documented for the 1.7B sibling, so this row is instruction, bench-only for tool work until measured. GGUF header architecture reads `llama` (SmolLM2 reuses the Llama arch in GGUF), read from the repo metadata rather than assumed.

**IBM Granite 4.0 H-Tiny Q4_K_M (candidate, 4,230,976,352 B).** The hybrid/Mamba-family slot. The exact GGUF architecture was read from the file KV header (first MB of the published Q4_0 blob), not inferred from the name: `granitehybrid`, the Mamba2 + attention hybrid - distinct from `granite`, the arch of the dense 4.0 1B/micro. H-Tiny is a 7B instruct model with documented tool-calling format. Largest candidate; fits 32 GB RAM but leaves less headroom than the 4B dense.

**Qwen3-VL-4B-Instruct Q4_0 + mmproj F16 (candidate, 3,211,955,136 B total).** The multimodal GGUF slot, recorded as a model+projector pair with separate hashes; validation rejects a multimodal GGUF row without both files. Listed (cpu/npu) in the v0.6.1 bench matrix with exactly this unsloth URL pair, which is why unsloth is pinned over Qwen's own GGUF repo (Q4_K_M/Q8_0 only, no Q4_0).

**Qwen3-VL-4B-Instruct QAIRT w4a16 (candidate, 3,034,262,089 B zip).** The precompiled Snapdragon X Elite bundle, already cached from the public QAI Hub bucket (on the target-PC side, not this Mac). `requires_projector: false` because the projector is compiled into the bundle; context length stays null rather than guessed, since the bundle metadata does not publish it. QAIRT backend status is "unverified" pending on-device dispatch diagnostics; the llama.cpp backend does not apply to this artifact form.

**Gemma 3 270M IT (candidate, third-party conversion).** Google publishes no official GGUF: its HF Gemma GGUF repos carry Q8_0/BF16 only, and the official small quantized artifact is a LiteRT `.task`/`.litertlm` bundle, which GenieX does not load. The only Q4_0 GGUF is a third-party (unsloth) conversion under the Gemma license. Third-party conversion is permitted with provenance; model license and compatibility still need verification.

## Recommended first additional download

SmolLM2-360M-Instruct Q8_0 - 386,404,992 bytes (~369 MiB, under the ~400 MB budget). The Gemma 270M alternative would be smaller but is unavailable as an official GGUF Q4_0; the Granite hybrid is ~4.2 GB and better taken later as a deliberate large fetch.

```
curl -L -o smollm2-360m-instruct-q8_0.gguf \
  "https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/593b5a2e04c8f3e4ee880263f93e0bd2901ad47f/smollm2-360m-instruct-q8_0.gguf"
shasum -a 256 smollm2-360m-instruct-q8_0.gguf
# expected: 48ab3034d0dd401fbc721eb1df3217902fee7dab9078992d66431f09b7750201
```

## Rules the loader enforces

- Any number of registered entries; unique ids; `kind` in {instruction, base, multimodal}; declared `total_bytes` must equal the sum of pinned file sizes.
- Every entry carries `source` (model card, quant repo, revision, files with sha256+bytes) and `backend_support` keyed `runtime@version`.
- "supported" is rejected in committed data until a runtime version is measured on the target laptop; tests fail the catalog if anyone sets it.
- Multimodal GGUF entries must pin two files (model + projector); QAIRT bundles pin one archive and may set `requires_projector: false`.
