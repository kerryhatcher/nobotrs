# Rust ML Inference Crates for nobotrs

Research date: 2026-07-26.

## Scope

`nobotrs` needs local ML inference for two of its five detection methods:

1. **Fine-tuned classifier inference** — a single forward pass through a pretrained AI-text classifier (e.g. a DeBERTa-v3/RoBERTa model like `desklib/ai-text-detector-v1.01`) to get a human/AI probability.
2. **Zero-shot twin-model perplexity** (Binoculars / Fast-DetectGPT style) — running two similar-sized LLMs over the same text and computing a cross-perplexity ratio.

This document evaluates the Rust crates that could serve either workload: `candle`, `ort`, `tch-rs`, plus the supporting crates `hf-hub` and `llama-cpp-2`/GGUF tooling. Deterministic pattern-matching, stylometry, CLI/packaging, and architecture are covered by other research documents in this set — this file is scoped to ML inference only.

All version numbers, license strings, and dates below were pulled from the crates.io API (`https://crates.io/api/v1/crates/<name>`) and the GitHub API (`gh api repos/<org>/<repo>`) on 2026-07-26, not from training-data memory.

---

## candle (`candle-core`, `candle-transformers`)

- crates.io: [candle-core](https://crates.io/crates/candle-core), [candle-transformers](https://crates.io/crates/candle-transformers)
- docs.rs: [candle-transformers models index](https://docs.rs/candle-transformers/latest/candle_transformers/models/index.html)
- GitHub: [huggingface/candle](https://github.com/huggingface/candle)
- Current version: **0.11.0** (both crates, published together)
- License: **MIT OR Apache-2.0**
- Last publish: 2026-06-26 · Last commit (pushed_at): 2026-07-23
- Maintenance: actively maintained by Hugging Face. 20,731 GitHub stars, 1,673 forks, 836 open issues (high but proportionate to a large, actively-used ML framework; not a sign of abandonment). `candle-core` alone has ~6.4M crates.io downloads, `candle-transformers` ~2.7M.

**Capability summary.** Pure-Rust ML framework built by Hugging Face specifically to avoid a Python dependency in production. Backends: CPU (with optional Intel MKL), CUDA, cuDNN, Apple Metal/Accelerate. Ships quantization support (GGML-style q4k/q8k etc.) out of the box. `candle-transformers` includes native (not ONNX-converted) implementations of a large model catalog, and — directly relevant to workload 1 — a `debertav2` module. That module exposes `DebertaV2SeqClassificationModel`, `DebertaV2ContextPooler`, and `Id2Label`/`Label2Id` type aliases, i.e. a full DeBERTa-v2-architecture sequence-classification head, not just an encoder. Since DeBERTa-v3 (used by `desklib/ai-text-detector-v1.01`) reuses the DeBERTa-v2 model architecture in Hugging Face's own `transformers` library (v3 only changes the *pretraining* objective — replaced-token-detection instead of masked-LM — not the classification-time module graph), a v3 checkpoint is architecturally compatible with `candle-transformers`' `debertav2` classification model. This means the desklib classifier likely does **not** need an ONNX export step at all — it could be loaded natively via `candle` + safetensors weights pulled through `hf-hub`. This is a strong practical finding but should be verified empirically early in implementation (config field names, tokenizer compatibility, and any v3-specific quirks like the disentangled-attention position projection need to be checked against actual desklib weights before committing to this path).

For workload 2, `candle-transformers` also ships a native `falcon` module plus Llama, Mistral, Phi, StableLM, Gemma, Mixtral, and quantized (GGUF-compatible) variants — so a Binoculars-style twin-model perplexity computation (two forward passes, log-prob extraction, no generation needed) is directly supported architecture-wise, including with quantized weights to cut memory footprint.

**Pros:**
- Pure Rust, no libtorch/ONNX Runtime system dependency for the CPU/CUDA/Metal path — smallest install friction of the three options.
- Native model implementations (not just a generic graph executor), including a classification head that plausibly covers the exact target model.
- Built-in quantization for the twin-model workload, which is the difference between "needs a 7B-class GPU box" and "can plausibly run smaller pairs on CPU."
- Actively developed by an organization (Hugging Face) with obvious incentive to keep it current with new HF model releases.

**Cons:**
- Training is explicitly experimental; candle is inference-first (fine for nobotrs, which only needs inference).
- Smaller ecosystem than PyTorch/ONNX: "when you hit an error, you're reading source and opening GitHub issues," not searching Stack Overflow.
- Any *niche* architecture not already ported has to be implemented by hand — a real risk if the eventual desklib-compatible path turns out to need custom glue.
- Windows CUDA support reportedly lags Linux/macOS.

---

## ort (ONNX Runtime Rust bindings)

- crates.io: [ort](https://crates.io/crates/ort)
- docs.rs: [ort](https://docs.rs/ort)
- Guide: [ort.pyke.io](https://ort.pyke.io/)
- GitHub: [pykeio/ort](https://github.com/pykeio/ort)
- Current version: **2.0.0-rc.12** (release-candidate track; described by the maintainer as "production-ready, just not API-stable" — no 2.x stable tag yet as of this search). A `1.x` line (e.g. 1.16.3) also still exists on crates.io for consumers who want a stable API surface at the cost of an older ONNX Runtime version.
- License: **MIT OR Apache-2.0**
- Last publish: 2026-03-05 · Last commit (pushed_at): 2026-07-25
- Maintenance: 2,419 stars, 256 forks. GitHub API reported only 1 open issue at query time, which is unusually low for a project this size — plausibly aggressive issue-triage/closing rather than low engagement, given the very recent push date and ~14M crates.io downloads (highest of the three inference crates surveyed). Used in production by Twitter (home timeline recommendations) and bloop (semantic code search), per the crate's own docs.

**Capability summary.** A safe Rust wrapper around Microsoft's ONNX Runtime (targeting ORT 1.24 as of the rc.12 line). This is the standard path for "I have a HF classifier, I exported it to ONNX with `optimum`, now I want to run it fast in Rust." It is *not* a training or architecture-definition library — you bring a `.onnx` graph, `ort` runs it. That makes it a strong, low-risk fit for workload 1 (a single classifier forward pass) and a poor fit for workload 2 (Binoculars/Fast-DetectGPT need custom log-prob extraction and two coordinated models; while technically representable as ONNX graphs, LLM-scale autoregressive models are a much less common ONNX export target and the ecosystem tooling for this is thinner than for encoder-only classifiers).

Regarding system dependencies: `ort` offers three linking strategies via Cargo features. `download-binaries` (default) fetches prebuilt ONNX Runtime shared libraries from Microsoft at build time — no separate install step for the user, but it does mean a multi-hundred-MB binary blob gets pulled during `cargo build` and typically has to ship alongside (or be dynamically loadable next to) the final binary. `load-dynamic` uses `dlopen()` at runtime against a path set by `ORT_DYLIB_PATH`, avoiding a compile-time link dependency and shared-library version conflicts — recommended by the maintainer, but pushes the "where does libonnxruntime.so live" problem onto packaging. The `system` strategy links against an ONNX Runtime the user/packager installs themselves via `ORT_LIB_LOCATION`. None of these are "pure Rust, zero external binary" the way `candle`'s CPU path is — there is always an ONNX Runtime native library in the loop somewhere, just with flexibility about when/how it's obtained.

**Pros:**
- Most mature, most widely production-deployed of the three (highest download count, real named production users).
- Clean separation of concerns: model conversion (Python/optimum, outside nobotrs) vs. inference (Rust, in nobotrs) — a well-trodden path for exactly the "single classifier" workload.
- Multiple linking strategies give packaging flexibility (bundle vs. dynamic-load vs. system-provided).
- ONNX Runtime itself has broad hardware acceleration support (CUDA, TensorRT, CoreML, DirectML, etc.) if nobotrs ever wants GPU acceleration for the classifier.

**Cons:**
- API not yet stable at 2.x (rc track); teams wanting stability today are on the older 1.x line with an older ORT version.
- Always carries an ONNX Runtime native binary somewhere in the deployment — not a self-contained pure-Rust binary, which cuts against the "standalone Rust CLI" goal more than `candle`'s CPU path does.
- Not a natural fit for twin-LLM perplexity scoring; would require exporting/adapting generative LLMs to ONNX and hand-rolling log-prob extraction, which is a heavier lift than candle's native model code.
- Requires an upstream ONNX export step (via `optimum` or similar) as a prerequisite — that conversion pipeline lives outside nobotrs and outside Rust entirely.

---

## tch-rs (`tch`)

- crates.io: [tch](https://crates.io/crates/tch)
- GitHub: [LaurentMazare/tch-rs](https://github.com/LaurentMazare/tch-rs)
- Current version: **0.24.0**
- License: **MIT/Apache-2.0**
- Last publish: 2026-03-26 · Last commit (pushed_at): 2026-07-17
- Maintenance: 5,456 stars, 443 forks, 244 open issues, ~5.9M crates.io downloads. Actively maintained (same author, Laurent Mazare, also a longtime candle contributor).

**Capability summary.** Rust bindings to the actual PyTorch C++ API (libtorch), staying close to the original API surface rather than reimplementing model code natively. This means `tch-rs` can, in principle, run *any* PyTorch model — including a DeBERTa-v3 classifier or an LLM pair for perplexity scoring — without a conversion step, as long as you can express the forward pass in Rust/libtorch terms (or load a TorchScript-traced module, which is the more realistic path). It is architecturally the most flexible of the three: it does not depend on someone having ported the target architecture, it depends on libtorch being able to execute it.

**Install complexity is the key differentiator, and it is the highest of the three.** `tch-rs` requires the libtorch C++ library (currently targeting v2.11.0) to be present at build and run time. Options: a system-wide libtorch install, a manually-downloaded libtorch pointed to via `LIBTORCH`, reuse of an existing Python PyTorch install via `LIBTORCH_USE_PYTORCH=1`, or a `download-libtorch` Cargo feature that fetches a prebuilt binary automatically. Libtorch itself is large (typically several hundred MB to >2GB depending on CUDA build) and is a C++ shared-library dependency with its own ABI/version sensitivity — this is meaningfully heavier and more fragile for end-user distribution than `ort`'s ONNX Runtime binary or `candle`'s pure-Rust build.

**Pros:**
- Broadest model compatibility — no need for a native Rust port of the architecture (unlike candle) or an ONNX export (unlike ort), since it runs real PyTorch/libtorch.
- Mature, closely tracks upstream libtorch releases.
- Same maintainer lineage as candle gives some confidence in code quality/idioms.

**Cons:**
- Heaviest, most fragile install/build story of the three: a large C++ native dependency with version-matched ABI requirements, awkward for a "download one binary and run it" CLI distribution goal.
- Largest binary/dependency footprint by a clear margin.
- For a standalone CLI tool distributed to end users (vs. a controlled server environment), shipping or requiring libtorch is a significant UX and packaging burden compared to candle's zero-system-dependency CPU path.

---

## Supporting: llama-cpp-2 / GGUF path

- crates.io: [llama-cpp-2](https://crates.io/crates/llama-cpp-2) (safe wrapper) and [llama-cpp-sys-2](https://crates.io/crates/llama-cpp-sys-2) (raw bindings)
- docs.rs: [llama_cpp_2](https://docs.rs/llama-cpp-2)
- GitHub: [utilityai/llama-cpp-rs](https://github.com/utilityai/llama-cpp-rs)
- Current version: **0.1.152**
- License: **MIT OR Apache-2.0**
- Last publish: 2026-07-21 · Last commit (pushed_at): 2026-07-26 (same day as this research)
- Maintenance: 617 stars, 220 forks, 46 open issues, ~883K downloads. Actively maintained — it's described as powering production LLM workloads at utilityai, with a commit on the day of this search. Smaller community than candle/ort/tch-rs but clearly live.

**Capability summary.** A safe Rust wrapper that mimics llama.cpp's own API, giving direct access to GGUF-quantized model loading and inference (the same format/runtime used by Ollama, LM Studio, etc.). This is the most realistic route to running a Binoculars/Fast-DetectGPT-style twin-model pair on **consumer CPU hardware** without a GPU: GGUF quantization (4-bit/8-bit) shrinks a 7B model to a few GB of RAM and llama.cpp's CPU inference is heavily optimized. It does pull in the C/C++ llama.cpp codebase as a build-time dependency (via `llama-cpp-sys-2`, requiring a C++ toolchain/cmake to compile), which is a build-environment requirement but not a *runtime* system-library dependency the way libtorch/ONNX Runtime are — once compiled, the resulting binary is self-contained.

**Relevance to workload 2 model-pair sizing.** The literature does not settle on one canonical "small" pair. Binoculars' own paper uses Falcon-7B / Falcon-7B-Instruct (needs ~16GB VRAM per the existing nobots research notes; on CPU via GGUF q4 quantization this drops to roughly 4-5GB RAM per model, ~8-10GB for the pair — plausible on a modern laptop, not yet verified empirically). Fast-DetectGPT's own experiments used larger pairs for best accuracy (Llama3-8B/Llama3-8B-Instruct, falcon-7b/falcon-7b-instruct) but also evaluated smaller/cheaper scoring-model configurations, including GPT-J-6B paired with GPT-Neo-2.7B, and a GPT-Neo-2.7B scoring model with a T5-Small sampling model in some of its ablations — none of these are "tiny," but they establish that the method has been validated with sub-Falcon-7B model sizes in the original research, which is a reasonable starting point for a nobotrs "lightweight" twin-model mode. No source found describing a validated Binoculars/Fast-DetectGPT pair smaller than the ~2.7B range; going smaller (e.g. GPT-2-scale) would be an untested extrapolation, not a documented result.

**hf-hub for model acquisition (either path).**
- crates.io: [hf-hub](https://crates.io/crates/hf-hub) · docs.rs: [hf_hub](https://docs.rs/hf-hub/latest/hf_hub/) · GitHub: [huggingface/hf-hub](https://github.com/huggingface/hf-hub)
- Current version: **1.0.0**, license **Apache-2.0**, last publish 2026-07-10, last commit 2026-07-13. 312 stars, 24 open issues — smaller but official (Hugging Face-maintained) and heavily depended-on (~13M downloads, largely as a transitive dependency of `candle-examples`/`candle-transformers` consumers).
- Rust equivalent of the Python `huggingface_hub` client: typed repo/file operations, async by default with a `blocking` feature for sync use, supports the Xet high-performance transfer backend. This is the natural way for nobotrs to pull classifier weights or GGUF model files at first run rather than bundling multi-GB weights in the binary itself.

---

## Comparison table

| | candle | ort | tch-rs | llama-cpp-2 (GGUF) |
|---|---|---|---|---|
| Pure Rust vs. system libs | Pure Rust (CPU); optional CUDA/Metal | Needs ONNX Runtime native lib (bundled via download, dynamic-loaded, or system) | Needs libtorch (C++), large, version-sensitive | Needs C++ toolchain at **build** time only; self-contained binary at runtime |
| Model format | Native Rust model code (safetensors weights) | Pre-exported `.onnx` graphs | Native libtorch execution / TorchScript | GGUF-quantized models |
| Classifier-inference fit (workload 1) | Strong — native `debertav2` module w/ seq-classification head, plausible desklib compatibility | Strong — standard, well-trodden "export to ONNX, run with ort" path | Possible but heaviest install cost for a single classifier | Not a natural fit (llama.cpp targets causal LMs, not classification heads) |
| Twin-LLM-perplexity fit (workload 2) | Good — native Falcon/Llama/Mistral impls + built-in quantization | Weak — LLM ONNX export/log-prob extraction is a heavier, less common path | Good — full PyTorch model flexibility, but heavy runtime dependency | Strong — best CPU-viable path via GGUF quantization for consumer hardware |
| Binary/dependency footprint | Smallest (pure Rust CPU build) | Medium (one native lib, flexible linking) | Largest (libtorch, multi-hundred-MB to multi-GB) | Small at runtime; build-time needs cmake/C++ compiler |
| License | MIT OR Apache-2.0 | MIT OR Apache-2.0 | MIT/Apache-2.0 | MIT OR Apache-2.0 |
| Maintenance health | Very active (HF), 20.7k★, pushed 2026-07-23 | Very active, 2.4k★, pushed 2026-07-25, highest downloads | Active, 5.5k★, pushed 2026-07-17 | Active, 617★, pushed 2026-07-26 (day of query) |

All four are MIT/Apache-2.0-family licensed — no GPL/AGPL/copyleft concerns for any of them.

---

## Recommendation

**Workload 1 (fine-tuned classifier inference): lead with `candle`, keep `ort` as the documented fallback.**

`candle-transformers`' native `debertav2` module with a `DebertaV2SeqClassificationModel` is a near-exact architectural match for `desklib/ai-text-detector-v1.01` (a DeBERTa-v3-large classifier — v3 reuses the v2 model graph in HF `transformers`), and it avoids the ONNX export step, the ONNX Runtime native-library dependency, and the associated packaging complexity entirely. Combined with `hf-hub` for weight download, this is the leanest path to "standalone Rust binary, no system ML libraries." The risk is that this compatibility is inferred from architecture, not yet verified against the actual desklib checkpoint — this should be the first thing prototyped, before committing the architecture doc to it. If it doesn't load cleanly (config mismatches, tokenizer differences, or v3-specific attention quirks), `ort` is the well-proven fallback: export the same model to ONNX via `optimum` once, and run it with `ort`'s `load-dynamic` strategy, accepting the extra native-library packaging step in exchange for a battle-tested, widely-deployed inference path.

**Workload 2 (twin-model zero-shot perplexity): `candle` for a from-source/quantized-native path, `llama-cpp-2` (GGUF) as the pragmatic CPU-first option.**

Both are credible. `candle` keeps everything in the Rust/HF ecosystem (native Falcon/Llama/Mistral implementations, built-in GGML-style quantization, `hf-hub` for weight fetch) and is the more "native to this stack" choice if nobotrs is already using candle for workload 1 — sharing one inference framework across both workloads reduces total dependency surface. `llama-cpp-2` is the more pragmatic choice specifically for making this workload viable on a typical user's CPU-only laptop: GGUF 4-bit quantization is the most mature, widely-used compression path for exactly this class of problem, and llama.cpp's CPU kernels are more mature/optimized than candle's for pure-CPU workloads at time of writing. Given that Binoculars' own validated pair (Falcon-7B/Falcon-7B-Instruct) is memory-heavy even quantized, and that no smaller validated pair was found in the literature searched, this workload should be treated as the "optional, heavier" detection method regardless of crate choice — the crate decision affects packaging and CPU performance, not the fundamental hardware-cost tradeoff. Recommend prototyping with `candle` first (avoids introducing a second inference framework), falling back to `llama-cpp-2` if candle's CPU performance or quantization support for the chosen Falcon-class pair proves inadequate in practice.

**On feature-gating:** Cargo feature flags are a standard, well-supported mechanism for making heavy optional dependencies (`candle`, `ort`, `tch`, `llama-cpp-2`, and their transitive weight — think hundreds of MB of compiled code and, for `tch`, an external native library) opt-in per build, so a user who only wants deterministic + stylometric detection pays zero cost for them; this is a normal pattern used throughout the Rust ecosystem (including by `ort` and `candle` themselves for their own backend/acceleration options) and doesn't need further justification here — the architecture research covers the concrete feature-flag layout for nobotrs.

---

## Sources

- [candle-core on crates.io](https://crates.io/crates/candle-core) — fetched via crates.io API, 2026-07-26
- [candle-transformers on crates.io](https://crates.io/crates/candle-transformers) — fetched via crates.io API, 2026-07-26
- [huggingface/candle on GitHub](https://github.com/huggingface/candle) — fetched via GitHub API, 2026-07-26
- [candle-transformers models index (docs.rs)](https://docs.rs/candle-transformers/latest/candle_transformers/models/index.html) — fetched 2026-07-26
- [candle-transformers debertav2 module (docs.rs)](https://docs.rs/candle-transformers/latest/candle_transformers/models/debertav2/index.html) — fetched 2026-07-26
- [ort on crates.io](https://crates.io/crates/ort) — fetched via crates.io API, 2026-07-26
- [ort documentation site](https://ort.pyke.io/) — referenced via search, 2026-07-26
- [ort Cargo features guide](https://ort.pyke.io/setup/cargo-features) — referenced via search, 2026-07-26
- [ort Linking guide](https://ort.pyke.io/setup/linking) — referenced via search, 2026-07-26
- [pykeio/ort on GitHub](https://github.com/pykeio/ort) — fetched via GitHub API, 2026-07-26
- [tch on crates.io](https://crates.io/crates/tch) — fetched via crates.io API, 2026-07-26
- [LaurentMazare/tch-rs on GitHub](https://github.com/LaurentMazare/tch-rs) — fetched via GitHub API, 2026-07-26
- [llama-cpp-2 on crates.io](https://crates.io/crates/llama-cpp-2) — fetched via crates.io API, 2026-07-26
- [llama-cpp-2 on docs.rs](https://docs.rs/llama-cpp-2) — referenced via search, 2026-07-26
- [utilityai/llama-cpp-rs on GitHub](https://github.com/utilityai/llama-cpp-rs) — fetched via GitHub API, 2026-07-26
- [hf-hub on crates.io](https://crates.io/crates/hf-hub) — fetched via crates.io API, 2026-07-26
- [hf-hub on docs.rs](https://docs.rs/hf-hub/latest/hf_hub/) — referenced via search, 2026-07-26
- [huggingface/hf-hub on GitHub](https://github.com/huggingface/hf-hub) — fetched via GitHub API, 2026-07-26
- [guillaume-be/rust-bert on GitHub](https://github.com/guillaume-be/rust-bert) — fetched via GitHub API, 2026-07-26 (referenced as a possible alternative combining DeBERTa + optional ONNX support, but not recommended as primary since it depends on tch-rs/libtorch by default)
- [desklib/ai-text-detector-v1.01 on Hugging Face](https://huggingface.co/desklib/ai-text-detector-v1.01) — referenced via search, 2026-07-26 (confirms 430M-parameter DeBERTa-v3-large architecture)
- [Binoculars paper (arXiv 2401.12070)](https://arxiv.org/pdf/2401.12070) — referenced via search, 2026-07-26 (confirms Falcon-7B/Falcon-7B-Instruct as the default model pair)
- [Fast-DetectGPT GitHub repo](https://github.com/baoguangsheng/fast-detect-gpt) — referenced via search, 2026-07-26
- [Fast-DetectGPT paper (arXiv 2310.05130)](https://arxiv.org/pdf/2310.05130) — referenced via search, 2026-07-26 (confirms GPT-J-6B/GPT-Neo-2.7B and GPT-Neo-2.7B/T5-Small as smaller-than-default evaluated configurations)

**Note on candle/desklib native-loading claim:** the compatibility between candle's `debertav2` module and the desklib DeBERTa-v3-large checkpoint is an architectural inference from documented module capabilities (both target the same DeBERTa-v2-style model graph), not a confirmed working example found in search — no source was located showing someone has actually loaded `desklib/ai-text-detector-v1.01` weights into `candle`. This should be the first thing empirically verified in implementation, with `ort` + ONNX export as the fallback if it doesn't pan out.
