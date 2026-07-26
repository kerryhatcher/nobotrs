# nobotrs `perplexity` Tier Implementation Plan (STUB)

> **STUB — not yet detailed.** This is a task outline, not a ready-to-execute plan: no file/interface contracts, no TDD steps, no code. Expand it into full task detail (per `superpowers:writing-plans`) before dispatching it for execution. Depends on `2026-07-26-nobotrs-core-default-build.md` being implemented first.

**Goal:** Add the `perplexity` Cargo feature — a twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style), `MlPerplexity` family, **non-voting/experimental in v1** (spec §2.2, §7 item 4).

**Source spec sections:** §2.2 (`perplexity` tier row), §7 item 4 (why it's non-voting: GGUF quantization shifts the logit distributions the published calibration threshold was tuned against, no refit data yet), §9 item 1 (license check for whichever model pair is chosen), §9 item 2 (checksum verification, shared requirement with `classifier`).

## Anticipated task outline (to expand later)

1. Select and validate a memory-feasible model pair (spec notes validated pairs run ~8-10GB RAM; research found no smaller validated pair) — confirm this is still acceptable before building against it.
2. **Model checkpoint license review** (spec §9 item 1) for whichever pair is chosen.
3. Model download/caching via `hf-hub` or `llama-cpp-2`'s GGUF loading path; **checksum verification against a pinned hash** before load (spec §9 item 2, shared requirement with `classifier`).
4. `MlPerplexity` backend implementing `DetectorBackend`, `family() -> SignalFamily::MlPerplexity`, **always non-voting** — reports the raw cross-perplexity ratio as evidence only, never contributes to quorum (spec §2.4, §7 item 4).
5. **Unmissable non-voting UX requirement** (spec §7 item 4, stated as a hard UX requirement, not a footnote): both `nobotrs detect` and `nobotrs config` output must plainly state "Perplexity tier: experimental, evidence-only, does not affect verdicts" whenever the tier is enabled — write a test asserting this string (or equivalent) appears in output when `perplexity` is active.
6. GGUF quantization numerics validation — confirm the ratio produced by the quantized model pair is stable/reproducible enough to report as evidence at all, even non-voting.
7. Integration tests gated behind the `perplexity` feature flag, not part of default `cargo test` (spec §8).
8. Wire into the `full` meta-feature alongside `classifier` (spec §2.2).
