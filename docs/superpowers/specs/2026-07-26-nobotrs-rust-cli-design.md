# nobotrs: Rust CLI for AI-text detection — design spec

**Status:** Draft, pending user review
**Date:** 2026-07-26
**Research basis:** `docs/research/00-consolidated-summary.md` and its eight source reports, plus prior art at `/mnt/storage/grimoire/research/ai-text-detection-2026/` and `/mnt/storage/grimoire/research/open-plugins-spec/`.

## 1. Overview

`nobotrs` is a Rust CLI that detects AI-generated text and lints prose for AI-writing "tells." It is a spiritual full port of the existing Python Claude Code plugin `nobots` (`/home/kwhatcher/projects/nobots`), covering both its detection side and its humanize-writing side — but the humanize side becomes lint-only (flag + suggest, never auto-rewrite), since a standalone Rust binary has no LLM in the loop to steer prose the way nobots' Claude-integrated skill does.

It ships two ways:
1. A standalone, cross-platform Rust binary, installable via `cargo install`, a GitHub Release download, or Homebrew.
2. An Agent Plugins Specification–conformant plugin (the spec formerly known as "Open Plugins," confirmed rebranded as of this research) wrapping that binary, so it works across Claude Code, and any other conformant harness, not just one vendor.

### Goals
- Local-first, offline-capable detection with no mandatory network calls or API keys.
- A spectrum of detection strength: instant deterministic pattern-matching up through heavy local ML, plus optional external commercial APIs, all behind one consistent interface.
- Line-anchored, evidence-backed output — a confidence tier and reasons, never a bare yes/no verdict (carried forward from nobots' existing philosophy).
- A lean default build: a user who only wants pattern + stylometric detection should not need to download any ML model or heavy dependency.

### Non-goals (v1)
- Text generation or auto-rewriting of any kind. `lint` only flags and suggests; it never edits files.
- Full feature parity with `nobots`' `deep_stylometry.py` on dependency-parse-dependent features (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence). Research found **no viable pure-Rust path** for dependency parsing at all — this is a hard ecosystem gap, not a scoping preference. See §7.
- Bundling prebuilt binaries inside the plugin repository itself. See §6.

## 2. Detection architecture

### 2.1 The `DetectorBackend` trait

A single trait unifies all detection methods:

```
trait DetectorBackend {
    fn name(&self) -> &str;
    fn score(&self, text: &str) -> Result<Score>;
}
```

Each backend is an independent, pluggable implementation. Heavy backends are gated behind Cargo feature flags so the default build stays small (precedent: `sccache`'s per-storage-backend feature gating, confirmed as established Rust practice in research report 05).

### 2.2 The five backend tiers

| Tier | Feature flag | Default? | What it does | Key crates |
|---|---|---|---|---|
| **deterministic** | *(always on)* | Yes | Exact tell-word / tell-phrase matching, ported from `check_ai_tells.py`'s word and phrase lists | `aho-corasick` (tell-words, linear time at scale), `regex` (tell-phrases with wildcards), `unicode-segmentation` (sentence/word boundaries) |
| **stylometric** | *(always on)* | Yes | Burstiness (sentence-length stdev/mean), lexical diversity (hand-rolled MTLD), readability (hand-rolled Flesch-Kincaid — see below), compression-ratio perplexity proxy, entropy-per-token | `unicode-segmentation`, `statrs`, `xz` (pure-Rust LZMA) |
| **classifier** | `classifier` | No | Single-pass fine-tuned AI-text classifier inference (DeBERTa-v3-style) | `candle` + `candle-transformers::debertav2` (confirmed to exist and match this use case); `ort` (ONNX Runtime) as documented fallback |
| **perplexity** | `perplexity` | No | Twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style) | `candle` or `llama-cpp-2` (GGUF quantization) |
| **api** | `api-clients` | No | Optional external commercial detector calls, user-supplied API key required | `reqwest` (`blocking` feature), one client module per vendor (Sapling, GPTZero, Copyleaks, Pangram) |

`classifier` and `perplexity` are separate flags (a user can enable one without the other); `api-clients` is one shared flag gating all four vendor clients rather than one flag per vendor, since they share the same `reqwest` dependency and trait shape.

A `full` meta-feature enables all five tiers for users who want maximum coverage in one build.

### 2.3 `Score` — the common result type

```
struct Score {
    backend: String,
    human_probability: f32,   // 0.0 (certainly AI) .. 1.0 (certainly human)
    confidence: ConfidenceTier, // Low | Medium | High
    evidence: Vec<Evidence>,   // line/offset-anchored where applicable
}
```

`human_probability` is the canonical continuous representation. Pangram's API returns continuous fractions natively; the other three commercial vendors and the deterministic/stylometric backends return coarser labels or thresholds, which map onto fraction *bands* rather than exact points — deliberately chosen so no backend's precision is silently lost on the way in.

### 2.4 Ensemble aggregation

A top-level `detect` command runs every enabled backend and combines their `Score`s using the same **quorum rule** `check_ai_tells.py` already uses: a verdict only fires when a minimum number of *independent signal families* agree (e.g. vocabulary + statistical + a third), not when a single noisy channel crosses a threshold alone. This is a deliberate carry-forward from the Python implementation's own documented lesson (an earlier "any one family over threshold" rule produced false positives). Starting default: `QUORUM = 2`, matching the Python constant — tunable via config, not hardcoded, since a 5-backend Rust tool has more signal families available than the 3-family Python hook did and may warrant retuning once real data is in.

## 3. CLI surface

```
nobotrs detect <path|--stdin>       # score a file or stdin, ensemble verdict + confidence tier
nobotrs lint <path>                 # line-anchored tells report: word/phrase hits + stylometric flags + suggested fixes
nobotrs scan <dir>                  # batch lint across a directory (e.g. CI use)
nobotrs config                      # manage API keys, model downloads, enabled backends
```

- Argument parsing: `clap` (derive API).
- Human output: colored terminal via `owo-colors` (respects `NO_COLOR`).
- Machine output: `--format json` via `serde`/`serde_json`, for CI/scripting.
- Exit codes follow standard linter convention (0 = clean, non-zero = tells found) so `scan` composes in CI pipelines.

## 4. Configuration and secrets

- Config file: `~/.config/nobotrs/config.toml` (via the `directories` crate for cross-platform path resolution), permissions tightened to `0600` on Unix.
- Precedence for API keys: environment variable → config file → optional OS keychain via the `keyring` crate (opt-in hardening, not required). This mirrors the precedence pattern used by tools like `gh` and `aws-cli`.
- No commercial API is ever called without an explicit key configured for that specific vendor — enabling the `api-clients` feature at build time does not itself send any data anywhere.

## 5. Packaging and distribution

- **Release pipeline:** `cargo-dist` builds and publishes per-platform binaries (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64) to GitHub Releases, auto-generates a Homebrew tap formula, and publishes to crates.io on tag push.
- **Binary size discipline:** default build (deterministic + stylometric only) targets roughly 10MB; `classifier`/`perplexity` features add candle (~50-80MB) or ONNX Runtime (~100-150MB) — these are documented as separate, explicit install paths, not silently bundled into a bloated default.

## 6. Plugin packaging (Agent Plugins Specification)

- Manifest at `.plugin/plugin.json` (generic) with a `.claude-plugin/plugin.json` vendor copy for Claude Code's own discovery path, per the spec's documented vendor-precedence rule.
- `skills/detect-ai-writing/SKILL.md` — portable across any conformant harness.
- `hooks/hooks.json` — a `PostToolUse` hook wiring the ambient scan-on-write UX. **This component is Claude-Code-only in practice** (OpenCode and Pi use their own native JS/TS event systems rather than consuming `hooks.json`) — the same caveat nobots' own README already documents for its Python hook, carried forward rather than newly introduced.
- `bin/nobotrs` — a thin wrapper script, **not a bundled binary**. It searches (in order): an env var override, `PATH`, well-known install directories; on failure it prints an actionable install message (`cargo install` / `brew install` / direct download link). No plugin repo in the ecosystem was found bundling actual per-platform binaries in-repo — the two real examples found (`nab`, `genasis`) both locate-or-download instead. Claude Code has no `postInstall` hook to lean on for automatic fetch-on-install (the relevant feature request, anthropics/claude-code#9394, is closed as not-planned), so "locate or fail with clear instructions" is the v1 behavior; an automatic-download wrapper is a plausible v2 addition once the binary is actually published via `cargo-dist`.

## 7. Explicit v1 scope-outs and known gaps

These are carried in the design deliberately, not silently dropped:

1. **Dependency-parse-dependent stylometric features** (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence). No pure-Rust dependency parser exists anywhere in the ecosystem (confirmed by dedicated research, not just "none found easily"). Out of scope for v1. A future option, not committed to: an optional Python sidecar shelling out to the existing `deep_stylometry.py`, degrading gracefully when absent.
2. **POS-tag-dependent features** (POS proportions, function/content-word ratio, hedges, amplifiers, nominalizations). The only real pure-Rust option (`postagger.rs`) is unproven/low-maintenance; the higher-confidence option (`rust-bert`'s MobileBERT tagger) only becomes "free" if `tch-rs` is already a dependency for other reasons. Deferred; revisit once the `classifier` tier's ML dependency choice is settled empirically.
3. **`stylometry` (ian-nai/rust_stylometry) license** — flagged as a direct dependency candidate for classic authorship-analysis statistics, but its license was not independently confirmed in research. Must be verified before it is actually added as a dependency.
4. **Any text generation or auto-rewrite capability.** Confirmed out of scope per product decision — lint-only.

## 8. Testing strategy

- Unit tests per backend against known-AI and known-human text fixtures (the existing `nobots` rubric and any of its test fixtures are a starting corpus).
- The quorum-aggregation logic gets dedicated tests for its false-positive-avoidance behavior (the specific bug class it was designed to prevent in the Python version).
- API-client backends are tested against mocked HTTP responses — no live network calls in the test suite, no requirement for real API keys to run `cargo test`.
- `classifier` and `perplexity` backends need a smaller, separate integration-test tier gated behind their own feature flags, since they require model downloads and real compute — not part of the default `cargo test` run.

## 9. Key open items carried into implementation planning

These are empirical or due-diligence items the plan should sequence early, since they affect architecture decisions downstream:

1. **Prototype candle + `desklib/ai-text-detector-v1.01`** as the first concrete step of the `classifier` tier — the `debertav2` module's existence is confirmed, but nobody has been found to have actually loaded that specific checkpoint into it. `ort` + ONNX export is the documented fallback if it doesn't work cleanly.
2. **Confirm `stylometry` crate's license** before depending on it.
3. **Validate `postagger.rs` accuracy** against a labeled sample before trusting it in any verdict, if/when POS features are picked back up.

## 10. Recommended dependency stack

See `docs/research/00-consolidated-summary.md` § "Recommended stack" for the full, license-verified table. All selected crates are MIT/Apache-2.0/Unlicense family with one correction already applied: `rust_readability` (GPL-3.0-or-later) is excluded; Flesch-Kincaid is hand-rolled instead.
