> Historical July specification/plan. The current contract is the [October remediation plan](../plans/2026-10-10-nobotrs-review-remediation.md) and shipped README: raw metrics replace unconditional human probabilities; informational families do not satisfy quorum; prepared prose and completeness govern reporting. Rust lzma-rs ratios are not numerically interchangeable with Python preset-6 compression.

# nobotrs Core Architecture + Default Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `nobotrs` default build — the `deterministic` + `stylometric` tiers, the `DetectorBackend`/`Score`/aggregation core, and the `detect`/`lint`/`scan`/`config` CLI — so `nobotrs detect README.md` works fully offline, sub-second, with no feature flags and no model downloads, per the spec's §3.1 "v1 definition of done."

**Architecture:** A single Rust crate (`nobotrs`, no workspace split, per spec §11.5) with a `DetectorBackend` trait implemented by six backend structs (`Vocabulary`, `Punctuation`, `Burstiness`, `LexicalDiversity`, `Readability`, `Compression`). Each backend produces one `SignalFamily`'s `ScoreOutcome`. An aggregator collects per-family votes into a quorum-based `Verdict`. `clap` wires four subcommands on top. The tell dictionary ships as a separately CC BY-SA 4.0–licensed JSON artifact, embedded at compile time.

**Tech Stack:** Rust (stable, edition 2021), `clap` (derive), `serde`/`serde_json`, `aho-corasick`, `regex`, `unicode-segmentation`, `statrs`, `lzma-rs`, `whichlang`, `owo-colors`, `directories`, `walkdir`.

**Source spec:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md` (approved 2026-07-26).

**Reference implementation (ground truth for ported thresholds/formulas):** `/home/kwhatcher/projects/nobots/hooks/scripts/check_ai_tells.py`.

**Sibling plans (stubs, not yet detailed):** `2026-07-26-nobotrs-classifier-tier.md`, `2026-07-26-nobotrs-perplexity-tier.md`, `2026-07-26-nobotrs-api-clients-tier.md`, `2026-07-26-nobotrs-plugin-packaging.md`.

## Global Constraints

These apply to every task below; they are not repeated per-task.

- Code is MIT-licensed (root `LICENSE`). `dictionary/` is CC BY-SA 4.0, in its own subdirectory with its own `LICENSE` file — the one deliberate exception (spec §10, §11).
- Default build makes **no network calls** and requires **no API keys** (spec §1 goal, §4).
- Single-crate-with-features layout, not a Cargo workspace (spec §11.5).
- `human_probability: f32` must never be `NaN`/infinite — validated/clamped at construction (spec §2.3).
- `f32` does not implement `Ord`; any sort/rank over `human_probability` uses `f32::total_cmp`, never `Ord`/`.cmp()` (spec §2.3).
- Only `Vocabulary`, `Punctuation`, `Burstiness` vote in v1; `LexicalDiversity`, `Readability`, `Compression` are evidence-only (spec §2.2, §2.4, §7 item 5).
- Default build's `QUORUM = 2` against exactly 3 voting families (spec §2.4) — tunable via config, not hardcoded as a magic literal inline.
- Exit codes: `0` = `Clean` with empty `warnings`; `1` = `Flagged`; `2` = tool failure **or** `Clean`/`Flagged` with non-empty `warnings`; `3` = `Inconclusive` (spec §3).
- `detect` reads stdin via a literal `-` path argument, not a `--stdin` flag (spec §3).
- `lint` never applies quorum (reports all evidence unfiltered); `scan <dir>` is a batch `detect`, not a batch `lint` (spec §3).
- Default binary size target ~10MB, CI-asserted once packaging exists (spec §5) — out of scope for this plan's tests but the release profile is set up in Task 20.
- `owo-colors` must have its `supports-colors` feature explicitly enabled — it ships with no default features and no `NO_COLOR` handling otherwise (spec §3).
- Config path is resolved via the `directories` crate, never a hardcoded Unix path (spec §4).
- `dictionary/entries.json` is embedded into the binary at compile time via `include_str!`/`build.rs` (spec §11.4).
- Every dictionary regex is compile-tested in CI under a deterministic `RegexBuilder::size_limit(N)`, never a wall-clock timing check (spec §8, §11.3).
- Ported statistical floors (verified against `check_ai_tells.py` directly, not just the spec prose): `MIN_WORDS_FOR_STATS = 150`, `MIN_WORDS_FOR_DIVERSITY = 50`, burstiness requires ≥5 sentences, MTLD threshold `0.72`, LZMA `preset = 6`.
- `aho-corasick` is configured with `MatchKind::LeftmostLongest`; a dictionary entry's `case_sensitive` defaults to `false`, `whole_word` (exact entries only) defaults to `true` (spec §11.3).

---

## File Structure

```
Cargo.toml
build.rs                          # embeds dictionary/entries.json, asserts dictionary regexes compile under size_limit
NOTICE                             # root: states the two-license split (spec §11.2)
dictionary/
  LICENSE                         # CC BY-SA 4.0 full text
  README.md                       # license statement, schema docs, inbound-contribution note (§9 item 4)
  entries.json                    # seed dictionary content
src/
  main.rs                        # clap entry point, dispatches to cli::*
  error.rs                       # Error, is_recoverable
  availability.rs                # Availability
  deadline.rs                    # Deadline (cooperative budget)
  document.rs                    # Document, ContentType, prose-span segmentation
  score.rs                       # Score, Evidence, ConfidenceTier, Severity, VoteStrength
  backend.rs                     # SignalFamily, ScoreOutcome, DetectorBackend trait
  dictionary.rs                  # DictionaryEntry, Dictionary, loading + size_limit-safe regex compile
  backends/
    mod.rs
    vocabulary.rs                # Vocabulary backend
    punctuation.rs                # Punctuation backend
    burstiness.rs                 # Burstiness backend
    lexical_diversity.rs          # MTLD, hand-rolled
    readability.rs                # Flesch-Kincaid, hand-rolled
    compression.rs                # LZMA ratio + entropy-per-token
  aggregate.rs                    # per-family vote derivation, quorum, Verdict, warnings
  output.rs                       # human + --format json rendering, schema_version, owo-colors
  cli/
    mod.rs
    detect.rs
    lint.rs
    scan.rs
    config.rs
tests/
  fixtures/                       # short known-AI / known-human snippets used across backend tests
```

---

### Task 1: Project scaffolding and CLI skeleton

**Files:**
- Create: `Cargo.toml`
- Create: `src/main.rs`
- Create: `src/cli/mod.rs`
- Create: `src/cli/detect.rs`
- Create: `src/cli/lint.rs`
- Create: `src/cli/scan.rs`
- Create: `src/cli/config.rs`
- Test: `tests/cli_smoke.rs`

**Interfaces:**
- Produces: a `clap` `Cli` struct with subcommands `Detect { path: String }`, `Lint { path: String }`, `Scan { dir: String }`, `Config`, each currently returning a fixed placeholder exit code so the binary builds and runs end-to-end. Later tasks replace each stub's body without changing its `clap` signature.

- [ ] **Step 1: Write the failing smoke test**

```rust
// tests/cli_smoke.rs
use std::process::Command;

#[test]
fn detect_dash_reads_stdin_and_runs() {
    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("detect")
        .arg("-")
        .env("CI", "1")
        .output()
        .expect("binary should run");
    // Stubbed in this task: only asserts the binary exists and exits with a
    // code the CLI actually defines (0-3), not 101 (panic) or 127 (not found).
    let code = output.status.code().expect("should exit with a code");
    assert!((0..=3).contains(&code), "unexpected exit code {code}");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --test cli_smoke`
Expected: FAIL — compile error, no `nobotrs` binary target yet.

- [ ] **Step 3: Write `Cargo.toml`**

```toml
[package]
name = "nobotrs"
version = "0.1.0"
edition = "2021"
license = "MIT"
description = "Detects AI-generated text and lints prose for AI-writing tells"
repository = "https://github.com/kerryhatcher/nobotrs"

[[bin]]
name = "nobotrs"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
aho-corasick = "1"
regex = "1"
unicode-segmentation = "1"
statrs = "0.17"
lzma-rs = "0.3"
whichlang = "0.1"
owo-colors = { version = "4", features = ["supports-colors"] }
directories = "5"
walkdir = "2"

[profile.release]
lto = true
strip = true
opt-level = "z"
```

- [ ] **Step 4: Write `src/cli/mod.rs`**

```rust
// src/cli/mod.rs
use clap::{Parser, Subcommand};

pub mod config;
pub mod detect;
pub mod lint;
pub mod scan;

#[derive(Parser)]
#[command(name = "nobotrs", about = "Detects AI-generated text and lints prose for AI-writing tells")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand)]
pub enum Command {
    /// Score a file or stdin ("-") for a quorum ensemble verdict.
    Detect { path: String },
    /// Line-anchored tells report: every backend's evidence, unfiltered by quorum.
    Lint { path: String },
    /// Batch lint across a directory.
    Scan { dir: String },
    /// Manage API keys, model downloads, enabled backends, availability status.
    Config,
}
```

- [ ] **Step 5: Write stub command modules**

```rust
// src/cli/detect.rs
pub fn run(_path: &str) -> i32 {
    0 // replaced in Task 16
}
```

```rust
// src/cli/lint.rs
pub fn run(_path: &str) -> i32 {
    0 // replaced in Task 17
}
```

```rust
// src/cli/scan.rs
pub fn run(_dir: &str) -> i32 {
    0 // replaced in Task 18
}
```

```rust
// src/cli/config.rs
pub fn run() -> i32 {
    0 // replaced in Task 19
}
```

- [ ] **Step 6: Write `src/main.rs`**

```rust
// src/main.rs
mod cli;

use clap::Parser;
use cli::{Cli, Command};

fn main() {
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Detect { path } => cli::detect::run(&path),
        Command::Lint { path } => cli::lint::run(&path),
        Command::Scan { dir } => cli::scan::run(&dir),
        Command::Config => cli::config::run(),
    };
    std::process::exit(code);
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cargo test --test cli_smoke`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add Cargo.toml src/main.rs src/cli tests/cli_smoke.rs
git commit -m "feat: scaffold nobotrs crate and CLI skeleton"
```

---

### Task 2: Foundational types — `Error`, `Availability`, `Deadline`

**Files:**
- Create: `src/error.rs`
- Create: `src/availability.rs`
- Create: `src/deadline.rs`
- Modify: `src/main.rs` (add `mod error; mod availability; mod deadline;`)
- Test: inline `#[cfg(test)]` modules in each file

**Interfaces:**
- Produces: `Error` enum (`ModelMissing`, `ModelLoadFailed(String)`, `ChecksumMismatch`, `NetworkError(String)`, `ConfigError(String)`, `InternalError(String)`) with `is_recoverable(&self) -> bool`; `Availability` enum (`Ready`, `NeedsDownload`, `Unavailable(String)`); `Deadline` struct with `fn new(budget: std::time::Duration) -> Self`, `fn expired(&self) -> bool`, `fn remaining(&self) -> std::time::Duration`.

- [ ] **Step 1: Write the failing tests**

```rust
// src/error.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn checksum_mismatch_is_not_recoverable() {
        assert!(!Error::ChecksumMismatch.is_recoverable());
    }

    #[test]
    fn internal_error_is_not_recoverable() {
        assert!(!Error::InternalError("bug".into()).is_recoverable());
    }

    #[test]
    fn model_missing_is_recoverable() {
        assert!(Error::ModelMissing.is_recoverable());
    }

    #[test]
    fn network_error_is_recoverable() {
        assert!(Error::NetworkError("timeout".into()).is_recoverable());
    }
}
```

```rust
// src/deadline.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn not_expired_immediately_after_creation() {
        let d = Deadline::new(Duration::from_secs(5));
        assert!(!d.expired());
    }

    #[test]
    fn expired_after_budget_elapses() {
        let d = Deadline::new(Duration::from_millis(1));
        std::thread::sleep(Duration::from_millis(20));
        assert!(d.expired());
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test error:: deadline::`
Expected: FAIL — `Error`, `Deadline` not defined yet.

- [ ] **Step 3: Write `src/error.rs`**

```rust
// src/error.rs

/// Recoverable vs. unrecoverable failure modes a `DetectorBackend` can surface.
/// Split explicitly so callers (the `config` command, `detect`'s `warnings`
/// surface, log output) can distinguish "retry/reconfigure" from "reinstall."
#[derive(Debug, Clone, PartialEq)]
pub enum Error {
    ModelMissing,
    ModelLoadFailed(String),
    ChecksumMismatch,
    NetworkError(String),
    ConfigError(String),
    InternalError(String),
}

impl Error {
    pub fn is_recoverable(&self) -> bool {
        !matches!(self, Error::ChecksumMismatch | Error::InternalError(_))
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::ModelMissing => write!(f, "model missing (run `nobotrs config` to download)"),
            Error::ModelLoadFailed(msg) => write!(f, "model load failed: {msg}"),
            Error::ChecksumMismatch => write!(f, "checksum mismatch (reinstall required)"),
            Error::NetworkError(msg) => write!(f, "network error: {msg}"),
            Error::ConfigError(msg) => write!(f, "config error: {msg}"),
            Error::InternalError(msg) => write!(f, "internal error: {msg}"),
        }
    }
}
```

- [ ] **Step 4: Write `src/availability.rs`**

```rust
// src/availability.rs

#[derive(Debug, Clone, PartialEq)]
pub enum Availability {
    Ready,
    NeedsDownload,
    Unavailable(String),
}
```

- [ ] **Step 5: Write `src/deadline.rs`**

```rust
// src/deadline.rs
use std::time::{Duration, Instant};

/// A cooperative budget, NOT a preemption mechanism (spec §2.1). A callee that
/// never polls `expired()` will not be interrupted by this type — it has no
/// effect on code already blocked in FFI, a blocking network call, or a tight
/// loop that never checks it.
#[derive(Debug, Clone, Copy)]
pub struct Deadline {
    deadline: Instant,
}

impl Deadline {
    pub fn new(budget: Duration) -> Self {
        Deadline { deadline: Instant::now() + budget }
    }

    pub fn expired(&self) -> bool {
        Instant::now() >= self.deadline
    }

    pub fn remaining(&self) -> Duration {
        self.deadline.saturating_duration_since(Instant::now())
    }
}
```

- [ ] **Step 6: Wire modules into `src/main.rs`**

```rust
// src/main.rs (add near top, before `mod cli;`)
mod availability;
mod deadline;
mod error;
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cargo test error:: deadline::`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/error.rs src/availability.rs src/deadline.rs src/main.rs
git commit -m "feat: add Error, Availability, and Deadline foundational types"
```

---

### Task 3: `Document` type and markdown-aware prose-span segmentation

**Files:**
- Create: `src/document.rs`
- Modify: `src/main.rs` (add `mod document;`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ContentType` enum (`Markdown`, `PlainText`, `Unknown`); `Document` struct (`raw: String`, `prose_spans: Vec<Range<usize>>`, `content_type: ContentType`) with `Document::from_path(path: &Path) -> std::io::Result<Document>` and `Document::from_stdin_text(raw: String, markdown_hint: bool) -> Document`. Later tasks (backends) consume `doc.raw`, `doc.prose_spans`, `doc.content_type` directly.

- [ ] **Step 1: Write the failing tests**

```rust
// src/document.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_text_has_one_prose_span_covering_whole_file() {
        let doc = Document::from_stdin_text("hello world".to_string(), false);
        assert_eq!(doc.content_type, ContentType::PlainText);
        assert_eq!(doc.prose_spans, vec![0..11]);
    }

    #[test]
    fn markdown_excludes_fenced_code_block() {
        let raw = "Intro text.\n\n```rust\nfn code() {}\n```\n\nOutro text.".to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        assert_eq!(doc.content_type, ContentType::Markdown);
        // the fenced block (from the opening ``` line through the closing ```
        // line, inclusive) must not be covered by any prose span
        let fence_start = raw.find("```rust").unwrap();
        let fence_end = raw.rfind("```").unwrap() + 3;
        for span in &doc.prose_spans {
            let overlaps = span.start < fence_end && fence_start < span.end;
            assert!(!overlaps, "prose span {:?} overlaps code fence [{fence_start}..{fence_end}]", span);
        }
        // but the intro and outro text are still covered by *some* prose span
        let intro_pos = raw.find("Intro text.").unwrap();
        let outro_pos = raw.find("Outro text.").unwrap();
        assert!(doc.prose_spans.iter().any(|s| s.start <= intro_pos && intro_pos < s.end));
        assert!(doc.prose_spans.iter().any(|s| s.start <= outro_pos && outro_pos < s.end));
    }

    #[test]
    fn markdown_excludes_front_matter() {
        let raw = "---\ntitle: test\n---\n\nBody text.".to_string();
        let doc = Document::from_stdin_text(raw.clone(), true);
        let body_pos = raw.find("Body text.").unwrap();
        assert!(doc.prose_spans.iter().any(|s| s.start <= body_pos && body_pos < s.end));
        assert!(!doc.prose_spans.iter().any(|s| s.start == 0));
    }

    #[test]
    fn stdin_defaults_to_plaintext_without_markdown_hint() {
        let doc = Document::from_stdin_text("# not a heading, just text".to_string(), false);
        assert_eq!(doc.content_type, ContentType::PlainText);
    }

    #[test]
    fn file_extension_dot_md_selects_markdown() {
        let dir = std::env::temp_dir().join(format!("nobotrs-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("sample.md");
        std::fs::write(&path, "# Title\n\nBody.").unwrap();
        let doc = Document::from_path(&path).unwrap();
        assert_eq!(doc.content_type, ContentType::Markdown);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test document::`
Expected: FAIL — `Document` not defined yet.

- [ ] **Step 3: Write `src/document.rs`**

```rust
// src/document.rs
use std::ops::Range;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentType {
    Markdown,
    PlainText,
    Unknown,
}

#[derive(Debug, Clone)]
pub struct Document {
    pub raw: String,
    pub prose_spans: Vec<Range<usize>>,
    pub content_type: ContentType,
}

impl Document {
    pub fn from_path(path: &Path) -> std::io::Result<Document> {
        let raw = std::fs::read_to_string(path)?;
        let is_markdown = matches!(
            path.extension().and_then(|e| e.to_str()).map(|e| e.to_ascii_lowercase()).as_deref(),
            Some("md") | Some("markdown")
        );
        Ok(Self::build(raw, is_markdown))
    }

    /// `markdown_hint` mirrors the CLI's `--markdown` flag for stdin (`-`),
    /// where no file extension exists to infer content type from (spec §2.1:
    /// stdin defaults to PlainText unless `--markdown` is passed explicitly).
    pub fn from_stdin_text(raw: String, markdown_hint: bool) -> Document {
        Self::build(raw, markdown_hint)
    }

    fn build(raw: String, is_markdown: bool) -> Document {
        if is_markdown {
            let prose_spans = markdown_prose_spans(&raw);
            Document { raw, prose_spans, content_type: ContentType::Markdown }
        } else {
            let len = raw.len();
            Document { raw, prose_spans: vec![0..len], content_type: ContentType::PlainText }
        }
    }
}

/// Computes prose-only byte ranges of `raw`, excluding fenced code blocks
/// (``` or ~~~ delimited) and a leading YAML front-matter block (--- delimited,
/// only recognized at byte offset 0). Computed once per `Document::new()` and
/// stored (spec §2.1) — never recomputed per backend.
fn markdown_prose_spans(raw: &str) -> Vec<Range<usize>> {
    let mut spans = Vec::new();
    let mut cursor = 0usize;
    let mut in_fence = false;
    let mut fence_marker: &str = "";

    // Front matter: a leading line of exactly `---` starts it; the next line
    // that is exactly `---` ends it. Only recognized at the very start of the
    // file, matching common front-matter convention.
    if raw.starts_with("---\n") || raw == "---" {
        if let Some(end_idx) = raw[4..].find("\n---") {
            let front_matter_end = 4 + end_idx + 4; // consume the closing "\n---"
            // also consume the rest of that closing line
            let after = raw[front_matter_end..].find('\n').map(|i| front_matter_end + i + 1)
                .unwrap_or(raw.len());
            cursor = after;
        }
    }

    let mut line_start = cursor;
    for (i, ch) in raw[cursor..].char_indices() {
        let abs = cursor + i;
        if ch == '\n' || abs + ch.len_utf8() == raw.len() {
            let line_end = if abs + ch.len_utf8() == raw.len() && ch != '\n' {
                abs + ch.len_utf8()
            } else {
                abs
            };
            let line = &raw[line_start..line_end];
            let trimmed = line.trim_start();
            let is_fence_line = trimmed.starts_with("```") || trimmed.starts_with("~~~");
            if is_fence_line {
                let marker = if trimmed.starts_with("```") { "```" } else { "~~~" };
                if !in_fence {
                    // close prose span up to (not including) this fence line
                    if line_start > line_start.min(spans.last().map(|r: &Range<usize>| r.end).unwrap_or(0)) {
                        // handled below via generic span-tracking
                    }
                    spans.push(cursor..line_start);
                    in_fence = true;
                    fence_marker = marker;
                } else if marker == fence_marker {
                    in_fence = false;
                    cursor = line_end + 1; // resume prose after this closing fence line
                }
            }
            line_start = line_end + 1;
        }
    }
    if !in_fence && cursor < raw.len() {
        spans.push(cursor..raw.len());
    }
    spans.retain(|r| r.start < r.end);
    if spans.is_empty() && !in_fence {
        spans.push(cursor..raw.len());
    }
    spans
}
```

- [ ] **Step 4: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod document;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test document::`
Expected: PASS

If the fence/front-matter span math fails on the exact boundary assertions, adjust `markdown_prose_spans` until all five tests pass — the tests, not the prose above, are the source of truth for exact boundary behavior.

- [ ] **Step 6: Commit**

```bash
git add src/document.rs src/main.rs
git commit -m "feat: add Document type with markdown-aware prose-span segmentation"
```

---

### Task 4: `Score`, `Evidence`, and supporting result types

**Files:**
- Create: `src/score.rs`
- Modify: `src/main.rs` (add `mod score;`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Severity` (`Low`, `Medium`, `High`), `ConfidenceTier` (`Low`, `Medium`, `High`), `VoteStrength` (`None`, `Suspicious`, `Strong`), `Evidence` struct, `Score` struct with `Score::new(...) -> Score` that clamps `human_probability`, and `Score::clamp_probability(p: f32) -> f32` (unit-tested standalone). Later tasks' backends construct `Score` via `Score::new`; the aggregator (Task 14) reads `score.vote`.

**Note on `vote: VoteStrength`:** the approved spec's §2.4 states aggregation needs a discrete per-family vote (`Abstain | Suspicious | Strong`) distinct from `human_probability`, but §2.3's `Score` struct listing doesn't carry a field for it. This is a small necessary addition, not a deviation: without it the aggregator in Task 14 has no discrete value to read. It's named `VoteStrength` rather than reusing "Abstain" to avoid colliding with `ScoreOutcome::Abstained` (a different concept — backend-level non-applicability vs. family-level "voted, found nothing"); `VoteStrength::None` is the "voted, found nothing" case, which still counts toward `votes_cast` per spec §2.4.

- [ ] **Step 1: Write the failing tests**

```rust
// src/score.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_rejects_nan() {
        assert!(!Score::clamp_probability(f32::NAN).is_nan());
    }

    #[test]
    fn clamp_rejects_positive_infinity() {
        assert_eq!(Score::clamp_probability(f32::INFINITY), 1.0);
    }

    #[test]
    fn clamp_rejects_negative_infinity() {
        assert_eq!(Score::clamp_probability(f32::NEG_INFINITY), 0.0);
    }

    #[test]
    fn clamp_passes_through_valid_values() {
        assert_eq!(Score::clamp_probability(0.42), 0.42);
    }

    #[test]
    fn clamp_bounds_out_of_range_values() {
        assert_eq!(Score::clamp_probability(1.5), 1.0);
        assert_eq!(Score::clamp_probability(-0.5), 0.0);
    }

    #[test]
    fn new_constructs_with_clamped_probability() {
        let s = Score::new(
            "vocabulary".into(),
            crate::backend::SignalFamily::Vocabulary,
            f32::NAN,
            ConfidenceTier::Medium,
            VoteStrength::Suspicious,
            vec![],
        );
        assert!(!s.human_probability.is_nan());
    }

    #[test]
    fn sorting_scores_by_probability_uses_total_cmp() {
        let mut scores = vec![0.9_f32, f32::NAN, 0.1, 0.5];
        scores.sort_by(f32::total_cmp);
        assert_eq!(scores[0], 0.1);
        assert_eq!(scores[1], 0.5);
        assert_eq!(scores[2], 0.9);
        assert!(scores[3].is_nan());
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test score::`
Expected: FAIL — `Score` not defined yet, and `crate::backend::SignalFamily` doesn't exist yet (added in Task 5).

- [ ] **Step 3: Write `src/score.rs`**

```rust
// src/score.rs
use std::ops::Range;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConfidenceTier {
    Low,
    Medium,
    High,
}

/// The discrete per-family strength a `Score` contributes to aggregation
/// (spec §2.4). `None` means "this family scored the document and found
/// nothing suspicious" — distinct from `ScoreOutcome::Abstained`, which means
/// the backend never scored the document at all (§2.1, §2.4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoteStrength {
    None,
    Suspicious,
    Strong,
}

#[derive(Debug, Clone)]
pub struct Evidence {
    pub raw_offset: Range<usize>,
    pub prose_offset: Range<usize>,
    pub line: u32,
    pub column: u32,
    pub matched_text: String,
    pub severity: Severity,
    pub suggestion: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Score {
    pub backend: String,
    pub family: crate::backend::SignalFamily,
    pub human_probability: f32,
    pub confidence: ConfidenceTier,
    pub vote: VoteStrength,
    pub evidence: Vec<Evidence>,
}

impl Score {
    pub fn new(
        backend: String,
        family: crate::backend::SignalFamily,
        human_probability: f32,
        confidence: ConfidenceTier,
        vote: VoteStrength,
        evidence: Vec<Evidence>,
    ) -> Score {
        Score {
            backend,
            family,
            human_probability: Self::clamp_probability(human_probability),
            confidence,
            vote,
            evidence,
        }
    }

    /// `human_probability` must never be NaN or infinite (spec §2.3): NaN
    /// makes every comparison (`> 0.5`, `< 0.5`, `== 0.5`) silently false
    /// without panicking, corrupting thresholding logic with no test catching
    /// it. NaN clamps to 0.5 (a neutral midpoint); +/-infinity clamp to 1.0/0.0.
    pub fn clamp_probability(p: f32) -> f32 {
        if p.is_nan() {
            0.5
        } else {
            p.clamp(0.0, 1.0)
        }
    }
}
```

- [ ] **Step 4: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod score;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test score::`
Expected: FAIL still — `crate::backend` doesn't exist yet. This is expected; proceed to Task 5, which adds it, then re-run this test as Task 5's own verification step.

- [ ] **Step 6: Commit**

```bash
git add src/score.rs src/main.rs
git commit -m "feat: add Score, Evidence, and VoteStrength types with NaN-safe probability clamping"
```

---

### Task 5: `SignalFamily`, `ScoreOutcome`, and the `DetectorBackend` trait

**Files:**
- Create: `src/backend.rs`
- Modify: `src/main.rs` (add `mod backend;`)

**Interfaces:**
- Consumes: `crate::document::Document` (Task 3), `crate::deadline::Deadline` (Task 2), `crate::score::Score` (Task 4), `crate::error::Error` (Task 2).
- Produces: `SignalFamily` enum (`Vocabulary`, `Punctuation`, `Burstiness`, `LexicalDiversity`, `Readability`, `Compression`), `ScoreOutcome` enum (`Scored(Score)`, `Abstained { reason: String }`, `Failed(Error)`), `DetectorBackend` trait with `name`, `family`, `availability`, `score`, default `score_batch`. All six backend structs (Tasks 8-13) implement this trait.

- [ ] **Step 1: Write the failing test**

```rust
// src/backend.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::deadline::Deadline;
    use crate::document::Document;

    struct AlwaysAbstains;
    impl DetectorBackend for AlwaysAbstains {
        fn name(&self) -> &str { "always-abstains" }
        fn family(&self) -> SignalFamily { SignalFamily::Vocabulary }
        fn availability(&self) -> crate::availability::Availability { crate::availability::Availability::Ready }
        fn score(&self, _doc: &Document, _deadline: Deadline) -> ScoreOutcome {
            ScoreOutcome::Abstained { reason: "test backend".into() }
        }
    }

    #[test]
    fn default_score_batch_maps_score_over_documents() {
        let backend = AlwaysAbstains;
        let docs = vec![
            Document::from_stdin_text("one".into(), false),
            Document::from_stdin_text("two".into(), false),
        ];
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        let outcomes = backend.score_batch(&docs, deadline);
        assert_eq!(outcomes.len(), 2);
        for outcome in outcomes {
            assert!(matches!(outcome, ScoreOutcome::Abstained { .. }));
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test backend::`
Expected: FAIL — `SignalFamily`, `ScoreOutcome`, `DetectorBackend` not defined yet.

- [ ] **Step 3: Write `src/backend.rs`**

```rust
// src/backend.rs
use crate::availability::Availability;
use crate::deadline::Deadline;
use crate::document::Document;
use crate::error::Error;
use crate::score::Score;

/// Which independent signal family a backend's vote belongs to (spec §2.2).
/// One `DetectorBackend` instance produces exactly one family's vote — a tier
/// that covers several families registers one backend instance per family,
/// not one backend that multiplexes several (spec §2.1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SignalFamily {
    Vocabulary,
    Punctuation,
    Burstiness,
    LexicalDiversity,
    Readability,
    Compression,
}

/// Distinguishes "not applicable to this input" (`Abstained`) from "something
/// broke" (`Failed`) — both excluded from the vote count in aggregation, but
/// `Failed` additionally surfaces as a `detect` warning (spec §2.1, §2.4).
pub enum ScoreOutcome {
    Scored(Score),
    Abstained { reason: String },
    Failed(Error),
}

pub trait DetectorBackend: Send + Sync {
    fn name(&self) -> &str;
    fn family(&self) -> SignalFamily;
    fn availability(&self) -> Availability;
    fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome;

    fn score_batch(&self, docs: &[Document], deadline: Deadline) -> Vec<ScoreOutcome> {
        docs.iter().map(|doc| self.score(doc, deadline)).collect()
    }
}
```

- [ ] **Step 4: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod backend;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test backend:: score::`
Expected: PASS for both modules — Task 4's deferred test (`new_constructs_with_clamped_probability`) now compiles and passes too.

- [ ] **Step 6: Commit**

```bash
git add src/backend.rs src/main.rs
git commit -m "feat: add SignalFamily, ScoreOutcome, and DetectorBackend trait"
```

---

### Task 6: Tell dictionary artifact — schema, seed content, licensing

**Files:**
- Create: `dictionary/entries.json`
- Create: `dictionary/LICENSE`
- Create: `dictionary/README.md`
- Create: `NOTICE`

**Interfaces:**
- Produces: the on-disk dictionary artifact Task 7's loader parses. Schema matches spec §11.3 exactly: `schema_version`, `dictionary_version`, `entries[]` of `{ id, kind, match_type, pattern, variants?, case_sensitive, whole_word?, family, category, suggested_replacements, model_era, source, notes }`.

- [ ] **Step 1: Write `dictionary/entries.json`**

Seed content ported directly from `check_ai_tells.py`'s `TELL_WORDS`/`TELL_PHRASES` patterns (verified against the source file directly) plus the vocabulary/phrase findings named in spec §11.5 from `docs/research/09-no-ai-slop-review.md`. Every entry's `family` is `"Vocabulary"` (spec §11.3 — `Punctuation` has no dictionary representation).

```json
{
  "schema_version": "1.0.0",
  "dictionary_version": "2026.07.26",
  "entries": [
    { "id": "delve", "kind": "word", "match_type": "exact", "pattern": "delve", "variants": ["delves", "delving"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["look into", "explore", "start"], "model_era": ["gpt-3.5", "gpt-4o"], "source": null, "notes": null },
    { "id": "tapestry", "kind": "word", "match_type": "exact", "pattern": "tapestry", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["mix", "combination"], "model_era": [], "source": null, "notes": null },
    { "id": "multifaceted", "kind": "word", "match_type": "exact", "pattern": "multifaceted", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["complex", "many-sided"], "model_era": [], "source": null, "notes": null },
    { "id": "nuanced", "kind": "word", "match_type": "exact", "pattern": "nuanced", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["subtle", "detailed"], "model_era": [], "source": null, "notes": null },
    { "id": "leverage", "kind": "word", "match_type": "exact", "pattern": "leverage", "variants": ["leveraging"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["use"], "model_era": [], "source": null, "notes": null },
    { "id": "utilize", "kind": "word", "match_type": "exact", "pattern": "utilize", "variants": ["utilizing"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["use"], "model_era": [], "source": null, "notes": null },
    { "id": "seamless", "kind": "word", "match_type": "exact", "pattern": "seamless", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["smooth", "consistent"], "model_era": [], "source": null, "notes": null },
    { "id": "foster", "kind": "word", "match_type": "exact", "pattern": "foster", "variants": ["fosters"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["encourage", "build"], "model_era": [], "source": null, "notes": null },
    { "id": "pivotal", "kind": "word", "match_type": "exact", "pattern": "pivotal", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["key", "critical"], "model_era": [], "source": null, "notes": null },
    { "id": "paramount", "kind": "word", "match_type": "exact", "pattern": "paramount", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["most important"], "model_era": [], "source": null, "notes": null },
    { "id": "holistic", "kind": "word", "match_type": "exact", "pattern": "holistic", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["complete", "whole"], "model_era": [], "source": null, "notes": null },
    { "id": "streamline", "kind": "word", "match_type": "exact", "pattern": "streamline", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["simplify"], "model_era": [], "source": null, "notes": null },
    { "id": "transformative", "kind": "word", "match_type": "exact", "pattern": "transformative", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["major", "significant"], "model_era": [], "source": null, "notes": null },
    { "id": "meticulous", "kind": "word", "match_type": "exact", "pattern": "meticulous", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["careful", "thorough"], "model_era": [], "source": null, "notes": null },
    { "id": "intricate", "kind": "word", "match_type": "exact", "pattern": "intricate", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["complex", "detailed"], "model_era": [], "source": null, "notes": null },
    { "id": "embark", "kind": "word", "match_type": "exact", "pattern": "embark", "variants": ["embarking"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["start", "begin"], "model_era": [], "source": null, "notes": null },
    { "id": "beacon", "kind": "word", "match_type": "exact", "pattern": "beacon", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["example", "guide"], "model_era": [], "source": null, "notes": null },
    { "id": "testament", "kind": "word", "match_type": "exact", "pattern": "testament", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["proof", "evidence"], "model_era": [], "source": null, "notes": null },
    { "id": "plethora", "kind": "word", "match_type": "exact", "pattern": "plethora", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["many", "a lot of"], "model_era": [], "source": null, "notes": null },
    { "id": "myriad", "kind": "word", "match_type": "exact", "pattern": "myriad", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["many"], "model_era": [], "source": null, "notes": null },
    { "id": "moreover", "kind": "word", "match_type": "exact", "pattern": "moreover", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["also", "also,"], "model_era": [], "source": null, "notes": null },
    { "id": "furthermore", "kind": "word", "match_type": "exact", "pattern": "furthermore", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["also", "and"], "model_era": [], "source": null, "notes": null },
    { "id": "nevertheless", "kind": "word", "match_type": "exact", "pattern": "nevertheless", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["still", "even so"], "model_era": [], "source": null, "notes": null },
    { "id": "underscore", "kind": "word", "match_type": "exact", "pattern": "underscores", "variants": ["underscoring"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["shows", "highlights"], "model_era": [], "source": null, "notes": null },
    { "id": "showcase", "kind": "word", "match_type": "exact", "pattern": "showcase", "variants": ["showcases", "showcasing"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["show", "demonstrate"], "model_era": [], "source": null, "notes": null },
    { "id": "emphasize", "kind": "word", "match_type": "exact", "pattern": "emphasize", "variants": ["emphasizes", "emphasizing"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["stress", "highlight"], "model_era": [], "source": null, "notes": null },
    { "id": "facilitate", "kind": "word", "match_type": "exact", "pattern": "facilitate", "variants": ["facilitates", "facilitating"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["help", "enable"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "empower", "kind": "word", "match_type": "exact", "pattern": "empower", "variants": ["empowers", "empowering"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["let", "allow"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "robust", "kind": "word", "match_type": "exact", "pattern": "robust", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["strong", "solid"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "cutting-edge", "kind": "word", "match_type": "exact", "pattern": "cutting-edge", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["new", "latest"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "paradigm-shift", "kind": "word", "match_type": "exact", "pattern": "paradigm shift", "variants": [], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["big change"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "harness-verb", "kind": "word", "match_type": "exact", "pattern": "harness", "variants": ["harnessing"], "case_sensitive": false, "whole_word": true, "family": "Vocabulary", "category": "vocabulary", "suggested_replacements": ["use"], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md; whole_word:true avoids matching inside e.g. proper nouns" },
    { "id": "not-just-x-but-y", "kind": "phrase", "match_type": "regex", "pattern": "it'?s not just [a-z ]+, it'?s", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "negative parallelism" },
    { "id": "important-to-note", "kind": "phrase", "match_type": "regex", "pattern": "it is important to note that", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "rapidly-evolving", "kind": "phrase", "match_type": "regex", "pattern": "in today'?s rapidly evolving", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "cannot-be-overstated", "kind": "phrase", "match_type": "regex", "pattern": "cannot be overstated", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "embark-on-a-journey", "kind": "phrase", "match_type": "regex", "pattern": "embark on a journey", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "a-testament-to", "kind": "phrase", "match_type": "regex", "pattern": "a testament to", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "plays-a-role", "kind": "phrase", "match_type": "regex", "pattern": "plays a (crucial|vital|pivotal) role", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "worth-noting", "kind": "phrase", "match_type": "regex", "pattern": "it'?s worth noting", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": null },
    { "id": "heres-the-thing", "kind": "phrase", "match_type": "regex", "pattern": "here'?s the thing", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "let-me-be-clear", "kind": "phrase", "match_type": "regex", "pattern": "let me be clear", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "uncomfortable-truth", "kind": "phrase", "match_type": "regex", "pattern": "the uncomfortable truth is", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "experts-agree", "kind": "phrase", "match_type": "regex", "pattern": "experts agree", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "studies-show", "kind": "phrase", "match_type": "regex", "pattern": "studies show", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" },
    { "id": "thats-it-thats-the-x", "kind": "phrase", "match_type": "regex", "pattern": "that'?s it, that'?s the [a-z ]+", "case_sensitive": false, "family": "Vocabulary", "category": "structural-phrase", "suggested_replacements": [], "model_era": [], "source": null, "notes": "from docs/research/09-no-ai-slop-review.md" }
  ]
}
```

- [ ] **Step 2: Write `dictionary/LICENSE`**

Paste the full, unmodified CC BY-SA 4.0 legal code (obtain the canonical text from `https://creativecommons.org/licenses/by-sa/4.0/legalcode` and save it verbatim — do not paraphrase or summarize a legal license text).

- [ ] **Step 3: Write `dictionary/README.md`**

```markdown
# nobotrs tell dictionary

This directory is licensed **CC BY-SA 4.0** (see `LICENSE` in this directory),
separately from the rest of the `nobotrs` repository, which is MIT-licensed
(see the root `LICENSE`). See the root `NOTICE` file for why.

## Schema

`entries.json` holds one JSON document: `schema_version`, `dictionary_version`,
and an `entries[]` array. Each entry:

- `id` (string): unique identifier.
- `kind` (`"word"` | `"phrase"`).
- `match_type` (`"exact"` | `"regex"`): `exact` entries are matched via
  `aho-corasick`; `regex` entries via the `regex` crate.
- `pattern` (string): the literal string (`exact`) or regex pattern (`regex`).
- `variants` (string array, `exact` entries only): morphological forms sharing
  this entry's `id`/`family`/`suggested_replacements`.
- `case_sensitive` (bool, default `false`).
- `whole_word` (bool, default `true`, `exact` entries only): word-boundary
  matching — without it, `"harness"` would match inside `"harnessed"`.
- `family`: the `SignalFamily` this entry votes into. Every entry in v1 is
  `"Vocabulary"` — `Punctuation` is code-only, not dictionary-driven.
- `category` (string): descriptive/organizational metadata for humans browsing
  the dictionary — not consumed by the aggregator.
- `suggested_replacements` (string array): feeds `lint`'s suggested-fix output.
- `model_era` (string array): optional, reserved for future per-era weighting.
- `source`, `notes`: optional free-text provenance/context.

## Contributing

**Before any external contribution is accepted**, contributors must license
their contribution under `CC-BY-SA-4.0 OR MIT`, mirroring this directory's
outbound terms. This is required so `nobotrs` can continue to embed the
dictionary in its MIT-licensed binary without needing per-contributor
renegotiation later. By opening a pull request that modifies `entries.json`,
you agree your changes are licensed `CC-BY-SA-4.0 OR MIT`.
```

- [ ] **Step 4: Write root `NOTICE`**

```
nobotrs contains two independently licensed components:

  - Source code (this repository, excluding `dictionary/`): MIT. See `LICENSE`.
  - `dictionary/`: CC BY-SA 4.0. See `dictionary/LICENSE`.

Anyone redistributing the dictionary content itself (forking or republishing
`dictionary/entries.json`) has ShareAlike/attribution obligations under CC BY-SA
4.0 distinct from the code's MIT terms. See `dictionary/README.md` for details.
```

- [ ] **Step 5: Verify the JSON parses**

Run: `python3 -c "import json; json.load(open('dictionary/entries.json'))" || cat dictionary/entries.json | jq . > /dev/null`

Expected: no error. (This step just checks the hand-authored JSON is syntactically valid before Task 7's Rust loader depends on it — no test framework needed yet since no Rust code reads this file until the next task.)

- [ ] **Step 6: Commit**

```bash
git add dictionary NOTICE
git commit -m "feat: add tell dictionary seed content, CC BY-SA 4.0 license, and NOTICE"
```

---

### Task 7: Dictionary loader

**Files:**
- Create: `src/dictionary.rs`
- Create: `build.rs`
- Modify: `Cargo.toml` (add `serde` derive already present; no new deps needed — `regex` already a dependency)
- Modify: `src/main.rs` (add `mod dictionary;`)

**Interfaces:**
- Consumes: `dictionary/entries.json` (Task 6), `crate::backend::SignalFamily` (Task 5).
- Produces: `DictionaryEntry` struct (serde-deserializable, matching §11.3's schema), `Dictionary` struct with `Dictionary::embedded() -> Dictionary` (parses the compile-time-embedded JSON once) and `Dictionary::compiled_regexes(&self) -> Result<Vec<(String, regex::Regex)>, String>` (compiles every `match_type: "regex"` entry's pattern under a conservative `RegexBuilder::size_limit`, returning `Err` naming the offending entry `id` on failure rather than panicking — a compile failure must be recoverable as `Abstained`, not a panic, per spec §11.3). Task 8 (`Vocabulary` backend) consumes both.

- [ ] **Step 1: Write the failing tests**

```rust
// src/dictionary.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_dictionary_parses_without_error() {
        let dict = Dictionary::embedded();
        assert!(!dict.entries.is_empty());
    }

    #[test]
    fn every_entry_family_is_vocabulary() {
        let dict = Dictionary::embedded();
        for entry in &dict.entries {
            assert_eq!(entry.family, crate::backend::SignalFamily::Vocabulary, "entry {} has non-Vocabulary family", entry.id);
        }
    }

    #[test]
    fn case_sensitive_defaults_to_false_when_absent() {
        // parse a minimal single-entry document lacking the field entirely
        let json = r#"{"schema_version":"1.0.0","dictionary_version":"test","entries":[
            {"id":"x","kind":"word","match_type":"exact","pattern":"x","family":"Vocabulary","category":"vocabulary","suggested_replacements":[],"model_era":[],"source":null,"notes":null}
        ]}"#;
        let dict: Dictionary = Dictionary::from_json_str(json).unwrap();
        assert_eq!(dict.entries[0].case_sensitive, false);
        assert_eq!(dict.entries[0].whole_word, true);
    }

    #[test]
    fn all_regex_entries_compile_under_size_limit() {
        let dict = Dictionary::embedded();
        let compiled = dict.compiled_regexes(1 << 16); // 64 KiB, the CI-asserted bound (spec §8, §11.3)
        assert!(compiled.is_ok(), "a dictionary regex failed to compile: {:?}", compiled.err());
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test dictionary::`
Expected: FAIL — `Dictionary` not defined yet.

- [ ] **Step 3: Write `build.rs`**

```rust
// build.rs
fn main() {
    println!("cargo:rerun-if-changed=dictionary/entries.json");
}
```

- [ ] **Step 4: Write `src/dictionary.rs`**

```rust
// src/dictionary.rs
use crate::backend::SignalFamily;
use regex::RegexBuilder;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntryKind {
    Word,
    Phrase,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MatchType {
    Exact,
    Regex,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DictionaryEntry {
    pub id: String,
    pub kind: EntryKind,
    pub match_type: MatchType,
    pub pattern: String,
    #[serde(default)]
    pub variants: Vec<String>,
    #[serde(default = "default_false")]
    pub case_sensitive: bool,
    #[serde(default = "default_true")]
    pub whole_word: bool,
    pub family: SignalFamily,
    pub category: String,
    #[serde(default)]
    pub suggested_replacements: Vec<String>,
    #[serde(default)]
    pub model_era: Vec<String>,
    pub source: Option<String>,
    pub notes: Option<String>,
}

fn default_false() -> bool { false }
fn default_true() -> bool { true }

#[derive(Debug, Clone, Deserialize)]
pub struct Dictionary {
    pub schema_version: String,
    pub dictionary_version: String,
    pub entries: Vec<DictionaryEntry>,
}

const EMBEDDED_JSON: &str = include_str!("../dictionary/entries.json");

impl Dictionary {
    pub fn embedded() -> Dictionary {
        Self::from_json_str(EMBEDDED_JSON).expect("embedded dictionary/entries.json must be valid at compile time")
    }

    pub fn from_json_str(json: &str) -> Result<Dictionary, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Compiles every `regex`-kind entry's pattern under `size_limit` bytes,
    /// per spec §8/§11.3: a deterministic size bound, not a wall-clock timing
    /// check. Returns the offending entry `id` on the first failure so a bad
    /// contributed pattern fails CI with an actionable message.
    pub fn compiled_regexes(&self, size_limit: usize) -> Result<Vec<(String, regex::Regex)>, String> {
        self.entries
            .iter()
            .filter(|e| matches!(e.match_type, MatchType::Regex))
            .map(|e| {
                RegexBuilder::new(&e.pattern)
                    .case_insensitive(!e.case_sensitive)
                    .size_limit(size_limit)
                    .build()
                    .map(|re| (e.id.clone(), re))
                    .map_err(|err| format!("entry '{}' failed to compile: {err}", e.id))
            })
            .collect()
    }
}
```

`serde(rename_all = "lowercase")` on `EntryKind`/`MatchType` matches the JSON's `"word"`/`"phrase"`/`"exact"`/`"regex"` string values. `SignalFamily` needs `Deserialize` derived — this requires revisiting Task 5's `SignalFamily` definition.

- [ ] **Step 5: Add `Deserialize` to `SignalFamily`**

In `src/backend.rs`, change:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SignalFamily {
```

to:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Deserialize)]
pub enum SignalFamily {
```

- [ ] **Step 6: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod dictionary;
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cargo test dictionary::`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/dictionary.rs src/backend.rs src/main.rs build.rs
git commit -m "feat: add dictionary loader with size-limited regex compilation"
```

---

### Task 8: `Vocabulary` backend

**Files:**
- Create: `src/backends/mod.rs`
- Create: `src/backends/vocabulary.rs`
- Modify: `src/main.rs` (add `mod backends;`)

**Interfaces:**
- Consumes: `crate::dictionary::Dictionary` (Task 7), `crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily}` (Task 5), `crate::document::Document` (Task 3), `crate::score::{Score, Evidence, VoteStrength, ConfidenceTier, Severity}` (Task 4).
- Produces: `Vocabulary` struct implementing `DetectorBackend`, constructed via `Vocabulary::new(dictionary: Dictionary) -> Result<Vocabulary, String>` (fails fast at construction if any regex entry doesn't compile — the CLI wiring in Task 16 decides what to do with that `Result`, e.g. treating it as a startup `Error::ConfigError`).

**Ported thresholds (verified directly against `check_ai_tells.py`):** `total_hits >= 4` → `VoteStrength::Strong`; `total_hits >= 2` → `VoteStrength::Suspicious`; otherwise `VoteStrength::None`. `total_hits` is the combined count of `aho-corasick` exact-match hits and `regex` phrase-match hits, per spec §2.2's "both feed the single `Vocabulary` family" rule.

- [ ] **Step 1: Write the failing tests**

```rust
// src/backends/vocabulary.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::deadline::Deadline;
    use crate::dictionary::Dictionary;
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn backend() -> Vocabulary {
        Vocabulary::new(Dictionary::embedded()).expect("embedded dictionary must compile")
    }

    fn score_text(text: &str) -> crate::score::Score {
        let backend = backend();
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        match backend.score(&doc, deadline) {
            crate::backend::ScoreOutcome::Scored(score) => score,
            other => panic!("expected Scored, got a different outcome"),
        }
    }

    #[test]
    fn zero_hits_votes_none() {
        let score = score_text("The cat sat quietly on the warm windowsill all afternoon.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn two_hits_votes_suspicious() {
        let score = score_text("Let's delve into this and leverage what we learn.");
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }

    #[test]
    fn four_hits_votes_strong() {
        let score = score_text(
            "Let's delve into this multifaceted, nuanced topic and leverage what we learn.",
        );
        assert_eq!(score.vote, VoteStrength::Strong);
    }

    #[test]
    fn whole_word_does_not_match_inside_longer_word() {
        // "era" must not match inside "operation"; "harness" must not match inside "harnessed"
        let score = score_text("The operation was harnessed successfully by the team.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn case_insensitive_matches_sentence_initial_capitalized_form() {
        let score = score_text("Delve into this and also delve into that thoroughly today.");
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }

    #[test]
    fn phrase_regex_entry_matches() {
        let score = score_text("It's not just a fix, it's a whole new approach worth trying.");
        assert!(!score.evidence.is_empty());
    }

    #[test]
    fn longest_match_wins_suppresses_overlapping_shorter_evidence() {
        // "delve" (word) and any future overlapping phrase entry containing it
        // must not both produce evidence for the same span; here we assert the
        // simpler invariant that no two evidence entries have overlapping
        // raw_offset ranges, which is the property "longest match wins" exists
        // to guarantee (spec §11.3).
        let score = score_text("Let's delve into the details of this plan together.");
        for (i, a) in score.evidence.iter().enumerate() {
            for b in score.evidence.iter().skip(i + 1) {
                let overlaps = a.raw_offset.start < b.raw_offset.end && b.raw_offset.start < a.raw_offset.end;
                assert!(!overlaps, "evidence spans {:?} and {:?} overlap", a.raw_offset, b.raw_offset);
            }
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test vocabulary::`
Expected: FAIL — `Vocabulary` not defined yet.

- [ ] **Step 3: Write `src/backends/mod.rs`**

```rust
// src/backends/mod.rs
pub mod burstiness;
pub mod compression;
pub mod lexical_diversity;
pub mod punctuation;
pub mod readability;
pub mod vocabulary;
```

- [ ] **Step 4: Write `src/backends/vocabulary.rs`**

```rust
// src/backends/vocabulary.rs
use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};
use regex::{Regex, RegexBuilder};

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::dictionary::{Dictionary, EntryKind, MatchType};
use crate::document::Document;
use crate::score::{ConfidenceTier, Evidence, Score, Severity, VoteStrength};

const REGEX_SIZE_LIMIT: usize = 1 << 16; // matches the CI-asserted bound (Task 7)

struct ExactEntry {
    id: String,
    suggestion: Option<String>,
    whole_word: bool,
}

struct RegexEntry {
    id: String,
    suggestion: Option<String>,
    regex: Regex,
}

pub struct Vocabulary {
    automaton: AhoCorasick,
    exact_entries: Vec<ExactEntry>, // parallel to automaton's pattern order
    regex_entries: Vec<RegexEntry>,
}

struct RawHit {
    start: usize,
    end: usize,
    matched_text: String,
    suggestion: Option<String>,
}

impl Vocabulary {
    pub fn new(dictionary: Dictionary) -> Result<Vocabulary, String> {
        let mut patterns = Vec::new();
        let mut exact_entries = Vec::new();
        let mut regex_entries = Vec::new();

        for entry in &dictionary.entries {
            match entry.match_type {
                MatchType::Exact => {
                    let mut forms = vec![entry.pattern.clone()];
                    forms.extend(entry.variants.clone());
                    for form in forms {
                        patterns.push(if entry.case_sensitive { form } else { form.to_lowercase() });
                        exact_entries.push(ExactEntry {
                            id: entry.id.clone(),
                            suggestion: entry.suggested_replacements.first().cloned(),
                            whole_word: entry.whole_word,
                        });
                    }
                }
                MatchType::Regex => {
                    let regex = RegexBuilder::new(&entry.pattern)
                        .case_insensitive(!entry.case_sensitive)
                        .size_limit(REGEX_SIZE_LIMIT)
                        .build()
                        .map_err(|err| format!("entry '{}' failed to compile: {err}", entry.id))?;
                    regex_entries.push(RegexEntry {
                        id: entry.id.clone(),
                        suggestion: entry.suggested_replacements.first().cloned(),
                        regex,
                    });
                }
            }
        }

        let automaton = AhoCorasickBuilder::new()
            .match_kind(MatchKind::LeftmostLongest)
            .ascii_case_insensitive(true) // dictionary defaults case_sensitive:false; per-entry case-sensitive exact matches are rare enough in v1 to fold into one automaton with lowercased patterns above
            .build(&patterns)
            .map_err(|err| format!("failed to build vocabulary automaton: {err}"))?;

        Ok(Vocabulary { automaton, exact_entries, regex_entries })
    }

    fn raw_hits(&self, prose_text: &str) -> Vec<RawHit> {
        let mut hits = Vec::new();

        for m in self.automaton.find_iter(prose_text) {
            let entry = &self.exact_entries[m.pattern().as_usize()];
            if entry.whole_word && !is_word_bounded(prose_text, m.start(), m.end()) {
                continue;
            }
            hits.push(RawHit {
                start: m.start(),
                end: m.end(),
                matched_text: prose_text[m.start()..m.end()].to_string(),
                suggestion: entry.suggestion.clone(),
            });
        }

        for entry in &self.regex_entries {
            for m in entry.regex.find_iter(prose_text) {
                hits.push(RawHit {
                    start: m.start(),
                    end: m.end(),
                    matched_text: m.as_str().to_string(),
                    suggestion: entry.suggestion.clone(),
                });
            }
        }

        // Longest-match-wins: drop any hit fully contained within a longer hit
        // from a different match (spec §11.3).
        hits.sort_by_key(|h| (h.start, std::cmp::Reverse(h.end)));
        let mut kept: Vec<RawHit> = Vec::new();
        for hit in hits {
            let contained = kept.iter().any(|k| k.start <= hit.start && hit.end <= k.end && !(k.start == hit.start && k.end == hit.end));
            if !contained {
                kept.push(hit);
            }
        }
        kept
    }
}

fn is_word_bounded(text: &str, start: usize, end: usize) -> bool {
    let before_ok = text[..start].chars().next_back().map(|c| !c.is_alphanumeric()).unwrap_or(true);
    let after_ok = text[end..].chars().next().map(|c| !c.is_alphanumeric()).unwrap_or(true);
    before_ok && after_ok
}

fn line_and_column(text: &str, byte_offset: usize) -> (u32, u32) {
    let mut line = 1u32;
    let mut col = 1u32;
    for ch in text[..byte_offset].chars() {
        if ch == '\n' {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }
    }
    (line, col)
}

impl DetectorBackend for Vocabulary {
    fn name(&self) -> &str { "vocabulary" }
    fn family(&self) -> SignalFamily { SignalFamily::Vocabulary }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let mut evidence = Vec::new();
        let mut total_hits = 0usize;

        for span in &doc.prose_spans {
            let prose_text = &doc.raw[span.clone()];
            for hit in self.raw_hits(prose_text) {
                total_hits += 1;
                let raw_start = span.start + hit.start;
                let raw_end = span.start + hit.end;
                let (line, column) = line_and_column(&doc.raw, raw_start);
                evidence.push(Evidence {
                    raw_offset: raw_start..raw_end,
                    prose_offset: hit.start..hit.end,
                    line,
                    column,
                    matched_text: hit.matched_text,
                    severity: Severity::Medium,
                    suggestion: hit.suggestion,
                });
            }
        }

        let vote = if total_hits >= 4 {
            VoteStrength::Strong
        } else if total_hits >= 2 {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let human_probability = match vote {
            VoteStrength::Strong => 0.1,
            VoteStrength::Suspicious => 0.4,
            VoteStrength::None => 0.9,
        };

        ScoreOutcome::Scored(Score::new(
            "vocabulary".to_string(),
            SignalFamily::Vocabulary,
            human_probability,
            ConfidenceTier::Medium,
            vote,
            evidence,
        ))
    }
}
```

- [ ] **Step 5: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod backends;
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cargo test vocabulary::`
Expected: PASS. If `four_hits_votes_strong` or `two_hits_votes_suspicious` fail because the fixture sentence doesn't contain the exact hit count assumed, adjust the fixture text (not the threshold constants) until the assertion matches the stated Python-ported thresholds.

- [ ] **Step 7: Commit**

```bash
git add src/backends/mod.rs src/backends/vocabulary.rs src/main.rs
git commit -m "feat: add Vocabulary backend with aho-corasick + regex dictionary matching"
```

---

### Task 9: `Punctuation` backend

**Files:**
- Create: `src/backends/punctuation.rs`

**Interfaces:**
- Consumes: `crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily}`, `crate::document::Document`, `crate::score::*`.
- Produces: `Punctuation` struct implementing `DetectorBackend`, no constructor arguments needed (code-only, no dictionary — spec §11.2).

**Ported thresholds (verified against `check_ai_tells.py`):** count of `'—'` (em dash) characters in the document. `em_dash_count >= 6 && em_dash_count as f64 > word_count as f64 / 100.0` → `Strong`. `em_dash_count >= 3 && em_dash_count as f64 > word_count as f64 / 150.0` → `Suspicious`. Otherwise `None`.

- [ ] **Step 1: Write the failing tests**

```rust
// src/backends/punctuation.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::deadline::Deadline;
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn score_text(text: &str) -> crate::score::Score {
        let backend = Punctuation;
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        match backend.score(&doc, deadline) {
            crate::backend::ScoreOutcome::Scored(score) => score,
            _ => panic!("expected Scored"),
        }
    }

    #[test]
    fn no_em_dashes_votes_none() {
        let score = score_text("A plain sentence with no unusual punctuation at all here.");
        assert_eq!(score.vote, VoteStrength::None);
    }

    #[test]
    fn high_em_dash_density_votes_strong() {
        // 100 words, 7 em dashes -> 7 >= 6 and 7 > 100/100 (1.0)
        let words: Vec<String> = (0..100).map(|i| format!("w{i}")).collect();
        let mut text = words.join(" ");
        for _ in 0..7 {
            text.push_str(" — ");
        }
        let score = score_text(&text);
        assert_eq!(score.vote, VoteStrength::Strong);
    }

    #[test]
    fn moderate_em_dash_density_votes_suspicious() {
        // 150 words, 4 em dashes -> 4 >= 3 and 4 > 150/150 (1.0), but < 6 so not Strong
        let words: Vec<String> = (0..150).map(|i| format!("w{i}")).collect();
        let mut text = words.join(" ");
        for _ in 0..4 {
            text.push_str(" — ");
        }
        let score = score_text(&text);
        assert_eq!(score.vote, VoteStrength::Suspicious);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test punctuation::`
Expected: FAIL — `Punctuation` not defined yet.

- [ ] **Step 3: Write `src/backends/punctuation.rs`**

```rust
// src/backends/punctuation.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

pub struct Punctuation;

impl DetectorBackend for Punctuation {
    fn name(&self) -> &str { "punctuation" }
    fn family(&self) -> SignalFamily { SignalFamily::Punctuation }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        let em_dash_count = doc.raw.matches('\u{2014}').count();

        let vote = if em_dash_count >= 6 && em_dash_count as f64 > word_count as f64 / 100.0 {
            VoteStrength::Strong
        } else if em_dash_count >= 3 && em_dash_count as f64 > word_count as f64 / 150.0 {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let human_probability = match vote {
            VoteStrength::Strong => 0.15,
            VoteStrength::Suspicious => 0.4,
            VoteStrength::None => 0.9,
        };

        ScoreOutcome::Scored(Score::new(
            "punctuation".to_string(),
            SignalFamily::Punctuation,
            human_probability,
            ConfidenceTier::Medium,
            vote,
            vec![], // density counting is not a per-location match; no line-anchored evidence to report
        ))
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test punctuation::`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backends/punctuation.rs
git commit -m "feat: add Punctuation backend with em-dash density thresholds"
```

---

### Task 10: `Burstiness` backend

**Files:**
- Create: `src/backends/burstiness.rs`

**Interfaces:**
- Consumes: same as Task 9.
- Produces: `Burstiness` struct implementing `DetectorBackend`.

**Ported thresholds and gating — verified directly against `check_ai_tells.py`, with one correction to the spec's prose:** the spec (§2.2) states burstiness is gated "on ≥5 sentences" only, separately from the other stylometric families' 150-word floor. Reading the actual Python source (`check_ai_tells.py:139-149`), `burstiness_ratio()` is only ever called *inside* the `if word_count >= MIN_WORDS_FOR_STATS:` block — meaning the reference implementation gates burstiness on **both** `word_count >= 150` **and** `>= 5 sentences`, not the 5-sentence floor alone. This plan follows the verified source behavior, not the spec's slightly imprecise restatement of it, since faithfully porting `check_ai_tells.py` is the stated design goal throughout §2.2. Thresholds: `pstdev(lengths) / mean(lengths) < 0.25` → `Strong`; `< 0.35` → `Suspicious`; otherwise `None`; abstain (not `None`-vote) if `word_count < 150`, or fewer than 5 sentences, or mean sentence length is 0.

- [ ] **Step 1: Write the failing tests**

```rust
// src/backends/burstiness.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::ScoreOutcome;
    use crate::deadline::Deadline;
    use crate::document::Document;
    use crate::score::VoteStrength;

    fn outcome_for(text: &str) -> ScoreOutcome {
        let backend = Burstiness;
        let doc = Document::from_stdin_text(text.to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        backend.score(&doc, deadline)
    }

    fn words(n: usize) -> String {
        (0..n).map(|i| format!("word{i}")).collect::<Vec<_>>().join(" ")
    }

    #[test]
    fn short_document_abstains() {
        let outcome = outcome_for("Too short to measure burstiness on at all.");
        assert!(matches!(outcome, ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn under_150_words_abstains_even_with_many_sentences() {
        // 20 sentences of 5 words each = 100 words, well over 5 sentences but under 150 words
        let text = (0..20).map(|_| "Five short words in sentence.".to_string()).collect::<Vec<_>>().join(" ");
        let outcome = outcome_for(&text);
        assert!(matches!(outcome, ScoreOutcome::Abstained { .. }), "must abstain below the 150-word floor even with >=5 sentences");
    }

    #[test]
    fn uniform_sentence_lengths_over_150_words_votes_strong() {
        // 30 sentences of exactly 6 words each = 180 words, stdev = 0 -> burstiness ratio 0.0
        let sentence = "This sentence has six words total.";
        let text = std::iter::repeat(sentence).take(31).collect::<Vec<_>>().join(" ");
        let outcome = outcome_for(&text);
        match outcome {
            ScoreOutcome::Scored(score) => assert_eq!(score.vote, VoteStrength::Strong),
            other => panic!("expected Scored, got abstain/fail"),
        }
        let _ = words(1); // silence unused helper warning if not otherwise used
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test burstiness::`
Expected: FAIL — `Burstiness` not defined yet.

- [ ] **Step 3: Write `src/backends/burstiness.rs`**

```rust
// src/backends/burstiness.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150; // check_ai_tells.py MIN_WORDS_FOR_STATS
const MIN_SENTENCES: usize = 5;         // check_ai_tells.py:38 (burstiness_ratio)
const VERY_LOW_BURSTINESS: f64 = 0.25;
const LOW_BURSTINESS_THRESHOLD: f64 = 0.35;

pub struct Burstiness;

fn sentence_word_lengths(prose_text: &str) -> Vec<usize> {
    // mirrors check_ai_tells.py's SENTENCE_SPLIT: split after ., !, or ? followed by whitespace
    let mut lengths = Vec::new();
    let mut start = 0usize;
    let bytes = prose_text.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        let b = bytes[i];
        if (b == b'.' || b == b'!' || b == b'?') && bytes.get(i + 1).map(|c| c.is_ascii_whitespace()).unwrap_or(true) {
            let sentence = prose_text[start..=i].trim();
            let word_count = sentence.split_whitespace().count();
            if word_count > 0 {
                lengths.push(word_count);
            }
            start = i + 1;
        }
        i += 1;
    }
    let tail = prose_text[start..].trim();
    if !tail.is_empty() {
        let word_count = tail.split_whitespace().count();
        if word_count > 0 {
            lengths.push(word_count);
        }
    }
    lengths
}

fn population_stdev(values: &[usize]) -> f64 {
    let n = values.len() as f64;
    let mean = values.iter().sum::<usize>() as f64 / n;
    let variance = values.iter().map(|&v| { let d = v as f64 - mean; d * d }).sum::<f64>() / n;
    variance.sqrt()
}

impl DetectorBackend for Burstiness {
    fn name(&self) -> &str { "burstiness" }
    fn family(&self) -> SignalFamily { SignalFamily::Burstiness }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained { reason: format!("text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor") };
        }

        let prose: String = doc.prose_spans.iter().map(|s| &doc.raw[s.clone()]).collect::<Vec<_>>().join(" ");
        let lengths = sentence_word_lengths(&prose);
        if lengths.len() < MIN_SENTENCES {
            return ScoreOutcome::Abstained { reason: format!("only {} sentences, below the {MIN_SENTENCES}-sentence floor", lengths.len()) };
        }

        let mean = lengths.iter().sum::<usize>() as f64 / lengths.len() as f64;
        if mean == 0.0 {
            return ScoreOutcome::Abstained { reason: "mean sentence length is zero".to_string() };
        }
        let ratio = population_stdev(&lengths) / mean;

        let vote = if ratio < VERY_LOW_BURSTINESS {
            VoteStrength::Strong
        } else if ratio < LOW_BURSTINESS_THRESHOLD {
            VoteStrength::Suspicious
        } else {
            VoteStrength::None
        };

        let human_probability = match vote {
            VoteStrength::Strong => 0.15,
            VoteStrength::Suspicious => 0.4,
            VoteStrength::None => 0.85,
        };

        ScoreOutcome::Scored(Score::new(
            "burstiness".to_string(),
            SignalFamily::Burstiness,
            human_probability,
            ConfidenceTier::Medium,
            vote,
            vec![], // a document-level statistic; no line-anchored evidence
        ))
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test burstiness::`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backends/burstiness.rs
git commit -m "feat: add Burstiness backend, gated on both word and sentence floors per verified check_ai_tells.py behavior"
```

---

### Task 11: `LexicalDiversity` backend (hand-rolled MTLD)

**Files:**
- Create: `src/backends/lexical_diversity.rs`
- Modify: `Cargo.toml` (no new deps — `whichlang` already present)

**Interfaces:**
- Consumes: same as prior backend tasks, plus `whichlang` for the language gate.
- Produces: `LexicalDiversity` struct implementing `DetectorBackend`. **Evidence-only in v1** — always returns `VoteStrength::None` regardless of score (spec §2.2, §2.4, §7 item 5); still must abstain correctly and report `human_probability` for display.

**Ported parameters (verified against `check_ai_tells.py` + `lexicalrichness`):** gated on `word_count >= 150` (the same `MIN_WORDS_FOR_STATS` floor Python's call site applies) — the `MIN_WORDS_FOR_DIVERSITY = 50` constant exists in the Python but is never the binding floor in practice, since it's only reached from inside the 150-word-gated call site; both floors are implemented here for parity, with 150 always the effective one. MTLD uses TTR factor threshold `0.72`, forward-plus-reverse-pass averaging (the standard McCarthy & Jarvis 2010 algorithm, which is what the `lexicalrichness` Python library implements).

- [ ] **Step 1: Generate a reference vector from the actual Python library**

Per this user's global instruction to always use `uv` (never system Python) for anything Python: run

```bash
uv run --with lexicalrichness python3 -c "
from lexicalrichness import LexicalRichness
text = ('The quick brown fox jumps over the lazy dog. ' * 1) + \
       'A completely different sentence follows using entirely distinct words now. ' + \
       'Yet another unique sentence continues the passage onward here. ' + \
       'Repetition of the the the the the fills this next portion up. ' * 3
print(LexicalRichness(text).mtld(threshold=0.72))
"
```

Record the printed float value — call it `REFERENCE_MTLD` — and the exact `text` string used. This becomes the fixed fixture and expected value in the test below. (Running this once, by hand, during implementation is the "reference test vector" spec §8 requires; it does not need to be re-run automatically in CI, only recorded.)

- [ ] **Step 2: Write the failing tests** (fill in `REFERENCE_MTLD` and the fixture text with Step 1's actual output before running)

```rust
// src/backends/lexical_diversity.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mtld_matches_lexicalrichness_reference_vector() {
        // Fixture text and expected value from Step 1's `uv run --with lexicalrichness` output.
        let fixture_text = "REPLACE_WITH_STEP_1_TEXT";
        let reference_mtld = 0.0_f64; // REPLACE_WITH_STEP_1_OUTPUT
        let tokens = tokenize(fixture_text);
        let computed = mtld(&tokens, 0.72);
        assert!(
            (computed - reference_mtld).abs() < reference_mtld * 0.05 + 1.0,
            "computed MTLD {computed} diverges from reference {reference_mtld} by more than 5%+1.0 tolerance"
        );
    }

    #[test]
    fn identical_repeated_word_has_low_mtld() {
        let tokens = tokenize(&"same ".repeat(200));
        let computed = mtld(&tokens, 0.72);
        assert!(computed < 5.0, "a text with zero lexical variety should have very low MTLD, got {computed}");
    }

    #[test]
    fn all_unique_words_has_high_mtld() {
        let text = (0..200).map(|i| format!("uniqueword{i}")).collect::<Vec<_>>().join(" ");
        let tokens = tokenize(&text);
        let computed = mtld(&tokens, 0.72);
        assert!(computed > 100.0, "an all-unique-word text should have very high MTLD, got {computed}");
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = LexicalDiversity;
        let doc = Document::from_stdin_text("only a few words here total".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        assert!(matches!(backend.score(&doc, deadline), ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = LexicalDiversity;
        let text = "same ".repeat(200); // deliberately low-diversity, over the word floor
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(score.vote, VoteStrength::None, "LexicalDiversity must never vote above None in v1 (evidence-only, spec §7 item 5)");
        }
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cargo test lexical_diversity::`
Expected: FAIL — `LexicalDiversity`, `tokenize`, `mtld` not defined yet.

- [ ] **Step 4: Write `src/backends/lexical_diversity.rs`**

```rust
// src/backends/lexical_diversity.rs
use unicode_segmentation::UnicodeSegmentation;

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;
const MTLD_THRESHOLD: f64 = 0.72;

pub struct LexicalDiversity;

pub(crate) fn tokenize(text: &str) -> Vec<String> {
    text.unicode_words().map(|w| w.to_lowercase()).collect()
}

/// Standard MTLD (McCarthy & Jarvis, 2010): walk tokens accumulating a
/// running type-token ratio; each time it drops to/below `threshold`, close
/// a "factor" and reset. A leftover partial segment contributes a fractional
/// factor. Run forward and reverse, average the two — matching the algorithm
/// `lexicalrichness.mtld()` (used by `check_ai_tells.py`) implements.
pub(crate) fn mtld(tokens: &[String], threshold: f64) -> f64 {
    if tokens.is_empty() {
        return 0.0;
    }
    let forward = mtld_single_pass(tokens, threshold);
    let mut reversed = tokens.to_vec();
    reversed.reverse();
    let backward = mtld_single_pass(&reversed, threshold);
    (forward + backward) / 2.0
}

fn mtld_single_pass(tokens: &[String], threshold: f64) -> f64 {
    use std::collections::HashSet;
    let mut factor_count = 0.0_f64;
    let mut segment_len = 0usize;
    let mut types: HashSet<&str> = HashSet::new();

    for token in tokens {
        types.insert(token.as_str());
        segment_len += 1;
        let ttr = types.len() as f64 / segment_len as f64;
        if ttr <= threshold {
            factor_count += 1.0;
            types.clear();
            segment_len = 0;
        }
    }

    if segment_len > 0 {
        let ttr = types.len() as f64 / segment_len as f64;
        let partial = (1.0 - ttr) / (1.0 - threshold);
        factor_count += partial;
    }

    if factor_count == 0.0 {
        tokens.len() as f64
    } else {
        tokens.len() as f64 / factor_count
    }
}

impl DetectorBackend for LexicalDiversity {
    fn name(&self) -> &str { "lexical-diversity" }
    fn family(&self) -> SignalFamily { SignalFamily::LexicalDiversity }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained { reason: format!("text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor") };
        }

        let prose: String = doc.prose_spans.iter().map(|s| &doc.raw[s.clone()]).collect::<Vec<_>>().join(" ");

        if let Ok(lang) = std::panic::catch_unwind(|| whichlang::detect_language(&prose)) {
            if lang != whichlang::Lang::Eng {
                return ScoreOutcome::Abstained { reason: "non-English text; lexical-diversity assumptions are English-tuned".to_string() };
            }
        }

        let tokens = tokenize(&prose);
        let mtld_score = mtld(&tokens, MTLD_THRESHOLD);

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.
        // human_probability still reflects the measurement for display purposes.
        let human_probability = (mtld_score / 150.0).clamp(0.0, 1.0) as f32;

        ScoreOutcome::Scored(Score::new(
            "lexical-diversity".to_string(),
            SignalFamily::LexicalDiversity,
            human_probability,
            ConfidenceTier::Low,
            VoteStrength::None,
            vec![],
        ))
    }
}
```

- [ ] **Step 5: Fill in the reference vector and run tests**

Replace `REPLACE_WITH_STEP_1_TEXT` and `REPLACE_WITH_STEP_1_OUTPUT` in the test from Step 2 with Step 1's actual recorded values, then:

Run: `cargo test lexical_diversity::`
Expected: PASS. If `mtld_matches_lexicalrichness_reference_vector` fails, first check whether `tokenize`'s word-splitting diverges from `lexicalrichness`'s own tokenization (e.g. contraction handling) — if so, adjust `tokenize` to match, then re-run Step 1 to regenerate the reference vector against the corrected tokenization, rather than loosening the tolerance further.

- [ ] **Step 6: Commit**

```bash
git add src/backends/lexical_diversity.rs
git commit -m "feat: add LexicalDiversity backend with hand-rolled MTLD, evidence-only per spec §7"
```

---

### Task 12: `Readability` backend (hand-rolled Flesch-Kincaid)

**Files:**
- Create: `src/backends/readability.rs`

**Interfaces:**
- Consumes: same as Task 11.
- Produces: `Readability` struct implementing `DetectorBackend`. **Evidence-only in v1** (always `VoteStrength::None`).

**Formula:** Flesch-Kincaid Grade Level = `0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59`. Gated on `word_count >= 150` (spec §2.2) and the same `whichlang` English-only gate as `LexicalDiversity` (readability formulas are English-syllable-tuned).

- [ ] **Step 1: Generate a reference vector from `textstat`**

```bash
uv run --with textstat python3 -c "
import textstat
text = 'The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant hills. ' * 15
print(textstat.flesch_kincaid_grade(text))
"
```

Record the printed grade level as `REFERENCE_GRADE`. Because this hand-rolled implementation uses a standard vowel-group syllable-counting heuristic rather than `textstat`'s own internal syllable counter, exact bit-for-bit parity isn't the bar — the test below uses a ±1.5 grade-level tolerance, wide enough to absorb syllable-counting heuristic differences while still catching a genuinely wrong formula (e.g. swapped coefficients, which would diverge by far more than 1.5 grades).

- [ ] **Step 2: Write the failing tests**

```rust
// src/backends/readability.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn syllable_count_handles_common_cases() {
        assert_eq!(count_syllables("cat"), 1);
        assert_eq!(count_syllables("running"), 2);
        assert_eq!(count_syllables("beautiful"), 3);
        assert_eq!(count_syllables("the"), 1);
        assert_eq!(count_syllables("time"), 1); // silent trailing e
    }

    #[test]
    fn grade_level_matches_textstat_reference_within_tolerance() {
        let text = "The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant hills. ".repeat(15);
        let reference_grade = 0.0_f64; // REPLACE_WITH_STEP_1_OUTPUT
        let grade = flesch_kincaid_grade(&text);
        assert!(
            (grade - reference_grade).abs() < 1.5,
            "computed grade {grade} diverges from textstat reference {reference_grade} by more than 1.5"
        );
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = Readability;
        let doc = Document::from_stdin_text("just a few words".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        assert!(matches!(backend.score(&doc, deadline), ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = Readability;
        let text = "The quick brown fox jumps over the lazy dog. ".repeat(30);
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(score.vote, VoteStrength::None);
        }
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cargo test readability::`
Expected: FAIL — nothing defined yet.

- [ ] **Step 4: Write `src/backends/readability.rs`**

```rust
// src/backends/readability.rs
use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;

pub struct Readability;

/// Standard vowel-group syllable-counting heuristic: count transitions into a
/// vowel group, then drop one for a silent trailing "e" (when that leaves at
/// least one syllable). Not bit-identical to any specific library's counter —
/// validated against `textstat`'s output within a stated tolerance instead
/// (see Task 12's Step 1/2), since matching the standard Flesch-Kincaid
/// formula's grade-level ballpark is the actual correctness bar (spec §8, §10).
pub(crate) fn count_syllables(word: &str) -> usize {
    let word = word.to_lowercase();
    let is_vowel = |c: char| matches!(c, 'a' | 'e' | 'i' | 'o' | 'u' | 'y');
    let mut count = 0usize;
    let mut prev_was_vowel = false;
    for c in word.chars() {
        let v = is_vowel(c);
        if v && !prev_was_vowel {
            count += 1;
        }
        prev_was_vowel = v;
    }
    if word.ends_with('e') && count > 1 {
        count -= 1;
    }
    count.max(1)
}

fn count_sentences(text: &str) -> usize {
    let count = text.matches(['.', '!', '?']).count();
    count.max(1)
}

pub(crate) fn flesch_kincaid_grade(text: &str) -> f64 {
    let words: Vec<&str> = text.split_whitespace().collect();
    let word_count = words.len().max(1) as f64;
    let sentence_count = count_sentences(text) as f64;
    let syllable_count: usize = words.iter().map(|w| count_syllables(w)).sum();

    0.39 * (word_count / sentence_count) + 11.8 * (syllable_count as f64 / word_count) - 15.59
}

impl DetectorBackend for Readability {
    fn name(&self) -> &str { "readability" }
    fn family(&self) -> SignalFamily { SignalFamily::Readability }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained { reason: format!("text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor") };
        }

        let prose: String = doc.prose_spans.iter().map(|s| &doc.raw[s.clone()]).collect::<Vec<_>>().join(" ");

        if let Ok(lang) = std::panic::catch_unwind(|| whichlang::detect_language(&prose)) {
            if lang != whichlang::Lang::Eng {
                return ScoreOutcome::Abstained { reason: "non-English text; Flesch-Kincaid is English-syllable-tuned".to_string() };
            }
        }

        let grade = flesch_kincaid_grade(&prose);

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.
        let human_probability = (1.0 - (grade / 20.0).clamp(0.0, 1.0)) as f32;

        ScoreOutcome::Scored(Score::new(
            "readability".to_string(),
            SignalFamily::Readability,
            human_probability,
            ConfidenceTier::Low,
            VoteStrength::None,
            vec![],
        ))
    }
}
```

- [ ] **Step 5: Fill in the reference vector and run tests**

Replace `REPLACE_WITH_STEP_1_OUTPUT` with Step 1's actual printed value.

Run: `cargo test readability::`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/backends/readability.rs
git commit -m "feat: add Readability backend with hand-rolled Flesch-Kincaid, evidence-only per spec §7"
```

---

### Task 13: `Compression` backend (LZMA ratio + entropy-per-token)

**Files:**
- Create: `src/backends/compression.rs`

**Interfaces:**
- Consumes: same as prior backends, plus `lzma_rs`.
- Produces: `Compression` struct implementing `DetectorBackend`. **Evidence-only in v1** (always `VoteStrength::None`).

**Before writing the implementation:** `lzma-rs` 0.3's public API for *encoding* (not just decoding) must be checked against its current docs.rs page — the crate has historically been decode-focused, and the exact function/module name for producing LZMA-compressed bytes at a chosen preset/level may differ from what's assumed below. Per this user's standing instruction to consult docs before guessing on an unfamiliar package, do this check first and adjust the `compress` call below to match the real API before writing tests against it.

- [ ] **Step 0: Verify `lzma-rs` 0.3's encode API**

Run: `cargo add lzma-rs@0.3 --dry-run` then check `https://docs.rs/lzma-rs/0.3.0` (or `cargo doc -p lzma-rs --open` after adding it for real in Step 3) for the exact compression entry point (e.g. `lzma_rs::lzma_compress` vs an `xz_compress` variant, and how/whether a preset-6-equivalent compression level is exposed). If `lzma-rs` 0.3 turns out not to expose a usable encoder at all, fall back to computing only the entropy-per-token half of this backend and file a follow-up note in this plan's Task 20 commit message rather than silently shipping a fake ratio — do not guess at an API that doesn't compile.

- [ ] **Step 1: Write the failing tests**

```rust
// src/backends/compression.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn entropy_of_all_identical_tokens_is_zero() {
        let tokens = vec!["same"; 50];
        assert_eq!(entropy_per_token(&tokens), 0.0);
    }

    #[test]
    fn entropy_of_all_unique_tokens_is_log2_of_count() {
        let owned: Vec<String> = (0..16).map(|i| format!("t{i}")).collect();
        let tokens: Vec<&str> = owned.iter().map(|s| s.as_str()).collect();
        let entropy = entropy_per_token(&tokens);
        assert!((entropy - 4.0).abs() < 1e-9, "16 equally-likely unique tokens should have entropy log2(16)=4.0, got {entropy}");
    }

    #[test]
    fn compression_ratio_of_highly_repetitive_text_is_low() {
        let repetitive = "the same words repeat over and over again ".repeat(50);
        let ratio = compression_ratio(repetitive.as_bytes());
        assert!(ratio < 0.5, "highly repetitive text should compress well (low ratio), got {ratio}");
    }

    #[test]
    fn under_150_words_abstains() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        let backend = Compression;
        let doc = Document::from_stdin_text("short text".to_string(), false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        assert!(matches!(backend.score(&doc, deadline), ScoreOutcome::Abstained { .. }));
    }

    #[test]
    fn evidence_only_never_votes_above_none() {
        use crate::backend::ScoreOutcome;
        use crate::deadline::Deadline;
        use crate::document::Document;
        use crate::score::VoteStrength;
        let backend = Compression;
        let text = "the same words repeat over and over again ".repeat(50);
        let doc = Document::from_stdin_text(text, false);
        let deadline = Deadline::new(std::time::Duration::from_secs(1));
        if let ScoreOutcome::Scored(score) = backend.score(&doc, deadline) {
            assert_eq!(score.vote, VoteStrength::None);
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test compression::`
Expected: FAIL — nothing defined yet.

- [ ] **Step 3: Write `src/backends/compression.rs`**

```rust
// src/backends/compression.rs
use std::collections::HashMap;

use crate::availability::Availability;
use crate::backend::{DetectorBackend, ScoreOutcome, SignalFamily};
use crate::deadline::Deadline;
use crate::document::Document;
use crate::score::{ConfidenceTier, Score, VoteStrength};

const MIN_WORDS_FOR_STATS: usize = 150;

pub struct Compression;

/// LZMA compression ratio at a fixed preset (preset 6, matching
/// `check_ai_tells.py`'s `lzma.compress(raw, preset=6)` — spec §10 notes the
/// ratio is meaningless without pinning the same preset a threshold was
/// calibrated against). Exact call adjusted per Task 13 Step 0's docs.rs check.
pub(crate) fn compression_ratio(raw: &[u8]) -> f64 {
    if raw.is_empty() {
        return 1.0;
    }
    let mut compressed = Vec::new();
    // NOTE: exact function name/options verified against lzma-rs 0.3's docs.rs
    // page in Step 0 before this line was finalized; adjust here if the real
    // API differs from this call shape.
    lzma_rs::lzma_compress(&mut &raw[..], &mut compressed).expect("lzma compression should not fail on valid input");
    compressed.len() as f64 / raw.len() as f64
}

/// Shannon entropy (bits) over the document's word-frequency distribution —
/// a proxy for how predictable the token stream is, bundled into this
/// backend's evidence rather than a separate family (spec §2.2).
pub(crate) fn entropy_per_token(words: &[&str]) -> f64 {
    if words.is_empty() {
        return 0.0;
    }
    let mut freq: HashMap<&str, usize> = HashMap::new();
    for w in words {
        *freq.entry(*w).or_insert(0) += 1;
    }
    let n = words.len() as f64;
    -freq.values().map(|&c| { let p = c as f64 / n; p * p.log2() }).sum::<f64>()
}

impl DetectorBackend for Compression {
    fn name(&self) -> &str { "compression" }
    fn family(&self) -> SignalFamily { SignalFamily::Compression }
    fn availability(&self) -> Availability { Availability::Ready }

    fn score(&self, doc: &Document, _deadline: Deadline) -> ScoreOutcome {
        let word_count = doc.raw.split_whitespace().count();
        if word_count < MIN_WORDS_FOR_STATS {
            return ScoreOutcome::Abstained { reason: format!("text has {word_count} words, below the {MIN_WORDS_FOR_STATS}-word floor") };
        }

        let prose: String = doc.prose_spans.iter().map(|s| &doc.raw[s.clone()]).collect::<Vec<_>>().join(" ");
        let ratio = compression_ratio(prose.as_bytes());
        let words: Vec<&str> = prose.split_whitespace().collect();
        let _entropy = entropy_per_token(&words); // reported via evidence/log surface wired in Task 16-17's output formatting

        // Evidence-only in v1 (spec §2.2, §7 item 5): always VoteStrength::None.
        // Lower ratio (more compressible/predictable) maps toward lower human_probability.
        let human_probability = ratio.clamp(0.0, 1.0) as f32;

        ScoreOutcome::Scored(Score::new(
            "compression".to_string(),
            SignalFamily::Compression,
            human_probability,
            ConfidenceTier::Low,
            VoteStrength::None,
            vec![],
        ))
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo test compression::`
Expected: PASS. If Step 0's docs.rs check found a different API shape than `lzma_rs::lzma_compress(&mut reader, &mut writer)`, this is where that gets corrected before committing.

- [ ] **Step 5: Commit**

```bash
git add src/backends/compression.rs
git commit -m "feat: add Compression backend with LZMA ratio and entropy-per-token, evidence-only per spec §7"
```

---

### Task 14: Ensemble aggregation — quorum, `Verdict`, `warnings`

**Files:**
- Create: `src/aggregate.rs`
- Modify: `src/main.rs` (add `mod aggregate;`)

**Interfaces:**
- Consumes: `Vec<(SignalFamily, ScoreOutcome)>` — one outcome per enabled backend, produced by Task 16's CLI wiring.
- Produces: `Verdict` enum (`Flagged`, `Clean`, `Inconclusive`), `AggregationResult` struct (`verdict: Verdict`, `votes_cast: usize`, `warnings: Vec<{ family: SignalFamily, error: Error }>`, `scores: Vec<Score>` — the full per-family `Score`s, for `lint`/`detect` output to render), `aggregate(outcomes: Vec<(SignalFamily, ScoreOutcome)>, quorum: usize) -> AggregationResult`.

- [ ] **Step 1: Write the failing tests**

```rust
// src/aggregate.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend::{ScoreOutcome, SignalFamily};
    use crate::error::Error;
    use crate::score::{ConfidenceTier, Score, VoteStrength};

    fn scored(family: SignalFamily, vote: VoteStrength) -> ScoreOutcome {
        ScoreOutcome::Scored(Score::new(format!("{:?}", family), family, 0.5, ConfidenceTier::Medium, vote, vec![]))
    }

    #[test]
    fn two_of_three_strong_votes_flags() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Strong)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::Strong)),
            (SignalFamily::Burstiness, scored(SignalFamily::Burstiness, VoteStrength::None)),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Flagged);
        assert_eq!(result.votes_cast, 3);
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn one_of_three_suspicious_stays_clean() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Suspicious)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, scored(SignalFamily::Burstiness, VoteStrength::None)),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Clean);
    }

    #[test]
    fn abstained_and_failed_do_not_count_toward_votes_cast() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::Strong)),
            (SignalFamily::Punctuation, ScoreOutcome::Abstained { reason: "n/a".into() }),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::InternalError("boom".into()))),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.votes_cast, 1);
        assert_eq!(result.verdict, Verdict::Inconclusive, "only 1 vote_cast < quorum 2 -> Inconclusive even though the one vote was Strong");
    }

    #[test]
    fn failed_backend_populates_warnings() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::None)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::ModelLoadFailed("corrupt".into()))),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.warnings.len(), 1);
        assert_eq!(result.warnings[0].family, SignalFamily::Burstiness);
    }

    #[test]
    fn clean_with_warnings_is_still_clean_verdict_but_nonempty_warnings() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, scored(SignalFamily::Vocabulary, VoteStrength::None)),
            (SignalFamily::Punctuation, scored(SignalFamily::Punctuation, VoteStrength::None)),
            (SignalFamily::Burstiness, ScoreOutcome::Failed(Error::NetworkError("timeout".into()))),
        ];
        // Only 2 votes_cast (Vocabulary, Punctuation) meets quorum=2, both None -> Clean.
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Clean);
        assert_eq!(result.warnings.len(), 1);
    }

    #[test]
    fn zero_votes_cast_is_inconclusive_not_clean() {
        let outcomes = vec![
            (SignalFamily::Vocabulary, ScoreOutcome::Abstained { reason: "n/a".into() }),
            (SignalFamily::Punctuation, ScoreOutcome::Abstained { reason: "n/a".into() }),
        ];
        let result = aggregate(outcomes, 2);
        assert_eq!(result.verdict, Verdict::Inconclusive);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test aggregate::`
Expected: FAIL — `aggregate`, `Verdict`, `AggregationResult` not defined yet.

- [ ] **Step 3: Write `src/aggregate.rs`**

```rust
// src/aggregate.rs
use crate::backend::{ScoreOutcome, SignalFamily};
use crate::error::Error;
use crate::score::{Score, VoteStrength};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Flagged,
    Clean,
    Inconclusive,
}

#[derive(Debug, Clone)]
pub struct Warning {
    pub family: SignalFamily,
    pub error: Error,
}

#[derive(Debug)]
pub struct AggregationResult {
    pub verdict: Verdict,
    pub votes_cast: usize,
    pub warnings: Vec<Warning>,
    pub scores: Vec<Score>,
}

/// Aggregates one `ScoreOutcome` per enabled family into a quorum verdict
/// (spec §2.4). `votes_cast` counts every family that returned `Scored(_)`
/// regardless of vote strength — a family that scored and found nothing
/// suspicious still completed a real analysis; only `Abstained`/`Failed` are
/// non-participation. If `votes_cast < quorum`, the verdict is `Inconclusive`
/// regardless of what the families that did vote said (spec §2.4).
pub fn aggregate(outcomes: Vec<(SignalFamily, ScoreOutcome)>, quorum: usize) -> AggregationResult {
    let mut votes_cast = 0usize;
    let mut agreeing = 0usize;
    let mut warnings = Vec::new();
    let mut scores = Vec::new();

    for (family, outcome) in outcomes {
        match outcome {
            ScoreOutcome::Scored(score) => {
                votes_cast += 1;
                if matches!(score.vote, VoteStrength::Suspicious | VoteStrength::Strong) {
                    agreeing += 1;
                }
                scores.push(score);
            }
            ScoreOutcome::Abstained { .. } => {}
            ScoreOutcome::Failed(error) => {
                warnings.push(Warning { family, error });
            }
        }
    }

    let verdict = if votes_cast < quorum {
        Verdict::Inconclusive
    } else if agreeing >= quorum {
        Verdict::Flagged
    } else {
        Verdict::Clean
    };

    AggregationResult { verdict, votes_cast, warnings, scores }
}
```

- [ ] **Step 4: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod aggregate;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test aggregate::`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/aggregate.rs src/main.rs
git commit -m "feat: add quorum aggregation with Inconclusive verdict and warnings surface"
```

---

### Task 15: Output rendering — human + `--format json`, exit codes

**Files:**
- Create: `src/output.rs`
- Modify: `src/main.rs` (add `mod output;`)

**Interfaces:**
- Consumes: `crate::aggregate::{AggregationResult, Verdict, Warning}`.
- Produces: `DetectOutputJson` (serde-serializable, carries `schema_version`), `fn render_human(result: &AggregationResult) -> String`, `fn render_json(result: &AggregationResult) -> String`, `fn exit_code(result: &AggregationResult) -> i32` (spec §3's exact mapping). Task 16 (`detect` command) is the first consumer.

- [ ] **Step 1: Write the failing tests**

```rust
// src/output.rs (bottom of file)
#[cfg(test)]
mod tests {
    use super::*;
    use crate::aggregate::{AggregationResult, Verdict, Warning};
    use crate::backend::SignalFamily;
    use crate::error::Error;

    fn result(verdict: Verdict, warnings: Vec<Warning>) -> AggregationResult {
        AggregationResult { verdict, votes_cast: 3, warnings, scores: vec![] }
    }

    #[test]
    fn clean_with_no_warnings_exits_zero() {
        assert_eq!(exit_code(&result(Verdict::Clean, vec![])), 0);
    }

    #[test]
    fn flagged_exits_one() {
        assert_eq!(exit_code(&result(Verdict::Flagged, vec![])), 1);
    }

    #[test]
    fn clean_with_warnings_exits_two_not_zero() {
        let warning = Warning { family: SignalFamily::Burstiness, error: Error::NetworkError("timeout".into()) };
        assert_eq!(exit_code(&result(Verdict::Clean, vec![warning])), 2);
    }

    #[test]
    fn flagged_with_warnings_exits_two_not_one() {
        let warning = Warning { family: SignalFamily::Burstiness, error: Error::NetworkError("timeout".into()) };
        assert_eq!(exit_code(&result(Verdict::Flagged, vec![warning])), 2);
    }

    #[test]
    fn inconclusive_exits_three() {
        assert_eq!(exit_code(&result(Verdict::Inconclusive, vec![])), 3);
    }

    #[test]
    fn json_output_carries_schema_version() {
        let json = render_json(&result(Verdict::Clean, vec![]));
        let parsed: serde_json::Value = serde_json::from_str(&json).expect("valid JSON");
        assert!(parsed.get("schema_version").is_some());
    }

    #[test]
    fn json_output_distinguishes_clean_with_and_without_warnings() {
        let clean_no_warnings = render_json(&result(Verdict::Clean, vec![]));
        let warning = Warning { family: SignalFamily::Burstiness, error: Error::NetworkError("timeout".into()) };
        let clean_with_warnings = render_json(&result(Verdict::Clean, vec![warning]));
        assert_ne!(clean_no_warnings, clean_with_warnings, "a Clean verdict with warnings must be distinguishable in JSON output from one without (spec §2.4)");
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test output::`
Expected: FAIL — nothing defined yet.

- [ ] **Step 3: Write `src/output.rs`**

```rust
// src/output.rs
use owo_colors::OwoColorize;
use serde::Serialize;

use crate::aggregate::{AggregationResult, Verdict};

const SCHEMA_VERSION: &str = "1.0.0";

#[derive(Serialize)]
struct WarningJson {
    family: String,
    error: String,
}

#[derive(Serialize)]
struct DetectOutputJson {
    schema_version: String,
    verdict: String,
    votes_cast: usize,
    warnings: Vec<WarningJson>,
}

/// Exit codes per spec §3: 0=Clean(no warnings), 1=Flagged, 2=tool failure OR
/// Clean/Flagged with non-empty warnings, 3=Inconclusive. Mapping *any*
/// warnings to 2 (not 0/1) is deliberately conservative: a corrupted backend
/// silently producing a "clean" `0` exit is the failure mode this exists to
/// prevent (spec §3).
pub fn exit_code(result: &AggregationResult) -> i32 {
    if !result.warnings.is_empty() {
        return 2;
    }
    match result.verdict {
        Verdict::Clean => 0,
        Verdict::Flagged => 1,
        Verdict::Inconclusive => 3,
    }
}

pub fn render_json(result: &AggregationResult) -> String {
    let verdict = match result.verdict {
        Verdict::Flagged => "Flagged",
        Verdict::Clean => "Clean",
        Verdict::Inconclusive => "Inconclusive",
    };
    let out = DetectOutputJson {
        schema_version: SCHEMA_VERSION.to_string(),
        verdict: verdict.to_string(),
        votes_cast: result.votes_cast,
        warnings: result
            .warnings
            .iter()
            .map(|w| WarningJson { family: format!("{:?}", w.family), error: w.error.to_string() })
            .collect(),
    };
    serde_json::to_string_pretty(&out).expect("DetectOutputJson always serializes")
}

pub fn render_human(result: &AggregationResult) -> String {
    let mut lines = Vec::new();
    match result.verdict {
        Verdict::Flagged => lines.push(format!("{}", "Flagged".red().bold())),
        Verdict::Clean => lines.push(format!("{}", "Clean".green().bold())),
        Verdict::Inconclusive => lines.push(format!("{}", "Inconclusive".yellow().bold())),
    }
    lines.push(format!("{} families voted", result.votes_cast));
    for warning in &result.warnings {
        lines.push(format!("{}: {:?} backend failed: {}", "warning".yellow(), warning.family, warning.error));
    }
    lines.join("\n")
}
```

- [ ] **Step 4: Wire module into `src/main.rs`**

```rust
// src/main.rs (add near top)
mod output;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo test output::`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/output.rs src/main.rs
git commit -m "feat: add human/JSON output rendering with spec-exact exit code mapping"
```

---

### Task 16: `detect` CLI command

**Files:**
- Modify: `src/cli/detect.rs`
- Modify: `Cargo.toml` (no new deps)

**Interfaces:**
- Consumes: everything from Tasks 3-15.
- Produces: `pub fn run(path: &str, json: bool, markdown_hint: bool) -> i32`, updates `src/cli/mod.rs`'s `Command::Detect` variant to carry `--format json` and `--markdown` flags, and updates `src/main.rs`'s dispatch accordingly.

- [ ] **Step 1: Write the failing integration test**

```rust
// tests/detect_command.rs
use std::io::Write;
use std::process::{Command, Stdio};

#[test]
fn detect_on_clean_text_via_stdin_exits_zero() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("detect")
        .arg("-")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn nobotrs");
    child.stdin.take().unwrap().write_all(
        b"The cat sat on the windowsill. It watched birds outside. Later it slept in the sun."
    ).unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(0));
}

#[test]
fn detect_json_output_is_valid_json_with_schema_version() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["detect", "-", "--format", "json"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn nobotrs");
    child.stdin.take().unwrap().write_all(b"Some plain text to analyze here today.").unwrap();
    let output = child.wait_with_output().unwrap();
    let stdout = String::from_utf8(output.stdout).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&stdout).expect("stdout should be valid JSON");
    assert!(parsed.get("schema_version").is_some());
}

#[test]
fn detect_missing_file_exits_two() {
    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .args(["detect", "/nonexistent/path/does-not-exist.md"])
        .output()
        .expect("run nobotrs");
    assert_eq!(output.status.code(), Some(2));
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test --test detect_command`
Expected: FAIL — `detect` still returns the Task 1 stub.

- [ ] **Step 3: Add `--format`/`--markdown` flags to the CLI definition**

```rust
// src/cli/mod.rs — replace the Detect variant
#[derive(Subcommand)]
pub enum Command {
    Detect {
        path: String,
        #[arg(long, value_enum, default_value = "human")]
        format: OutputFormat,
        #[arg(long)]
        markdown: bool,
    },
    Lint { path: String },
    Scan { dir: String },
    Config,
}

#[derive(Clone, clap::ValueEnum)]
pub enum OutputFormat {
    Human,
    Json,
}
```

- [ ] **Step 4: Write `src/cli/detect.rs`**

```rust
// src/cli/detect.rs
use crate::aggregate::aggregate;
use crate::backend::DetectorBackend;
use crate::backends::burstiness::Burstiness;
use crate::backends::compression::Compression;
use crate::backends::lexical_diversity::LexicalDiversity;
use crate::backends::punctuation::Punctuation;
use crate::backends::readability::Readability;
use crate::backends::vocabulary::Vocabulary;
use crate::deadline::Deadline;
use crate::dictionary::Dictionary;
use crate::document::Document;
use crate::output::{exit_code, render_human, render_json};

const DEFAULT_QUORUM: usize = 2; // spec §2.4: 2-of-3 over Vocabulary/Punctuation/Burstiness

pub fn run(path: &str, json: bool, markdown_hint: bool) -> i32 {
    let doc = match load_document(path, markdown_hint) {
        Ok(doc) => doc,
        Err(msg) => {
            eprintln!("nobotrs: {msg}");
            return 2;
        }
    };

    let vocabulary = match Vocabulary::new(Dictionary::embedded()) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("nobotrs: failed to build vocabulary backend: {msg}");
            return 2;
        }
    };

    let deadline = Deadline::new(std::time::Duration::from_secs(10));

    let outcomes = vec![
        (vocabulary.family(), vocabulary.score(&doc, deadline)),
        (Punctuation.family(), Punctuation.score(&doc, deadline)),
        (Burstiness.family(), Burstiness.score(&doc, deadline)),
        (LexicalDiversity.family(), LexicalDiversity.score(&doc, deadline)),
        (Readability.family(), Readability.score(&doc, deadline)),
        (Compression.family(), Compression.score(&doc, deadline)),
    ];

    let result = aggregate(outcomes, DEFAULT_QUORUM);

    if json {
        println!("{}", render_json(&result));
    } else {
        println!("{}", render_human(&result));
    }

    exit_code(&result)
}

fn load_document(path: &str, markdown_hint: bool) -> Result<Document, String> {
    if path == "-" {
        let mut raw = String::new();
        std::io::Read::read_to_string(&mut std::io::stdin(), &mut raw)
            .map_err(|e| format!("failed to read stdin: {e}"))?;
        Ok(Document::from_stdin_text(raw, markdown_hint))
    } else {
        Document::from_path(std::path::Path::new(path)).map_err(|e| format!("failed to read '{path}': {e}"))
    }
}
```

- [ ] **Step 5: Wire flags through in `src/main.rs`**

```rust
// src/main.rs — update the Detect match arm
Command::Detect { path, format, markdown } => {
    let json = matches!(format, cli::OutputFormat::Json);
    cli::detect::run(&path, json, markdown)
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cargo test --test detect_command`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cli/detect.rs src/cli/mod.rs src/main.rs tests/detect_command.rs
git commit -m "feat: wire detect command to full backend pipeline with quorum verdict"
```

---

### Task 17: `lint` CLI command

**Files:**
- Modify: `src/cli/lint.rs`
- Test: `tests/lint_command.rs`

**Interfaces:**
- Consumes: same backends as Task 16, but bypasses `aggregate` entirely — every backend's raw `Evidence` is reported (spec §3).
- Produces: `pub fn run(path: &str) -> i32`.

- [ ] **Step 1: Write the failing integration test**

```rust
// tests/lint_command.rs
use std::io::Write;
use std::process::{Command, Stdio};

#[test]
fn lint_reports_single_vocabulary_hit_that_detect_would_suppress() {
    // A single "delve" is below detect's quorum (needs >=2 Vocabulary hits to
    // even reach Suspicious, plus a second agreeing family to meet quorum=2) —
    // but lint must still surface it, since lint never applies quorum (spec §3).
    let mut child = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("lint")
        .arg("-")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn nobotrs");
    child.stdin.take().unwrap().write_all(
        b"Let's delve into this topic together and see where it leads us next."
    ).unwrap();
    let output = child.wait_with_output().unwrap();
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.to_lowercase().contains("delve"), "lint output should mention the matched tell word; got: {stdout}");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --test lint_command`
Expected: FAIL — `lint` still returns the Task 1 stub.

- [ ] **Step 3: Write `src/cli/lint.rs`**

```rust
// src/cli/lint.rs
use crate::backend::DetectorBackend;
use crate::backends::punctuation::Punctuation;
use crate::backends::vocabulary::Vocabulary;
use crate::backend::ScoreOutcome;
use crate::deadline::Deadline;
use crate::dictionary::Dictionary;
use crate::document::Document;

pub fn run(path: &str) -> i32 {
    let doc = match load_document(path) {
        Ok(doc) => doc,
        Err(msg) => {
            eprintln!("nobotrs: {msg}");
            return 2;
        }
    };

    let vocabulary = match Vocabulary::new(Dictionary::embedded()) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("nobotrs: failed to build vocabulary backend: {msg}");
            return 2;
        }
    };
    let deadline = Deadline::new(std::time::Duration::from_secs(10));

    let mut any_evidence = false;
    for outcome in [vocabulary.score(&doc, deadline), Punctuation.score(&doc, deadline)] {
        if let ScoreOutcome::Scored(score) = outcome {
            for ev in &score.evidence {
                any_evidence = true;
                let suggestion = ev.suggestion.as_deref().unwrap_or("(no suggestion)");
                println!("{}:{}: {} [{}] -> {}", ev.line, ev.column, ev.matched_text, score.backend, suggestion);
            }
        }
    }

    if !any_evidence {
        println!("No tells found.");
    }
    0
}

fn load_document(path: &str) -> Result<Document, String> {
    if path == "-" {
        let mut raw = String::new();
        std::io::Read::read_to_string(&mut std::io::stdin(), &mut raw)
            .map_err(|e| format!("failed to read stdin: {e}"))?;
        Ok(Document::from_stdin_text(raw, false))
    } else {
        Document::from_path(std::path::Path::new(path)).map_err(|e| format!("failed to read '{path}': {e}"))
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --test lint_command`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/lint.rs tests/lint_command.rs
git commit -m "feat: wire lint command to report unfiltered per-backend evidence"
```

---

### Task 18: `scan <dir>` CLI command

**Files:**
- Modify: `src/cli/scan.rs`
- Test: `tests/scan_command.rs`

**Interfaces:**
- Consumes: `walkdir::WalkDir`, the same `detect`-equivalent pipeline as Task 16 (per file).
- Produces: `pub fn run(dir: &str) -> i32`; applies default ignore patterns (`.git/`, `node_modules/`) and prints a summary line.

- [ ] **Step 1: Write the failing integration test**

```rust
// tests/scan_command.rs
use std::process::Command;

#[test]
fn scan_prints_summary_line_and_ignores_git_dir() {
    let dir = std::env::temp_dir().join(format!("nobotrs-scan-test-{}", std::process::id()));
    std::fs::create_dir_all(dir.join(".git")).unwrap();
    std::fs::write(dir.join(".git/should-be-ignored.md"), "delve delve delve delve delve").unwrap();
    std::fs::write(dir.join("clean.md"), "The cat sat on the mat and watched the birds outside quietly.").unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("scan")
        .arg(dir.to_str().unwrap())
        .output()
        .expect("run nobotrs scan");
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("analyzed"), "scan output should print a summary line; got: {stdout}");
    assert!(!stdout.contains("should-be-ignored"), "scan must not report on files under .git/");

    std::fs::remove_dir_all(&dir).unwrap();
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --test scan_command`
Expected: FAIL — `scan` still returns the Task 1 stub.

- [ ] **Step 3: Write `src/cli/scan.rs`**

```rust
// src/cli/scan.rs
use walkdir::WalkDir;

use crate::aggregate::aggregate;
use crate::backend::DetectorBackend;
use crate::backends::burstiness::Burstiness;
use crate::backends::compression::Compression;
use crate::backends::lexical_diversity::LexicalDiversity;
use crate::backends::punctuation::Punctuation;
use crate::backends::readability::Readability;
use crate::backends::vocabulary::Vocabulary;
use crate::aggregate::Verdict;
use crate::deadline::Deadline;
use crate::dictionary::Dictionary;
use crate::document::Document;

const DEFAULT_QUORUM: usize = 2;
const IGNORED_DIR_NAMES: [&str; 2] = [".git", "node_modules"];

pub fn run(dir: &str) -> i32 {
    let vocabulary = match Vocabulary::new(Dictionary::embedded()) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("nobotrs: failed to build vocabulary backend: {msg}");
            return 2;
        }
    };
    let deadline = Deadline::new(std::time::Duration::from_secs(10));

    let mut analyzed = 0usize;
    let mut flagged = 0usize;
    let mut inconclusive = 0usize;
    let mut any_warnings = false;

    let walker = WalkDir::new(dir).into_iter().filter_entry(|e| {
        !IGNORED_DIR_NAMES.iter().any(|ignored| e.path().components().any(|c| c.as_os_str() == *ignored))
    });

    for entry in walker.filter_map(|e| e.ok()) {
        if !entry.file_type().is_file() {
            continue;
        }
        let is_prose = matches!(
            entry.path().extension().and_then(|e| e.to_str()).map(|e| e.to_ascii_lowercase()).as_deref(),
            Some("md") | Some("markdown") | Some("txt")
        );
        if !is_prose {
            continue;
        }

        let doc = match Document::from_path(entry.path()) {
            Ok(doc) => doc,
            Err(_) => continue,
        };
        analyzed += 1;

        let outcomes = vec![
            (vocabulary.family(), vocabulary.score(&doc, deadline)),
            (Punctuation.family(), Punctuation.score(&doc, deadline)),
            (Burstiness.family(), Burstiness.score(&doc, deadline)),
            (LexicalDiversity.family(), LexicalDiversity.score(&doc, deadline)),
            (Readability.family(), Readability.score(&doc, deadline)),
            (Compression.family(), Compression.score(&doc, deadline)),
        ];
        let result = aggregate(outcomes, DEFAULT_QUORUM);
        if !result.warnings.is_empty() {
            any_warnings = true;
        }
        match result.verdict {
            Verdict::Flagged => flagged += 1,
            Verdict::Inconclusive => inconclusive += 1,
            Verdict::Clean => {}
        }
    }

    println!("{analyzed} files analyzed, {flagged} flagged, {inconclusive} inconclusive");

    if any_warnings {
        2
    } else if flagged > 0 {
        1
    } else {
        0
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --test scan_command`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/scan.rs tests/scan_command.rs
git commit -m "feat: wire scan command as batch-detect with default ignore patterns and summary line"
```

---

### Task 19: `config` CLI command (basic — path resolution and availability status)

**Files:**
- Modify: `src/cli/config.rs`
- Test: `tests/config_command.rs`

**Interfaces:**
- Consumes: `directories::ProjectDirs`.
- Produces: `pub fn run() -> i32`, printing the resolved platform config path and each default-build backend's `Availability`. API-key/model-download management is explicitly deferred to the `classifier`/`api-clients` tier plans (out of scope here).

- [ ] **Step 1: Write the failing integration test**

```rust
// tests/config_command.rs
use std::process::Command;

#[test]
fn config_prints_a_resolved_path_not_the_literal_linux_default() {
    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs")).arg("config").output().expect("run nobotrs config");
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("config.toml"), "config output should mention the resolved config file path; got: {stdout}");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --test config_command`
Expected: FAIL — `config` still returns the Task 1 stub.

- [ ] **Step 3: Write `src/cli/config.rs`**

```rust
// src/cli/config.rs
use directories::ProjectDirs;

use crate::backend::DetectorBackend;
use crate::backends::burstiness::Burstiness;
use crate::backends::compression::Compression;
use crate::backends::lexical_diversity::LexicalDiversity;
use crate::backends::punctuation::Punctuation;
use crate::backends::readability::Readability;
use crate::backends::vocabulary::Vocabulary;
use crate::dictionary::Dictionary;

pub fn run() -> i32 {
    let config_path = ProjectDirs::from("com", "nobotrs", "nobotrs")
        .map(|dirs| dirs.config_dir().join("config.toml"))
        .expect("could not resolve a config directory for this platform");
    println!("Config file: {}", config_path.display());

    let vocabulary_status = match Vocabulary::new(Dictionary::embedded()) {
        Ok(v) => format!("{:?}", v.availability()),
        Err(_) => "Unavailable(dictionary failed to compile)".to_string(),
    };
    println!("vocabulary: {vocabulary_status}");
    println!("punctuation: {:?}", Punctuation.availability());
    println!("burstiness: {:?}", Burstiness.availability());
    println!("lexical-diversity: {:?}", LexicalDiversity.availability());
    println!("readability: {:?}", Readability.availability());
    println!("compression: {:?}", Compression.availability());
    println!("(classifier/perplexity/api-clients tiers are managed by their own plans; not yet built)");

    0
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --test config_command`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/config.rs tests/config_command.rs
git commit -m "feat: wire config command to print resolved platform config path and backend availability"
```

---

### Task 20: Packaging basics — release profile, binary size CI check, `cargo-dist` scaffold

**Files:**
- Modify: `Cargo.toml` (release profile already added in Task 1 — verify it's present)
- Create: `.github/workflows/binary-size.yml`
- Create: `deny.toml`

**Interfaces:**
- Produces: a CI job that fails the build if the default-feature release binary exceeds a stated size threshold (spec §5's ~10MB target, CI-asserted rather than hoped for), and a `cargo-deny` config for the supply-chain audit spec §5 requires.

- [ ] **Step 1: Write `.github/workflows/binary-size.yml`**

```yaml
name: binary-size
on: [push, pull_request]
jobs:
  check-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo build --release --no-default-features
      - name: Assert default binary stays under budget
        run: |
          SIZE=$(stat -c%s target/release/nobotrs)
          BUDGET=$((15 * 1024 * 1024))
          echo "binary size: $SIZE bytes (budget: $BUDGET bytes)"
          if [ "$SIZE" -gt "$BUDGET" ]; then
            echo "::error::default build binary exceeds the 15MB size budget (target is ~10MB per spec §5)"
            exit 1
          fi
```

The budget is set at 15MB rather than a razor-thin 10MB: the spec states ~10MB as an aspiration to converge toward, not a number this plan should treat as already precisely hit — a CI budget with some headroom still catches real regressions (a dependency accidentally pulling in something heavy) without failing the very first CI run over a few hundred KB of initial slack. Tighten this threshold once an actual measured baseline exists.

- [ ] **Step 2: Write `deny.toml`**

```toml
[licenses]
allow = ["MIT", "Apache-2.0", "Unlicense", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib", "CC0-1.0"]

[bans]
multiple-versions = "warn"

[advisories]
vulnerability = "deny"
unmaintained = "warn"
```

- [ ] **Step 3: Run the audit locally**

Run: `cargo install cargo-deny --locked && cargo deny check`
Expected: passes, or names a specific dependency to address before proceeding (do not silence a real advisory/license finding by loosening `deny.toml` without understanding why it fired).

- [ ] **Step 4: Verify the release build compiles with the profile settings**

Run: `cargo build --release`
Expected: succeeds; note the resulting `target/release/nobotrs` size for future reference against the CI budget.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/binary-size.yml deny.toml
git commit -m "chore: add binary-size CI budget and cargo-deny supply-chain audit config"
```

---

### Task 21: End-to-end integration test — the v1 "definition of done" scenario

**Files:**
- Test: `tests/definition_of_done.rs`

**Interfaces:**
- Consumes: the fully wired `detect` command from Task 16.
- Verifies the exact scenario spec §3.1 states as the minimum "must work": `nobotrs detect README.md` on the default build, no feature flags, no model downloads, returns a verdict in well under a second, fully offline.

- [ ] **Step 1: Write the test**

```rust
// tests/definition_of_done.rs
use std::process::Command;
use std::time::Instant;

#[test]
fn detect_on_this_repos_readme_completes_in_under_a_second_offline() {
    let readme = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("README.md");
    assert!(readme.exists(), "this test assumes a README.md exists at the crate root");

    let start = Instant::now();
    let output = Command::new(env!("CARGO_BIN_EXE_nobotrs"))
        .arg("detect")
        .arg(readme.to_str().unwrap())
        // No network-related env vars set; no API keys; default build only.
        .output()
        .expect("run nobotrs detect");
    let elapsed = start.elapsed();

    assert!(elapsed.as_secs_f64() < 1.0, "detect took {:?}, expected well under 1 second", elapsed);
    assert!(
        matches!(output.status.code(), Some(0) | Some(1) | Some(2) | Some(3)),
        "detect should exit with one of its four defined codes, got {:?}",
        output.status.code()
    );
}
```

- [ ] **Step 2: Run the test**

Run: `cargo test --test definition_of_done --release`
Expected: PASS. If it's slow, profile which backend dominates (the `Compression` backend's LZMA call is the most likely culprit on a large README) before assuming the whole architecture needs rework.

- [ ] **Step 3: Run the full test suite one final time**

Run: `cargo test`
Expected: PASS — every test from Tasks 1-21 green together.

- [ ] **Step 4: Commit**

```bash
git add tests/definition_of_done.rs
git commit -m "test: verify detect meets the spec's v1 definition-of-done scenario end to end"
```

---

## Self-Review Notes

- **Spec coverage:** §2.1 (Document/Error/Availability/Deadline/DetectorBackend) → Tasks 2-3, 5. §2.2 (tiers/families) → Tasks 8-13. §2.3 (Score/Evidence) → Task 4. §2.4 (aggregation/quorum/Inconclusive/warnings) → Task 14. §3 (CLI surface, exit codes) → Tasks 15-19. §4 (config path) → Task 19 (API keys/keychain precedence deferred to the `api-clients` tier plan, since the default build makes no API calls). §5 (packaging) → Task 20. §11 (dictionary) → Tasks 6-7. §8 (testing strategy: reference vectors, size-limited regex CI, quorum tests) → Tasks 7, 11, 12, 14. Not covered here, by design: §2.2's `classifier`/`perplexity`/`api-clients` rows, §6 (plugin packaging), §9 items 1-3/5 (ML-tier due diligence) — these belong to the sibling plans.
- **Burstiness gating correction:** Task 10 documents and implements the verified `check_ai_tells.py` behavior (both the 150-word and 5-sentence floors), which differs slightly from §2.2's prose claiming only the 5-sentence floor applies. Flagged inline in Task 10 rather than silently deviating from the written spec without explanation.
- **`VoteStrength` addition:** Task 4 documents why `Score` needed a field not literally listed in the spec's §2.3 struct sketch — necessary for §2.4's aggregation to be implementable at all, not a design change.
- **Placeholder scan:** the one deliberately-left "fill in from a command's output" pattern (Tasks 11, 12, 13's reference-vector generation) is not a placeholder in the prohibited sense — it's a concrete, reproducible step producing a real value, chosen over fabricating academic test-vector numbers I can't independently verify without network access at plan-writing time.
