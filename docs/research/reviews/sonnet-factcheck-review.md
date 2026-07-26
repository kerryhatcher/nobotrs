# Fact-check review: spec vs. research corpus

**Reviewer:** Sonnet (fact-check pass)
**Target:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`
**Checked against:** all 9 files in `docs/research/` (`00-consolidated-summary.md` + `01`–`08`)
**Scope:** spec-vs-research fidelity only (does the spec accurately carry forward what the research found, with correct confidence levels and caveats). Architecture soundness, completeness gaps, internal consistency, and decision-alignment are covered by other reviewers.

## Verdict

**Mostly faithful, with two notable overstatements and one clearly dropped caveat.** The spec correctly threads the three "known candidate" corrections it was expected to handle (candle/debertav2 checkpoint-vs-module distinction — mostly; rust_readability GPL correction — fully, everywhere; is-it-slop star count — not applicable, never mentioned). It also does something better than simple transcription in one place: it uses the *corrected* postInstall-issue status (closed/not-planned) rather than propagating source report 07's own stale claim (open). But it overstates confidence in two places — one of them a direct self-contradiction with its own §7 — and silently drops a hardware-cost caveat the research flagged as a first-class open decision.

---

## Findings

### 1. Overstated confidence — §2.2 classifier row conflates "module confirmed to exist" with "confirmed to fit this checkpoint"

**Spec, §2.2, classifier row:**
> `candle` + `candle-transformers::debertav2` (confirmed to exist and match this use case); `ort` (ONNX Runtime) as documented fallback

**Research, `00-consolidated-summary.md`, correction #2:**
> "the *module's existence* is confirmed, but empirical compatibility with that specific checkpoint is not, and should be the first thing prototyped."

**Research, `01-ml-inference-crates.md`, closing note:**
> "the compatibility between candle's `debertav2` module and the desklib DeBERTa-v3-large checkpoint is an architectural inference from documented module capabilities... not a confirmed working example found in search — no source was located showing someone has actually loaded `desklib/ai-text-detector-v1.01` weights into `candle`."

**Discrepancy:** the parenthetical "(confirmed to exist **and match this use case**)" packages two claims of different confidence into one "confirmed" verb. Only module *existence* is confirmed; "match this use case" (i.e., checkpoint compatibility) is an unverified architectural inference, per both the research file and its own consolidated correction. A reader who only sees the §2.2 table (a quick-reference row, plausibly read in isolation) would come away thinking checkpoint fit is settled.

**Mitigating factor:** §9 item 1 gets this exactly right — "the `debertav2` module's existence is confirmed, but nobody has been found to have actually loaded that specific checkpoint into it" — which is a near-verbatim, correctly-hedged echo of the consolidated summary. So the caveat survives in the document overall; it's specifically the §2.2 table cell that blurs it.

**Severity:** Medium. The correct caveat is present elsewhere in the same document, but the table is the first thing a skimming reader hits, and its wording actively erases the distinction the research went out of its way to preserve.

---

### 2. Overstated confidence / self-contradiction — §10 calls the dependency table "license-verified" while §7 (and the table itself) flags one crate's license as unconfirmed

**Spec, §10 (full text):**
> "See `docs/research/00-consolidated-summary.md` § "Recommended stack" for the full, **license-verified table**. All selected crates are MIT/Apache-2.0/Unlicense family with one correction already applied: `rust_readability` (GPL-3.0-or-later) is excluded; Flesch-Kincaid is hand-rolled instead."

**Spec, §7, scope-out item 3 (same document, earlier section):**
> "`stylometry` (ian-nai/rust_stylometry) license — flagged as a direct dependency candidate for classic authorship-analysis statistics, but its license was not independently confirmed in research. Must be verified before it is actually added as a dependency."

**Research, `00-consolidated-summary.md`, "Recommended stack" table (the exact table §10 cites and calls "license-verified"):**
> `| Stylometric feature foundation | stylometry (ian-nai/rust_stylometry) | unconfirmed — verify before use | Medium |`

**Research, `00-consolidated-summary.md`, open design decision #8:**
> "Not verified in this pass either (out of the prioritized checklist) — verify before depending on it, since it's recommended as a direct dependency for stylometric feature extraction."

**Discrepancy:** §10 describes the referenced table as "the full, license-verified table" and asserts "All selected crates are MIT/Apache-2.0/Unlicense family," but that very table carries `stylometry`'s license as explicitly **unconfirmed**, not verified-permissive. This directly contradicts §7 point 3 two sections earlier in the same spec, which correctly (and separately) flags the same crate's license as unverified. §10's blanket claim is not just an overstatement relative to the research — it's an internal inconsistency the spec introduces on top of it, since §7 already had the correct, hedged version of the same fact.

**Severity:** Medium-high. This is the clearest case in the spec of confidence being inflated beyond what the cited source actually supports, and it's self-contradicting, not just under-cautious.

---

### 3. Dropped caveat — perplexity tier's memory/hardware cost is never mentioned anywhere in the spec

**Spec, §2.2, perplexity row (only mention of this tier):**
> "Twin-model zero-shot perplexity ratio (Binoculars/Fast-DetectGPT style) | `candle` or `llama-cpp-2` (GGUF quantization)"

No other section of the spec (§7, §9, or elsewhere) mentions this tier's resource cost. A grep of the full spec for "RAM," "memory," "GB," "Falcon," "Binoculars," or "hardware" turns up nothing beyond this one table cell.

**Research, `01-ml-inference-crates.md`:**
> "Binoculars' own validated pair (Falcon-7B/Falcon-7B-Instruct) is memory-heavy even quantized... this workload should be treated as the 'optional, heavier' detection method regardless of crate choice"; and: "No source found describing a validated Binoculars/Fast-DetectGPT pair smaller than the ~2.7B range; going smaller (e.g. GPT-2-scale) would be an untested extrapolation, not a documented result."

**Research, `00-consolidated-summary.md`, open design decision #4:**
> "Binoculars' validated model pair (Falcon-7B/Falcon-7B-Instruct) is memory-heavy even GGUF-quantized (~8–10GB RAM for the pair); no smaller *validated* pair was found in the literature. Decide whether this ships as an explicitly 'heavy, opt-in' detection method gated behind its own feature flag, is deferred past v1 entirely, or is scoped only to users who opt into downloading multi-GB models."

**Discrepancy:** the consolidated summary lists this as one of nine explicit "open design decisions" the design doc needs to address — not a minor detail. The spec does implicitly resolve *part* of it (perplexity gets its own opt-in feature flag, satisfying the "heavy, opt-in" branch of the decision), but it never states *why* — the ~8-10GB RAM figure and the "no smaller validated pair exists" finding are simply absent. Someone reading only the spec would have no idea that enabling `perplexity` implies multi-gigabyte model downloads and meaningful RAM pressure, which is exactly the kind of caveat a design doc is supposed to carry forward even after making the associated decision.

**Severity:** Medium-high. This is a real, load-bearing research finding that shaped a design decision (the feature-flag gating) but the finding itself didn't survive into the spec text.

---

### 4. Unsourced claim — spec's research-basis line cites a grimoire directory none of the 9 reports actually used

**Spec, §1 header (line 5):**
> "**Research basis:** `docs/research/00-consolidated-summary.md` and its eight source reports, plus prior art at `/mnt/storage/grimoire/research/ai-text-detection-2026/` and `/mnt/storage/grimoire/research/open-plugins-spec/`."

**Check:** grepped all 9 research files for "grimoire" — the only hits are in `07-open-plugins-integration.md`, which does genuinely build on `/mnt/storage/grimoire/research/open-plugins-spec/` (cited and used throughout report 07, with a "freshness spot-check" section explicitly reconciling it against live fetches). **No research file mentions or cites `/mnt/storage/grimoire/research/ai-text-detection-2026/` anywhere** — including `08-prior-art-existing-tools.md`, which is the report that would naturally draw on prior AI-text-detection research and instead documents a fresh, from-scratch web search (its own "Search Methods & Queries Executed" section lists 23 web queries, no local-file citations at all).

The path itself does exist on disk (`/mnt/storage/grimoire/research/ai-text-detection-2026/`, containing files like `COMPREHENSIVE_SYNTHESIS.md`, `detection-tools-landscape.md`, etc.), so this isn't a fabricated path — but nothing in the 9-report research corpus shows it was actually consulted or fed into any finding. This looks like either (a) an assumption that report 08 used it the way report 07 used its grimoire directory, carried over by analogy without verification, or (b) a genuinely separate input the spec author had access to that simply isn't reflected in the research corpus this review was scoped to check.

**Severity:** Low-medium. Doesn't affect any technical claim in the body of the spec, but it's a provenance/grounding statement in the document's own header, and half of it isn't backed by the cited research.

---

### 5. Unsourced (but verified accurate) — the quorum-aggregation description in §2.4 comes from the nobots source, not the research corpus

**Spec, §2.4:**
> "...combines their `Score`s using the same **quorum rule** `check_ai_tells.py` already uses... This is a deliberate carry-forward from the Python implementation's own documented lesson (an earlier "any one family over threshold" rule produced false positives). Starting default: `QUORUM = 2`, matching the Python constant..."

**Check:** none of the 9 research files mention "quorum," "QUORUM," or "any one family over threshold." I checked this directly against the actual source it describes, `/home/kwhatcher/projects/nobots/hooks/scripts/check_ai_tells.py`, and every detail is accurate: `QUORUM = 2` (line 39), three named families — vocabulary, punctuation, sentence-length/burstiness (docstring lines 18-19, code lines 121-155), and the exact "any one family over threshold" phrasing is a near-verbatim quote from the file's own docstring (line 22-23).

**Assessment:** this is not an error — it's a correct, well-grounded claim — but it is not grounded in *the research corpus this review was scoped to check*. It appears the spec author read the actual nobots source directly (reasonable, since nobotrs is explicitly a port of it) rather than relying on the 9 research reports, none of which analyze `check_ai_tells.py`'s aggregation logic. Flagging per the assignment's instruction to call out unsourced claims either way — this one resolves as "reasonable synthesis from a legitimate but out-of-corpus source," not an invented detail.

**Severity:** Informational only.

---

## Correctly represented findings (positive notes)

- **rust_readability GPL correction**: applied consistently everywhere readability is mentioned — §2.2 ("hand-rolled Flesch-Kincaid — see below") and §10 ("`rust_readability` (GPL-3.0-or-later) is excluded; Flesch-Kincaid is hand-rolled instead"). No stray reference to the old crate anywhere in the document. This is the one correction the spec applies with zero drift from the research.

- **postInstall issue status**: §6 states the Claude Code `postInstall` feature request "is closed as not-planned." This is the *corrected* fact from `00-consolidated-summary.md`'s verification pass — the spec's own source report, `07-open-plugins-integration.md`, still incorrectly says the issue is "open/unresolved" in its own body text (§5, last paragraph) and its sources list. The spec author evidently used the consolidated summary's correction rather than propagating report 07's stale claim. Worth calling out as a case where the synthesis step improved on a source document rather than degrading it.

- **§7 v1 scope-out reasoning** (dependency-parse-dependent features, POS-tagging deferral) closely tracks the research's own hedging language almost verbatim — "no viable pure-Rust path... hard ecosystem gap, not a scoping preference" mirrors report 02's "no viable pure-Rust option exists at all" with the same emphasis, and the POS-tagging deferral correctly preserves the conditional relationship between `postagger.rs` (real but unproven) and `rust-bert`'s MobileBERT tagger (better, but only "free" if `tch-rs` is already a dependency) exactly as report 02 frames it.

- **is-it-slop / aislop corrections**: neither crate is mentioned anywhere in the spec, so the star-count correction and the "written in TypeScript, not Rust" correction from `00-consolidated-summary.md` don't come up — there's nothing to get wrong here, but confirming there's no stray reference to the old, incorrect 81-star figure.

---

## Summary

Two real overstatements (§2.2's classifier row, §10's "license-verified" claim), one dropped caveat with real design implications (perplexity tier's hardware cost), and one ungrounded provenance claim (§1's grimoire citation) are the actionable items. The §10 finding is the most serious of the four, since it's not just imprecise relative to the research — it actively contradicts a correctly-hedged claim the spec itself makes two sections earlier. The rest of the document, including the highest-risk synthesis points (the GPL correction, the postInstall status, the dependency-parsing scope-out), tracks the research corpus faithfully and in a few cases improves on it.
