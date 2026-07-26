# Alignment Review: nobotrs Spec vs. Product Decisions
**Reviewer:** Haiku agent  
**Date:** 2026-07-26  
**Scope:** Faithfulness check — do the 6 explicit product decisions appear accurately in the design spec?

---

## 1. Full Rust port of `nobots` covering BOTH detection AND humanization (humanization scoped to LINT-ONLY)

**Decision restated:** The project ports nobots fully but shifts humanization to lint-only (flag + suggest fixes, never auto-rewrite text, no text-generation capability).

**Spec quotes:**

> `nobotrs` is a Rust CLI that detects AI-generated text and lints prose for AI-writing "tells." It is a spiritual full port of the existing Python Claude Code plugin `nobots` (`/home/kwhatcher/projects/nobots`), covering both its detection side and its humanize-writing side — but the humanize side becomes lint-only (flag + suggest, never auto-rewrite), since a standalone Rust binary has no LLM in the loop to steer prose the way nobots' Claude-integrated skill does.  
> — § 1, Overview (lines 9–10)

> Text generation or auto-rewriting of any kind. `lint` only flags and suggests; it never edits files.  
> — § 1, Non-goals (v1) (line 22)

> `nobotrs lint <path>                 # line-anchored tells report: word/phrase hits + stylometric flags + suggested fixes`  
> — § 3, CLI surface (line 76)

**Verdict:** ✅ **Fully aligned.** The spec explicitly states the full port scope, the shift to lint-only for humanization, and the absence of auto-rewrite or text-generation capability. The language matches the decision intent precisely.

---

## 2. All three ML detection tiers in scope (deterministic + stylometric, local fine-tuned classifier, local zero-shot twin-model perplexity)

**Decision restated:** The v1 release includes all three distinct tiers: (a) pattern/statistical methods (deterministic + stylometric), (b) a local fine-tuned classifier, and (c) a local zero-shot twin-model perplexity method (Binoculars/Fast-DetectGPT style). None are deferred or omitted.

**Spec quotes:**

| Tier | Feature flag | Default? | What it does |
|---|---|---|---|
| **deterministic** | *(always on)* | Yes | Exact tell-word / tell-phrase matching, ported from `check_ai_tells.py`'s word and phrase lists |
| **stylometric** | *(always on)* | Yes | Burstiness (sentence-length stdev/mean), lexical diversity (hand-rolled MTLD), readability (hand-rolled Flesch-Kincaid), compression-ratio perplexity proxy, entropy-per-token |
| **classifier** | `classifier` | No | Single-pass fine-tuned AI-text classifier inference (DeBERTa-v3-style) |
| **perplexity** | `perplexity` | No | Twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style) |

> A `full` meta-feature enables all five tiers for users who want maximum coverage in one build.  
> — § 2.2, The five backend tiers (line 53)

**Verdict:** ✅ **Fully aligned.** All three tiers are explicitly listed in the table with their detection methodologies named directly (deterministic, stylometric, classifier, perplexity). The spec does not hedge these as "future" or defer any to v2.

---

## 3. External commercial detection APIs supported as OPTIONAL PLUGGABLE backends (opt-in only, no default-on, no unauthenticated external calls)

**Decision restated:** Commercial APIs (Sapling, GPTZero, Copyleaks, Pangram style) are pluggable optional backends. Opt-in only: no commercial API fires unless the user explicitly configures that vendor's API key. Enabling the feature at build time does not itself enable API calls or send data anywhere.

**Spec quotes:**

| **api** | `api-clients` | No | Optional external commercial detector calls, user-supplied API key required |  
> — § 2.2, The five backend tiers (line 49)

> `api-clients` is one shared flag gating all four vendor clients rather than one flag per vendor, since they share the same `reqwest` dependency and trait shape.  
> — § 2.2 (line 51)

> Precedence for API keys: environment variable → config file → optional OS keychain via the `keyring` crate (opt-in hardening, not required). This mirrors the precedence pattern used by tools like `gh` and `aws-cli`.  
> No commercial API is ever called without an explicit key configured for that specific vendor — enabling the `api-clients` feature at build time does not itself send any data anywhere.  
> — § 4, Configuration and secrets (lines 89–90)

**Verdict:** ✅ **Fully aligned.** The spec names the four vendors (Sapling, GPTZero, Copyleaks, Pangram), gates them behind a single `api-clients` feature flag (default: No / opt-in only), and explicitly states that feature-gating alone does not trigger API calls. The spec uses the exact phrase "user-supplied API key required."

---

## 4. Ships as BOTH standalone CLI binary AND an Agent Plugins Specification–conformant plugin (not Claude-Code-specific, works across multiple harnesses)

**Decision restated:** Two distribution vectors: (a) standalone cross-platform CLI binary via cargo/Homebrew/GitHub Releases, and (b) a plugin that conforms to the Agent Plugins Specification (not the Claude Code plugin spec), so it works across Claude Code and other conformant harnesses, not vendor-locked to a single platform.

**Spec quotes:**

> It ships two ways:
> 1. A standalone, cross-platform Rust binary, installable via `cargo install`, a GitHub Release download, or Homebrew.
> 2. An Agent Plugins Specification–conformant plugin (the spec formerly known as "Open Plugins," confirmed rebranded as of this research) wrapping that binary, so it works across Claude Code, and any other conformant harness, not just one vendor.  
> — § 1, Overview (lines 11–13)

> Manifest at `.plugin/plugin.json` (generic) with a `.claude-plugin/plugin.json` vendor copy for Claude Code's own discovery path, per the spec's documented vendor-precedence rule.  
> `skills/detect-ai-writing/SKILL.md` — portable across any conformant harness.  
> — § 6, Plugin packaging (lines 99–100)

> **This component is Claude-Code-only in practice** (OpenCode and Pi use their own native JS/TS event systems rather than consuming `hooks.json`) — the same caveat nobots' own README already documents for its Python hook, carried forward rather than newly introduced.  
> — § 6, Plugin packaging (line 101)

**Verdict:** ✅ **Fully aligned.** The spec explicitly describes both vectors (standalone binary and conformant plugin), names the Agent Plugins Specification by its current branding, and notes that the generic `.plugin/plugin.json` manifest is portable across harnesses. The candid note about `hooks.json` being Claude-Code-only is an accurate caveat that does not contradict the core decision (the plugin spec and skill definitions are still portable; only the hook system is vendor-specific).

---

## 5. Twin-model perplexity tier explicitly ships in v1 (not deferred to v2; opt-in/feature-gated but present and buildable)

**Decision restated:** The twin-model perplexity detection method (Binoculars/Fast-DetectGPT style) is part of v1 scope, not deferred to v2 despite its 8–10GB RAM and multi-GB download cost. It is feature-gated (`perplexity` flag, default off) so users opting for minimal builds can skip it, but the feature and its build integration are present and working in the first release.

**Spec quotes:**

| **perplexity** | `perplexity` | No | Twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style) |  
> — § 2.2, The five backend tiers (line 48)

> A spectrum of detection strength: instant deterministic pattern-matching up through heavy local ML, plus optional external commercial APIs, all behind one consistent interface.  
> — § 1, Goals (lines 17–18)

> `classifier`/`perplexity` features add candle (~50-80MB) or ONNX Runtime (~100-150MB) — these are documented as separate, explicit install paths, not silently bundled into a bloated default.  
> — § 5, Packaging and distribution (line 95)

**Verdict:** ✅ **Fully aligned.** The perplexity tier appears in the main backend table as a v1 component (not under "Explicit v1 scope-outs"). It is feature-gated (`perplexity`, default: No). The spec documents its heavyweight footprint ("~50-80MB" for candle or higher for ONNX) as a separate, explicit install path, which matches the decision to make it opt-in but present. The spec does not move it to v2.

---

## 6. `Score` type's canonical internal representation is a continuous 0.0–1.0 fraction (`human_probability`), not a label/tier-only representation

**Decision restated:** The `Score` struct's canonical ground truth is a continuous floating-point fraction from 0.0 (certainly AI) to 1.0 (certainly human), not a discrete label or confidence tier. This preserves fine-grained precision from vendors like Pangram that return fractions natively.

**Spec quotes:**

```
struct Score {
    backend: String,
    human_probability: f32,   // 0.0 (certainly AI) .. 1.0 (certainly human)
    confidence: ConfidenceTier, // Low | Medium | High
    evidence: Vec<Evidence>,   // line/offset-anchored where applicable
}
```  
> — § 2.3, `Score` — the common result type (lines 58–63)

> `human_probability` is the canonical continuous representation. Pangram's API returns continuous fractions natively; the other three commercial vendors and the deterministic/stylometric backends return coarser labels or thresholds, which map onto fraction *bands* rather than exact points — deliberately chosen so no backend's precision is silently lost on the way in.  
> — § 2.3 (lines 66)

**Verdict:** ✅ **Fully aligned.** The spec defines `human_probability: f32` as the canonical representation and explicitly states it is canonical (not just one of several fields). The rationale for preserving Pangram's fine-grained fractions is documented. The field range (0.0–1.0 with semantic anchors) matches the decision exactly.

---

## Summary

**All 6 decisions are fully aligned with the spec.** No decisions are missing, weakened, or contradicted. The spec accurately reflects all explicit product choices: the full port with lint-only humanization, all three ML tiers in v1, optional pluggable commercial APIs with explicit key requirement, dual distribution (standalone + portable plugin), perplexity tier present and feature-gated, and the continuous `human_probability` field as canonical. The language is precise and unhedged.
