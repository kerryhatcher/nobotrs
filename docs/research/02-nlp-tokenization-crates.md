# NLP / Tokenization / Parsing Crates for nobotrs

Research date: 2026-07-26. Scope: the Rust crate ecosystem needed to replicate (or best-effort approximate) the linguistic-analysis layer of `nobots`' `scripts/deep_stylometry.py`, which is out of scope for other research tracks (ML classifiers/perplexity, stylometric statistics libraries, pattern matching, architecture, CLI/packaging, Open Plugins, prior art — covered elsewhere).

## What `deep_stylometry.py` actually does

Read in full at `/home/kwhatcher/projects/nobots/scripts/deep_stylometry.py`. It builds a spaCy `en_core_web_sm` pipeline and layers on two add-on packages:

- **spaCy core**: tokenization, sentence segmentation, POS tagging, and dependency parsing (`en_core_web_sm` is a small pretrained pipeline that includes a tagger and a transition-based dependency parser).
- **`textdescriptives`** (spaCy pipeline components): `descriptive_stats` (sentence-length mean/std, token counts — used for **burstiness_ratio**), `readability`, `dependency_distance` (mean dependency-arc length/complexity — requires the parse tree), `pos_proportions` (per-tag proportion of the document — used to derive **content_to_function_word_ratio**), `coherence` (semantic similarity between consecutive sentences, requires word vectors), and `information_theory` (per-document entropy over the token stream — the script divides this by token count itself to get **entropy_per_token**, since textdescriptives' own perplexity fields are explicitly discarded as broken).
- **`pybiber`**: computes all 67 Biber (1988) register/multidimensional-analysis features from a spaCy-parsed corpus — the script keeps a curated subset of 14 (nominalizations, participle/whiz-deletion counts, pronoun rates, hedges/amplifiers/conjuncts, type-token ratio, mean word length, contraction rate). These features are POS-tag and syntactic-pattern counts normalized per 1000 tokens; several (whiz-deletion, sentence-relatives) require dependency-parse or at least chunk-level syntactic structure, not just flat POS tags.

So the hard linguistic dependencies are, in order of difficulty to replace: **(1) tokenization/sentence segmentation — easy**, **(2) POS tagging — moderate, real gap in production-grade pure Rust**, **(3) dependency parsing — hard, essentially no pure-Rust option**, **(4) semantic/coherence via word vectors — separate concern, likely covered by the ML-inference research track (embeddings)**.

---

## 1. Tokenization / segmentation

### `unicode-segmentation`
- crates.io: https://crates.io/crates/unicode-segmentation · docs.rs: https://docs.rs/unicode-segmentation/
- License: MIT OR Apache-2.0. Latest: 1.13.3. `no_std`-compatible, 448M+ all-time downloads — a foundational, extremely stable crate.
- Capability: implements UAX #29 grapheme-cluster, word, and sentence boundary splitting per the Unicode standard. This is **rule-based segmentation, not linguistic tokenization** — it splits on Unicode-defined boundaries (whitespace, punctuation class changes, locale-agnostic rules), with no notion of POS, lemma, or syntax.
- Verdict: **directly useful** as the sentence/word segmenter feeding every downstream statistical feature (sentence-length mean/std for burstiness, token counts for entropy-per-token, word counts for mean-word-length/type-token-ratio). This is a reasonable Rust-native substitute for spaCy's tokenizer + sentencizer for the *statistical* (non-syntactic) features.

### `icu_segmenter` (ICU4X, unicode-org)
- lib.rs: https://lib.rs/crates/icu_segmenter
- License: Unicode-3.0. Latest: 2.2.0, published 2026-04-01, ~1.8M downloads/month.
- Capability: line, grapheme, word, and sentence segmentation per UAX #14/#29, as part of the broader ICU4X internationalization project. More actively developed and higher-throughput than `unicode-segmentation` in some benchmarks, with better locale-awareness for line/sentence breaking, but functionally overlapping for the word/sentence-boundary use case nobotrs needs.
- License note: Unicode-3.0 is OSI-approved and permissive, but is a less common license than MIT/Apache-2.0 — worth a quick compatibility check if the project wants a strict allowlist, though it should not be a blocker (comparable in spirit to a BSD-style license).
- Verdict: **complementary/alternative to `unicode-segmentation`**, not something additional to it. Pick one; `unicode-segmentation` is the more established, narrowly-scoped choice for this use case, `icu_segmenter` is the better choice if the project anticipates needing broader Unicode/locale infrastructure (line breaking, normalization, collation) later.

### `tokenizers` (Hugging Face)
- crates.io: https://crates.io/crates/tokenizers · GitHub: https://github.com/huggingface/tokenizers
- License: Apache-2.0. Latest: 0.23.1, published 2026-04-27 — actively maintained (this is the Rust core that backs the Python `tokenizers` package used throughout the HF ecosystem).
- Capability: **subword tokenization** (BPE, WordPiece, Unigram, SentencePiece-compatible) — i.e., it produces the model-vocabulary token IDs a transformer expects as input, not linguistic word/sentence boundaries. It includes a normalizer stage (NFD/NFKC) and configurable pre-tokenizers, but its purpose is feeding a neural model, not stylometric measurement.
- Verdict: **not a substitute for `unicode-segmentation`** — different job entirely. `tokenizers` is only relevant to nobotrs if/when a transformer-based classifier or perplexity model is loaded (that's the ML-inference research track's territory, via `candle`/`ort`/`tch-rs`), since those models expect subword token IDs, not whitespace-split words. The two crates are **complementary, not overlapping**: `unicode-segmentation` for human-readable stylometric units (sentences, words), `tokenizers` only if a neural model needs subword IDs as input.

---

## 2. POS tagging & dependency parsing — the hard gap

### Dependency parsing: no viable pure-Rust option

Searched specifically for "rust dependency parser," "rust POS tagger crate," GitHub topic `dependency-parsing`, and lib.rs's parsing/text-processing category listings. **Found no maintained, general-purpose, pure-Rust dependency parser for natural language** (as opposed to parser-generator/grammar tooling for programming languages, which dominates the `parser-generator` keyword and is unrelated). This matches the honest expectation set in the task: dependency parsing is a genuinely hard NLP problem (transition-based or graph-based parsing over a trained treebank model), and the Rust NLP ecosystem has not produced an equivalent to spaCy's parser, Stanza, or UDPipe.

**Consequence for `textdescriptives/dependency_distance` and the whiz-deletion / sentence-relative Biber features**: these require actual syntactic structure (which token depends on which, and via what relation), not just a POS tag stream. There is no pure-Rust path to this today.

### POS tagging: partial, lower-confidence options exist

- **`postagger.rs`** (aka `postagger` on crates.io) — GitHub: https://github.com/shubham0204/postagger.rs
  - License: Apache-2.0. Published on crates.io, 18 commits, low activity (8 stars). Last-commit date not surfaced by lib.rs/GitHub fetch.
  - Capability: an NLTK-inspired reimplementation of the **averaged perceptron tagger** (the same algorithm NLTK's default English POS tagger uses), trained offline in Python/NLTK and run for inference in Rust. This is a real, working algorithm — not a toy — but it's a single-contributor project with minimal track record and no stated accuracy benchmark against the model card.
  - Verdict: the closest thing to a usable pure-Rust POS tagger, but low-confidence/low-maintenance; would need independent accuracy validation before being trusted for any calibrated threshold.

- **`viterbi_pos_tagger`** — crates.io: https://crates.io/crates/viterbi_pos_tagger
  - **License: GPL-3.0-or-later.** Flagged per the project's MIT-compatibility requirement — this is copyleft and **must be excluded** from nobotrs regardless of technical merit.
  - Latest: 0.1.0, published 2025-01-10. Implements Viterbi-algorithm HMM tagging with no external dependencies, but example output uses a Brown-Corpus-style abbreviated tagset (AT/JJ/NN), not confirmed to match the Penn Treebank tagset the Biber features are defined against.
  - Verdict: **excluded on license grounds.**

- **`nlp_annotations`** — docs.rs: https://docs.rs/nlp-annotations/0.1.2/nlp_annotations/pos/
  - Provides POS **tagset definitions** (Penn Treebank tags, Universal POS tags) as Rust types/enums, not a tagger itself — i.e., a schema crate, useful only as plumbing once you have tags from somewhere else.

- **`rust-bert`'s POS pipeline** — see section 4 below; a MobileBERT-based neural tagger exists but pulls in the full tch-rs/libtorch dependency chain for a single feature.

### `nlprule` — investigated specifically, verdict: unmaintained, do not adopt

- GitHub: https://github.com/bminixhofer/nlprule · lib.rs: https://lib.rs/crates/nlprule
- License: MIT OR Apache-2.0 for the code; the shipped rule binaries are derived from LanguageTool v5.2 and licensed **LGPLv2.1** — a copyleft license on the data artifact even though the code itself is permissive. This alone is a licensing complication for an MIT project (LGPL is more permissive than GPL for dynamic linking/data use, but still needs explicit legal sign-off, not a default "fine").
- **Maintenance: last release 0.6.4 on 2021-04-24 — over five years stale as of 2026-07-26.** Still pre-1.0, ~3.5k downloads/month (legacy usage, e.g. `ltapiserv-rs`), but no evidence of active development, security patching, or compatibility updates for current Rust toolchains.
- Capability (for the record, since it's a real and reasonably sophisticated system when it worked): rule-based grammar/text-correction engine parsing LanguageTool's XML rule files, with POS tagging, lemmatization, sentence segmentation, and noun/verb-phrase chunking for English, German, and Spanish (~3,725 English rules). Chunking is shallower than full dependency parsing but could partially substitute for whiz-deletion-style pattern detection if it worked reliably.
- Verdict: **do not adopt.** Interesting prior art, technically closest single package to "spaCy-lite," but unmaintained for 5+ years plus an LGPL data-licensing wrinkle makes it a liability, not a shortcut. If dependency-parse-equivalent features are ever pursued in pure Rust, treat `nlprule`'s source as a design reference at most, not a dependency.

### Rust binding to spaCy itself, or a pure-Rust dependency parser: does not exist
No FFI crate or PyO3 binding specifically wrapping spaCy was found (PyO3/`pyo3_bindgen`/maturin are general Python-interop tooling, not spaCy-specific — see section 5). No pure-Rust dependency-parser crate (trained or rule-based) was found on crates.io or in GitHub's `dependency-parsing` topic search that targets natural-language (as opposed to programming-language) parsing.

---

## 3. `rust-bert` — capability audit

- GitHub: https://github.com/guillaume-be/rust-bert · lib.rs: https://lib.rs/crates/rust-bert
- License: Apache-2.0. Latest: 0.23.0, released 2024-09-29 — **~22 months stale as of 2026-07-26**, with an earlier multi-month gap between 0.21.0 (2023-06) and 0.22.0 (2024-01) visible in the changelog, suggesting bursty rather than steady maintenance. Still shows ongoing adoption (31 dependent crates, ~5.4k downloads/month, 45 contributors), so not abandoned, just slow-moving.
- Pipelines out of the box (12 total): question answering, translation, summarization, dialogue, NLG, zero-shot classification, **sentiment analysis, named entity recognition, POS tagging**, keyword/keyphrase extraction, sentence embeddings, masked LM.
- The **POS tagging pipeline** (`rust_bert::pipelines::pos_tagging`) uses a lightweight pretrained **MobileBERT** token-classification model for English. No published accuracy benchmark was found for this specific model/tagset combination in the docs.
- **Dependency**: yes, requires **`tch-rs`** (LibTorch C++ bindings) by default — meaning a working libtorch v2.4 install/link step — with an alternative ONNX-runtime backend path also available per the docs. This is the same heavyweight native-dependency profile the ML-inference research track will already be weighing for classifier/perplexity work; POS tagging alone does not justify pulling in this dependency chain if it isn't already needed for other reasons.
- No dependency parsing, coherence/semantic-similarity, or Biber-style register-feature pipeline of any kind — `rust-bert` closes part of the POS-tagging gap only, and only at the cost of a libtorch dependency.
- Verdict: **viable but conditional.** Only worth adopting for POS tagging if the ML-inference track is already bringing in `tch-rs`/libtorch for a classifier or perplexity model; not worth the dependency weight for POS alone when `unicode-segmentation`-based statistical features don't need it and dependency parsing (the harder half of the problem) remains unaddressed regardless.

---

## 4. Language detection

- **`whichlang`** — crates.io: https://crates.io/crates/whichlang · Quickwit writeup: https://quickwit.io/blog/whichlang-language-detection-library
  - License: MIT. Latest: 0.1.1, published 2025-01-21 (~18 months stale but a small, stable, single-purpose crate — staleness here reads as "done," not "abandoned"). Built for Quickwit; multiclass logistic regression over a 4096-dim hashed feature space, >100MB/s throughput, ~99.5% accuracy on its validation set, 16 languages.
- **`whatlang`** — crates.io: https://crates.io/crates/whatlang
  - License: MIT. Latest: 0.18.0, published 2025-10-16 — actively maintained. Slower (~10MB/s per Quickwit's comparison) but broader language coverage than `whichlang`.
- Either is a fine, low-risk choice to gate non-English input before running English-tuned stylometric features (POS proportions, Biber features, and English word-frequency lookups are all meaningless or misleading on non-English text). **Design note, one sentence as requested**: prior detection-tooling research has found AI-detector false-positive rates spike sharply on non-native/ESL English writing, so a language gate should be paired with caution about over-trusting stylometric verdicts on any English text that itself shows signs of non-native authorship, not just non-English text outright.

---

## 5. Fallback strategies for dependency parsing / full spaCy-equivalence

Three options were evaluated, since pure-Rust dependency parsing is a confirmed gap:

**(a) Shell out to a local Python process running spaCy.** This is exactly what `nobots` itself does today (`deep_stylometry.py` is a `uv run --script` Python file). It's a well-understood, "boring" pattern — not something with a dedicated crate, just subprocess invocation (`std::process::Command`) plus JSON over stdout, which is literally the interface `deep_stylometry.py` already exposes. No Rust crate research is needed for this path; it's an architecture decision (keep the heavy linguistic analysis as an optional Python sidecar/subprocess that nobotrs's Rust core calls when available, degrading gracefully when it isn't) rather than a library dependency. This preserves 100% of the Python capability at the cost of requiring Python + spaCy + textdescriptives + pybiber installed alongside the Rust binary — arguably defeating the point of a from-scratch Rust port for users who want a single static binary. (There is a lighter-weight in-process variant of this same idea, in-process FFI via `pyo3`/`pyo3_bindgen` (https://github.com/PyO3/pyo3, https://github.com/AndrejOrsula/pyo3_bindgen) rather than a subprocess — the `rsnltk` crate, https://crates.io/crates/rsnltk (MIT, last published 2022-02-02), is a real if minor example of exactly this pattern already: it wraps Python's Stanza toolkit via Python bindings rather than reimplementing NLP in Rust. Same fundamental tradeoff as shelling out — still requires a Python runtime and the wrapped package installed — just a tighter coupling and no subprocess/JSON boundary.)

**(b) ONNX-exported spaCy pipeline run via `ort`.** `ort` (https://github.com/pykeio/ort, Apache-2.0/MIT, v2.0.0-rc.12, actively developed, successor to the inactive `onnxruntime-rs`) is a solid, general-purpose ONNX Runtime binding with no spaCy-specific tooling or precedent found in this research. spaCy's transition-based dependency parser is not a simple feed-forward graph — it's a **stateful, iterative decision process** (repeatedly predicting the next parser action and applying it to a state, closer to a small RL/search loop than a single forward pass), which does not export cleanly to a static ONNX graph the way a transformer classifier does. spaCy itself does not offer or document an official ONNX export path for its parser component (only its transformer-based *tok2vec* embeddings are sometimes exported this way in community projects). No evidence was found of anyone doing this for spaCy's dependency parser specifically; treat this as **speculative and unproven**, not a documented pattern, despite being technically the "purest Rust" option on paper.

**(c) Drop dependency-parse-complexity and whiz-deletion/sentence-relative Biber features; keep everything that doesn't require a parse tree.** Of the features in `deep_stylometry.py`, this is what remains Rust-native-feasible without parsing:
- **Entropy-per-token**: needs only tokenization (`unicode-segmentation`) + a **unigram word-frequency table** — the `wordfreq` crate (MIT/Apache-2.0, https://crates.io/crates/wordfreq) implements the frequency-lookup *algorithm* but explicitly ships no data (last release 2023-06-24, stale but algorithmically simple enough that staleness barely matters); a companion `wordfreq-model` crate or a hand-rolled frequency table (e.g. derived from a public English corpus) would need to supply the actual data. This is a solvable, low-risk gap, closer to a data-sourcing problem than a hard NLP problem.
- **Burstiness ratio, type-token ratio, mean word length, contraction rate**: pure sentence/word-boundary statistics — fully covered by `unicode-segmentation`, no tagging or parsing needed.
- **POS proportions / content-to-function-word ratio**: needs a POS tagger, but not a parser — this is the `postagger.rs` / `rust-bert` MobileBERT tier of the gap (moderate confidence, not a hard blocker like dependency parsing).
- **Dependency distance, whiz-deletion (f_27/f_28), sentence-relatives (f_34), and `textdescriptives/coherence`** (which needs word-vector similarity, a separate concern from parsing but still outside this track's scope): **genuinely not available in pure Rust today.** These should be explicitly scoped out of a v1 pure-Rust build, or deferred to option (a) as an optional enhanced-analysis mode.

---

## Recommendation

1. **Build with pure Rust now**: `unicode-segmentation` for all sentence/word-boundary work; a small hand-maintained or `wordfreq`-model-backed unigram frequency table for entropy-per-token; the lexical/statistical Biber features that don't require POS or parsing (type-token ratio, mean word length, contraction rate, burstiness). These map to features already flagged as low-value-per-feature in the guide anyway (weak corroborating signals, not calibrated cutoffs), so a partial feature set is defensible.
2. **Approximate cautiously**: POS-tag-dependent features (POS proportions, content/function-word ratio, pronoun/hedge/amplifier/conjunct counts, nominalization counts) via `postagger.rs`'s perceptron tagger as a first attempt, with explicit accuracy validation against a labeled sample before trusting its output in the tool's verdicts — it's real but unproven. If the ML-inference track ends up pulling in `tch-rs`/libtorch anyway for a classifier or perplexity model, `rust-bert`'s MobileBERT POS pipeline becomes a stronger, better-tested alternative "for free."
3. **Explicitly scope out of v1**: dependency-parse-complexity, whiz-deletion/sentence-relative Biber features, and textdescriptives-style coherence. No pure-Rust path exists; `nlprule` is a dead end (unmaintained 5+ years, LGPL data licensing); ONNX-export of spaCy's parser is unproven speculation, not a documented pattern. If full parity is ever required, the only proven path is shelling out to the existing Python `deep_stylometry.py` as an optional sidecar — an architecture decision, not a crate choice — and that tradeoff (loses single-binary distribution, gains full feature parity) should be made explicitly by whoever owns the architecture doc, not defaulted into.
4. **Language gating**: add `whichlang` (MIT, small, fast, good-enough accuracy) ahead of any English-tuned stylometric feature, and note in the design that even English text can trigger elevated false-positive risk when written by non-native speakers — a detection-calibration concern, not just a language-filter one.

## Sources
- https://github.com/bminixhofer/nlprule
- https://lib.rs/crates/nlprule
- https://docs.rs/nlprule/latest/nlprule/
- https://crates.io/crates/unicode-segmentation
- https://unicode-rs.github.io/unicode-segmentation/
- https://lib.rs/crates/icu_segmenter
- https://crates.io/crates/tokenizers
- https://lib.rs/crates/tokenizers
- https://github.com/huggingface/tokenizers (via search)
- https://github.com/shubham0204/postagger.rs
- https://crates.io/crates/viterbi_pos_tagger
- https://lib.rs/crates/viterbi_pos_tagger
- https://docs.rs/nlp-annotations/0.1.2/nlp_annotations/pos/
- https://github.com/guillaume-be/rust-bert
- https://lib.rs/crates/rust-bert
- https://docs.rs/rust-bert/latest/rust_bert/pipelines/pos_tagging/
- https://crates.io/crates/whichlang
- https://lib.rs/crates/whichlang
- https://quickwit.io/blog/whichlang-language-detection-library
- https://crates.io/crates/whatlang
- https://lib.rs/crates/whatlang
- https://crates.io/crates/rsnltk
- https://github.com/dhchenx/rsnltk
- https://github.com/pykeio/ort
- https://ort.pyke.io/
- https://crates.io/crates/wordfreq
- https://lib.rs/crates/wordfreq
- https://lib.rs/crates/layered-nlp
- /home/kwhatcher/projects/nobots/scripts/deep_stylometry.py (primary reference read in full)
- /home/kwhatcher/projects/nobots/ai-writing-guide.md (context on what features matter and why)
