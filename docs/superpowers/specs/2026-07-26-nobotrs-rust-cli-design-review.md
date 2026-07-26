# Consolidated review: nobotrs Rust CLI design spec

**Spec reviewed:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`
**Inputs:** 5 independent reviews in `docs/research/reviews/` (opus-architecture, sonnet-factcheck, sonnet-completeness, haiku-consistency, haiku-alignment)
**This document:** synthesis + independent verification of the reviewers' most consequential claims, by re-reading the spec, the research corpus, and the `nobots` Python source directly — not a re-transcription of the five reviews.

---

## Overall verdict

**Needs a targeted design pass before implementation planning — specifically §2 (detection architecture) and the licensing/i18n gaps. It does not need a full re-design.**

Sections 3–6 (CLI surface, config/secrets, packaging, plugin integration) are well-researched, decisive, and ready for planning essentially as-is, modulo a handful of Important-tier fixes below. The blocking problem is concentrated and specific: **§2.3–2.4's aggregation design does not actually specify how a verdict is produced.** I independently verified this against both the spec text and the Python original it claims to port, and the gap is real, not reviewer overstatement (see Finding B1 below). Two more independent reviewers separately converged on a second real gap — non-native-English/i18n handling was explicitly researched and recommended, and is completely absent from the spec (zero mentions of language, ESL, or `whichlang`) — which is a stronger signal than either finding alone. A third confirmed issue is a direct, verifiable self-contradiction in the license claims (§10 vs §7).

None of this requires abandoning the architecture. `DetectorBackend` as a plugin seam, the CLI surface, the packaging story, and five of the six explicit product decisions are sound and unanimously confirmed aligned with intent (decision-alignment review: 6/6 confirmed, no hedging). The fix is to stop treating "combine N heterogeneous signals into one number" as solved by citing the Python original, since the Rust redesign changed the thing being combined (backends, not feature families) without re-deriving the rule.

**Recommendation:** resolve the items marked **Blocker** below (they change shared types — `Score`, the trait signature — that every backend implementation touches; getting them wrong now costs a five-backend refactor later), then proceed to planning. Important-tier items can be resolved during planning if genuinely time-boxed; several are one- or two-sentence spec additions.

---

## Verification notes (Part 2 — what I checked myself)

**1. Opus's central claim: no defined mapping from deterministic hit-count to `human_probability`, and `QUORUM=2` behaves inconsistently across build configs.**

Confirmed on both counts, independently, against the spec text and the Python source.

- Spec §2.3 states only: *"`human_probability` is the canonical continuous representation... the other three commercial vendors and the deterministic/stylometric backends return coarser labels or thresholds, which map onto fraction *bands* rather than exact points"* — this asserts a mapping exists but never states it (what band? what boundaries? is it linear, tiered, hand-picked?). No formula, table, or reference appears anywhere in §2.3 or §2.4.
- I read `check_ai_tells.py` directly (not just trusting the reviewer's line numbers). It confirms exactly what Opus described: three named families — `vocabulary`, `punctuation`, `burstiness` (code, lines 123–149) — each casting a discrete vote of `0/1/2` (abstain/suspicious/strong), aggregated via `agree = len(families); if agree < QUORUM: return` (lines 155–156), with `QUORUM = 2` (line 39) and an explicit abstention comment: *"A family that cannot be measured (e.g. burstiness on a short file) simply abstains"* (line 122). The Python **never produces a continuous probability at all** — it's discrete family-votes, all the way through.
- Mapping the spec's own tier table (§2.2) onto these three Python families shows two of the three collapse into one Rust backend (`stylometric` covers both `punctuation`/em-dash-density and `burstiness`). The default build (`deterministic` + `stylometric`, both always-on, §2.2) therefore has exactly two voters, so `QUORUM = 2` — "starting default... matching the Python constant" (§2.4) — silently changes meaning from "2 of 3 independent families agree" to "both backends must agree," i.e. unanimity. This is a real, mechanical consequence of the spec's own tier definitions, not an inference stretch.

**Verdict: Opus did not overstate this. It is the single most load-bearing finding across all five reviews.**

**2. Sonnet fact-check's claim: §10 contradicts §7 on the `stylometry` crate's license.**

Confirmed as an exact, direct contradiction — both quotes below are drawn straight from the spec text I read in full:

> §10: *"See `docs/research/00-consolidated-summary.md` § 'Recommended stack' for the full, **license-verified table**. All selected crates are MIT/Apache-2.0/Unlicense family with one correction already applied..."*

> §7, point 3: *"`stylometry` (ian-nai/rust_stylometry) license — flagged as a direct dependency candidate for classic authorship-analysis statistics, but its license was **not independently confirmed in research**. Must be verified before it is actually added as a dependency."*

§10's "All selected crates are MIT/Apache-2.0/Unlicense" is flatly inconsistent with §7's "not independently confirmed," two sections earlier in the same document, about the same crate, sourced from the same research table. **Verdict: confirmed real, not overstated.** (Separately worth noting per Opus's C3: `stylometry` isn't even in §2.2's actual crate list for the `stylometric` tier — the tier is built on `unicode-segmentation`/`statrs`/`xz` — so the cheapest fix is to drop the dependency and the contradiction along with it, rather than go verify a license for a crate the architecture doesn't use.)

**3. Sonnet completeness's claim: research report 02 recommended a `whichlang`-based non-native-English gate, and the spec drops it entirely.**

Confirmed on both halves.

- I read `docs/research/02-nlp-tokenization-crates.md` §4 and its Recommendation §4 directly. It explicitly recommends: *"add `whichlang` (MIT, small, fast, good-enough accuracy) ahead of any English-tuned stylometric feature, and note in the design that even English text can trigger elevated false-positive risk when written by non-native speakers — a detection-calibration concern, not just a language-filter one."* This is stated as a numbered, prescriptive recommendation (item 4 of 4), not a passing mention.
- I grepped the full spec text for `language|esl|non-native|whichlang|english` (case-insensitive): **zero matches.** The omission is total — not just the crate name, but the entire concept of language-gating or ESL false-positive risk.

**Verdict: confirmed, not overstated.** This is also independently corroborated by the Opus review's D3 finding (no stated position on AI-detector false-positive bias against non-native writers), reached via a completely different line of reasoning (general knowledge of detector bias literature vs. this project's own commissioned research). Two reviewers, two methods, same gap — this is the strongest convergent signal in the whole review round besides the quorum-design issue.

**4. Spot-checks on the two Haiku (mechanical) reviews.**

- Haiku-consistency's claim that §5 (packaging) documents binary-size impact for `classifier`/`perplexity` but not `api-clients` — confirmed by direct read of §5: only candle (~50-80MB) and ONNX Runtime (~100-150MB) are sized; `reqwest`/`api-clients` gets no size figure. Correctly flagged as an incompleteness, not a contradiction — accurate characterization.
- Haiku-alignment's claim that all 6 explicit product decisions are faithfully reflected in the spec — spot-checked decision 6 (`human_probability: f32` as canonical continuous representation) directly against §2.3's struct definition and prose; matches exactly, including the Pangram-native-fractions rationale. I'll flag one nuance the alignment review doesn't surface (it wasn't in its scope): decision 5 confirms *perplexity ships in v1* is faithfully implemented, and Opus's E1 finding (perplexity's calibration is invalidated by GGUF quantization, with no data to refit against) is not a contradiction of that alignment finding — Opus's own recommended fix (ship it, but non-voting/experimental in v1) preserves the product decision to include it while fixing the specific technical defect. Both reviews are correct; they're answering different questions.

Both Haiku reviews read as accurate for what they scoped (mechanical/alignment checks) — I found no errors in either during spot-checking, though I did not exhaustively re-verify every line-number citation.

---

## Prioritized findings

### Blocker — resolve before writing an implementation plan

**B1. The quorum/aggregation design (§2.3–2.4) has no defined signal→probability mapping, and its voting unit silently changed from "signal family" to "backend."**
- **Raised by:** Opus (A1, A2, A4 — primary and most detailed), independently corroborated by my own read of `check_ai_tells.py`.
- **Status:** confirmed, not overstated (see verification #1 above).
- **Why it's a blocker, not a during-planning fix:** it determines the shape of `Score` (needs a family/signal identifier, not just `backend: String`) and the trait's return type. Every backend implementation depends on this type. Discovering the fix after backends exist means a cross-cutting refactor.
- **Fix:** Pick one of two paths and say so explicitly in §2.3–2.4:
  - (a) **Recommended — keep discrete family votes.** Add a `family: SignalFamily` (or similar) field so multiple signals within one backend (e.g. `stylometric`'s burstiness and em-dash-density) can vote independently, matching what the Python actually measures the false-positive lesson against. Keep `human_probability` as a *reported* per-backend continuous value for display/JSON, but make the vote itself the Python's discrete `{abstain, suspicious, strong}` per family, with no invented calibration required.
  - (b) Keep the float as the aggregation currency, but only if paired with D1 below (an actual calibration corpus/procedure) — do not ship (b) without D1.
  - Either way, state explicitly what the default two-backend build's quorum behavior is intended to be (unanimity is fine as a *stated conservative choice*; it is not fine as an unstated accident).

**B2. `api-clients` tier contributes up to four correlated votes to the same quorum that assumes independence.**
- **Raised by:** Opus (A3).
- **Status:** plausible and well-argued; follows directly from B1's premise once accepted — not independently re-derived by me beyond confirming §2.2's "one client module per vendor" language, which does read as one `DetectorBackend` impl per vendor.
- **Fix:** In §2.4, state that the `api` tier reduces to **one** vote (e.g., max-confidence or majority-of-configured-vendors), not one vote per vendor client.

**B3. The trait has no abstention outcome, but abstention is load-bearing in the design it claims to port.**
- **Raised by:** Opus (A5).
- **Status:** confirmed — `check_ai_tells.py:122` explicitly documents family-level abstention ("burstiness on a short file simply abstains") as a false-positive-avoidance mechanism, and the spec's `fn score(&self, text: &str) -> Result<Score>` (§2.1) has only two outcomes (`Score` or `Err`), with no way to say "not applicable to this input" distinct from "the model failed to load." Both collapse into the same quorum-denominator ambiguity as B1/B2.
- **Fix:** Change the trait signature to return something like `Result<Option<Score>>` or an explicit `ScoreOutcome{ Scored | Abstained{reason} | Failed(Error) }`, and state in §2.4 how abstention/failure affects the quorum denominator (dropped from the pool vs. counted as a non-vote).

**B4. `text: &str` cannot simultaneously support original-file offset anchoring (required by `Evidence`/`lint`) and prose-only content extraction (required by every stylometric measure), and the spec never mentions markdown/code-fence handling.**
- **Raised by:** Opus (B1).
- **Status:** plausible-unverified by me directly (I did not attempt to disprove it by testing an implementation), but the underlying tension is real on inspection: §2.3 requires evidence to be "line/offset-anchored," §3 extends `scan <dir>` to arbitrary directory trees (not just the Python's `PROSE_EXTENSIONS`-gated hook input), and no preprocessing/segmentation stage appears anywhere in §2. I did not find a counter-argument reading the spec.
- **Fix:** Introduce a `Document` type (original text + prose spans + offset map + detected content type) as the trait's actual input in §2.1, and state the segmentation strategy (at minimum: markdown-aware) before backends are implemented.

**B5. §10 asserts the dependency table is "license-verified" and all crates are MIT/Apache-2.0/Unlicense, directly contradicting §7 point 3's "not independently confirmed" for the same crate.**
- **Raised by:** Sonnet fact-check (#2).
- **Status:** confirmed exact contradiction (see verification #2 above).
- **Fix:** Since `stylometry` isn't actually referenced in §2.2's crate list for any tier, the cleanest fix is to **drop the `stylometry` line from §7 and §9 entirely** (hand-roll the few statistics it would have provided, consistent with how MTLD and Flesch-Kincaid are already handled) and change §10 to just "all crates in the recommended stack are MIT/Apache-2.0/Unlicense family" without the "full, license-verified table" framing, since that phrase overclaims regardless of the `stylometry` question.

**B6. Non-native-English/ESL false-positive risk and language-gating are completely absent from the spec, despite being explicitly researched and recommended.**
- **Raised by:** Sonnet completeness (#5) and Opus (D3), independently, via different methods.
- **Status:** confirmed on both the research-recommendation side and the spec-omission side (see verification #3 above). This is the strongest convergent finding in the review round.
- **Fix:** Add to §2 (near the stylometric tier definition) a concrete commitment, even a narrow one: gate English-tuned stylometric features behind a `whichlang`-based language check, and add one sentence noting that even English text shows elevated false-positive risk for non-native writers — a calibration caveat, not just a language filter (this is close to verbatim what the research already wrote — it can likely be lifted directly from `docs/research/02-nlp-tokenization-crates.md` §4).

**B7. No evaluation corpus, accuracy/FPR target, or calibration plan anywhere in the spec — and §2.4's own "tunable... once real data is in" plan has nothing that produces that data.**
- **Raised by:** Opus (D1).
- **Status:** confirmed by direct read of §8 (Testing strategy), which covers code-correctness testing (unit tests, mocked HTTP, feature-gated integration tests) but nothing about measuring detection accuracy or false-positive rate on real text.
- **Fix:** Add to §8 (or a new §8a): a held-out labeled corpus (human vs. AI text), a stated target false-positive rate on human text, and a rule that no threshold constant (`QUORUM`, burstiness cutoffs, etc.) ships without a number behind it. This is a prerequisite for B1's calibration path (b) and for evaluating whether the `perplexity` tier (see I1 below) is worth shipping at all.

**B8. Model-checkpoint licensing is entirely unaddressed, despite meticulous crate-license diligence elsewhere.**
- **Raised by:** Opus (C2) and Sonnet completeness (#10) — independent convergence.
- **Status:** confirmed by direct read of §7, §9, §10 — all three sections discuss *crate* licenses in detail (including catching the `rust_readability` GPL issue) but none mention the license of `desklib/ai-text-detector-v1.01` (§9.1) or the Falcon-7B/Falcon-7B-Instruct pair (§2.2 perplexity tier), both of which carry their own, often more restrictive, license terms distinct from the code that loads them.
- **Fix:** Add a line to §9 (same priority as item 1, the candle/desklib prototype item): verify `desklib/ai-text-detector-v1.01`'s license permits nobotrs's intended use, and do the same for whatever perplexity-tier checkpoint pair is chosen, before either is prototyped past a spike.

### Important — should resolve, can be during planning if genuinely time-boxed

**I1. Twin-model perplexity tier: GGUF quantization invalidates the published Binoculars calibration threshold, and there's no data to refit against.**
- **Raised by:** Opus (E1), reinforced by Sonnet fact-check's independent finding (#3) that the tier's ~8-10GB RAM cost and "no smaller validated pair exists" caveat were dropped from the spec text entirely (present in research, absent from §2.2, §7, §9).
- **Status:** confirmed as a real technical concern (quantization shifting logit distributions is a well-understood effect, not a stretch) and confirmed as a dropped caveat (I independently grepped the spec for "RAM"/"GB"/"Falcon"/"Binoculars"/"hardware" — zero hits beyond the one §2.2 table cell). Does not require blocking planning — Opus's own recommended fix is additive, not a redesign.
- **Fix:** Per Opus's E3 — keep `perplexity` behind its feature flag (preserves the confirmed product decision, per the alignment review), but ship it in v1 as **non-voting/experimental**: report the raw cross-perplexity ratio and evidence, exclude it from quorum aggregation until B7's calibration corpus exists and the threshold is refit against the *quantized* numerics actually shipping. Also restore the dropped RAM/download-size caveat to §2.2 or §7.

**I2. `full` meta-feature silently includes `api-clients`, meaning a convenience build flag enables third-party data egress once keys are configured.**
- **Raised by:** Opus (F1).
- **Status:** plausible, confirmed by direct read of §2.2 ("A `full` meta-feature enables all five tiers") and §4's key-gating guarantee — the mechanics check out; whether this is undesirable is a product call, not a fact, so I present it as the reviewer's judgment rather than an established defect.
- **Fix:** Exclude `api-clients` from `full` (rename the alias, or require a separate explicit flag), especially given `scan <dir>` can run unattended in CI with keys in the environment.

**I3. Exit-code convention ("0 = clean, non-zero = tells found") has no code for tool failure, and collides with the `PostToolUse` hook's exit-code semantics.**
- **Raised by:** Opus (F2).
- **Status:** confirmed by direct read of §3 and the Python's documented behavior (fails open, exits differently for feedback vs. silence per `check_ai_tells.py:14-15` referenced in the review). The standard-linter-convention claim (0/1/2 = clean/findings/error) is reasonable and the hook-collision mechanism (Claude Code treats exit 1 and exit 2 differently) is a real protocol detail worth stating explicitly in §6 either way.
- **Fix:** Adopt 0/1/2 = clean/findings/error in §3, and add one sentence to §6 stating how the plugin wrapper translates `nobotrs`'s exit codes to the hook protocol's expected codes.

**I4. `lint`'s "suggested fixes" content is committed to in §3's CLI surface but never defined — unclear whether stylometric flags (burstiness, MTLD) get template-able fixes the way tell-word hits do.**
- **Raised by:** Sonnet completeness (#11).
- **Status:** plausible-unverified in the sense that I confirmed the spec text is exactly as ambiguous as claimed (§3's one-line description promises "suggested fixes" for all of "word/phrase hits + stylometric flags") but did not independently determine what the *right* answer is — that's a product decision, not a fact I can verify.
- **Fix:** State explicitly in §3 or a new §3a whether suggested fixes apply only to deterministic tell-word/phrase hits (template-swap, has an obvious mechanism) or are attempted for stylometric flags too (no obvious template exists for "your burstiness is low" beyond generic advice) — this affects what `Evidence` (§2.3) needs to carry.

**I5. API keys have no stated guarantee against appearing in logs, error output, or `Debug` output.**
- **Raised by:** Sonnet completeness (#8).
- **Status:** not independently verified against actual code (none exists yet), but the risk pattern described (a `reqwest` error or derived `Debug` impl printing a `String` secret) is a well-known, generic Rust footgun, not a speculative one.
- **Fix:** Add one line to §4: "API keys must never appear in log output, error messages, or `Debug` representations" — cheap now, expensive to retrofit across four vendor client modules later.

**I6. `--format json` is positioned as a CI/scripting interface (§3) with no stability/versioning contract, while `Score` (its underlying shape) is also the type B1 needs to change.**
- **Raised by:** Sonnet completeness (#4).
- **Status:** confirmed by direct read of §3 — the claim itself ("for CI/scripting") is exact spec language, and no stability statement exists anywhere in the document.
- **Fix:** Add a one-line stability contract to §3 (e.g., a `schema_version` field in the JSON output, or a stated semver policy for the output shape independent of crate semver) — worth doing in the same pass as B1 since both touch `Score`'s shape.

**I7. Downloaded model weights have no stated integrity-verification commitment (checksum/hash pinning).**
- **Raised by:** Sonnet completeness (#9).
- **Status:** confirmed absent from §9's discussion of the candle/desklib prototype step — the mechanism can reasonably be deferred to the prototyping work itself, but the *commitment to do it* is what's missing.
- **Fix:** One line in §9 item 1: downloaded checkpoints are checksum-verified against a pinned hash before load.

**I8. No model-download/lifecycle mechanism in the `DetectorBackend` trait; `hf-hub` (named in research) doesn't appear in the spec.**
- **Raised by:** Opus (B2).
- **Status:** plausible-unverified — I confirmed `hf-hub` doesn't appear in §2.2's crate columns, but did not independently verify it's the right crate to add; taking the reviewer's word that this is a real gap in the trait design given `classifier`/`perplexity` clearly need model acquisition.
- **Fix:** Add an `availability()`/lifecycle method to the trait sketch in §2.1 (Ready / NeedsDownload / Unavailable), and name the download mechanism explicitly rather than leaving `nobotrs config`'s "model downloads" (§3) as the only mention.

**I9. `scan <dir>` over the `DetectorBackend` trait as specified has no batching, no `Send + Sync`, no timeout — a CI-composability concern given ML tiers can be enabled.**
- **Raised by:** Opus (B3).
- **Status:** plausible-unverified — sound reasoning about the trait signature as written, not independently tested.
- **Fix:** Add `Send + Sync` bound, consider an optional `score_batch`, and state which tiers `scan` runs by default (Opus suggests restricting to `deterministic`+`stylometric` unless ML tiers are opted into explicitly).

**I10. `ConfidenceTier` is defined on `Score` but never used in aggregation, and the ensemble's own output confidence tier (promised in §1's goals) is never derived from anything.**
- **Raised by:** Opus (A6).
- **Status:** confirmed by direct read — §2.4 makes no mention of `confidence` at all.
- **Fix:** Either use per-backend confidence as a vote weight in §2.4 (and say so), or state that the ensemble tier is derived solely from quorum margin and drop per-backend confidence from influencing aggregation.

**I11. §2.2's classifier-tier table cell overstates confidence: "confirmed to exist and match this use case" packages two different confidence levels (module exists ✓; checkpoint compatibility ✗ unconfirmed) into one word.**
- **Raised by:** Sonnet fact-check (#1).
- **Status:** confirmed — I compared the exact §2.2 phrasing against §9 item 1's more careful phrasing in the same document ("the module's existence is confirmed, but nobody has been found to have actually loaded that specific checkpoint into it") and against the research's own hedge. The caveat survives in §9 but is lost in the §2.2 table specifically.
- **Fix:** Reword the §2.2 table cell to something like `candle-transformers::debertav2` (module confirmed; checkpoint compatibility unconfirmed — see §9)`.

### Minor — polish, low cost, do whenever

- **M1.** §5's binary-size discussion covers `classifier`/`perplexity` but not `api-clients` (Haiku-consistency, confirmed by direct read — likely negligible since `reqwest` is small, but worth a one-clause mention for completeness).
- **M2.** §5/§6 don't jointly specify whether plugin installation triggers/prompts binary installation, or whether it's entirely manual after the fact (Haiku-consistency — confirmed gap, not a contradiction; genuinely low-stakes UX-copy question, not architectural).
- **M3.** Relationship between `detect` and `lint` — does `lint` apply the quorum, or report every hit unconditionally? (Opus F3 — matters for what the hook in §6 actually calls, but easy to state in one sentence.)
- **M4.** `candle`'s pre-1.0 status and lack of a pinning/MSRV policy statement (Opus F4).
- **M5.** Mocked API-client tests can't catch vendor schema drift over time; worth a documented periodic manual re-verification note (Opus F5).
- **M6.** §1's "Research basis" line cites two grimoire directories, but only one (`open-plugins-spec/`) is actually used anywhere in the 9-report research corpus — I did not independently re-verify this (would require grepping all 9 research files for the second path, which I did not do), so treat this as **plausible-unverified**, sourced from Sonnet fact-check (#4) alone. Low stakes either way — doesn't affect any technical claim in the spec body.
- **M7.** MSRV/edition, workspace-vs-single-crate layout, and telemetry/privacy stance are all silent in spec text but already substantively resolved by the research corpus — recommend one sentence each for explicitness, no design work needed (Sonnet completeness #2, #3, #6).
- **M8.** CI feature-flag matrix (which of default/classifier/perplexity/api-clients/full combinations get tested) isn't specified in §8 — recommend naming a specific minimal matrix (default, each flag isolated, `full`) rather than full combinatorial coverage (Sonnet completeness #7).

---

## Recommended spec edits (actionable list)

In priority order, matching the Blocker/Important tiers above:

1. **§2.3–2.4:** Add a `family`/signal identifier to `Score` (or an equivalent construct) so aggregation counts independent signal families, not backends. State explicitly what quorum behavior is intended for the default 2-backend build. State that the `api` tier contributes one reduced vote, not one vote per vendor. (B1, B2)
2. **§2.1:** Change `fn score(&self, text: &str) -> Result<Score>` to support a third abstain outcome (e.g. `Result<Option<Score>>` or an explicit outcome enum), and state in §2.4 how abstention/failure affects the quorum denominator. (B3)
3. **§2.1–§2.3:** Introduce a `Document` type (original text + prose spans + offset map + content type) as the trait's actual input, replacing bare `&str`; state the segmentation strategy (markdown-aware at minimum). (B4)
4. **§7 and §10:** Remove the `stylometry` (ian-nai/rust_stylometry) crate reference from §7 point 3 and §9 item 2 (it's unused in §2.2's actual crate list); reword §10 to drop the "license-verified table" framing that overclaims relative to §7. (B5)
5. **§2 (near stylometric tier) or a new subsection:** Add explicit `whichlang`-based language gating ahead of English-tuned stylometric features, plus the ESL-calibration-risk caveat — text can likely be adapted directly from `docs/research/02-nlp-tokenization-crates.md` §4's recommendation. (B6)
6. **§8:** Add an evaluation-corpus / accuracy-target / FPR-target / calibration-plan subsection, sequenced early in the implementation plan, since it's a prerequisite for tuning `QUORUM` and any per-feature thresholds. (B7)
7. **§9:** Add checkpoint-license verification for `desklib/ai-text-detector-v1.01` and the perplexity-tier model pair, at the same priority as the existing candle-prototype item. (B8)
8. **§2.2 or §7:** Mark `perplexity` as non-voting/experimental in v1 pending calibration against quantized numerics; restore the dropped ~8–10GB RAM / no-smaller-validated-pair caveat to the spec text. (I1)
9. **§2.2:** Exclude `api-clients` from the `full` meta-feature, or rename it so "full" doesn't silently imply third-party data egress once keys are configured. (I2)
10. **§3 and §6:** Adopt 0/1/2 = clean/findings/error exit codes; state the hook wrapper's exit-code translation in §6. (I3)
11. **§3:** State explicitly whether "suggested fixes" apply to all finding types or only deterministic tell-word/phrase hits. (I4)
12. **§4:** Add "API keys must never appear in log output, error messages, or `Debug` representations." (I5)
13. **§3:** Add a one-line JSON output stability/versioning statement (e.g. a `schema_version` field). (I6)
14. **§9:** Add "downloaded model weights are checksum-verified against a pinned hash before load." (I7)
15. **§2.1:** Add a model-lifecycle/availability method to the trait sketch; name the download mechanism (e.g. `hf-hub`) explicitly. (I8)
16. **§2.1/§3:** Add `Send + Sync` to the trait; state which tiers `scan` runs by default. (I9)
17. **§2.4:** State whether/how `confidence: ConfidenceTier` factors into aggregation, or drop it from influencing the ensemble tier. (I10)
18. **§2.2:** Reword the classifier-tier table cell to distinguish "module confirmed to exist" from "checkpoint compatibility unconfirmed." (I11)
19. Minor items (M1–M8): fold into the same editing pass opportunistically — each is a sentence or two, none require new research.
