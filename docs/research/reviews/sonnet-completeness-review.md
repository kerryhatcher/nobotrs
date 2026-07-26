# Completeness review: `nobotrs` Rust CLI design spec

**Reviewer:** review-sonnet (completeness/gaps pass)
**Subject:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`
**Scope:** This review checks only for *missing* decisions — things a real implementation-planning pass would need that the spec doesn't currently address. It does not evaluate architecture soundness, research fidelity, internal consistency, or decision-alignment; those are covered by other reviewers in this pass.

Verdict key used below: **addressed** (cited), **defer** (silent, but fine to leave to planning), **blocker** (silent, and should be resolved or at least explicitly scoped before planning starts).

---

## 1. Error-handling philosophy

**Silent — defer, but flag the interaction with §2.1.** Nothing in the spec states what happens on malformed/binary input to `detect`/`lint`, network failures for `api` backends, missing/corrupt model files for `classifier`/`perplexity`, or an unparseable `config.toml`. §8 (Testing) only says API backends are tested against mocked responses — that's a testing statement, not an error-handling policy. §3's exit-code convention (0 = clean, non-zero = tells found) implicitly needs a *third* class of exit code for "the tool itself failed" (bad input, network down, corrupt model) versus "ran fine, found tells" — the spec doesn't distinguish these, which matters for `scan`'s CI composability claim. This also touches the `DetectorBackend` trait directly: `fn score(&self, text: &str) -> Result<Score>` (§2.1) doesn't say what the error type is or how ensemble aggregation (§2.4) behaves when one backend errors while others succeed (skip it? abort the whole quorum?). That last question is architectural, not cosmetic, and should be answered before backends are implemented.

## 2. Rust edition & MSRV

**Silent in the spec text — defer, but the ingredients for a decision already exist in research.** The spec itself never states an edition or MSRV. Research does: `05-architecture-pluggable-backends.md` assumes "edition 2021+, which nobotrs will use," and `04-pattern-matching-crates.md` records MSRVs of 1.65.0 and 1.60.0 for two candidate crates — but the heavier `candle`/`ort` deps' MSRV floors aren't in the spec at all. This is low-stakes to resolve (it's a Cargo.toml line), but worth one explicit sentence in the spec rather than leaving it purely inferable from research artifacts, since MSRV interacts with which crate versions are pinned in §10's dependency table.

## 3. Workspace vs. single-crate layout

**Silent on an explicit decision — defer, research already answered the substance.** The spec's Cargo feature table (§2.2) and dependency stack (§10) *imply* a single crate with feature flags, but never states this as a decision. Research (`05-architecture-pluggable-backends.md`, feature-unification section) explicitly raised the workspace question and concluded: "for a single-binary CLI like nobotrs this is low-risk... worth remembering if the project later splits into a `nobotrs-core` lib crate plus a `nobotrs` CLI crate in a workspace." The spec should have surfaced that conclusion explicitly (single crate for v1, workspace split is a plausible future move) rather than leaving readers to infer it from the feature table's shape. Not a blocker since the research already resolved the substantive question — just an editorial gap.

## 4. Versioning/semver policy

**Silent — split verdict.** Nothing addresses CLI crate semver or plugin-manifest version independence. Ordinary crate/CLI semver is fine to **defer** — standard practice, low cost to decide later. But §3 explicitly positions `--format json` as a machine-readable interface "for CI/scripting," and §2.3's `Score` struct is the thing that would get serialized. A breaking change to that JSON shape is a breaking change for every CI pipeline consuming it, yet the spec has no stability contract for it (versioned schema? `--format json` output includes a schema version field? SemVer applies to the JSON shape independent of the crate version?). This part should be **blocker**-adjacent: not because it needs a full policy written now, but because §3 already commits to the interface without acknowledging it needs one.

## 5. i18n / non-native-English handling

**Silent in the spec — blocker.** This is the clearest gap found. Research (`02-nlp-tokenization-crates.md`, lines 96 and 121) directly addresses this, in response to what the report itself flags as specifically-requested design guidance: it recommends gating on `whichlang` ahead of any English-tuned stylometric feature, and adds an explicit calibration warning — "even English text can trigger elevated false-positive risk when written by non-native speakers — a detection-calibration concern, not just a language-filter one." None of this — not the language gate, not the calibration caveat, not even the word "language" — appears anywhere in the spec. Given the tool's stated purpose is producing "evidence-backed" verdicts about whether a human wrote something (§1 Goals), and the research already did the legwork to identify both the risk and a concrete crate-level mitigation, this should not be left to implicit inference. It needs to be an explicit design commitment (even if the commitment is narrow: "v1 does not attempt non-English-author calibration; language-gate stylometric features behind `whichlang` and document the residual false-positive risk on ESL English text") before planning proceeds on the stylometric tier.

## 6. Privacy/telemetry stance

**Silent — defer, but recommend one explicit line.** §1's stated Goal ("Local-first, offline-capable detection with no mandatory network calls or API keys") implies no telemetry, but that's an inference from a goal about *detection*, not an explicit privacy/telemetry policy statement about the tool as a whole (e.g., update checks, crash reporting, anonymous usage pings — none of which are "detection" but all of which are network calls a CLI tool commonly adds later without it feeling like scope creep). Cheap to close: one sentence stating nobotrs never phones home, full stop, no opt-out telemetry either. Not a blocker, but worth doing before the CLI scaffolding is opinionated by omission.

## 7. CI/testing infra beyond §8

**Silent — should be scoped before planning, leaning blocker.** §8 covers unit-test philosophy, quorum-logic tests, mocked API tests, and a separate integration tier for `classifier`/`perplexity`. It does not cover: an actual CI pipeline definition, feature-flag matrix testing, or platform matrix testing tied to §5's cargo-dist targets (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64), or clippy/fmt/MSRV gating. The feature-flag matrix point matters specifically because §2.2 defines five independently-toggleable tiers plus a `full` meta-feature — that's a real combinatorial surface (default / classifier / perplexity / api-clients / any pair / full), and a broken feature combination is a class of bug this exact architecture invites. The spec doesn't need to commit to testing every combination (that would be its own poor decision — full N-way combinatorial testing is usually not worth it), but it should state which combinations are tested (e.g., default, each single flag in isolation, and `full`) rather than leaving §8 silent on the question entirely.

## 8. Security review needs for API-key handling

**Partially addressed, partially silent — blocker on the silent part.** §4 addresses storage precedence (env var → config file → keyring) and file permissions (0600). It does not address: keys never appearing in logs or error output (a well-known Rust footgun — a `reqwest` error or a `Debug`-derived struct holding a `String` API key will happily print it in a panic or `--verbose` log), zeroizing key material in memory, or key rotation. The logging-leak risk is concrete and easy to introduce by accident once four vendor client modules exist (§2.2), each formatting its own request/error output. This should get an explicit one-line constraint in the spec ("API keys must never appear in log output, error messages, or `Debug` representations") before the `api` backends are implemented, since it's the kind of thing that's much cheaper to design in than to retrofit across four client modules. It also intersects with item 1's open error-type question.

## 9. Model weight provenance

**Silent — split verdict.** How downloaded model weights (e.g., `desklib/ai-text-detector-v1.01`, referenced in §9 item 1) are fetched, cached, and version-pinned is reasonably **deferrable** to the prototyping work §9 already calls for — that's mechanical and will fall out of actually doing the candle prototype. But *integrity verification* (checksum/hash pinning before loading a downloaded checkpoint) is a distinct, security-relevant question that isn't mentioned at all, and ML checkpoint supply-chain tampering is a known real-world attack class. Even a one-line commitment ("downloaded model weights are checksum-verified against a pinned hash before load; cached under the `directories`-crate cache dir") would close this. Recommend treating the integrity-verification half as a **blocker**-lite: not because the mechanism needs designing now, but because the spec should commit to *doing* verification before implementation starts, rather than have it be an afterthought bolted on (or skipped) later.

## 10. License/NOTICE requirements for model weights

**Silent — blocker.** §7 item 3 and §10 address Rust *crate* licensing carefully (MIT/Apache-2.0/Unlicense family, GPL-3.0 exclusion of `rust_readability`, and an open item to confirm the `stylometry` crate's license). None of that machinery is applied to *model weight* licensing for the `classifier`/`perplexity` tiers. Model weights routinely carry licenses distinct from — and sometimes more restrictive than — the code that loads them (non-commercial-only clauses, attribution/NOTICE requirements, redistribution restrictions). This is a different legal question from the crate-licensing work already done and shouldn't be assumed covered by it. Should be resolved (at minimum: confirm `desklib/ai-text-detector-v1.01`'s license permits nobotrs's intended use) before the `classifier` tier moves past prototyping.

## 11. How `lint`'s "suggested fixes" are generated

**Hand-waved — blocker.** §3 commits to a specific CLI surface: `lint` produces "line-anchored tells report: word/phrase hits + stylometric flags + suggested fixes." Given §1's explicit non-goal ("no LLM in the loop... `lint` only flags and suggests; it never edits files"), the natural inference is that suggestions are static, per-tell templates ported from nobots' existing tell lists — but the spec never says this, never confirms `check_ai_tells.py` actually has such templates to port (it's cited elsewhere in the spec only as a source of word/phrase *lists*, not fix templates), and doesn't address the harder case at all: stylometric flags (burstiness, lexical diversity, entropy-per-token) don't have an obvious template-able "fix" the way a tell-phrase swap does. This is a real scope ambiguity baked into a one-line CLI commitment — does every finding get a suggested fix, or only deterministic tell-word/phrase hits? That's a UX-shape decision the spec should make explicitly, since it changes what `Evidence` (§2.3) needs to carry and what `lint`'s output schema looks like.

---

## Prioritized closing list

**Blockers — resolve or explicitly scope before implementation planning starts:**
1. **§5 non-native-English / i18n handling** — research already answered this (language-gate via `whichlang` + calibration caveat); spec silently dropped it. Highest priority: affects verdict fairness, not just a nice-to-have.
2. **§11 suggested-fix generation mechanism** — §3 commits to a CLI surface with undefined content generation; ambiguous whether stylometric flags get fixes at all.
3. **§10 model-weight licensing** — distinct legal risk from the crate-licensing work already done; not addressed at all.
4. **§9 model-weight integrity verification** — supply-chain risk on downloaded checkpoints; needs a one-line commitment to *do* verification, even if mechanism is deferred to prototyping.
5. **§8 "never log API keys" constraint** — concrete, well-known Rust footgun that's cheap to prevent by design and expensive to retrofit across four vendor client modules.
6. **§4 JSON output (`--format json`) stability contract** — §3 already positions it as a CI-facing interface; needs at least a one-line semver/stability statement distinct from ordinary crate semver.

**Defer to implementation planning — real gaps, but low-cost to resolve later or already substantively answered by research:**
7. **§1 error-handling philosophy** — normal early-implementation work, but note it determines the `DetectorBackend::score` error type and ensemble-aggregation-on-partial-failure behavior (§2.1, §2.4).
8. **§2 MSRV/edition** — set in Cargo.toml at scaffolding time; research already assumes edition 2021.
9. **§3 workspace vs. single-crate** — research already recommends single-crate-with-features for v1; spec should state this explicitly but the substance is resolved.
10. **§6 telemetry/privacy stance** — inferable from stated goals; one explicit sentence would remove ambiguity but isn't blocking.
11. **§7 CI/feature-matrix testing** — §8 doesn't cover it; recommend the plan pick specific feature combinations to test (default, each isolated flag, `full`) rather than attempting full combinatorial coverage.
