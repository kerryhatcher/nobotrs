# nobotrs: Rust CLI for AI-text detection — design spec

**Status:** Draft, pending user review
**Date:** 2026-07-26
**Research basis:** `docs/research/00-consolidated-summary.md` and its eight source reports, which themselves drew on prior art at `/mnt/storage/grimoire/research/open-plugins-spec/` (used directly by report 07).
**Revision note (2026-07-26, post-review):** revised per `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design-review.md`, a 5-agent (Opus/Sonnet×2/Haiku×2) review round plus independent Sonnet verification. See that file for the full findings; this revision applies all 8 Blocker and 11 Important items.
**Revision note (2026-07-26, dictionary addition):** adds §11, a separately CC BY-SA 4.0–licensed tell dictionary, per product decision. Cross-referenced from §2.2, §3, §9, and §10.
**Revision note (2026-07-26, adversarial review):** incorporates findings from two external adversarial reviews (`2026-07-26-nobotrs-rust-cli-design-review-ds-4-flash.md`, `...-reivew-gemma4-12b.md`) plus independent verification of their checkable technical claims. Most-severe fixes: defines the `Error` type and distinguishes recoverable failures from silent verdict-masking (a "false green" risk both reviews converged on independently); adds a NaN/infinity contract on `human_probability`; defines the previously-unspecified `Evidence` struct and the aho-corasick/regex vote-composition rule; reframes the CC BY-SA/MIT binary question as an explicit two-option decision rather than a deferred TBD. One reviewer claim (Rust trait-object default-method dispatch) was checked and found incorrect — not applied. See the verification notes inline where relevant.

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

enum Error {
    ModelMissing,               // recoverable: run `nobotrs config` to download
    ModelLoadFailed(String),    // recoverable: retry; may indicate a corrupt install
    ChecksumMismatch,           // unrecoverable without reinstalling: pinned hash didn't match (§9 item 2)
    NetworkError(String),       // recoverable: transient, retry
    ConfigError(String),        // recoverable: user must fix config, not a retry
    InternalError(String),      // bug in nobotrs itself
}

impl Error {
    fn is_recoverable(&self) -> bool { !matches!(self, Error::ChecksumMismatch | Error::InternalError(_)) }
}

enum ScoreOutcome {
    Scored(Score),
    Abstained { reason: String },     // e.g. "text too short for burstiness", "non-English text" — not applicable, not a failure
    Failed(Error),                    // backend errored — distinct from abstention, and itself distinguishes recoverable vs. not
}

trait DetectorBackend: Send + Sync {
    fn name(&self) -> &str;
    fn family(&self) -> SignalFamily;              // which independent signal family this backend's vote belongs to (§2.2)
    fn availability(&self) -> Availability;         // model/network readiness, surfaced by `nobotrs config`
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome;
    fn score_batch(&self, docs: &[Document], deadline: Deadline) -> Vec<ScoreOutcome> { /* default: map score() */ }
}
```

`Document` replaces a bare `&str` as the trait's input. Evidence needs byte/line offsets into the *original* file for `lint`'s line-anchored output, while stylometric measures need prose-only content — code fences and YAML front matter would otherwise corrupt burstiness/MTLD/readability numbers. Segmentation is markdown-aware at minimum for v1; `content_type` names the strategy explicitly so other formats can be added later without changing the trait shape. `prose_spans` is computed exactly once, at `Document::new()`, and stored — not recomputed per backend; six default backends re-parsing markdown per file would be a real cost on `scan <dir>` over a large tree, and the spec states the O(file-size × 1) cost explicitly to rule that out. `content_type` is determined primarily by file extension (`.md`/`.markdown` → `Markdown`, else `PlainText`); for `detect -`/stdin, where no extension exists, content defaults to `PlainText` unless `--markdown` is passed explicitly — this is a deliberate default (safe, no false-positive code-fence stripping on plain input), not an oversight, and is called out here because it was previously unstated.

`ScoreOutcome` gives a backend a real way to say "not applicable to this input" (`Abstained`) distinct from "something broke" (`Failed`) — matching `check_ai_tells.py`'s own documented behavior, where a family that can't be measured (e.g. burstiness on a short file) simply abstains rather than voting either way. Both `Abstained` and `Failed` are excluded from the vote count in aggregation (§2.4) — neither counts as a "no" — but they are *not* treated identically everywhere: `Failed` additionally surfaces as a `warning` on `detect`'s output (§2.4), because a backend that broke silently is a materially different situation from one that legitimately had nothing to say, and collapsing the two risks a "clean" verdict that's actually just a broken backend (a risk two independent reviews converged on: a stuck/corrupted `classifier` model could otherwise let `detect` report "human-written" when it simply never got to vote). `Error`'s variants are deliberately split so callers (the `config` command, `detect`'s warning surface, log output) can distinguish recoverable conditions (retry, re-download, fix config) from ones that need a reinstall.

`Send + Sync` supports `scan <dir>`'s batch use (§3); `score_batch` gives ML-backed backends (`classifier`, `perplexity`) a seam to batch multiple documents through one model load instead of reloading per file. Model acquisition (downloading and caching weights via `hf-hub`) is out of the trait itself — `availability()` reports readiness, and `nobotrs config` (§3) is what triggers a download.

**Deadlines, size limits, and FFI failure modes.** `score`/`score_batch` take a `Deadline` (a simple wall-clock cutoff) so a hung model load or a slow API call can't block `detect`/`scan` indefinitely — the `api` tier's `reqwest` clients default to a 30s HTTP timeout; local ML tiers get a generous but finite default deadline, configurable. `detect`/`scan` also enforce a file-size cap (skip files above a configurable threshold, default in the tens of MB, with a warning rather than an OOM) — the same lesson ripgrep and tree-sitter both encode structurally, applied here because `Document::raw` holds a file fully in memory. Separately, and not fully solvable at the Rust level: `classifier` and `perplexity` cross an FFI boundary into C/C++ ML runtimes (candle's CUDA/Metal backends, `llama-cpp-2`), and a hard crash there (segfault, abort) is not a catchable Rust panic — `catch_unwind` cannot intercept a signal. This is accepted as a stated v1 limitation, not solved: input validation before handing text to these backends is the primary mitigation, not exception handling. Running multiple ML backends concurrently (e.g. `scan <dir>` parallelizing across files with `classifier` enabled) additionally needs a concurrency model this spec does not prescribe — `candle`'s GPU backends are not safely shared across threads by default, so implementation planning must pick one of: per-thread model instances (simple, costs RAM per thread), a mutex around inference (simple, serializes GPU work), or a dedicated inference thread with message-passing (best throughput, more code) before `scan` is allowed to parallelize the ML tiers.

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

**How `aho-corasick` word-hits and `regex` phrase-hits combine into one vote:** both feed the single `Vocabulary` family, not two separate families — this mirrors `check_ai_tells.py` exactly, where tell-words and tell-phrases were already one combined "vocabulary" signal, not split. A word hit and a phrase hit are not weighted differently by match type; the `Vocabulary` family's vote strength (`Suspicious`/`Strong`) is a hit-count threshold across both matchers combined, tuned against the evaluation corpus (§8.1) like every other threshold in this design — not hand-picked, and not something this spec fixes a specific number for.

### 2.3 `Score` — the common result type

```
struct Score {
    backend: String,
    family: SignalFamily,        // which independent signal family this vote belongs to (§2.2)
    human_probability: f32,      // 0.0 (certainly AI) .. 1.0 (certainly human) — a reporting value, not the aggregation currency
    confidence: ConfidenceTier,  // Low | Medium | High
    evidence: Vec<Evidence>,     // line/offset-anchored into Document::raw where applicable
}

struct Evidence {
    raw_offset: Range<usize>,     // byte range into Document::raw — what an editor/lint annotation points at
    prose_offset: Range<usize>,   // byte range into the matched prose span — what stylometric measures computed over
    line: u32,
    column: u32,
    matched_text: String,         // the actual substring that triggered this evidence
    severity: Severity,           // Low | Medium | High
    suggestion: Option<String>,   // populated from the dictionary (§11.3) for deterministic hits; None otherwise (§3)
}
```

`human_probability` is the canonical continuous representation for display and JSON output (§3). Pangram's API returns continuous fractions natively; the other three commercial vendors and the deterministic/stylometric backends return coarser labels or thresholds, which map onto fraction *bands* rather than exact points — deliberately chosen so no backend's precision is silently lost on the way in. **This float is reported per backend but is not what aggregation operates on** — see §2.4.

**`human_probability` must never be NaN or infinite.** `f32` permits both, and neither is a meaningful probability. This is stated as a hard contract, not a guideline: a backend that emits `NaN` produces a value where every comparison (`> 0.5`, `< 0.5`, `== 0.5`) is false, which would silently corrupt any thresholding logic without a test ever catching it, since nothing panics. The aggregation boundary validates/clamps this at construction (implementation detail for planning; the spec's commitment is the contract, not the exact enforcement mechanism). Relatedly: `f32` does not implement `Ord` (only `PartialOrd`), precisely because of `NaN`. Anywhere this spec's aggregation or output logic sorts or ranks `Score`s by `human_probability`, it must use `f32::total_cmp` or explicit `partial_cmp` handling — never assume `Ord` is available.

`Evidence`'s two offset fields are deliberately distinct: `raw_offset` is what `lint` points an editor at (position in the file the user actually wrote), while `prose_offset` is the position within the extracted prose span a stylometric backend actually measured — these differ whenever code fences or front matter precede the match, and conflating them would point evidence at the wrong byte in one direction or the other.

### 2.4 Ensemble aggregation

Aggregation operates on **signal families** (§2.2), not on backends and not directly on `human_probability` floats. This is a deliberate correction from an earlier draft of this spec, which claimed to carry forward `check_ai_tells.py`'s quorum rule without noticing that the Rust redesign changed what the rule counts: the Python votes by family (`vocabulary`, `punctuation`, `burstiness`); a naive Rust port that voted by *backend* would silently make the default two-backend build's `QUORUM = 2` mean unanimity instead of "2 of several agree."

Each signal family, for a given `Document`, produces one discrete vote: `Abstain | Suspicious | Strong` — mirroring `check_ai_tells.py`'s own three-way per-family vote. The vote is discrete, not continuous; the Python original never produces a continuous probability either, and `human_probability` (§2.3) is reported alongside the vote for display, not derived into it. A family whose backend returned `ScoreOutcome::Abstained` or `ScoreOutcome::Failed` for this document contributes no vote at all — excluded from both numerator and denominator, never counted as a "no."

A top-level `detect` command runs every enabled backend, collects one vote per non-abstaining family, and fires a verdict when at least `QUORUM` families agree at `Suspicious` or stronger — the same principle `check_ai_tells.py` uses (an earlier "any one family over threshold" rule produced false positives in the Python version; this quorum is the fix that lesson led to).

**`detect`'s output is a `verdict` plus a separate `warnings` list, not just a verdict.** `verdict` is one of `Flagged` (quorum met), `Clean` (quorum not met, and every enabled family that could vote actually voted or legitimately abstained), or — the state that did not exist in an earlier draft of this spec — the output additionally carries `warnings: Vec<{ family: SignalFamily, error: Error }>` populated whenever a family's backend returned `Failed`. A `Clean` verdict with a non-empty `warnings` list means something different from a `Clean` verdict with an empty one: the former is "quorum wasn't met, but also not every family that should have voted actually could" (e.g. a corrupted `classifier` model, a config with `api-clients` enabled but no working network), and both `nobotrs detect`'s human output and its `--format json` output must surface that distinction rather than collapsing both cases into an indistinguishable "clean." This closes a real gap: without it, a broken backend and a genuinely clean document produce byte-identical `detect` output.

**The default build's quorum is explicitly unanimity, stated on purpose, not by accident.** The default (`deterministic` + `stylometric`) build exposes six independent families (`Vocabulary`, `Punctuation`, `Burstiness`, `LexicalDiversity`, `Readability`, `Compression`), not the Python's three, so `QUORUM = 2` here is a much looser bar than the Python's 2-of-3 ever was. This needs its own calibration pass against the evaluation corpus (§8) rather than inheriting the Python constant unexamined. Starting default remains `QUORUM = 2` pending that calibration; it is tunable via config, not hardcoded.

`CommercialApi` contributes exactly one vote regardless of how many vendors are configured (§2.2): computed as a majority (or, if configured, max-confidence) verdict across whichever vendors are active, so correlated commercial signals cannot out-vote the local families by sheer vendor count.

`MlPerplexity` does not vote at all in v1 — see §7 item 4 and §8.

`ConfidenceTier` on each `Score` (§2.3) is reported for display but does not currently weight the vote; a family's vote is binary-strength (`Suspicious`/`Strong`) regardless of its confidence tier. Confidence-weighted voting is a plausible v2 refinement once the evaluation corpus (§8) exists to validate it actually improves accuracy rather than adding an untested knob.

## 3. CLI surface

```
nobotrs detect <path|->            # score a file or stdin (- follows UNIX convention, e.g. `cat f | nobotrs detect -`), quorum ensemble verdict + confidence tier (§2.4)
nobotrs lint <path>                 # line-anchored tells report: every backend's evidence, unfiltered by quorum
nobotrs scan <dir>                  # batch lint across a directory (e.g. CI use); deterministic + stylometric only by default
nobotrs config                      # manage API keys, model downloads, enabled backends, availability status
```

`-` (not a `--stdin` flag) is how `detect` reads from stdin, matching the standard UNIX convention used by `grep`, `ripgrep`, and most composable CLI tools — a bespoke `--stdin` flag would duplicate behavior most users already expect from the dash.

`detect` applies the §2.4 quorum and reports one aggregated verdict (plus `warnings`, §2.4). `lint` does **not** apply quorum — it reports every backend's raw evidence (including sub-quorum, single-family hits) so a human can see everything a `detect` verdict would have suppressed; this is a deliberate difference, not an oversight. `scan <dir>` runs the `deterministic` + `stylometric` tiers by default (fast, no model downloads, safe for unattended CI); `classifier`/`perplexity`/`api-clients` participate in `scan` only when explicitly enabled via `--features`/config, since a batch directory scan is exactly the case where unbounded model-loading or API cost is most likely to surprise a user.

`scan <dir>` applies default ignore patterns (`.git/`, `node_modules/`, common binary/compiled-artifact extensions — the same category of lesson ripgrep's default ignore list encodes) and prints a summary line (files analyzed / skipped / excluded) rather than silently reporting "clean" on a directory that was mostly vendored binaries and never actually analyzed anything. `scan`'s exit code follows standard linter convention: exit `1` if any file in the tree triggers a `detect`-equivalent quorum verdict (the same behavior `eslint`/`ruff`/most linters default to — noisy-by-default on a large repo is the expected, not surprising, behavior for this class of tool); a per-file flagged-ratio threshold is a plausible v2 configuration knob, not required for v1.

**Suggested fixes** (in `lint` output) apply to deterministic tell-word/tell-phrase hits, sourced directly from the tell dictionary's `suggested_replacements` field (§11.3) — e.g. "delve" → "look into"/"start" — rather than being generated or templated by nobotrs itself. Stylometric flags (low burstiness, low MTLD, compression-ratio anomalies) get diagnostic explanation but not a templated fix — there's no single correct rewrite for "your sentence-length variance is low," only general guidance. `Evidence` (§2.3) carries a `suggestion: Option<String>` to reflect this: `Some` (populated from the dictionary) for deterministic hits, `None` for stylometric flags where no specific fix applies.

- Argument parsing: `clap` (derive API).
- Human output: colored terminal via `owo-colors`, **with its `supports-colors` Cargo feature explicitly enabled** — verified against the crate's own source: `owo-colors` ships with no default features at all, and `NO_COLOR`/`FORCE_COLOR` detection is entirely absent unless `supports-colors` is turned on. Stating this explicitly here because the earlier draft's "(respects `NO_COLOR`)" was true only conditionally, not by default.
- Machine output: `--format json` via `serde`/`serde_json`, for CI/scripting. The JSON shape carries a `schema_version` field from v1 onward; breaking changes to the output shape bump it independently of the crate's own semver, since CI consumers parse the JSON contract, not the crate API. **The concrete v1 schema (exact field names/shapes per command) is an implementation-planning deliverable, not specified here** — §2.3's `Score`/`Evidence` struct sketches are its foundation, but the actual wire format, and what a terminal `lint` report visually looks like, need a UX pass during planning; this spec has been architecturally reviewed, not UX-reviewed, and that gap is stated explicitly rather than left implicit.
- Exit codes: `0` = clean, `1` = tells/verdict found, `2` = tool failure (config error, model load failure, network error on a required backend) — standard linter convention, with a dedicated failure code so CI can distinguish "found something" from "the tool itself broke." See §6 for how the plugin's `PostToolUse` hook wrapper translates these.

### 3.1 v1 definition of done

The primary v1 user is an individual developer or a CI pipeline checking prose files (READMEs, docs, PR descriptions) for AI-writing tells — not a platform team running accusation-grade audits at scale; that use case needs the calibration rigor of §8.1 before it's responsible to support, and this spec does not claim v1 is ready for it. The minimum "must work" scenario: `nobotrs detect README.md` on the default build (no feature flags, no model downloads) returns a verdict in well under a second, fully offline. v1 is ready to ship when: the default build's measured false-positive rate on the §8.1 evaluation corpus is below its stated target, all Blocker items from both review rounds are resolved, and `cargo install nobotrs` / the Homebrew tap both work end-to-end on a clean machine. Without this stated somewhere, the spec's five tiers and four commands have no stopping rule for when implementation is "done enough" — this section is that stopping rule.

## 4. Configuration and secrets

- Config file: resolved via the `directories` crate, **not a hardcoded Unix path** — the earlier draft's `~/.config/nobotrs/config.toml` is the Linux path only. Actual resolved paths per platform:

  | Platform | Config path |
  |---|---|
  | Linux | `~/.config/nobotrs/config.toml` |
  | macOS | `~/Library/Application Support/com.nobotrs.nobotrs/config.toml` |
  | Windows | `C:\Users\<user>\AppData\Roaming\nobotrs\nobotrs\config.toml` |

  Documentation and `nobotrs config`'s own help text must reference "your platform's config directory" (or print the resolved path directly), not the Linux path specifically. File permissions are restricted on every platform, but the mechanism is platform-specific: `0600` on Unix, an equivalent ACL restriction on Windows — stated generically here because "tightened to `0600`" (the earlier wording) is meaningless on Windows.
- Precedence for API keys: environment variable → config file → optional OS keychain via the `keyring` crate (opt-in hardening, not required). This mirrors the precedence pattern used by tools like `gh` and `aws-cli`. `keyring` is deliberately opt-in rather than a default part of the precedence chain because its Linux backend depends on the Secret Service D-Bus API (via `zbus`) — commonly absent on headless CI runners with no D-Bus session running, where it would fail with a platform-specific error a non-expert user can't easily diagnose. CI users should rely on the environment-variable method, which has no such dependency; this is the practical reason `keyring` is hardening, not the primary mechanism.
- No commercial API is ever called without an explicit key configured for that specific vendor — enabling the `api-clients` feature at build time does not itself send any data anywhere.
- API keys must never appear in log output, error messages, or `Debug` representations — and this needs to be enforced at more surfaces than "don't log the key directly": `reqwest::Error` can include the request URL, so vendor clients that pass a key as a query parameter must sanitize the URL before it's ever logged; a panic or `unwrap()` inside a vendor client's request-building code must not let the default panic hook print a key held in a local variable; any future `--verbose`/`--debug` flag must redact secret values in its output by design, not by later patch; and error messages must never echo a misconfigured secret's *value* back to the user (echoing the *variable name*, e.g. "SAPLING_API_KEY is not set," is fine and helpful — echoing what the user typed for it is not). This is stated explicitly now, before four vendor client modules exist, because it is a well-known, generic Rust footgun that is cheap to prevent up front and expensive to retrofit across every client afterward.

## 5. Packaging and distribution

- **Release pipeline:** `cargo-dist` builds and publishes per-platform binaries (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64) to GitHub Releases, auto-generates a Homebrew tap formula, and publishes to crates.io on tag push. `cargo-dist`'s checksum generation is enabled for every release artifact, and the auto-generated Homebrew formula pins a SHA256 checksum — a user downloading a GitHub Release binary has a way to verify it wasn't tampered with in transit. `cargo install nobotrs` trusts the full dependency tree at build time; for a tool whose entire purpose is resisting adversarial input, an unaudited dependency tree is a real (if generic) supply-chain risk — CI runs `cargo deny` (or equivalent dependency-audit tooling) as a stated policy, not an aspiration.
- **Binary size discipline:** default build (deterministic + stylometric only) targets roughly 10MB; `classifier`/`perplexity` features add candle (~50-80MB) or ONNX Runtime (~100-150MB) — these are documented as separate, explicit install paths, not silently bundled into a bloated default. `api-clients` adds negligible size (`reqwest` alone, no ML runtime).
- **Explicitly not v1 scope:** Nix flake packaging, a `cargo nobotrs` subcommand alias, and a WASM build target are all plausible future distribution channels with no v1 commitment — `cargo-dist`, crates.io, and Homebrew are the only channels this spec commits to. Named here so the absence reads as a scope decision, not an oversight.

## 6. Plugin packaging (Agent Plugins Specification)

- Manifest at `.plugin/plugin.json` (generic) with a `.claude-plugin/plugin.json` vendor copy for Claude Code's own discovery path, per the spec's documented vendor-precedence rule.
- `skills/detect-ai-writing/SKILL.md` — portable across any conformant harness.
- `hooks/hooks.json` — a `PostToolUse` hook wiring the ambient scan-on-write UX, invoking `bin/nobotrs lint --format json` and translating its exit codes (§3) into the hook protocol's expected codes (Claude Code distinguishes exit 1 "feedback to show" from exit 2 "block," so the wrapper maps `nobotrs`'s `1` (tells found) to the hook's non-blocking-feedback code, never to its blocking code — the ambient scan must never block a write, matching `check_ai_tells.py`'s existing "fails open" behavior). **This component is Claude-Code-only in practice** (OpenCode and Pi use their own native JS/TS event systems rather than consuming `hooks.json`) — the same caveat nobots' own README already documents for its Python hook, carried forward rather than newly introduced.
- `bin/nobotrs` — a thin wrapper, **not a bundled binary**, and **not a single Bash script** — Bash alone doesn't cover Windows without WSL/Git Bash, and this spec commits to real cross-platform support (§5), so a Bash-only wrapper would be a silent gap for Windows-native users. v1 ships an `sh`/`bash` wrapper for Linux/macOS and a `.ps1` companion for Windows (both doing the same search), or, if implementation planning finds that simpler to maintain, a tiny statically-linked Rust binary that does nothing but the search-and-locate logic (same idea `nab`/`genasis` use, minus the shell-vs-PowerShell duplication). Search order (in order): an env var override, `PATH`, well-known install directories per platform (`~/.cargo/bin`, `/opt/homebrew/bin`, `/usr/local/bin` on Unix; `%USERPROFILE%\.cargo\bin` on Windows) — resolved generically the same way §4's config path table is, not hardcoded to one platform. If multiple installed versions are found (e.g. both a Homebrew and a `cargo install` copy), the wrapper picks the first match in search order and this is stated as the resolution rule, not left to be environment-dependent surprise. On failure it prints an actionable install message: the exact `cargo install` command, the `brew install` command, and a direct GitHub Release download URL, all as plain text (not tool-specific formatting). No plugin repo in the ecosystem was found bundling actual per-platform binaries in-repo — the two real examples found (`nab`, `genasis`) both locate-or-download instead. Claude Code has no `postInstall` hook to lean on for automatic fetch-on-install (the relevant feature request, anthropics/claude-code#9394, is closed as not-planned), so "locate or fail with clear instructions" is the v1 behavior; an automatic-download wrapper is a plausible v2 addition once the binary is actually published via `cargo-dist`. Plugin installation (`/plugin install`) does **not** trigger binary installation — the two are manual, separate steps in v1, and the wrapper's failure message is what bridges that gap.

## 7. Explicit v1 scope-outs and known gaps

These are carried in the design deliberately, not silently dropped:

1. **Dependency-parse-dependent stylometric features** (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence). No pure-Rust dependency parser exists anywhere in the ecosystem (confirmed by dedicated research, not just "none found easily"). Out of scope for v1. A future option, not committed to: an optional Python sidecar shelling out to the existing `deep_stylometry.py`, degrading gracefully when absent.
2. **POS-tag-dependent features** (POS proportions, function/content-word ratio, hedges, amplifiers, nominalizations). The only real pure-Rust option (`postagger.rs`) is unproven/low-maintenance; the higher-confidence option (`rust-bert`'s MobileBERT tagger) only becomes "free" if `tch-rs` is already a dependency for other reasons. Deferred; revisit once the `classifier` tier's ML dependency choice is settled empirically.
3. **Any text generation or auto-rewrite capability.** Confirmed out of scope per product decision — lint-only.
4. **`MlPerplexity` as a voting signal family** (§2.4). GGUF quantization shifts the logit distributions Binoculars' published calibration threshold was tuned against, and there is no data yet to refit that threshold for the quantized numerics nobotrs would actually ship. `perplexity` still ships in v1, feature-gated, and still reports its raw cross-perplexity ratio as evidence — the product decision to include the tier stands — but it is explicitly non-voting until the evaluation corpus (§8) exists to calibrate it properly. **This non-voting status must be impossible to miss, not a footnote a user has to already know to look for**: a user who enables `perplexity` has downloaded 8-10GB of model weights, and if `nobotrs detect`'s output doesn't make it obvious that the tier they paid that cost for isn't influencing the verdict, that's a bad experience masquerading as a subtle design nuance. Both `nobotrs detect` and `nobotrs config`'s output must state plainly, unmissably: "Perplexity tier: experimental, evidence-only, does not affect verdicts" — this is a UX requirement carried into implementation, not just an internal aggregation rule.

(The `stylometry` (ian-nai/rust_stylometry) crate previously listed here has been dropped — it isn't referenced anywhere in §2.2's actual crate list, and its unverified license created an unnecessary contradiction with §10. If a future need for classic authorship-analysis statistics arises, the same functionality can be hand-rolled the way MTLD and Flesch-Kincaid already are.)

## 8. Testing strategy

- Unit tests per backend against known-AI and known-human text fixtures (the existing `nobots` rubric and any of its test fixtures are a starting corpus).
- The quorum-aggregation logic gets dedicated tests for its false-positive-avoidance behavior (the specific bug class it was designed to prevent in the Python version).
- API-client backends are tested against mocked HTTP responses — no live network calls in the test suite, no requirement for real API keys to run `cargo test`. Mocked responses can't catch upstream vendor schema drift over time; this needs a documented periodic manual re-verification note, not just a one-time integration test.
- `classifier` and `perplexity` backends need a smaller, separate integration-test tier gated behind their own feature flags, since they require model downloads and real compute — not part of the default `cargo test` run.
- CI runs a minimal feature-flag matrix rather than full combinatorial coverage: `default`, each of `classifier`/`perplexity`/`api-clients` isolated, and `full`. This catches feature-interaction bugs without an exponential build matrix.
- Hand-rolled stylometric formulas (MTLD, Flesch-Kincaid — §10) are unit-tested against published reference test vectors (known texts with known, citable MTLD/Flesch-Kincaid scores), not just checked for internal self-consistency — a hand-rolled formula that's internally consistent but diverges from the standard algorithm is a correctness bug that self-consistency tests alone won't catch.
- Every dictionary (§11) regex pattern is compiled in CI with a bounded-time limit (confirmed against the `regex` crate's own documentation: compile-time cost for counted repetitions can blow up combinatorially even though *matching* is linear-time — the crate ships a `size_limit` builder option precisely because this is a real, acknowledged resource-exhaustion vector, not a theoretical one). A pattern that fails the bounded-time compile check fails CI, not silently degrades at runtime.
- Timeout/deadline behavior (§2.1) has dedicated tests: a backend that never returns must not hang `detect`/`scan` past its configured deadline.

### 8.1 Evaluation corpus and calibration (prerequisite for tuning any threshold)

No detection threshold in this spec — `QUORUM`, per-family `Suspicious`/`Strong` cutoffs, the eventual `MlPerplexity` calibration in §7 item 4 — ships with a real number behind it without this existing first. Before those constants are finalized:

- Assemble a held-out labeled corpus of known-human and known-AI text (starting point: the existing `nobots` rubric/fixtures, extended with fresh samples across multiple LLM generations, since vocabulary tells are time-bound and generation-specific per the research corpus).
- State an explicit target false-positive rate on human text — this is a product decision (what FPR is acceptable for a linter vs. an accusation-grade tool), not something to leave implicit.
- Every threshold constant in the codebase (`QUORUM`, family-level cutoffs, eventually the perplexity ratio threshold) is tuned against this corpus and the FPR target, not hand-picked, and re-run whenever the corpus grows.
- This calibration pass is what determines whether `QUORUM = 2` is actually right for the default build's six-family quorum (§2.4) — the constant is a starting point, not a conclusion.
- **The corpus has a shelf life and needs a refresh cadence, not a one-time build.** §8's own premise — "vocabulary tells are time-bound and generation-specific" — means a corpus built from today's model generations stops being representative as newer models ship; thresholds tuned against a stale corpus decay silently rather than failing loudly. Corpus refresh (and re-tuning every threshold constant against the refreshed corpus) is an ongoing maintenance commitment — a starting cadence of roughly annual refresh, revisited if new model generations ship faster than that in practice.

## 9. Key open items carried into implementation planning

These are empirical or due-diligence items the plan should sequence early, since they affect architecture decisions downstream:

1. **Prototype candle + `desklib/ai-text-detector-v1.01`** as the first concrete step of the `classifier` tier — the `debertav2` module's existence is confirmed, but nobody has been found to have actually loaded that specific checkpoint into it. `ort` + ONNX export is the documented fallback if it doesn't work cleanly. **At the same priority:** verify the checkpoint's own license (separate from the Rust crates that load it — model weights carry their own, often more restrictive, license terms) permits nobotrs's intended use, before prototyping past a spike. Do the same license check for whatever perplexity-tier model pair is ultimately chosen.
2. **Downloaded model weights are checksum-verified against a pinned hash before load**, for both the `classifier` and `perplexity` tiers — a supply-chain integrity requirement, not just a correctness nicety.
3. **Validate `postagger.rs` accuracy** against a labeled sample before trusting it in any verdict, if/when POS features are picked back up.
4. **Resolve the CC BY-SA/MIT binary question (§11) before the first tagged release — this blocks distribution, not just prototyping.** Two concrete options, not a vague "verify later":
   - **(a) Embed at compile time** (§11.4's original design: `include_str!`, single-file binary, works out of the box for every install path including `cargo install`) — requires an actual legal opinion that distributing a compiled binary containing embedded CC BY-SA content does not obligate the binary itself under CC BY-SA's terms.
   - **(b) Load at runtime from a sibling file**, distributed alongside the binary in the same release package (GitHub Release tarball, Homebrew formula's `share/` install) rather than compiled in — architecturally cleaner (the two licenses never end up in the same compiled artifact, similar to how GPL/non-GPL code is conventionally kept as separate processes/files rather than statically linked), but has a real, unsolved cost: `cargo install nobotrs` only produces the binary, with no general Cargo mechanism to also place a sibling data file at a known runtime path — this install path would need its own story (e.g. a required one-time `nobotrs config fetch-dictionary` step, which arguably regresses the "works offline out of the box" goal for that specific install method) before (b) is actually complete.
   
   Neither option is committed to yet. This needs a real decision — informed by actual legal input on (a), not just architectural preference — before implementation starts on §11, not discovered after the binary already ships.
5. **Establish an explicit fallback preference order across `candle`, `ort`, and `llama-cpp-2`, tested per target platform in CI** — not just documented as "candle first, ort as fallback" (§2.2) with no verification that both paths actually work identically. A binary distribution where `classifier` silently uses a different backend on Windows than on Linux because of a missing system library is a non-deterministic UX bug users would discover by accident, not by design. CI needs a distinct build/test job per platform × backend-path combination this fallback can take.

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
- A root-level `NOTICE` file states plainly that the repository contains two independently licensed components (code: MIT, root `LICENSE`; dictionary: CC BY-SA 4.0, `dictionary/LICENSE`). Anyone redistributing the *dictionary content itself* (forking/republishing the JSON) has ShareAlike/attribution obligations distinct from the code's MIT terms, regardless of how the binary consumes it. **Whether the binary embeds this data at compile time or loads it at runtime from a sibling file is an open, undecided question — see §9 item 4, which frames it as two concrete options rather than a settled design.** §11.4 below describes both.

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

**Conflicting/overlapping suggestions.** If two entries match overlapping spans of text (e.g. a `"delve"` entry and a `"delve into"` phrase entry both matching "delve into the details"), `lint` needs a defined priority rule rather than emitting two contradictory suggestions for the same text: **longest match wins.** The narrower entry's match is suppressed when it's fully contained within a longer match from another entry; this is a simple, deterministic rule that doesn't require entry-authoring-order to matter (a property worth preserving given the dictionary is meant for external contribution, §11.5).

**Regex entries and compile-time cost.** Because the dictionary accepts external contributions and its `regex`-kind entries are compiled at runtime via `regex::Regex::new()`, a poorly-formed pattern (nested repetitions, large character classes) can be expensive to *compile* even though the `regex` crate guarantees linear-time *matching* — this is a real, crate-documented resource-exhaustion vector (see §8's CI requirement), not a theoretical one. Mitigations: every dictionary regex is compile-tested with a bounded time limit in CI (§8) before it can be merged, and entries are compiled with `RegexBuilder::size_limit` set to a conservative bound at runtime rather than the crate's unbounded default, so a pattern that somehow slips past CI still fails safely (the entry's `Vocabulary` family vote treats a compile failure as `Abstained`, not a panic or a hang).

**Scope boundary:** the dictionary covers word- and phrase-level tells expressible as an exact string or a regex pattern. The three structural patterns identified during prior-art review (`docs/research/09-no-ai-slop-review.md`) — colon-reveal, negative-listing, markdown formatting-slop — are not all cleanly regex-expressible (formatting-slop in particular requires counting/structural logic, not string matching) and are therefore implemented as code-level checks within the `deterministic` backend, not as dictionary entries, even though negative-listing and colon-reveal may end up regex-representable in practice. This keeps the dictionary schema honest: an entry describes a match rule any consumer, in any language, can apply directly from the JSON — not a rule that requires nobotrs's specific code to interpret.

### 11.4 Consumption

**Not yet decided — see §9 item 4.** Two options are on the table, and implementation planning must pick one with actual legal input, not just architectural preference:

- **(a) Compile-time embedding** (`include_str!` / a small `build.rs`): the shipped binary stays single-file and works fully offline everywhere, including `cargo install`, with no extra install step anywhere — but requires confidence that a compiled binary containing embedded CC BY-SA content doesn't itself become obligated under CC BY-SA's terms.
- **(b) Runtime loading from a sibling file**, shipped alongside the binary in the same release package (the GitHub Release tarball, the Homebrew formula's `share/` install) rather than compiled in: architecturally cleaner separation between the MIT code and the CC BY-SA data, at the cost of an unsolved gap for `cargo install` users specifically, since Cargo has no general mechanism to place a companion data file at a runtime-discoverable path.

Whichever is chosen, the JSON files in `dictionary/` remain the canonical, independently fetchable source regardless of how nobotrs itself consumes them: any tool, in any language, can read them directly from the repository without depending on nobotrs. Publishing the dictionary to a stable CDN URL or a package registry (npm/PyPI-style, for easier non-Rust consumption than "clone the repo") is a plausible v2 addition, not committed to for v1.

### 11.5 Versioning

The dictionary carries its own `schema_version` (format stability, mirroring §3's JSON output `schema_version` pattern) and `dictionary_version` (content revision, independent of the nobotrs crate's own semver) — the two evolve on different cadences: the schema should rarely change, while entries get added/refined much more often as new model-era vocabulary tells are identified. Seed content: `check_ai_tells.py`'s existing word/phrase lists, plus the vocabulary/phrase findings from `docs/research/09-no-ai-slop-review.md` (facilitate, empower, robust, cutting-edge, paradigm shift, harness; "here's the thing," "let me be clear," "the uncomfortable truth is," "experts agree," "studies show," "that's it, that's the [x]").

`candle` is pre-1.0 — no MSRV/pinning policy is stated here yet; pin an exact version in `Cargo.lock` and revisit pinning strategy once the `classifier`/`perplexity` prototypes (§9) are underway. Rust edition and MSRV otherwise follow current stable Rust at implementation start, stated explicitly in `Cargo.toml` rather than left implicit. A single-crate-with-features layout (not a Cargo workspace split) is sufficient for v1, consistent with research report 05's conclusion — revisit only if the optional heavy dependencies start causing real build-graph friction in practice. `nobotrs` makes no telemetry or usage-data calls of any kind; this follows directly from the local-first goal in §1 but is stated here explicitly rather than left to be inferred.
