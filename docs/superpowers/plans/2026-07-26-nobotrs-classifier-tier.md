# nobotrs `classifier` Tier Implementation Plan (STUB)

> **STUB — not yet detailed.** This is a task outline, not a ready-to-execute plan: no file/interface contracts, no TDD steps, no code. Expand it into full task detail (per `superpowers:writing-plans`) before dispatching it for execution. Depends on `2026-07-26-nobotrs-core-default-build.md` being implemented first (the `DetectorBackend` trait, `SignalFamily`, `ScoreOutcome`, `Score`/`Evidence` types, and CLI skeleton it builds on).

**Goal:** Add the `classifier` Cargo feature — a single-pass fine-tuned AI-text classifier (`MlClassifier`, voting family) via `candle-transformers::debertav2`, per spec §2.2's `classifier` tier row.

**Source spec sections:** §2.2 (`classifier` tier row), §7 item 4 is perplexity not this — see §9 item 1 (candle + `desklib/ai-text-detector-v1.01` prototype, checkpoint license check), §9 item 2 (checksum verification), §9 item 5 (candle/ort/llama-cpp-2 fallback order tested per platform in CI), §2.4 (the `MlClassifier` solo-quorum calibration question — not resolved by default).

## Anticipated task outline (to expand later)

1. **Spike: load `desklib/ai-text-detector-v1.01` into `candle-transformers::debertav2`.** This is explicitly flagged in spec §9 item 1 as unconfirmed — do this before committing further plan detail, since a failed spike changes the whole tier's design (fallback to `ort` + ONNX export).
2. **Checkpoint license review** (spec §9 item 1) — verify the specific model weights' license permits nobotrs's intended use, separate from the Rust crates' licenses. Do this alongside the spike, not after.
3. Model download + caching via `hf-hub`, wired to `Availability::NeedsDownload` → `Ready` transition, surfaced through `nobotrs config`.
4. **Checksum verification** (spec §9 item 2): downloaded weights verified against a pinned hash before load, for both this tier and the future `perplexity` tier.
5. `MlClassifier` backend implementing `DetectorBackend`, `family() -> SignalFamily::MlClassifier`, voting.
6. Concurrency model decision for `scan <dir>` running `classifier` across files in parallel (spec §2.1: per-thread model instances vs. mutex vs. dedicated inference thread — this spec does not prescribe one, implementation planning must).
7. Hang/crash containment for the FFI boundary (spec §2.1): worker-thread-abandon vs. subprocess-kill strategy for a genuine hang; `catch_unwind` cannot intercept an FFI-side segfault, so input validation is the primary mitigation, not exception handling.
8. `full` meta-feature wiring (enables `classifier` + `perplexity`, explicitly excludes `api-clients` per spec §2.2).
9. Solo-quorum calibration flag for `MlClassifier` (spec §2.4) — gated on §8.1's evaluation corpus existing; do not implement an override without it.
10. Fallback preference order test matrix across `candle`/`ort` per platform (spec §9 item 5) — a distinct CI job per platform × backend-path combination.
11. Integration tests gated behind the `classifier` feature flag, not part of default `cargo test` (spec §8).
