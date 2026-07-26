# Rust Pattern-Matching and Text-Scanning Crates

## Overview

This research evaluates Rust crates for fast, correct text pattern-matching and scanning to replicate the word-list/phrase-list/punctuation-scanning approach from the Python `nobots` reference implementation. The Python tool uses regex to match dozens of tell-words and tell-phrases case-insensitively, plus Unicode-aware sentence splitting for stylometric analysis.

For a production Rust port expected to handle hundreds of tell-words and dozens of tell-phrases (growing over time), we need crates that:
1. Support fast, case-insensitive exact-word or phrase matching at scale
2. Handle Unicode-aware sentence and word segmentation correctly
3. Maintain compatible licensing (MIT/Apache-2.0/BSD preferred)
4. Show active maintenance

---

## `regex` Crate

**Crates.io:** [regex](https://crates.io/crates/regex)  
**Docs.rs:** [regex 1.13.1](https://docs.rs/regex/latest/regex/)  
**GitHub:** [rust-lang/regex](https://github.com/rust-lang/regex)

### Current State
- **Latest Version:** 1.13.1
- **Release Date:** July 15, 2026 (actively maintained)
- **License:** MIT OR Apache-2.0 ✓
- **Maintenance:** Actively maintained; rust-lang organization; 1,624 commits on master; 47 open issues; 26 PRs in progress
- **MSRV:** 1.65.0

### Capabilities

The `regex` crate is Rust's standard regex engine, providing:

- **Case-Insensitive Matching:** Supported via `(?i)` flag or builder option (`RegexBuilder::case_insensitive()`). Example: `regex::Regex::new(r"(?i)delve|leverage|seamless")`.
- **Alternation Patterns:** Multiple branches work with left-to-right precedence; earlier alternatives take priority if multiple match at the same position.
- **Linear-Time Guarantee:** Implements bounded backtracking via finite automata construction (regex-automata + regex-syntax backends). Worst-case time complexity is O(m × n), where m ∝ regex size and n ∝ haystack size. Protects against ReDoS attacks even on untrusted patterns.
- **Unicode Support:** Full Unicode character classes and properties by default; configurable to reduce binary size.

### Performance Characteristics

For a large word list (hundreds of alternatives), regex alternation hits diminishing returns:

- **Pros:** Handles both literal words and phrase patterns in one pass with unified API. Matches semantics of original Python implementation.
- **Cons:** Performance degrades with regex size. A regex like `\b(word1|word2|...|word500)\b` compiles to a state machine whose performance scales roughly linearly with the number of alternatives in practice, but may exhibit noticeable startup cost and regex compilation time.

### Fit for This Use Case

**Moderate fit.** Regex works for phrase matching (e.g., `"it'?s not just [a-z ]+, it'?s"`) where alternation is a natural fit. However, for a growing list of exact tell-words (hundreds of entries), a dedicated multi-pattern matching algorithm (aho-corasick) is significantly faster and more maintainable than a mega-alternation regex.

### Known Gotchas

- No backreferences or lookahead/lookbehind assertions (by design, for linear-time guarantee).
- Regex compilation time and size grows with pattern complexity; not ideal for 500+ word lists.
- Case-insensitive matching only supports ASCII mode by default for ASCII letter classes; full Unicode case-folding works but adds overhead.

---

## `aho-corasick` Crate

**Crates.io:** [aho-corasick](https://crates.io/crates/aho-corasick)  
**Docs.rs:** [aho-corasick 1.1.4](https://docs.rs/aho-corasick/)  
**GitHub:** [BurntSushi/aho-corasick](https://github.com/BurntSushi/aho-corasick)

### Current State
- **Latest Version:** 1.1.4
- **Release Date:** June 4, 2026 (actively maintained)
- **License:** Unlicense OR MIT ✓
- **Maintenance:** Actively maintained; BurntSushi (Andrew Gallant); 300 commits; 7 open issues; 10 PRs
- **MSRV:** 1.60.0

### Capabilities

The `aho-corasick` crate implements the Aho-Corasick algorithm for simultaneously finding occurrences of many patterns in a single pass:

- **Multiple Pattern Matching:** Searches for dozens or hundreds of literal substrings in a single haystack in linear time O(n + z), where n is haystack length and z is number of matches.
- **Case-Insensitive Matching:** Built-in via `AhoCorasickBuilder::ascii_case_insensitive(true)`. Works on ASCII subset; full Unicode case folding handled by preprocessing patterns.
- **Overlapping Matches:** Supports detecting overlapping patterns (e.g., "foo" and "ooo" both matching in "foooo").
- **Stream Processing:** Can search and replace in streaming mode without loading entire text into memory.
- **Advanced Match Semantics:** Supports leftmost-first and leftmost-longest matching modes—more nuanced than typical Aho-Corasick implementations.
- **SIMD Acceleration:** Uses vectorized prefilters for sub-linear scanning on smaller pattern sets (< ~100 patterns).

### Performance Characteristics

For 100–500+ exact-word patterns:

- **Pros:** Linear-time guarantee independent of pattern count. State machine construction is O(sum of pattern lengths). After construction, a single haystack pass finds all matches. Dramatically faster than regex alternation.
- **Cons:** Prefilters (SIMD acceleration) are most effective with < ~100 patterns; larger sets see diminishing prefilter gains. Must handle phrases and wildcards differently than literals (phrase handling requires additional logic).

### Fit for This Use Case

**Excellent fit for tell-words; partial fit for tell-phrases.**

- **Tell-words** (exact literals): Direct win. A word list like `["delve", "leverage", "seamless", …]` maps to an automaton that scans a document in linear time and reports all matches.
- **Tell-phrases** (regex patterns with wildcards): More complex. Phrases like `"it'?s not just [a-z ]+, it'?s"` cannot be represented as fixed literal strings. Options:
  1. Use `aho-corasick` for the tell-words, regex for tell-phrases, combine results.
  2. Pre-expand phrase patterns into a set of example strings and run them through aho-corasick (less flexible; misses phrase variations).
  3. Use regex alone for both word and phrase matching (simpler but slower).

For a production tool, **hybrid approach** (aho-corasick for words, regex for phrases) is recommended: aho-corasick handles the high-volume word list scaling, regex handles flexible pattern matching.

### Known Gotchas

- Phrase matching requires regex or additional preprocessing; not a drop-in replacement for mixed word+phrase detection.
- SIMD prefilters can be disabled if predictable performance under edge cases is needed: `AhoCorasickBuilder::prefilter(None)`.

---

## `fst` Crate

**Crates.io:** [fst](https://crates.io/crates/fst)  
**Docs.rs:** [fst 0.4.7](https://docs.rs/fst/)  
**GitHub:** [BurntSushi/fst](https://github.com/BurntSushi/fst)

### Current State
- **Latest Version:** 0.4.7
- **Release Date:** July 16, 2026 (actively maintained)
- **License:** MIT OR Unlicense ✓
- **Maintenance:** Actively maintained; BurntSushi; 271 commits; 2.1k stars; 26 open issues; 16 PRs
- **MSRV:** 1.x (version-specific)

### Capabilities

The `fst` crate uses finite state transducers to compactly represent large ordered sets and maps:

- **Compression:** Keys and values are stored using FST compression, exploiting common prefixes and suffixes. Supports billions of keys.
- **Ordered Keys:** Keys must be lexicographically sorted; the FST preserves ordering for range queries and prefix searches.
- **Query Methods:** Search via regex automata, Levenshtein distance (fuzzy matching), or lexicographic ranges.
- **Disk-Based Access:** Can memory-map FST structures, enabling fast searches without loading entire dataset into memory.
- **Set Operations:** Supports union, intersection, difference on multiple FSTs.

### Performance Characteristics

For 500–1000 tell-words as a membership lookup:

- **Pros:** Extremely space-efficient. If you need to persist the word list to disk and query it rapidly across many documents, FST shines.
- **Cons:** Overkill for in-memory word-list membership testing. A simple `HashSet` is faster for random lookups and requires no sorting. FST construction requires sorted input; useful when data is naturally sorted or when disk persistence is a requirement.

### Fit for This Use Case

**Low fit for basic word-list matching; high fit for persistent, large-scale indexed lookups.**

For `nobotrs`:
- If the tell-word list is baked into the binary or loaded once per run from a small file (< 100k words), **skip FST**. A `HashSet` or `aho-corasick` is sufficient.
- If the tool needs to support user-supplied growing word lists (> 1M words), persistent storage, or multi-tool coordination via shared FST indexes, **FST becomes valuable**.

### Known Gotchas

- Requires lexicographically sorted keys during construction; cannot be built incrementally.
- Map values limited to 64-bit unsigned integers (not suitable for arbitrary value types).
- Byte-string keys only (no native Unicode string support; must encode UTF-8).
- Random access patterns can be slower on traditional HDDs.

---

## `unicode-segmentation` Crate

**Crates.io:** [unicode-segmentation](https://crates.io/crates/unicode-segmentation)  
**Docs.rs:** [unicode-segmentation 1.13.3](https://docs.rs/unicode-segmentation/)  
**GitHub:** [unicode-rs/unicode-segmentation](https://github.com/unicode-rs/unicode-segmentation)

### Current State
- **Latest Version:** 1.13.3
- **Release Date:** June 1, 2026 (actively maintained)
- **License:** MIT OR Apache-2.0 ✓
- **Maintenance:** Actively maintained; unicode-rs organization; 247 commits; 669 stars; 22 open issues; 4 PRs
- **Recent Work:** Unicode 17.0.0 support; ASCII fast paths for word indices; performance optimizations

### Capabilities

The `unicode-segmentation` crate provides iterators for splitting text according to Unicode Standard Annex #29:

- **Grapheme Cluster Segmentation** (`Graphemes`): Splits on perceived character boundaries, handling combining marks and multi-codepoint sequences (e.g., emoji with modifiers).
- **Word Boundary Detection** (`UnicodeWords`, `UnicodeWordIndices`): Identifies word boundaries per Unicode rules. Provides both complete words and byte-offset tracking.
- **Sentence Boundary Detection** (`UnicodeSentences`, `UnicodeSentenceIndices`): Segments text at sentence boundaries, respecting Unicode rules for sentence-final punctuation.
- **no_std Support:** Works in `#![no_std]` environments; no dependency on libstd.
- **Performance:** Recent commits include "ASCII fast path" optimizations for common case (ASCII-only text).

### Fit for This Use Case

**Excellent fit for stylometric analysis.**

The Python reference implementation splits sentences via regex (`SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")`) to compute burstiness (sentence-length variation). Using `unicode-segmentation` provides:

- **Correctness:** Handles edge cases (abbreviations, ellipsis, Unicode punctuation variants) per UAX#29 rules, not just ASCII `.!?`.
- **Robustness:** Correctly identifies em dashes and curly quotes across locales; important for punctuation counting (em-dash density is one of the Python tool's signals).
- **Word Splitting:** `UnicodeWords` correctly splits on word boundaries for word-count statistics, avoiding ASCII-only assumptions.

### Known Gotchas

- No sentence-ending abbreviation handling (e.g., "Dr. Smith" may split incorrectly). For high-precision NLP, consider pairing with a dedicated sentence tokenizer (beyond scope of this research).
- Performance is good but not optimal for streaming gigabytes; reasonable for document-scale text processing.

---

## Practical Recommendation

### For `nobotrs` MVP

**Recommended combination:**

1. **`aho-corasick`** (primary): Dedicate this to tell-word scanning. Pre-build an `AhoCorasick` automaton from the tell-word list at startup. Scan text in linear time. Fast, maintainable, scales to hundreds of words.

2. **`regex`** (secondary): Use for tell-phrase matching. Build regex patterns for phrases like `"it'?s not just [a-z ]+, it'?s"`. Combine results from both scanners.

3. **`unicode-segmentation`** (supporting): Use `UnicodeSentences` and `UnicodeWords` iterators to split text for stylometric calculations (burstiness, em-dash density). Replaces the Python tool's ad-hoc `SENTENCE_SPLIT.split()`.

### Rationale

- **Performance:** aho-corasick + regex avoids the pathological regex-alternation scaling. For 500 tell-words, this is 1-2 orders of magnitude faster than a mega-regex.
- **Correctness:** Unicode-segmentation handles edge cases in sentence splitting that regex cannot. Critical for accurate burstiness and punctuation statistics.
- **Maintainability:** Clear separation of concerns (exact words → aho-corasick, flexible patterns → regex, text splitting → unicode-segmentation).
- **Licensing:** All three are MIT-compatible; safe for MIT-licensed `nobotrs`.

### Architecture Sketch

```
TextAnalyzer {
  tell_words: AhoCorasick,      // Built once at startup
  tell_phrases: Regex,          // Built once at startup
  text: &str,
}

impl TextAnalyzer {
  fn scan(&self) -> AnalysisResult {
    // Word and phrase matches
    word_hits = self.tell_words.find_iter(text)
    phrase_hits = self.tell_phrases.find_iter(text)
    
    // Stylometric features
    sentences = UnicodeSentences::new(text).collect()
    word_lengths = UnicodeSentences::new(text)
      .map(|s| UnicodeWords::new(s).count())
      .collect()
    
    // Compute burstiness, em-dash density, etc.
    ...
  }
}
```

### Considered but Not Recommended

- **`fst`:** Overkill unless `nobotrs` supports user-supplied 1M+ word lists or requires persistent, disk-based indexes.
- **`regex` alone:** Possible but slower than hybrid for high-volume word lists. If simplicity is paramount and word counts stay under ~50, regex-only is acceptable.

---

## Sources

- [regex crate on crates.io](https://crates.io/crates/regex)
- [regex documentation on docs.rs](https://docs.rs/regex/latest/regex/)
- [rust-lang/regex on GitHub](https://github.com/rust-lang/regex)
- [aho-corasick crate on crates.io](https://crates.io/crates/aho-corasick)
- [aho-corasick documentation on docs.rs](https://docs.rs/aho-corasick/)
- [BurntSushi/aho-corasick on GitHub](https://github.com/BurntSushi/aho-corasick)
- [fst crate on crates.io](https://crates.io/crates/fst)
- [fst documentation on docs.rs](https://docs.rs/fst/)
- [BurntSushi/fst on GitHub](https://github.com/BurntSushi/fst)
- [unicode-segmentation crate on crates.io](https://crates.io/crates/unicode-segmentation)
- [unicode-segmentation documentation on docs.rs](https://docs.rs/unicode-segmentation/)
- [unicode-rs/unicode-segmentation on GitHub](https://github.com/unicode-rs/unicode-segmentation)
