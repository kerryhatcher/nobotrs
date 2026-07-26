# nobotrs: Rust CLI for AI-text detection — design spec

**Status:** Draft, pending user review
**Date:** 2026-07-26
**Research basis:** `docs/research/00-consolidated-summary.md` and its eight source reports, which themselves drew on prior art at `/mnt/storage/grimoire/research/open-plugins-spec/` (used directly by report 07).
**Revision note (2026-07-26, post-review):** revised per `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design-review.md`, a 5-agent (Opus/Sonnet×2/Haiku×2) review round plus independent Sonnet verification. See that file for the full findings; this revision applies all 8 Blocker and 11 Important items.
**Revision note (2026-07-26, dictionary addition):** adds §11, a separately CC BY-SA 4.0–licensed tell dictionary, per product decision. Cross-referenced from §2.2, §3, §9, and §10.

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

### 2.1 The `Document` type and `DetectorBackend` trait

```
struct Document {
    raw: String,                      // original file/stdin content, byte-exact
    prose_spans: Vec<Range<usize>>,   // byte ranges of `raw` treated as prose (markdown-aware: excludes code fences, front matter)
    content_type: ContentType,        // Markdown | PlainText | Unknown
}

enum Availability { Ready, NeedsDownload, Unavailable(String) }

enum ScoreOutcome {
    Scored(Score),
    Abstained { reason: String },     // e.g. "text too short for burstiness", "non-English text"
    Failed(Error),                    // backend errored (model missing, network failure, etc.) — distinct from abstention
}

trait DetectorBackend: Send + Sync {
    fn name(&self) -> &str;
    fn family(&self) -> SignalFamily;              // which independent signal family this backend's vote belongs to (§2.2)
    fn availability(&self) -> Availability;         // model/network readiness, surfaced by `nobotrs config`
    fn score(&self, doc: &Document) -> ScoreOutcome;
    fn score_batch(&self, docs: &[Document]) -> Vec<ScoreOutcome> { /* default: map score() */ }
}
```

`Document` replaces a bare `&str` as the trait's input. Evidence needs byte/line offsets into the *original* file for `lint`'s line-anchored output, while stylometric measures need prose-only content — code fences and YAML front matter would otherwise corrupt burstiness/MTLD/readability numbers. Segmentation is markdown-aware at minimum for v1; `content_type` names the strategy explicitly so other formats can be added later without changing the trait shape.

`ScoreOutcome` gives a backend a real way to say "not applicable to this input" (`Abstained`) distinct from "something broke" (`Failed`) — matching `check_ai_tells.py`'s own documented behavior, where a family that can't be measured (e.g. burstiness on a short file) simply abstains rather than voting either way. Both `Abstained` and `Failed` are excluded from aggregation (§2.4); they are not the same as a "no" vote.

`Send + Sync` supports `scan <dir>`'s batch use (§3); `score_batch` gives ML-backed backends (`classifier`, `perplexity`) a seam to batch multiple documents through one model load instead of reloading per file. Model acquisition (downloading and caching weights via `hf-hub`) is out of the trait itself — `availability()` reports readiness, and `nobotrs config` (§3) is what triggers a download.

### 2.2 The five backend tiers and signal families

Backends are grouped into independent **signal families** for aggregation purposes (§2.4) — a different axis than the Cargo feature-flag grouping below, and the two must not be conflated. A single backend can house more than one family (e.g. `stylometric` houses four independently-abstaining families in one implementation).

| Tier | Feature flag | Default? | Signal family/families | What it does | Key crates |
|---|---|---|---|---|---|
| **deterministic** | *(always on)* | Yes | `Vocabulary`, `Punctuation` | Exact tell-word / tell-phrase matching, data-driven from the separately-licensed tell dictionary (§11) rather than hardcoded in the binary — the dictionary itself is the Rust port's source of truth, seeded from `check_ai_tells.py`'s existing lists | `aho-corasick` (tell-words, linear time at scale), `regex` (tell-phrases with wildcards), `unicode-segmentation` (sentence/word boundaries) |
| **stylometric** | *(always on)* | Yes | `Burstiness`, `LexicalDiversity`, `Readability`, `Compression` | Burstiness (sentence-length stdev/mean), lexical diversity (hand-rolled MTLD), readability (hand-rolled Flesch-Kincaid — see §10), compression-ratio perplexity proxy, entropy-per-token. Language-tuned features (readability, some lexical-diversity assumptions) are gated behind a `whichlang` check; non-English input abstains rather than scoring incorrectly | `unicode-segmentation`, `statrs`, `xz` (pure-Rust LZMA), `whichlang` |
| **classifier** | `classifier` | No | `MlClassifier` | Single-pass fine-tuned AI-text classifier inference (DeBERTa-v3-style) via `candle-transformers::debertav2` — **module confirmed to exist and architecturally match this use case; compatibility with the specific `desklib/ai-text-detector-v1.01` checkpoint is unconfirmed, see §9 item 1** | `candle` + `candle-transformers::debertav2`; `ort` (ONNX Runtime) as documented fallback; `hf-hub` for weight download |
| **perplexity** | `perplexity` | No | `MlPerplexity` — **non-voting/experimental in v1, see §7 item 4** | Twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style); reports the raw cross-perplexity ratio as evidence but does not participate in quorum aggregation until calibrated (§8). Validated model pairs are memory-heavy (~8–10GB RAM); no smaller validated pair was found in research | `candle` or `llama-cpp-2` (GGUF quantization); `hf-hub` |
| **api** | `api-clients` | No | `CommercialApi` (one family for the whole tier, regardless of vendor count) | Optional external commercial detector calls, user-supplied API key required | `reqwest` (`blocking` feature), one client module per vendor (Sapling, GPTZero, Copyleaks, Pangram) |

`classifier` and `perplexity` are separate flags (a user can enable one without the other). `api-clients` is one shared flag gating all four vendor clients, since they share the same `reqwest` dependency and trait shape — but at the signal-family level (§2.4), all configured API vendors collapse into a single `CommercialApi` vote, not one vote per vendor, since commercial detectors are often trained/calibrated on overlapping data and are not independent signals.

A `full` meta-feature enables `classifier` and `perplexity` — the local ML tiers — for users who want maximum local coverage in one build. **`full` deliberately excludes `api-clients`**: a convenience build flag should not silently enable third-party data egress once a user later configures a key. Commercial API calls always require the separate, explicit `api-clients` flag.

### 2.3 `Score` — the common result type

```
struct Score {
    backend: String,
    family: SignalFamily,        // which independent signal family this vote belongs to (§2.2)
    human_probability: f32,      // 0.0 (certainly AI) .. 1.0 (certainly human) — a reporting value, not the aggregation currency
    confidence: ConfidenceTier,  // Low | Medium | High
    evidence: Vec<Evidence>,     // line/offset-anchored into Document::raw where applicable
}
```

`human_probability` is the canonical continuous representation for display and JSON output (§3). Pangram's API returns continuous fractions natively; the other three commercial vendors and the deterministic/stylometric backends return coarser labels or thresholds, which map onto fraction *bands* rather than exact points — deliberately chosen so no backend's precision is silently lost on the way in. **This float is reported per backend but is not what aggregation operates on** — see §2.4.

### 2.4 Ensemble aggregation

Aggregation operates on **signal families** (§2.2), not on backends and not directly on `human_probability` floats. This is a deliberate correction from an earlier draft of this spec, which claimed to carry forward `check_ai_tells.py`'s quorum rule without noticing that the Rust redesign changed what the rule counts: the Python votes by family (`vocabulary`, `punctuation`, `burstiness`); a naive Rust port that voted by *backend* would silently make the default two-backend build's `QUORUM = 2` mean unanimity instead of "2 of several agree."

Each signal family, for a given `Document`, produces one discrete vote: `Abstain | Suspicious | Strong` — mirroring `check_ai_tells.py`'s own three-way per-family vote. The vote is discrete, not continuous; the Python original never produces a continuous probability either, and `human_probability` (§2.3) is reported alongside the vote for display, not derived into it. A family whose backend returned `ScoreOutcome::Abstained` or `ScoreOutcome::Failed` for this document contributes no vote at all — excluded from both numerator and denominator, never counted as a "no."

A top-level `detect` command runs every enabled backend, collects one vote per non-abstaining family, and fires a verdict when at least `QUORUM` families agree at `Suspicious` or stronger — the same principle `check_ai_tells.py` uses (an earlier "any one family over threshold" rule produced false positives in the Python version; this quorum is the fix that lesson led to).

**The default build's quorum is explicitly unanimity, stated on purpose, not by accident.** The default (`deterministic` + `stylometric`) build exposes six independent families (`Vocabulary`, `Punctuation`, `Burstiness`, `LexicalDiversity`, `Readability`, `Compression`), not the Python's three, so `QUORUM = 2` here is a much looser bar than the Python's 2-of-3 ever was. This needs its own calibration pass against the evaluation corpus (§8) rather than inheriting the Python constant unexamined. Starting default remains `QUORUM = 2` pending that calibration; it is tunable via config, not hardcoded.

`CommercialApi` contributes exactly one vote regardless of how many vendors are configured (§2.2): computed as a majority (or, if configured, max-confidence) verdict across whichever vendors are active, so correlated commercial signals cannot out-vote the local families by sheer vendor count.

`MlPerplexity` does not vote at all in v1 — see §7 item 4 and §8.

`ConfidenceTier` on each `Score` (§2.3) is reported for display but does not currently weight the vote; a family's vote is binary-strength (`Suspicious`/`Strong`) regardless of its confidence tier. Confidence-weighted voting is a plausible v2 refinement once the evaluation corpus (§8) exists to validate it actually improves accuracy rather than adding an untested knob.

## 3. CLI surface

```
nobotrs detect <path|--stdin>       # score a file or stdin, quorum ensemble verdict + confidence tier (§2.4)
nobotrs lint <path>                 # line-anchored tells report: every backend's evidence, unfiltered by quorum
nobotrs scan <dir>                  # batch lint across a directory (e.g. CI use); deterministic + stylometric only by default
nobotrs config                      # manage API keys, model downloads, enabled backends, availability status
```

`detect` applies the §2.4 quorum and reports one aggregated verdict. `lint` does **not** apply quorum — it reports every backend's raw evidence (including sub-quorum, single-family hits) so a human can see everything a `detect` verdict would have suppressed; this is a deliberate difference, not an oversight. `scan <dir>` runs the `deterministic` + `stylometric` tiers by default (fast, no model downloads, safe for unattended CI); `classifier`/`perplexity`/`api-clients` participate in `scan` only when explicitly enabled via `--features`/config, since a batch directory scan is exactly the case where unbounded model-loading or API cost is most likely to surprise a user.

**Suggested fixes** (in `lint` output) apply to deterministic tell-word/tell-phrase hits, sourced directly from the tell dictionary's `suggested_replacements` field (§11.3) — e.g. "delve" → "look into"/"start" — rather than being generated or templated by nobotrs itself. Stylometric flags (low burstiness, low MTLD, compression-ratio anomalies) get diagnostic explanation but not a templated fix — there's no single correct rewrite for "your sentence-length variance is low," only general guidance. `Evidence` (§2.3) carries a `suggestion: Option<String>` to reflect this: `Some` (populated from the dictionary) for deterministic hits, `None` for stylometric flags where no specific fix applies.

- Argument parsing: `clap` (derive API).
- Human output: colored terminal via `owo-colors` (respects `NO_COLOR`).
- Machine output: `--format json` via `serde`/`serde_json`, for CI/scripting. The JSON shape carries a `schema_version` field from v1 onward; breaking changes to the output shape bump it independently of the crate's own semver, since CI consumers parse the JSON contract, not the crate API.
- Exit codes: `0` = clean, `1` = tells/verdict found, `2` = tool failure (config error, model load failure, network error on a required backend) — standard linter convention, with a dedicated failure code so CI can distinguish "found something" from "the tool itself broke." See §6 for how the plugin's `PostToolUse` hook wrapper translates these.

## 4. Configuration and secrets

- Config file: `~/.config/nobotrs/config.toml` (via the `directories` crate for cross-platform path resolution), permissions tightened to `0600` on Unix.
- Precedence for API keys: environment variable → config file → optional OS keychain via the `keyring` crate (opt-in hardening, not required). This mirrors the precedence pattern used by tools like `gh` and `aws-cli`.
- No commercial API is ever called without an explicit key configured for that specific vendor — enabling the `api-clients` feature at build time does not itself send any data anywhere.
- API keys must never appear in log output, error messages, or `Debug` representations. This is stated explicitly now, before four vendor client modules exist, because it is a well-known, generic Rust footgun (a `reqwest` error or a derived `Debug` impl printing a `String` secret) that is cheap to prevent up front and expensive to retrofit across every client afterward.

## 5. Packaging and distribution

- **Release pipeline:** `cargo-dist` builds and publishes per-platform binaries (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64) to GitHub Releases, auto-generates a Homebrew tap formula, and publishes to crates.io on tag push.
- **Binary size discipline:** default build (deterministic + stylometric only) targets roughly 10MB; `classifier`/`perplexity` features add candle (~50-80MB) or ONNX Runtime (~100-150MB) — these are documented as separate, explicit install paths, not silently bundled into a bloated default. `api-clients` adds negligible size (`reqwest` alone, no ML runtime).

## 6. Plugin packaging (Agent Plugins Specification)

- Manifest at `.plugin/plugin.json` (generic) with a `.claude-plugin/plugin.json` vendor copy for Claude Code's own discovery path, per the spec's documented vendor-precedence rule.
- `skills/detect-ai-writing/SKILL.md` — portable across any conformant harness.
- `hooks/hooks.json` — a `PostToolUse` hook wiring the ambient scan-on-write UX, invoking `bin/nobotrs lint --format json` and translating its exit codes (§3) into the hook protocol's expected codes (Claude Code distinguishes exit 1 "feedback to show" from exit 2 "block," so the wrapper maps `nobotrs`'s `1` (tells found) to the hook's non-blocking-feedback code, never to its blocking code — the ambient scan must never block a write, matching `check_ai_tells.py`'s existing "fails open" behavior). **This component is Claude-Code-only in practice** (OpenCode and Pi use their own native JS/TS event systems rather than consuming `hooks.json`) — the same caveat nobots' own README already documents for its Python hook, carried forward rather than newly introduced.
- `bin/nobotrs` — a thin wrapper script, **not a bundled binary**. It searches (in order): an env var override, `PATH`, well-known install directories; on failure it prints an actionable install message (`cargo install` / `brew install` / direct download link). No plugin repo in the ecosystem was found bundling actual per-platform binaries in-repo — the two real examples found (`nab`, `genasis`) both locate-or-download instead. Claude Code has no `postInstall` hook to lean on for automatic fetch-on-install (the relevant feature request, anthropics/claude-code#9394, is closed as not-planned), so "locate or fail with clear instructions" is the v1 behavior; an automatic-download wrapper is a plausible v2 addition once the binary is actually published via `cargo-dist`. Plugin installation (`/plugin install`) does **not** trigger binary installation — the two are manual, separate steps in v1, and the wrapper's failure message is what bridges that gap.

## 7. Explicit v1 scope-outs and known gaps

These are carried in the design deliberately, not silently dropped:

1. **Dependency-parse-dependent stylometric features** (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence). No pure-Rust dependency parser exists anywhere in the ecosystem (confirmed by dedicated research, not just "none found easily"). Out of scope for v1. A future option, not committed to: an optional Python sidecar shelling out to the existing `deep_stylometry.py`, degrading gracefully when absent.
2. **POS-tag-dependent features** (POS proportions, function/content-word ratio, hedges, amplifiers, nominalizations). The only real pure-Rust option (`postagger.rs`) is unproven/low-maintenance; the higher-confidence option (`rust-bert`'s MobileBERT tagger) only becomes "free" if `tch-rs` is already a dependency for other reasons. Deferred; revisit once the `classifier` tier's ML dependency choice is settled empirically.
3. **Any text generation or auto-rewrite capability.** Confirmed out of scope per product decision — lint-only.
4. **`MlPerplexity` as a voting signal family** (§2.4). GGUF quantization shifts the logit distributions Binoculars' published calibration threshold was tuned against, and there is no data yet to refit that threshold for the quantized numerics nobotrs would actually ship. `perplexity` still ships in v1, feature-gated, and still reports its raw cross-perplexity ratio as evidence — the product decision to include the tier stands — but it is explicitly non-voting until the evaluation corpus (§8) exists to calibrate it properly.

(The `stylometry` (ian-nai/rust_stylometry) crate previously listed here has been dropped — it isn't referenced anywhere in §2.2's actual crate list, and its unverified license created an unnecessary contradiction with §10. If a future need for classic authorship-analysis statistics arises, the same functionality can be hand-rolled the way MTLD and Flesch-Kincaid already are.)

## 8. Testing strategy

- Unit tests per backend against known-AI and known-human text fixtures (the existing `nobots` rubric and any of its test fixtures are a starting corpus).
- The quorum-aggregation logic gets dedicated tests for its false-positive-avoidance behavior (the specific bug class it was designed to prevent in the Python version).
- API-client backends are tested against mocked HTTP responses — no live network calls in the test suite, no requirement for real API keys to run `cargo test`. Mocked responses can't catch upstream vendor schema drift over time; this needs a documented periodic manual re-verification note, not just a one-time integration test.
- `classifier` and `perplexity` backends need a smaller, separate integration-test tier gated behind their own feature flags, since they require model downloads and real compute — not part of the default `cargo test` run.
- CI runs a minimal feature-flag matrix rather than full combinatorial coverage: `default`, each of `classifier`/`perplexity`/`api-clients` isolated, and `full`. This catches feature-interaction bugs without an exponential build matrix.

### 8.1 Evaluation corpus and calibration (prerequisite for tuning any threshold)

No detection threshold in this spec — `QUORUM`, per-family `Suspicious`/`Strong` cutoffs, the eventual `MlPerplexity` calibration in §7 item 4 — ships with a real number behind it without this existing first. Before those constants are finalized:

- Assemble a held-out labeled corpus of known-human and known-AI text (starting point: the existing `nobots` rubric/fixtures, extended with fresh samples across multiple LLM generations, since vocabulary tells are time-bound and generation-specific per the research corpus).
- State an explicit target false-positive rate on human text — this is a product decision (what FPR is acceptable for a linter vs. an accusation-grade tool), not something to leave implicit.
- Every threshold constant in the codebase (`QUORUM`, family-level cutoffs, eventually the perplexity ratio threshold) is tuned against this corpus and the FPR target, not hand-picked, and re-run whenever the corpus grows.
- This calibration pass is what determines whether `QUORUM = 2` is actually right for the default build's six-family quorum (§2.4) — the constant is a starting point, not a conclusion.

## 9. Key open items carried into implementation planning

These are empirical or due-diligence items the plan should sequence early, since they affect architecture decisions downstream:

1. **Prototype candle + `desklib/ai-text-detector-v1.01`** as the first concrete step of the `classifier` tier — the `debertav2` module's existence is confirmed, but nobody has been found to have actually loaded that specific checkpoint into it. `ort` + ONNX export is the documented fallback if it doesn't work cleanly. **At the same priority:** verify the checkpoint's own license (separate from the Rust crates that load it — model weights carry their own, often more restrictive, license terms) permits nobotrs's intended use, before prototyping past a spike. Do the same license check for whatever perplexity-tier model pair is ultimately chosen.
2. **Downloaded model weights are checksum-verified against a pinned hash before load**, for both the `classifier` and `perplexity` tiers — a supply-chain integrity requirement, not just a correctness nicety.
3. **Validate `postagger.rs` accuracy** against a labeled sample before trusting it in any verdict, if/when POS features are picked back up.
4. **Confirm whether embedding CC BY-SA 4.0 dictionary data (§11) inside a compiled MIT-licensed binary creates any obligation on the binary distribution itself**, as opposed to on redistributing the dictionary's JSON data directly (which clearly requires attribution/ShareAlike compliance). Not confidently resolved in this spec — verify before the first tagged release, not just before prototyping.

## 10. Recommended dependency stack

See `docs/research/00-consolidated-summary.md` § "Recommended stack" for the full table. Every crate actually referenced in §2.2's tier definitions is MIT/Apache-2.0/Unlicense family, with one correction already applied: `rust_readability` (GPL-3.0-or-later) is excluded; Flesch-Kincaid is hand-rolled instead. (This section previously also claimed the `stylometry` crate as MIT-family license-verified while §7 correctly flagged the same crate's license as unconfirmed — that contradiction is resolved by dropping the unused `stylometry` dependency entirely, per §7.)

**The one deliberate exception to "everything is MIT/Apache-2.0/Unlicense" is the tell dictionary (§11), which is CC BY-SA 4.0 by design** — a separate, independently-licensed data artifact, not a code dependency, kept in its own subdirectory with its own LICENSE file specifically so this exception is unambiguous rather than silently mixed into the crate's license story.

## 11. Tell dictionary (separately licensed)

The word/phrase tell list ships as its own artifact, `dictionary/`, licensed **CC BY-SA 4.0** — distinct from the rest of the repository (source code, MIT, root `LICENSE`). This is the one place in the project where two licenses coexist by design, called out explicitly in §10.

### 11.1 Why a separate license

A curated word/phrase list is a creative/curatorial dataset, not source code — CC BY-SA 4.0 is the standard choice for this kind of lexical resource. Its ShareAlike clause ensures downstream forks/derivatives of the *dictionary* stay open and attributed, which isn't a concern the MIT-licensed code needs or benefits from. Keeping the two licenses in separate directories with separate `LICENSE` files avoids ambiguity about which terms apply to which files — there is never a file where both licenses could plausibly apply.

### 11.2 Location and contents

- `dictionary/LICENSE` — full CC BY-SA 4.0 text.
- `dictionary/README.md` — states the license, attribution requirements, and schema documentation.
- `dictionary/words.json`, `dictionary/phrases.json` — the actual data, plain JSON (broadest cross-language consumability; no Rust toolchain required to read it).
- A root-level `NOTICE` file states plainly that the repository contains two independently licensed components (code: MIT, root `LICENSE`; dictionary: CC BY-SA 4.0, `dictionary/LICENSE`). This is stated explicitly because nobotrs's compiled binary embeds the dictionary data (§11.4), and anyone redistributing the *dictionary content itself* (forking/republishing the JSON) has ShareAlike/attribution obligations distinct from the code's MIT terms. **Whether bundling CC BY-SA data inside a compiled MIT-licensed binary creates any obligation on the binary distribution itself is a real nuance, not confidently resolved here — see §9 item 4.**

### 11.3 Entry schema (rich records, per product decision)

```json
{
  "schema_version": "1.0.0",
  "dictionary_version": "2026.07.26",
  "entries": [
    {
      "id": "delve",
      "kind": "word",
      "match_type": "exact",
      "pattern": "delve",
      "category": "vocabulary",
      "suggested_replacements": ["look into", "explore", "start"],
      "model_era": ["gpt-3.5", "gpt-4o"],
      "source": null,
      "notes": null
    },
    {
      "id": "not-just-x-but-y",
      "kind": "phrase",
      "match_type": "regex",
      "pattern": "it'?s not just [a-z ]+, it'?s",
      "category": "structural-phrase",
      "suggested_replacements": [],
      "model_era": [],
      "source": null,
      "notes": "negative parallelism"
    }
  ]
}
```

`match_type` tells the `deterministic` tier (§2.2) which matcher to use: `exact` entries feed `aho-corasick`; `regex` entries feed the `regex` crate. `suggested_replacements` feeds `lint`'s `Evidence.suggestion` (§3) directly for word-kind entries — the mechanism §3 refers to as sourced "from the tell dictionary." `model_era` is optional metadata (populated over time, not required at v1 launch) reflecting the research finding that vocabulary tells are time-bound and generation-specific; it is not currently consumed by aggregation (§2.4) but is reserved for a plausible future per-era weighting refinement.

**Scope boundary:** the dictionary covers word- and phrase-level tells expressible as an exact string or a regex pattern. The three structural patterns identified during prior-art review (`docs/research/09-no-ai-slop-review.md`) — colon-reveal, negative-listing, markdown formatting-slop — are not all cleanly regex-expressible (formatting-slop in particular requires counting/structural logic, not string matching) and are therefore implemented as code-level checks within the `deterministic` backend, not as dictionary entries, even though negative-listing and colon-reveal may end up regex-representable in practice. This keeps the dictionary schema honest: an entry describes a match rule any consumer, in any language, can apply directly from the JSON — not a rule that requires nobotrs's specific code to interpret.

### 11.4 Consumption

nobotrs embeds `dictionary/*.json` at compile time (`include_str!` / a small `build.rs`) so the shipped binary stays single-file and works fully offline — no network fetch needed at runtime for the `deterministic` tier's data. The JSON files in `dictionary/` remain the canonical, independently fetchable source: any tool, in any language, can read them directly from the repository without depending on nobotrs itself. Publishing the dictionary to a stable CDN URL or a package registry (npm/PyPI-style, for easier non-Rust consumption than "clone the repo") is a plausible v2 addition, not committed to for v1.

### 11.5 Versioning

The dictionary carries its own `schema_version` (format stability, mirroring §3's JSON output `schema_version` pattern) and `dictionary_version` (content revision, independent of the nobotrs crate's own semver) — the two evolve on different cadences: the schema should rarely change, while entries get added/refined much more often as new model-era vocabulary tells are identified. Seed content: `check_ai_tells.py`'s existing word/phrase lists, plus the vocabulary/phrase findings from `docs/research/09-no-ai-slop-review.md` (facilitate, empower, robust, cutting-edge, paradigm shift, harness; "here's the thing," "let me be clear," "the uncomfortable truth is," "experts agree," "studies show," "that's it, that's the [x]").

`candle` is pre-1.0 — no MSRV/pinning policy is stated here yet; pin an exact version in `Cargo.lock` and revisit pinning strategy once the `classifier`/`perplexity` prototypes (§9) are underway. Rust edition and MSRV otherwise follow current stable Rust at implementation start, stated explicitly in `Cargo.toml` rather than left implicit. A single-crate-with-features layout (not a Cargo workspace split) is sufficient for v1, consistent with research report 05's conclusion — revisit only if the optional heavy dependencies start causing real build-graph friction in practice. `nobotrs` makes no telemetry or usage-data calls of any kind; this follows directly from the local-first goal in §1 but is stated here explicitly rather than left to be inferred.
