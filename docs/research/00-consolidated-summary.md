# nobotrs Research: Consolidated Summary

This document synthesizes the eight research reports in this directory into a single reference
for the design/spec phase. Each topic section below is a distillation — see the linked source
file for full detail, rationale, and code sketches.

Source reports:
- [01-ml-inference-crates.md](01-ml-inference-crates.md)
- [02-nlp-tokenization-crates.md](02-nlp-tokenization-crates.md)
- [03-stylometric-statistical-crates.md](03-stylometric-statistical-crates.md)
- [04-pattern-matching-crates.md](04-pattern-matching-crates.md)
- [05-architecture-pluggable-backends.md](05-architecture-pluggable-backends.md)
- [06-cli-packaging-distribution.md](06-cli-packaging-distribution.md)
- [07-open-plugins-integration.md](07-open-plugins-integration.md)
- [08-prior-art-existing-tools.md](08-prior-art-existing-tools.md)

---

## Verification notes

Every load-bearing claim called out for verification was independently re-checked against
crates.io's API, GitHub's API (`gh api`), or the live docs, rather than trusted from the source
report's citation. Two real errors were found — one a fabricated cross-attribution, one a
mischaracterized license — both are corrected below and must be corrected in any design doc that
draws on report 08 or report 03.

### 1. Prior art: "is-it-slop" and "aislop" (report 08)

- **aislop — CONFIRMED**, with one correction. `scanaislop/aislop` is a real, active GitHub repo:
  511 stars, 23 forks, MIT license, 322 commits (all figures match the report exactly, verified
  via GitHub API and Link-header pagination). Its README confirms "50+ rules across 8 language
  targets (TypeScript, JavaScript, Expo / React Native, Python, Go, Rust, Ruby, PHP)," sub-second
  deterministic scanning, no runtime LLM calls — all as reported.
  **Correction:** the repo's language breakdown is 100% TypeScript/JavaScript — aislop is *not*
  written in Rust. It scans Rust code as one of its 8 *target* languages, but the tool itself is
  an npm/pipx package, not a Rust crate. Report 08's "or from Rust source" install option is
  unsupported by evidence and should be dropped.

- **is-it-slop — CORRECTED (fabricated cross-attribution).** This is the more serious finding.
  Report 08 describes the *real* `is-it-slop` crate on crates.io accurately in its "What it does"
  section (TF-IDF/logistic-regression classifier, ONNX-embedded binary, no Python runtime,
  ~96% accuracy — the real README states 95.6% accuracy, F1 0.958, so this is a close paraphrase,
  fine). **But the citation, license, and GitHub stats attached to that description belong to a
  different, unrelated project.** Two distinct GitHub repos are both named `is-it-slop`:
  - `github.com/SamBroomy/is-it-slop` — the actual owner of the `is-it-slop` crate on crates.io
    (confirmed via `crates.io/api/v1/crates/is-it-slop/owner_user`). MIT license. **10 stars, 2
    forks** (not 81/6). This is the TF-IDF/ONNX text classifier the report describes functionally.
  - `github.com/sermuns/is-it-slop` — a *completely different tool*: a Rust CLI that checks
    whether a **GitHub Rust project** looks like low-effort AI-generated slop (stale dependencies,
    Rust 2021 edition, workspace resolver v1) — it has nothing to do with detecting AI-generated
    *text*. WTFPL license, 81 stars, 6 forks, 67 commits — these are the numbers report 08 cited,
    but they describe this unrelated repo, not the crates.io package.
  **Corrected facts for the design doc:** `is-it-slop` (crates.io) = MIT license,
  `github.com/SamBroomy/is-it-slop`, 10 stars, 2 forks. The report's licensing conclusion ("Not a
  blocker... could depend on it as an optional backend") is *unaffected* by this correction (MIT
  is if anything more permissive than the wrongly-cited WTFPL), but the popularity/maturity
  signal (81★ vs. the real 10★) was overstated and should not be repeated as-is — 10 stars is a
  much younger, less-battle-tested project than the report implied.

### 2. candle `debertav2` module (report 01)

**CONFIRMED.** Fetched `docs.rs/candle-transformers/latest/candle_transformers/models/debertav2/`
directly. The module exports `DebertaV2SeqClassificationModel` (described in its own docs as "a
struct for sequence classification tasks with DeBERTa-v2"), alongside `DebertaV2Model`,
`DebertaV2ContextPooler`, `DebertaV2NERModel`, `Id2Label`/`Label2Id`, and more — exactly as
report 01 claimed. This is a load-bearing architecture claim (it determines whether `ort`/ONNX
export is even necessary for the classifier workload) and it holds up. The report's own caveat
still stands and should be kept: nobody has been found to have actually loaded the
`desklib/ai-text-detector-v1.01` checkpoint into this module — the *module's existence* is
confirmed, but empirical compatibility with that specific checkpoint is not, and should be the
first thing prototyped.

### 3. Open Plugins / Agent Plugins Specification and Claude Code hooks (report 07)

- **Rebrand to "Agent Plugins Specification" — CONFIRMED.** Live fetch of
  `github.com/vercel-labs/open-plugin-spec` confirms it now identifies as "Agent Plugins
  Specification v1.0.0," a working draft, with schema host `agent-plugins.org`
  (`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`) exactly as cited.

- **"Both forms support compiled native binaries" — CORRECTED (unverifiable quote).** This exact
  sentence, and the paired example `"command": "/usr/local/bin/my-compiled-tool"`, do **not**
  appear anywhere on the current live `code.claude.com/docs/en/hooks` page — a full-text search
  for "binary," "binaries," and "compiled" turned up only an unrelated passage about Windows
  `.cmd`/`.bat` shims. This looks like either a hallucinated citation or documentation that has
  since changed; either way, it should not be repeated as a direct quote in the design doc.
  **However, the underlying conclusion is still substantively correct** based on what the current
  docs actually say: exec-form `command` ("with `args` present") is "resolve[d]... as an
  executable on PATH and spawn[ed]... directly," and the only documented restriction is that
  Windows `.cmd`/`.bat` *shims* (not real executables) can't be spawned without a shell — implying
  real compiled binaries work fine in exec form. Use this paraphrase, not the invented quote, in
  the design doc.

- **`nab` and `genasis` example plugins — CONFIRMED.** Both `github.com/MikkoParkkola/nab` and
  `github.com/claude-genasis/genasis` are real, existing repos, and their GitHub descriptions
  ("A single Rust binary — not a browser" / "Single Rust binary, MCP-friendly") corroborate the
  report's characterization of both as Rust-binary-backed Claude Code plugins using a
  locate-or-download pattern rather than bundling binaries in-repo.

- **`postInstall` gap (issue #9394) — CONFIRMED to exist, state CORRECTED.** The issue
  ("[FEATURE] Plugins - Add postInstall, postUpdate and postUninstall hooks in plugin.json") is
  real, but it is **closed, `state_reason: not_planned`** (closed 2026-02-07), not "open,
  unresolved" as report 07 stated. This actually *strengthens* the report's conclusion rather than
  undermining it: Anthropic has explicitly decided not to build this, so "no supported way to
  auto-install nobotrs at plugin-install time" is not a temporary gap but a settled position as of
  now. The design doc should say "closed as not-planned," not "open."

### 4. Licenses (spot-checked 8 of the most consequential crates, against crates.io directly)

| Crate | Reported license | Verified license | Status |
|---|---|---|---|
| candle-core | MIT OR Apache-2.0 | MIT OR Apache-2.0 | CONFIRMED |
| ort | MIT OR Apache-2.0 | MIT OR Apache-2.0 | CONFIRMED |
| tch | MIT/Apache-2.0 | MIT/Apache-2.0 | CONFIRMED |
| aho-corasick | Unlicense OR MIT | Unlicense OR MIT | CONFIRMED |
| reqwest | MIT OR Apache-2.0 | MIT OR Apache-2.0 | CONFIRMED |
| clap | MIT OR Apache-2.0 | MIT OR Apache-2.0 | CONFIRMED |
| **rust_readability** | "Likely MIT or Apache 2.0 (not confirmed)" | **GPL-3.0-or-later** | **CORRECTED — copyleft** |
| viterbi_pos_tagger | GPL-3.0-or-later (already flagged/excluded) | GPL-3.0-or-later | CONFIRMED |

Also spot-checked while verifying report 03's own "verify before finalizing" flags: `xz` (MIT OR
Apache-2.0), `lzma-rs` (MIT), `entropy` (MIT), `shannon-entropy` (MIT OR Apache-2.0), `statrs`
(MIT), `nlprule` code (MIT OR Apache-2.0 — matches report 02; its *shipped rule-data* LGPL claim
is plausible but not independently re-verified here), `wordfreq` (MIT OR Apache-2.0), `keyring`
(MIT OR Apache-2.0), `directories` (MIT OR Apache-2.0), `tokio` (MIT). All CONFIRMED as reported.

**The `rust_readability` finding is a real, consequential error requiring action.** Report 03
recommended `rust_readability` 0.2.0 as "✓ Directly usable" for Flesch-Kincaid readability and
listed it in its License Compatibility Checklist as presumptively MIT/Apache. It is actually
**GPL-3.0-or-later** (confirmed both via crates.io API and the upstream GitHub repo's
`Cargo.toml`), which is copyleft and not safely embeddable as a compiled-in dependency of an
MIT-licensed binary without legal review. Recommendation: **do not depend on `rust_readability`.**
Flesch-Kincaid is a simple formula (syllable count, word count, sentence count — see
[Wikipedia](https://en.wikipedia.org/wiki/Flesch%E2%80%93Kincaid_readability_tests)) and should be
hand-rolled on top of `unicode-segmentation`, the same way report 03 already recommends
hand-rolling MTLD.

### 5. cargo-dist vs. nab/genasis "contradiction" (reports 06 and 07)

**Reconciled — not a real contradiction, confirmed sound.** Report 06 recommends `cargo-dist` to
build and publish per-platform binaries to GitHub Releases/Homebrew/crates.io. Report 07's real
examples (`nab`, `genasis`) show plugins that *locate* an already-installed binary via
PATH/well-known-dirs, or *download* one via a separate `install.sh`, rather than bundling
binaries in the plugin repo. These are two different layers of the same pipeline, not competing
approaches: `cargo-dist` is what produces and hosts the release binaries; the plugin-side
wrapper/`install.sh` is what a plugin uses to *consume* those already-published artifacts. Design
doc guidance: adopt `cargo-dist` for the release pipeline (report 06) and Option A
("locate-don't-bundle," report 07 §5) for how the plugin's `bin/nobotrs` wrapper finds or fetches
the binary `cargo-dist` published. No change needed to either report's recommendation.

---

## Distilled findings by topic

### ML inference ([01](01-ml-inference-crates.md))

Two workloads: (1) single-pass fine-tuned classifier inference, (2) twin-model zero-shot
perplexity (Binoculars/Fast-DetectGPT style). `candle` is the lead recommendation for both —
pure Rust, no system ML library, and its native `debertav2` module (confirmed above) is a
plausible fit for a DeBERTa-v3-large classifier like `desklib/ai-text-detector-v1.01` without an
ONNX export step. `ort` (ONNX Runtime bindings) is the well-proven fallback for the classifier if
candle's native loading doesn't pan out empirically. For the twin-model perplexity workload,
`candle` (shared framework) or `llama-cpp-2`/GGUF (more mature CPU quantization, more pragmatic
for consumer laptops) are both credible; `tch-rs` is the most flexible but heaviest to distribute
(libtorch is a large, version-sensitive C++ dependency) and is not recommended as primary. All
four candidate crates are MIT/Apache-2.0 family — no license concerns. Everything in this track
should sit behind Cargo feature flags so the default build stays lean.

### NLP / tokenization ([02](02-nlp-tokenization-crates.md))

`unicode-segmentation` covers sentence/word boundary splitting cleanly (MIT/Apache-2.0, extremely
stable) and is sufficient for every purely statistical feature (burstiness, TTR, mean word
length, entropy-per-token). The hard gap is **dependency parsing: no viable pure-Rust option
exists at all**, and POS tagging only has low-confidence options (`postagger.rs`, unproven;
`rust-bert`'s MobileBERT tagger, viable but only worth it if `tch-rs` is already a dependency for
other reasons). `nlprule` was investigated and explicitly rejected: unmaintained 5+ years, and its
shipped LanguageTool-derived rule data is LGPL-licensed even though its own code is
MIT/Apache-2.0. **Recommendation: explicitly scope dependency-parse-dependent features (dependency
distance, whiz-deletion, sentence-relatives, textdescriptives-style coherence) out of v1.** These
require either an unproven ONNX export of spaCy's parser (no precedent found) or shelling out to
the existing Python `deep_stylometry.py` as an optional sidecar — a genuine architecture decision
for the design doc, not a crate choice.

### Stylometric / statistical crates ([03](03-stylometric-statistical-crates.md))

MTLD lexical diversity has no Rust crate and should be hand-rolled (~50 LOC, algorithm is
well-documented). Flesch-Kincaid readability **should also now be hand-rolled**, not sourced from
`rust_readability` — see the license correction above. LZMA/XZ for the compression-ratio
perplexity proxy: use pure-Rust `xz` for portability (no system liblzma dependency), matching the
report's own recommendation. `statrs` covers burstiness statistics (mean/stdev); Shannon entropy
is trivial to hand-roll or use the tiny `entropy`/`shannon-entropy` crates. All licenses in this
group are confirmed permissive except the now-corrected `rust_readability`.

### Pattern matching ([04](04-pattern-matching-crates.md))

Hybrid approach confirmed sound: `aho-corasick` (Unlicense OR MIT) for exact tell-word matching at
scale (linear time regardless of list size, dramatically faster than mega-alternation regex for
hundreds of words), `regex` (MIT OR Apache-2.0) for tell-*phrase* patterns that need wildcards,
and `unicode-segmentation` for sentence/word splitting feeding burstiness and em-dash-density
stats. `fst` was correctly assessed as overkill unless the tool ever needs to support
user-supplied million-word lists or persistent disk-based indexes — skip it at MVP scope.

### Architecture / pluggable backends ([05](05-architecture-pluggable-backends.md))

The `trait DetectorBackend` + Cargo-feature-gated-optional-dependency pattern is standard,
well-supported Rust practice, with `sccache`'s per-backend-feature storage design as strong
real-world precedent for exactly this shape. Recommended feature layout: `default =
["deterministic", "stylometric"]` (zero heavy deps), `classifier`/`perplexity` gating
`candle`/`ort`, one shared `api-clients` feature (gating `reqwest`) for all four external
commercial detector vendors (Sapling, GPTZero, Copyleaks, Pangram) rather than one feature per
vendor. For those API clients: `reqwest::blocking` is the pragmatic choice if the deterministic
core stays synchronous (avoids async-tainting the whole `DetectorBackend` trait); secrets should
layer env var → config file (`directories` + `serde`/`toml`) → optional `keyring` upgrade, in that
precedence order, matching how tools like `gh`/`aws-cli` handle credentials. Pangram's response
shape (continuous `fraction_ai`/`fraction_human` floats) is more granular than the other three
vendors' label-based responses — the common `Score` type should be designed to accommodate a
continuous fraction, not just a label. No license issues anywhere in this dependency set.

### CLI framework / packaging ([06](06-cli-packaging-distribution.md))

`clap` (derive API) for subcommands, `owo-colors` for terminal color (respects `NO_COLOR`, zero
allocations), `serde`/`serde_json` for `--format json` output — all standard, all confirmed
MIT/Apache-2.0. For distribution, `cargo-dist` automates the full pipeline (multi-target builds,
GitHub Releases, Homebrew tap, crates.io) and is the clear recommendation for production releases;
`cross` is useful for local/manual cross-compilation but subordinate to `cargo-dist` for CI. Binary
size is a real concern once ML features are enabled (ONNX Runtime static-linked: ~100–150MB;
candle: ~50–80MB) — this is precisely why report 05's feature-gating (default build excludes all
ML deps) matters, and why the design doc should treat "lightweight pattern-only binary" and
"full ML binary" as two clearly documented install paths rather than one bloated default.

### Open Plugins integration ([07](07-open-plugins-integration.md))

nobotrs can ship as both a standalone CLI and an Open-Plugins/Agent-Plugins-Spec-conformant plugin
(manifest, skills, hooks) without conflict. The ambient `PostToolUse` hook-based scanning UX is
**Claude-Code-only in practice** — OpenCode and Pi use their own native JS/TS event systems, not
`hooks.json`, so only the `detect-ai-writing` skill (and any slash command) carries over
cross-harness, exactly matching nobots' own existing Python-plugin caveat. The binary-distribution
question (bundle prebuilt binaries in the plugin repo vs. locate/download a separately-installed
one) has real-world precedent pointing one direction: both examined examples (`nab`, `genasis`)
converged on "locate or download, don't bundle" — see the open design decision below.

### Prior art ([08](08-prior-art-existing-tools.md))

The Rust AI-text-detection ecosystem is thin: `is-it-slop` (crates.io, corrected identity above)
is a narrow ML binary classifier; `aislop` targets code, not prose; `stylometry`
(`ian-nai/rust_stylometry`) provides classic authorship-analysis statistics (Mendenhall,
Kilgariff, hapax legomena) but no AI-specific logic; `rust-bert` offers zero-shot classification
at the cost of a `tch-rs`/libtorch dependency. No Rust equivalent exists for Fast-DetectGPT,
detect-gpt, or GPTZero's perplexity/burstiness approach. This supports the report's conclusion
that building nobotrs is justified: no existing Rust tool combines prose-focused stylometric
linting, pattern-based tell detection, and pluggable ML/API backends in one tool.

---

## Recommended stack (consolidated)

| Capability | Crate(s) | License | Confidence |
|---|---|---|---|
| CLI parsing | `clap` (derive) | MIT OR Apache-2.0 | High — confirmed |
| Colored output | `owo-colors` | MIT | High |
| JSON output | `serde` + `serde_json` | MIT OR Apache-2.0 | High |
| Sentence/word segmentation | `unicode-segmentation` | MIT OR Apache-2.0 | High — confirmed |
| Tell-word matching | `aho-corasick` | Unlicense OR MIT | High — confirmed |
| Tell-phrase matching | `regex` | MIT OR Apache-2.0 | High |
| Lexical diversity (MTLD) | hand-rolled | n/a | Medium (well-documented algorithm) |
| Readability (Flesch-Kincaid) | **hand-rolled** (not `rust_readability`) | n/a | Medium — corrected, see above |
| Compression-ratio perplexity proxy | `xz` (pure Rust) | MIT OR Apache-2.0 | High |
| Burstiness / stats | `statrs` (or stdlib) | MIT | High |
| Shannon entropy | hand-rolled or `entropy` | MIT | High |
| Stylometric feature foundation | `stylometry` (ian-nai/rust_stylometry) | unconfirmed — verify before use | Medium |
| POS tagging (optional, low-confidence) | `postagger.rs` | Apache-2.0 | Low — needs accuracy validation |
| Dependency parsing | **none available in pure Rust** | — | Gap — scope out of v1 or shell to Python |
| Fine-tuned classifier inference | `candle` (`candle-transformers::debertav2`), fallback `ort` | MIT OR Apache-2.0 | High for candle module existence — confirmed; Medium for desklib-checkpoint compatibility — unverified |
| Twin-model perplexity | `candle` or `llama-cpp-2` (GGUF) | MIT OR Apache-2.0 | Medium — both credible, hardware cost is the open question |
| Weight download | `hf-hub` | Apache-2.0 | High |
| External API HTTP client | `reqwest` (`blocking` feature) | MIT OR Apache-2.0 | High — confirmed |
| Secrets/config | `directories` + `serde`/`toml`, optional `keyring` | MIT OR Apache-2.0 | High |
| Release pipeline | `cargo-dist` | MIT OR Apache-2.0 | High — confirmed |
| Local cross-compilation | `cross` | MIT OR Apache-2.0 | High |

---

## Open design decisions

Punch list for the design/spec phase — every place the source reports disagreed, flagged an
explicit decision point, or found a genuine gap:

1. **Readability formula source.** Must switch from `rust_readability` (GPL-3.0-or-later,
   confirmed above) to a hand-rolled Flesch-Kincaid implementation. Decide whether to hand-roll
   other readability formulas too or keep scope to Flesch-Kincaid only (matches nobots' existing
   scope).

2. **Dependency-parse-dependent stylometric features.** No pure-Rust path exists for dependency
   distance, whiz-deletion/sentence-relative Biber features, or textdescriptives-style coherence.
   Decide: scope these out of v1 entirely, or support them only via an optional Python sidecar
   (`deep_stylometry.py`) that degrades gracefully when absent — trading full feature parity
   against single-binary distribution. This is the single biggest feature-parity gap versus the
   Python `nobots` tool.

3. **POS-tag-dependent features** (POS proportions, content/function-word ratio, hedges,
   amplifiers, nominalizations). Decide whether to ship these behind `postagger.rs` (real but
   unproven — needs accuracy validation against a labeled sample before trusting it in verdicts)
   at v1, or defer them alongside the dependency-parse gap above until `tch-rs` is already a
   dependency (making `rust-bert`'s MobileBERT tagger "free").

4. **Whether to build the twin-model zero-shot perplexity feature at all.** Binoculars' validated
   model pair (Falcon-7B/Falcon-7B-Instruct) is memory-heavy even GGUF-quantized (~8–10GB RAM for
   the pair); no smaller *validated* pair was found in the literature. Decide whether this ships
   as an explicitly "heavy, opt-in" detection method gated behind its own feature flag, is deferred
   past v1 entirely, or is scoped only to users who opt into downloading multi-GB models.

5. **candle-vs-desklib empirical compatibility.** The `debertav2`/`DebertaV2SeqClassificationModel`
   module's existence is confirmed, but nobody has been found to have actually loaded
   `desklib/ai-text-detector-v1.01` weights into it. This should be the first empirical prototype
   of the ML-inference track, with `ort` + ONNX export as the documented fallback if it fails
   (config mismatches, tokenizer differences, v3-specific attention quirks).

6. **Plugin binary distribution: bundle vs. locate/download (`bin/` question, report 07 §5).**
   No ecosystem precedent for bundling per-platform binaries directly in a plugin repo; both real
   examples found (`nab`, `genasis`) locate an already-installed binary or download one via a
   separate installer. Report 07 recommends Option A (locate-don't-bundle) as the safer default.
   This composes cleanly with report 06's `cargo-dist` recommendation (see reconciliation above)
   but still needs to be a deliberate, stated decision in the design doc, including exactly what
   the `bin/nobotrs` wrapper script's search order and failure message look like.

7. **External commercial API backends: which vendors, and default-on or opt-in.** Four vendors
   (Sapling, GPTZero, Copyleaks, Pangram) have usable public docs, but three require paid API keys
   and Pangram's response shape (continuous fractions) differs from the other three's label-based
   responses. Decide the common `Score` type shape now (continuous fraction vs. label) so it
   doesn't need reworking once a second vendor is added, and decide whether any commercial backend
   ships in the default `full` feature set or stays purely opt-in given the cost/privacy
   implications of sending user text to a third-party API.

8. **`stylometry` (ian-nai/rust_stylometry) license.** Report 08 flagged this as "specific license
   not stated in search results; verify on GitHub" and report 03 didn't independently check it.
   Not verified in this pass either (out of the prioritized checklist) — verify before depending
   on it, since it's recommended as a direct dependency for stylometric feature extraction.

9. **`nlprule`'s LGPL data-licensing claim.** Report 02's code-license claim (MIT OR Apache-2.0)
   was reconfirmed here, but its claim that the shipped LanguageTool-derived rule *data* is
   LGPLv2.1 was not independently re-verified in this pass (moot in practice since report 02
   already recommends against adopting `nlprule` on maintenance grounds — 5+ years stale — but
   worth a footnote if anyone later reconsiders it).

---

## Sources consulted during verification

- `https://crates.io/api/v1/crates/is-it-slop` — crates.io API
- `https://crates.io/api/v1/crates/aislop` — crates.io API (confirms no such crate exists)
- `https://api.github.com/repos/sermuns/is-it-slop` — GitHub API (via `gh api`)
- `https://api.github.com/repos/SamBroomy/is-it-slop` — GitHub API
- `https://api.github.com/repos/scanaislop/aislop` — GitHub API, incl. `/languages` and README content
- `https://crates.io/api/v1/crates/is-it-slop/owner_user` — crates.io API
- `https://docs.rs/candle-transformers/latest/candle_transformers/models/debertav2/index.html`
- `https://crates.io/api/v1/crates/candle-core`, `/ort`, `/tch`, `/aho-corasick`, `/reqwest`,
  `/clap`, `/rust_readability`, `/xz`, `/lzma-rs`, `/entropy`, `/shannon-entropy`, `/statrs`,
  `/nlprule`, `/viterbi_pos_tagger`, `/wordfreq`, `/keyring`, `/directories`, `/tokio`,
  `/cargo-dist` — crates.io API
- `https://api.github.com/repos/ian-nai/rust_readability` and its `Cargo.toml` — GitHub API
- `https://code.claude.com/docs/en/hooks` — live fetch, full-text search for
  "binary"/"binaries"/"compiled"
- `https://github.com/vercel-labs/open-plugin-spec` — live fetch
- `https://api.github.com/repos/MikkoParkkola/nab` — GitHub API
- `https://api.github.com/repos/claude-genasis/genasis` — GitHub API
- `https://api.github.com/repos/anthropics/claude-code/issues/9394` — GitHub API
