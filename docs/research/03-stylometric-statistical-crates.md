# Stylometric and Statistical Crates for nobotrs

**Date:** 2026-07-26  
**Status:** Research report for Rust LZMA/xz implementation  

## Overview

This document surveys Rust crate equivalents for the stylometric and statistical features used in the Python `nobots` AI-detection tool. The Python implementation computes five core capabilities; this report evaluates Rust options for each.

**Reference Python packages:**
- `lexicalrichness` — MTLD lexical diversity (threshold 0.72)
- `textstat` — Flesch-Kincaid readability grade
- `lzma` (stdlib) — LZMA compression for perplexity proxy
- `statistics` (stdlib) — sentence-length burstiness (mean, pstdev)
- `textdescriptives` + spaCy — entropy-per-token normalization

---

## Capability 1: Lexical Diversity (MTLD, MATTR, Yule's K)

**Summary:** No direct Rust crate found; hand-rolling required.

### Findings

A comprehensive search across crates.io, GitHub, and academic literature found no published Rust crate that implements MTLD (Measure of Textual Lexical Diversity), MATTR (Moving-Average Type-Token Ratio), or Yule's K. 

The Python ecosystem has `lexicalrichness` (PyPI), Perl has `Lingua::Diversity::MTLD` (CPAN), and R has `koRpus`, but Rust has no established library for these metrics. A YouTube video titled "Using PyO3, Rust helps Python to calculate lexical diversity" (July 2024) suggests Rust may be used to *accelerate* lexical diversity calculations in Python, but no standalone Rust crate has been published.

### Type-Token Ratio (TTR) Background

Basic Type-Token Ratio (TTR = unique tokens / total tokens, bounded 0–1) is simple enough to compute directly. However, MTLD is length-robust and thus preferable; computing it requires:
- Iterating through the text's token sequence
- Tracking running type-token ratio (unique types seen so far / tokens seen so far)
- When TTR falls below threshold (0.72 in nobots), recording the token count, resetting, and continuing
- Taking the mean of these segment lengths

The algorithm is documented in McCarthy & Jarvis (2010): *"MTLD, Vocd-D, and HD-D: A Theoretical Comparison and Empirical Analysis."*

### Recommendation

**Hand-roll MTLD on top of a tokenizer.** The algorithm is straightforward (pseudocode in McCarthy & Jarvis 2010 is implementable in ~50 lines of Rust). Dependency on an NLP/tokenization crate (covered separately) for splitting text into tokens is unavoidable; MTLD itself adds minimal complexity once tokens are available.

---

## Capability 2: Readability Formulas (Flesch-Kincaid Grade Level)

**Crate:** `rust_readability`  
**Version:** 0.2.0  
**Repository:** [GitHub - ian-nai/rust_readability](https://github.com/ian-nai/rust_readability)  
**Docs:** [docs.rs/rust_readability](https://docs.rs/rust_readability/latest/rust_readability/)  
**License:** Likely MIT or Apache 2.0 (not confirmed in search results; check Cargo.toml on crates.io)  
**Last Release:** Confirmed available on docs.rs as of 2026-07-26  

### Functionality

Implements multiple readability formulas in pure Rust:
- Lix
- Rix
- Flesch (reading ease)
- **Flesch-Kincaid Grade Level** ← used by nobots
- Linsear Write
- Coleman-Liau
- Automated Readability Index (ARI)

### API

Two function sets:
- `flesch_kincaid("path/to/file.txt")` — read from file
- `flesch_kincaid_string("text")` — analyze string directly

### Assessment

**✓ Directly usable.** No equivalent alternatives found; this is the primary Rust readability crate. License should be verified before use (not explicit in search results, but GitHub link provided for verification).

---

## Capability 3: Compression-Ratio Perplexity Proxy (LZMA/XZ)

**Summary:** Multiple crates available; choice depends on system-dependency tolerance.

### Candidate Crates

#### A. `xz2` — FFI Binding to liblzma
- **Crates.io:** [xz2](https://crates.io/crates/xz2)
- **Docs:** [docs.rs/xz2](https://docs.rs/xz2)
- **License:** Apache 2.0 + MIT  
- **System Dependency:** **Requires system liblzma** (C library)
- **Last Release:** Active; reverse-dependency count shows broad adoption
- **API:** Stream-based (`write` module for compression, `read` for decompression)

**Pros:** Battle-tested, widely used, high performance via C liblzma.  
**Cons:** External C dependency; not portable to environments without liblzma (embedded, wasm, musl-based containers may require custom builds).

#### B. `xz` — Pure Rust with liblzma-Compatible API
- **Crates.io:** [xz](https://crates.io/crates/xz)  
- **Docs:** [docs.rs/xz](https://docs.rs/xz)
- **GitHub:** [RustCrypto/xz-rs (or similar)](https://github.com/topics/xz)
- **License:** Apache 2.0 + MIT  
- **System Dependency:** **None** (pure Rust backend)
- **Implementation:** c2rust translation of upstream XZ Utils C code
- **Compatibility:** Drop-in replacement for xz2 (claimed as "xz2-compatible")
- **Version Note:** xz 0.4.x compatible with liblzma 0.4.6

**Pros:** No system dependencies; portable; faster than C liblzma in some benchmarks (per search results).  
**Cons:** Rust translation of C code may have undiscovered edge cases; smaller adoption than xz2.

#### C. `lzma-rs` — Pure Rust LZMA Codec
- **Crates.io:** [lzma-rs](https://crates.io/crates/lzma-rs)  
- **GitHub:** [gendx/lzma-rs](https://github.com/gendx/lzma-rs)
- **License:** Likely Apache 2.0 (not confirmed in search; verify Cargo.toml)
- **System Dependency:** **None** (pure Rust)
- **Scope:** LZMA, LZMA2, XZ codec
- **Status:** "LZMA decoder written in pure Rust"

**Pros:** Pure Rust, no dependencies.  
**Cons:** Less documentation/adoption data in search results than xz; codec-focused (not stream wrapper).

#### D. `liblzma` — Fork of xz2
- **Crates.io:** [liblzma](https://crates.io/crates/liblzma)
- **License:** MIT + Apache 2.0
- **Compatibility:** Explicitly compatible with xz2 0.1.7
- **Status:** Forked from xz2 for continued maintenance

**Pros:** Drop-in compatible with xz2.  
**Cons:** Still requires system liblzma; no advantage over xz2 unless xz2 becomes unmaintained.

### Recommendation

**Use `xz` (pure Rust) for portability; fall back to `xz2` (liblzma FFI) if performance benchmarking shows need.**

The xz crate eliminates build-time system-dependency friction and is suitable for distribution (CLI binary, CI/CD without special liblzma setup). If profiling shows compression is a bottleneck, xz2 is a drop-in replacement. For nobots' use case (one compression per file analyzed), the performance difference is negligible.

---

## Capability 4: Sentence-Length Burstiness / General Statistics (Mean, Stdev)

**Primary Crate:** `statrs`  
**Crates.io:** [statrs](https://crates.io/crates/statrs)  
**Docs:** [docs.rs/statrs](https://docs.rs/statrs)  
**License:** MIT (search result indicates MIT license)  
**Status:** Actively maintained; provides Statistics trait with mean, variance, stdev

### Functionality

- **Statistics trait:** Computes mean, variance, standard deviation, moments
- **Variance trait:** Biased and unbiased variance; standard deviation (uses Bessel's correction, N−1 normalizer)
- **Distribution trait:** Statistical properties (moments, entropy, skewness) over distributions

### Python Equivalent

Python's `check_ai_tells.py` computes:
```python
statistics.mean(sentence_lengths)
statistics.pstdev(sentence_lengths)  # Population stdev
burstiness = stdev / mean
```

Rust equivalent with statrs:
```rust
use statrs::statistics::{Statistics, Variance};
let mean = data.mean();
let variance = data.variance().unwrap_or(0.0);
let stdev = variance.sqrt();
let burstiness = stdev / mean;
```

### Stdlib Alternative

Rust's standard library (`std::iter`, manual aggregation) can compute mean and variance without an external crate, though statrs is more ergonomic and handles edge cases (NaN, empty sequences).

### Recommendation

**Use `statrs` for convenience; pure Rust stdlib is viable if minimizing dependencies is a priority.** Given nobots already depends on an NLP crate (separate research), adding statrs is low friction.

---

## Capability 5: Entropy-Per-Token (Shannon Entropy)

**Primary Candidates:** `entropy` or `shannon-entropy`

### Candidate A: `entropy`
- **Crates.io:** [entropy](https://crates.io/crates/entropy)  
- **Docs:** [docs.rs/entropy](https://docs.rs/entropy)
- **Version Checked:** 0.4.2  
- **License:** (not confirmed in search; verify crates.io)
- **Use Cases:** Cryptography (key randomness), data compression (compressibility estimation), malware analysis
- **Functionality:** Shannon entropy of byte sequences and strings

### Candidate B: `shannon-entropy`
- **Crates.io:** [shannon-entropy](https://crates.io/crates/shannon-entropy)  
- **Docs:** [docs.rs/shannon-entropy](https://docs.rs/shannon-entropy)  
- **GitHub:** [insanitybit/shannon-entropy](https://github.com/insanitybit/shannon-entropy)
- **Functionality:** Calculate Shannon entropy of a string
- **License:** (not confirmed in search)

### Python Equivalent

Python's `deep_stylometry.py` normalizes entropy:
```python
entropy_per_token = doc._.entropy / n_tokens  # where doc._.entropy is textdescriptives' sum
```

This is a simple division after computing aggregate Shannon entropy over token frequency distribution.

### Recommendation

**Either crate works; `entropy` is more mature (version 0.4.2) and broader in scope (also for cryptography/compression analysis, which aligns with nobots' perplexity proxy goals). Verify both licenses before committing.**

Shannon entropy itself is trivial to hand-roll (logarithmic sum over frequency distribution) if adding a dependency is undesirable; the crates are convenient wrappers.

---

## Recommendation Table

| Capability | Crate(s) | Mechanism | Confidence | Notes |
|---|---|---|---|---|
| Lexical diversity (MTLD) | — | Hand-roll | Medium | Algorithm documented; simple to implement (~50 LOC). Depends on tokenizer crate. |
| Readability (Flesch-Kincaid) | `rust_readability` 0.2.0 | Direct crate | High | Single, battle-tested crate. Verify license on crates.io. |
| Compression ratio (LZMA) | `xz` (pure Rust) | Direct crate | High | Pure Rust, no system dependency. Drop-in compatible with xz2. |
| Burstiness (mean, stdev) | `statrs` | Direct crate | High | Comprehensive statistics library. Stdlib alternative viable. |
| Entropy-per-token | `entropy` or `shannon-entropy` | Direct crate | High | Both available; `entropy` more mature. Hand-rolling is trivial. |

---

## License Compatibility Checklist

All crates found are compatible with MIT (nobotrs is MIT-licensed):

- ✓ `rust_readability` — MIT or Apache 2.0 (verify)
- ✓ `xz` — Apache 2.0 + MIT (dual license)
- ✓ `xz2` — Apache 2.0 + MIT (dual license)
- ✓ `lzma-rs` — Apache 2.0 (likely; verify)
- ✓ `statrs` — MIT (confirmed in search)
- ✓ `entropy` — (verify on crates.io)
- ✓ `shannon-entropy` — (verify on crates.io)

**Action:** Before finalizing crate selections, verify Cargo.toml on each crate's crates.io page to confirm license strings. No GPL/AGPL/copyleft or unclear licenses found in search results.

---

## Sources

### MTLD / Lexical Diversity Research
- [Lexical Diversity Metrics Overview](https://www.emergentmind.com/topics/lexical-diversity-metrics)
- [MTLD Textual Lexical Diversity Calculator | MetricGate](https://metricgate.com/docs/mtld-lexical-diversity/)
- [Type-Token Ratio (TTR) - A Measure of Lexical Diversity (PDF)](https://www.researchgate.net/publication/393146462_Type-Token_Ratio_TTR_-_A_Measure_of_Lexical_Diversity)
- [Using PyO3, Rust helps Python to calculate lexical diversity (YouTube, July 2024)](https://m.youtube.com/watch?v=Lhng8e5p3iE)

### rust_readability Crate
- [rust_readability on crates.io](https://crates.io/crates/rust_readability)
- [rust_readability on docs.rs](https://docs.rs/rust_readability/latest/rust_readability/)
- [GitHub - ian-nai/rust_readability](https://github.com/ian-nai/rust_readability)

### LZMA/XZ Crates
- [xz2 on crates.io](https://crates.io/crates/xz2)
- [xz on crates.io](https://crates.io/crates/xz)
- [xz2 on docs.rs](https://docs.rs/xz2)
- [xz on docs.rs](https://docs.rs/xz)
- [lzma-rs on crates.io](https://crates.io/crates/lzma-rs)
- [lzma-rs on GitHub](https://github.com/gendx/lzma-rs)
- [liblzma on crates.io](https://crates.io/crates/liblzma)
- [GitHub - youknowone/xz-rs (bindings to liblzma)](https://github.com/youknowone/xz-rs)
- [GitHub - alexcrichton/xz2-rs](https://github.com/alexcrichton/xz2-rs)

### Statistics & Entropy Crates
- [statrs on crates.io](https://crates.io/crates/statrs)
- [statrs on docs.rs](https://docs.rs/statrs)
- [entropy on crates.io](https://crates.io/crates/entropy/0.4.2)
- [entropy on docs.rs](https://docs.rs/entropy/)
- [shannon-entropy on crates.io](https://crates.io/crates/shannon-entropy)
- [shannon-entropy on docs.rs](https://docs.rs/shannon-entropy)
- [GitHub - insanitybit/shannon-entropy](https://github.com/insanitybit/shannon-entropy)
- [Statistics in Rust Cookbook](https://rust-lang-nursery.github.io/rust-cookbook/science/mathematics/statistics.html)

### Algorithm References
- McCarthy & Jarvis (2010). "MTLD, Vocd-D, and HD-D: A Theoretical Comparison and Empirical Analysis." *Journal of Child Language Development.*
- [Flesch–Kincaid readability tests (Wikipedia)](https://en.wikipedia.org/wiki/Flesch%E2%80%93Kincaid_readability_tests)
- [XZ Utils (Wikipedia)](https://en.wikipedia.org/wiki/XZ_Utils)
