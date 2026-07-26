# Prior Art: Existing Rust AI-Detection Tools Research

**Date:** July 26, 2026  
**Scope:** Comprehensive search for existing Rust crates, CLI tools, and GitHub projects that detect AI-generated text or perform stylometric/AI-writing analysis.

## Executive Summary

The Rust AI-text-detection tooling ecosystem is **thin but actively growing**. A small number of dedicated tools and crates exist, most released or actively developed in 2024–2026. The Python ecosystem is far more mature, with several well-established approaches (Fast-DetectGPT, detect-gpt, GPTZero) that have no direct Rust ports. However, Rust does have:

1. **is-it-slop** — A mature, production-ready ML-based text detector (TF-IDF + ensemble)
2. **aislop** — Code-pattern-based AI slop detection (50+ deterministic rules across 8 languages)
3. **stylometry** — Stylometric analysis foundation (Mendenhall, Kilgariff, hapax legomena)
4. **rust-bert** — Zero-shot transformer-based classification (can be leveraged for custom detection)

**Conclusion:** Building nobotrs from scratch is **justified and valuable**. While is-it-slop covers text classification, it does not do prose linting for AI writing tells; aislop focuses on code, not natural language; no Rust crate implements perplexity-based or burstiness-based detection. nobotrs can occupy the middle ground: text-focused, stylometric + pattern-driven, and designed from the start for pluggable backends.

---

## Finding 1: is-it-slop (Rust Crate)

**Category:** ML-based AI-generated text detection  
**Type:** Rust library + CLI tool  
**Repository:** https://github.com/sermuns/is-it-slop  
**Crate:** https://crates.io/crates/is-it-slop/  
**License:** WTFPL (permissive)  
**Latest Release:** v0.3.1+ (active 2024–2026)  
**GitHub Stats:** 81 stars, 6 forks, 67 commits  
**Status:** Maintenance-level; feature-complete for its scope  

### What it does

- Detects AI-generated slop text using **TF-IDF and ensemble classifiers**
- Claims ~96% accuracy
- Portable ONNX model (~16 MB) embedded in the CLI binary—no Python runtime required
- Multi-dataset training to avoid overfitting to any single text source
- Available as Rust library, CLI tool, and Python bindings
- Outputs either a probability score or binary human/AI classification

### Relevance to nobotrs

- **Strengths:** Production-ready ML detection; ONNX portability; well-maintained; covers the binary classification problem
- **Limitations:** Does not perform prose linting or stylometric analysis; no perplexity/burstiness metrics; no pattern-based detection for AI writing tells; not designed for explainability or rule-driven output

### Assessment

**Not a blocker for nobotrs.** is-it-slop is narrow and complementary. nobotrs can potentially depend on is-it-slop as an optional backend for ML classification, but the project's primary goal (linting prose for AI tells, stylometric features, explainable pattern matching) is orthogonal.

---

## Finding 2: aislop (Rust + Multi-Language Code Detector)

**Category:** Deterministic pattern-based AI code slop detection  
**Type:** Standalone CLI tool + agent integration  
**Repository:** https://github.com/scanaislop/aislop  
**Install:** `npm install -g aislop`, `pipx install aislop`, or from Rust source  
**License:** MIT  
**Latest Release:** Active 2024–2026, 322 commits  
**GitHub Stats:** 511 stars, 23 forks  
**Status:** Actively maintained; widely adopted  

### What it does

- Detects **AI-specific code patterns** that pass traditional linters but are structurally/semantically broken
- 50+ deterministic rules across 8 languages: TypeScript, JavaScript, Python, Go, **Rust**, Ruby, PHP, React Native
- Examples: empty function bodies, swallowed exceptions, as-any casts, dead code, oversized functions, narrative comments, inflated documentation
- Produces 0–100 quality score
- Auto-fix capabilities for some issues
- Sub-second, deterministic scanning—no runtime LLM calls
- Integrates with CI/CD, pre-commit hooks, GitHub Actions, and AI coding agents (Claude Code, Cursor, Codex)
- SARIF output for GitHub code scanning

### Relevance to nobotrs

- **Strengths:** Complementary to text detection; proven at scale; pattern-based (not ML); works offline; could inspire rule architecture
- **Limitations:** Focuses on *code* structure, not *natural language prose*; different problem domain; does not analyze human vs. AI writing patterns in text

### Assessment

**Complementary, not overlapping.** aislop and nobotrs operate on different inputs (code vs. prose). However, aislop's rule-based architecture and 50+ curated checks could inspire nobotrs's own pattern/rule system. Not a blocker; no dependency conflict.

---

## Finding 3: stylometry (Rust Crate)

**Category:** Stylometric and linguistic analysis  
**Type:** Rust library  
**Repository:** https://github.com/ian-nai/rust_stylometry  
**Crate:** https://crates.io/crates/stylometry/  
**License:** Appears to be permissive (specific license not stated in search results; verify on GitHub)  
**Latest Release:** v0.2.8 (appears maintained)  
**Status:** Established; suitable for integration  

### What it does

- Implements classic stylometry algorithms:
  - **Mendenhall's word-length analysis** — graphs distribution of word lengths (forensic authorship analysis)
  - **Kilgariff chi-squared test** — compares linguistic patterns between texts (known authorship vs. disputed)
  - **Hapax legomena** — identifies words that occur in only one text (not the other)
- Outputs analysis results as PNG graphs or statistical scores
- Suitable for feature extraction in authorship analysis pipelines

### Relevance to nobotrs

- **Strengths:** Pre-built statistical foundations; proven algorithms; directly applicable to stylometric feature extraction
- **Limitations:** No AI-specific detection logic; designed for authorship disputes, not AI vs. human classification; limited to specific metrics

### Assessment

**Directly useful as a dependency.** stylometry can provide feature extraction for nobotrs's statistical analysis pipeline. It addresses part of the "linting" goal (stylometric features). nobotrs could wrap or extend this crate's output.

---

## Finding 4: rust-bert (Rust Crate)

**Category:** Transformer-based NLP and zero-shot classification  
**Type:** Rust library binding to ONNX/tch-rs  
**Repository:** https://github.com/guillaume-be/rust-bert  
**Crate:** https://crates.io/crates/rust-bert/  
**License:** Permissive (MIT or Apache)  
**Latest Release:** v0.10.0+ (actively maintained)  
**Status:** Production-ready; widely used  

### What it does

- Ports Hugging Face Transformers library to Rust
- Pre-built pipelines for:
  - Zero-shot classification (classifies text into labels using NLI models, no fine-tuning needed)
  - Sequence classification, token classification (NER, POS), question-answering, text generation, summarization, translation
- Multi-threaded tokenization and GPU inference support
- Loads pretrained models from Hugging Face hub
- ONNX or tch-rs backends

### Relevance to nobotrs

- **Strengths:** Zero-shot classification could support custom detection rules (e.g., "is this text 'templated' or 'formulaic'?"); transformer embeddings can feed into classifiers; mature, production-ready
- **Limitations:** Requires model download and inference overhead; not specialized for AI-text detection; mostly for classification, not stylometric feature extraction

### Assessment

**Useful as an optional backend.** rust-bert could power a zero-shot or supervised classifier backend for nobotrs. Not essential; is-it-slop (via ONNX) is simpler for this. But rust-bert provides more flexibility and could enable fine-tuned custom detection.

---

## Finding 5: Other Crates (Peripheral Relevance)

### lint-ai (crates.io)
- Analyzes text corpora for consistency issues
- Limited information; appears to be more of a linting tool than AI detection
- **Relevance:** Low; different purpose

### slop-guard, antislop (crates.io)
- Similar "slop" detection themes
- Minimal information available in search results
- **Relevance:** Low; not detailed enough to assess

### tirith (Rust Crate)
- **Repository:** https://github.com/sheeki03/tirith
- Terminal security analyzer for shell injection, ANSI injection, homograph attacks
- Designed to protect AI coding agents (Claude Code, Copilot, Cursor) at runtime
- **Relevance:** Low for text detection; orthogonal security concern

---

## Finding 6: Python Tools (Benchmarks, Not Rust Ports)

**Category:** Reference implementations in Python  
**Status:** Not ported to Rust; included for context

### detect-gpt (Original)
- **Repository:** https://github.com/eric-mitchell/detect-gpt
- Zero-shot detector using conditional probability
- Academic paper; widely cited baseline
- **Status:** Python; no Rust port found

### Fast-DetectGPT (ICLR 2024)
- **Repository:** https://github.com/baoguangsheng/fast-detect-gpt
- Efficient zero-shot detection via conditional probability curvature
- **Status:** Python; optimized version of detect-gpt; no Rust port

### GPTZero
- Online service + open-source re-implementations (Python)
- Uses perplexity and burstiness metrics
- **Status:** Primarily closed-source SaaS; Python community implementations exist; no official Rust port

### AI Slop Detector Tools (Python)
- **distil-ai-slop-detector:** Local browser-based image/text detection
- **sloppylint:** Python-specific code analysis
- **Various web tools:** SlopDetector.org, Sapling, Slop or Not
- **Status:** None have Rust equivalents; all Python or web-based

### Relevance to nobotrs
- These represent established methodologies (perplexity, burstiness, ensemble classification)
- No direct Rust reimplementation found
- nobotrs can take inspiration from research but must build from scratch for Rust

---

## Finding 7: GitHub Projects Tagged "ai-detection"

**Category:** Miscellaneous Rust projects on GitHub  
**Search:** https://github.com/topics/ai-detection (Rust repos only)

Found only **4 Rust repositories** (vs. 183 Python):
1. **agent-sh/agent-analyzer** — AST analysis, 7 stars
2. **aegntic/aegnt-27** — Behavioral authenticity patterns, 4 stars
3. **zmaril/Straitjacket** — Minimal, 2 stars, recent activity
4. **drakkB/sky-proof** — Physics-based video authenticity, 0 stars

**Assessment:** Early-stage projects; none are mature production tools. AI-detection as a Rust-first concern is still emerging.

---

## Search Methods & Queries Executed

1. `ai text detector rust crate`
2. `rust crate ai generated text detection`
3. `"rust" "AI detector" OR "AI detection" site:github.com`
4. `stylometry rust crate linguistic analysis`
5. `binoculars detector rust` (returned game Rust results, not relevant)
6. `fast-detectgpt detector rust implementation`
7. `gptzero rust cli`
8. `"chatgpt detector" rust`
9. `"llm text detector" cli rust`
10. `"AI slop detector"`
11. `site:github.com rust "AI" "text" "detection" OR "detector"`
12. `site:crates.io ai detection text`
13. `"detect-gpt" OR "detectgpt" github rust`
14. `Rust crate "zero-shot" detection language model`
15. `tirith rust crate github`
16. `"ai-text-detector" rust github crate repository`
17. `rust-bert zero-shot classification transformer`
18. `"is-it-slop" rust crate github`
19. `is-it-slop crate.io rust ai detection`
20. `github.com "is-it-slop" language:rust`
21. `aislop github AI slop code detector`
22. `detectgpt rust implementation github`
23. `perplexity burstiness detector rust`

---

## Conclusion

### The State of Rust AI-Detection Tooling

The Rust ecosystem for AI-text detection is **nascent but not empty**:

- **No comprehensive equivalent** to Fast-DetectGPT or detect-gpt exists in Rust
- **is-it-slop** is the closest to production-ready, but it is a **narrow tool** (binary ML classifier only)
- **aislop** is mature and widely adopted, but focuses on **code patterns, not prose**
- **stylometry** provides **statistical foundations** but no AI-specific logic
- **rust-bert** enables **transformer-based inference** but requires model management
- **Python dominates** AI-text detection (183 GitHub repositories vs. 4 Rust)

### Rationale for Building nobotrs

1. **No prose-linting tool exists in Rust.** aislop does code; is-it-slop does binary classification. nobotrs fills the gap: explainable stylometric analysis + pattern matching for natural language prose.

2. **Perplexity and burstiness detection are absent from Rust.** These key metrics (used by GPTZero and others) have no Rust implementation. nobotrs can introduce these.

3. **Stylometric rules need curation for AI detection.** stylometry provides the math; nobotrs would provide the AI-specific heuristics and reporting.

4. **Pluggable architecture is underexplored in Rust.** nobotrs's design to support multiple backends (rule-based, ML, API-based) is novel and valuable.

5. **Timing is right.** The 2024–2026 wave of AI coding tools has motivated some Rust tooling, but the text-analysis / linting space is open.

### Recommendations

- **Do not depend on is-it-slop** (licensing/scope conflict unclear); can optionally integrate later
- **Consider depending on stylometry** for feature extraction
- **rust-bert is optional**; primary detection will be rule/pattern-based
- **Implement zero-shot perplexity** and **burstiness** metrics from first principles or via candle/llm backend
- **Design Open Plugins architecture** to enable community contribution of detection rules and backends

---

## Sources

- [ai-text-detector - crates.io Keywords](https://crates.io/keywords/ai-text-detector?sort=alpha)
- [AI Content Detection for Rust | Sapling](https://sapling.ai/programming-language/ai-content-detector/rust)
- [GitHub - pemistahl/lingua-rs](https://github.com/pemistahl/lingua-rs)
- [Text processing — Lib.rs](https://lib.rs/text-processing)
- [GitHub - VelathGroup/rust-detection-ai](https://github.com/VelathGroup/rust-detection-ai)
- [GitHub - worka-ai/pii](https://github.com/worka-ai/pii)
- [GitHub - rustyneuron01/AI-Generated-Content-Detection](https://github.com/rustyneuron01/AI-Generated-Content-Detection)
- [ai-detection · GitHub Topics](https://github.com/topics/ai-detection)
- [stylometry - crates.io](https://crates.io/crates/stylometry)
- [stylometry - Rust](https://docs.rs/stylometry)
- [GitHub - ian-nai/rust_stylometry](https://github.com/ian-nai/rust_stylometry)
- [Text analysis - crates.io](https://crates.io/crates/text_analysis)
- [Fast-DetectGPT: Efficient Zero-Shot Detection](https://arxiv.org/html/2310.05130v3)
- [GitHub - baoguangsheng/fast-detect-gpt](https://github.com/baoguangsheng/fast-detect-gpt)
- [GitHub - armaan-rashid/detect-chatgpt](https://github.com/armaan-rashid/detect-chatgpt)
- [GitHub - BurhanUlTayyab/GPTZero](https://github.com/burhanultayyab/gptzero)
- [GPTZero - Wikipedia](https://en.wikipedia.org/wiki/GPTZero)
- [GitHub - graniet/llm](https://github.com/graniet/llm)
- [GitHub - rustformers/llm](https://github.com/rustformers/llm)
- [AI Slop Detector — SlopDetector.org](https://slopdetector.org/)
- [GitHub - sanjeevafk/ai-slop-detector](https://github.com/sanjeevafk/ai-slop-detector)
- [GitHub - flamehaven01/AI-SLOP-Detector](https://github.com/flamehaven01/ai-slop-detector)
- [tirith - crates.io](https://crates.io/crates/tirith/0.2.8)
- [GitHub - sheeki03/tirith](https://github.com/sheeki03/tirith)
- [lint-ai - crates.io](https://crates.io/crates/lint-ai)
- [sentinel-agent-ai-gateway - crates.io](https://crates.io/crates/sentinel-agent-ai-gateway)
- [tirith - crates.io](https://crates.io/crates/tirith)
- [GitHub - sermuns/is-it-slop](https://github.com/sermuns/is-it-slop)
- [is-it-slop - crates.io](https://crates.io/crates/is-it-slop/0.3.1)
- [GitHub - scanaislop/aislop](https://github.com/scanaislop/aislop)
- [ai-slop-detector · PyPI](https://pypi.org/project/ai-slop-detector/)
- [Burstiness & Perplexity | Quillbot](https://quillbot.com/blog/ai-writing-tools/burstiness-and-perplexity/)
- [Perplexity vs Burstiness | Leap AI](https://www.tryleap.ai/learn/perplexity-vs-burstiness)
- [What is perplexity & burstiness for AI detection? - GPTZero](https://gptzero.me/news/perplexity-and-burstiness-what-is-it/)
- [rust-bert - crates.io](https://crates.io/crates/rust-bert/0.10.0)
- [GitHub - guillaume-be/rust-bert](https://github.com/guillaume-be/rust-bert)
- [ZeroShotClassificationModel - rust_bert docs](https://docs.rs/rust-bert/latest/rust_bert/pipelines/zero_shot_classification/struct.ZeroShotClassificationModel.html)
- [GitHub - eric-mitchell/detect-gpt](https://github.com/eric-mitchell/detect-gpt)
- [GitHub - tybens/detect-gpt](https://github.com/tybens/detect-gpt)
