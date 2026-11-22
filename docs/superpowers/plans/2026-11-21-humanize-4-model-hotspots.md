# Humanize 4: Model Hotspots Implementation Plan

## Reconciled diagnostic contract (2026-11-21)

The revised roadmap supersedes the historical goal of directing rewrite effort from classifier rankings. This milestone supplies optional local diagnostics only. Opening mode remains the default for legacy commands, with unchanged opening evidence fields and no extra inference pass. Full mode is explicit through `--model-coverage full`, configuration or environment. Review with selected models defaults to full diagnostics; an explicit opening selection is respected. Both modes share the configured cooperative deadline. Full mode preserves opening `raw_output`, threshold, metrics and excerpt metadata, and adds separately versioned coverage, windows, failures and a token-weighted aggregate only for a successful full run.

A source-mapped editorial index drives section packing. Heading changes always end a window, even if the whole document fits the token limit. Therefore the historical Bibb “one DetectorScope window” assertion below is superseded by section-boundary and complete-coverage assertions. Each body token belongs to one planned window. Tokenizer postprocessing adds special tokens per window. Retokenization disagreements or worker count mismatches fail the affected window honestly; no silent truncation or claimed coverage. ConPara normalization maps transformed display bytes back to original prose and source ranges.

Ranks are within a document, never authorship probabilities. Partial model runs, windows below 128 body tokens and constant-score runs do not contribute ranks. Reference windows use the first contributing model's partition; other tokenizers align by greatest unit overlap and then byte overlap. Per-model ranks and top-three agreement remain visible. Compare section deltas have a separate owner.

`guidance/hotspot-validation.json` stays false until a recorded blinded editor comparison demonstrates more actionable passages than section heuristics at comparable review effort. Authorship AUROC and overlap with expert edits alone cannot pass this gate. Feature mapping requires the tokenizer parity gate and documented human review; unknown or unreviewed features keep `guidance_id: null`. No human review is fabricated. The shipped mapping is intentionally empty, with survey tooling for counts and a pending review record. No corpus excerpt is written by that tooling.

---

**Goal:** Expose opt-in section-level reactions from the local classifiers (Desklib, ConPara, DetectorScope), with honest coverage, source locations, runtime parity and a measured editorial-validity gate. Rankings are diagnostic and never direct an automatic revision loop.

**Why this replaces the earlier Plan B:** the earlier plan aimed at document scores with full coverage. Three things changed:
- **The scores didn't fit this genre.** On the owner's AI-drafted Bibb fixture, all three models leaned human, so a better-covered document score is not useful on its own.
- **Search reads whole pages.** Google judges whole pages for originality and value, not single sentences, so section-level signals over the complete published page are the useful unit.
- **The data to check hotspots now exists.** Beemo pairs raw AI output with expert edits, so hotspots can be checked against where human editors actually intervened.

The improvements are:
1. Windows follow sections and paragraphs, not just sentences, so a hotspot is something an agent can rewrite.
2. Hotspots are ranked within the document, which is robust to each model's miscalibrated absolute scale.
3. `compare --models` shows per-section before and after.
4. DetectorScope features map to guidance entries.
5. A validation record gates the presentation.

**Architecture:**
- A pure planner (`src/models/windows.rs`) packs Plan 2's sentence units into section-aware windows within each model's limit.
- A deadline-aware runner scores the windows through a closure.
- Encoders and DetectorScope gain an opt-in full-coverage mode that leaves today's opening-excerpt `raw_output` untouched.
- `src/hotspots.rs` ranks windows by within-document z-score across models and attaches mapped guidance.
- `review` and `compare` (Plans 1 and 3) show hotspots when `--models` is given.

**Tech Stack:** Rust; `tokenizers` 0.23.2 and `candle` 0.8.4 (`models-encoders`); the DetectorScope Python worker (`models-detectorscope`).

**Spec:** `docs/superpowers/plans/2026-11-21-humanize-roadmap.md`. Depends on Plan 2 Task 2 (units), Plan 1 Task 4 (`review`) and Plan 3 Task 2 (`compare`). Plan 5 Task 6 writes the validation record.

## Global Constraints

- Without `--model-coverage full`, `ModelEvidence` JSON is byte-identical to today. `raw_output`, `threshold` and the `model_score` metric always describe the opening excerpt. Models never vote.
- Policy ids (exact): packing `"section-packed-v1"` (no overlap), aggregation `"token-weighted-mean-v1"`, ranking `"within-doc-z-v1"`.
- `MIN_HOTSPOT_TOKENS: usize = 128`. Windows with fewer body tokens are scored but excluded from ranking, and are marked `insufficient_context`.
- Every eligible token is covered exactly once on a successful run. A partial run yields `ScoreOutcome::Incomplete` with token coverage and gap ranges.
- Hotspot output always carries the exact label `"Where local classifiers react most. Not a Google signal and not evidence of authorship."` and the field `validated`, read from `guidance/hotspot-validation.json` (default `{"validated": false}`).
- Model-artifact tests are `#[ignore = "requires staged model artifacts"]` and run with `--include-ignored` when `NOBOTRS_MODELS_DIR` is set (as in `tests/model_parity.rs`).
- The DetectorScope feature mapping (Task 7) requires the Task 1 parity gate to pass.

## Review Focus

- A single paragraph longer than the token budget must be split at sentence units, then at token boundaries, and never truncated. Test in Task 2.
- ConPara normalization shifts byte offsets, so window ranges must still map to `doc.prose` and `doc.raw`. Test in Task 3.
- A document whose every window is below `MIN_HOTSPOT_TOKENS` must return `hotspots: []` with a reason, not rank noise. Test in Task 5.
- When the models disagree on the top section, the ranking must show the per-model ranks and an agreement count, not just a mean that hides the disagreement. Test in Task 5.
- In `compare --models`, a section deleted in AFTER must appear as `removed`, not be matched to an unrelated section. Test in Task 6.

---

### Task 1: DetectorScope tokenizer and offset parity gate

**Files:**
- Create: `scripts/dump_reference_tokens.py`
- Create: `tests/fixtures/models/detectorscope-bibb-tokens.json` (generated)
- Modify: `tests/detectorscope_parity.rs`, `docs/local-models.md`

**Interfaces:**
- Produces: the fixture `{ "tokenizer_revision", "text_sha256", "ids": [u32], "offsets": [[start, end]] }` for the flattened fixture text (mirror `flatten_with_map`, `src/models/detectorscope.rs:840`).

- [ ] **Step 1: Write the ignored test** `detector_scope_tokens_and_offsets_match_reference`. Load the pinned tokenizer, encode with truncation and padding disabled, and compare ids and offsets element by element. On a mismatch, print the first differing index with ±3 tokens of context.
- [ ] **Step 2: Generate the reference**

Run: `$NOBOTRS_MODEL_PYTHON scripts/dump_reference_tokens.py --manifest models/detectorscope.json --text evaluation/fixtures/bibb-fy27.txt --out tests/fixtures/models/detectorscope-bibb-tokens.json`

- [ ] **Step 3: Run the gate**

Run: `NOBOTRS_MODELS_DIR=… cargo test --locked --features models-detectorscope --test detectorscope_parity -- --include-ignored tokens_and_offsets`
Expected: PASS. If it fails, record the divergence and the regex-warning cause in `docs/local-models.md`, mark Task 7 blocked, and continue with the other tasks.

- [ ] **Step 4: Commit**

```bash
git add scripts/dump_reference_tokens.py tests/fixtures/models/detectorscope-bibb-tokens.json tests/detectorscope_parity.rs docs/local-models.md
git commit -m "test(detectorscope): tokenizer offset parity gate"
```

---

### Task 2: Section-aware window planner and runner

**Files:**
- Create: `src/models/windows.rs`
- Modify: `src/models/mod.rs`
- Test: `src/models/windows.rs` (a WordLevel tokenizer built in code; no artifacts)

**Interfaces:**
- Consumes: `PlanUnit { pub text: Range<usize>, pub paragraph: usize, pub heading: Option<String> }`, built by callers from Plan 2 `SentenceUnit` with ranges in the tokenized text.
- Produces:
  - Constants `PACKING_POLICY`, `AGGREGATION_POLICY`, `MIN_HOTSPOT_TOKENS` (values above)
  - `pub struct Window { pub index: usize, pub text: Range<usize>, pub units: Range<usize>, pub paragraphs: Range<usize>, pub heading: Option<String>, pub body_tokens: usize, pub ids: Vec<u32>, pub split: bool }`
  - `pub fn plan_windows(tokenizer: &Tokenizer, text: &str, units: &[PlanUnit], max_tokens: usize) -> Result<Vec<Window>, Error>`
  - `pub enum WindowStatus { Scored, TimedOut, NotRun, Failed(String) }`
  - `pub struct WindowResult { pub index: usize, pub status: WindowStatus, pub raw_output: Option<f64> }`
  - `pub struct WindowRun { pub results: Vec<WindowResult>, pub covered_tokens: usize, pub eligible_tokens: usize, pub aggregate: Option<f64> }`
  - `pub fn run_windows(windows: &[Window], deadline: Deadline, infer: impl FnMut(&[u32]) -> Result<f64, Error>) -> WindowRun`
- Packing order:
  1. Whole paragraphs, greedily, never crossing a change in `heading`.
  2. A paragraph larger than the budget is split into whole units.
  3. A unit larger than the budget is split at token boundaries (`split = true`).

  The budget is `max_tokens - special`, where `special` is the token count of `encode("", true)`.

- [ ] **Step 1: Write the failing tests**
  - `below_at_above_limit`: 1, 1 and 2 windows; every window's `ids.len() <= max_tokens`.
  - `every_token_covered_exactly_once`: the sum of `body_tokens` equals the unspecial encode length, and windows don't overlap.
  - `windows_never_cross_headings`: two headed sections that would fit in one window give 2 windows, each with the right `heading`.
  - `oversized_paragraph_then_sentence_split`: a 3-sentence paragraph over budget splits at units. A single 11-token sentence with a budget of 4 splits into ≥3 windows with `split`, covering 11 tokens.
  - `tail_only_edit_changes_only_last_window`: all ids are equal except the last window's.
  - `timed_out_middle_window_reports_gaps`: window 1 is `TimedOut`, the rest `NotRun`, `covered_tokens == w[0].body_tokens` and `aggregate == None`.
  - `aggregate_is_token_weighted`: the hand-computed weighted mean matches to 1e-12.
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models-encoders --lib models::windows`
Expected: FAIL

- [ ] **Step 3: Implement.** Encode once without specials and assign tokens to units by start offset. Wrap each body slice with the tokenizer post-processor. The runner checks the deadline before each window: an expired deadline or `Err(Timeout)` gives `TimedOut` and then `NotRun`, while other errors give `Failed` and the run continues. `aggregate` is set only when every window is `Scored`.
- [ ] **Step 4: Run tests** (same command). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add src/models/windows.rs src/models/mod.rs
git commit -m "feat(models): section-aware window planner and deadline-aware runner"
```

---

### Task 3: Full coverage for Desklib and ConPara

**Files:**
- Modify: `src/config.rs` (`model_coverage: ModelCoverage { Opening, Full }`, config key `model_coverage`, env `NOBOTRS_MODEL_COVERAGE`), `src/cli/mod.rs` (`--model-coverage`)
- Modify: `src/models/mod.rs` (`normalize_input_with_map`; new `ModelEvidence` fields), `src/models/encoders.rs`, `src/output.rs`
- Test: `src/models/mod.rs` tests, `tests/local_model_contract.rs`, `tests/model_parity.rs` (ignored)

**Interfaces:**
- Produces:
  - `fn normalize_input_with_map(text: &str) -> (String, Vec<Range<usize>>)`. `normalize_input` becomes `.0` of it.
  - New `ModelEvidence` fields, each skipped when empty or `None`: `packing_policy: Option<String>`, `aggregation_policy: Option<String>`, `windows: Vec<WindowEvidence>`, `full_coverage_output: Option<f64>`, `token_coverage: Option<f64>`, `coverage_gaps: Vec<Range<usize>>`
  - `pub struct WindowEvidence { pub index: usize, pub prose: Range<usize>, pub source_ranges: Vec<Range<usize>>, pub heading: Option<String>, pub body_tokens: usize, pub status: String, pub raw_output: Option<f64>, pub insufficient_context: bool, #[serde(skip_serializing_if = "Option::is_none")] pub detectorscope: Option<DetectorScopeEvidence> }`
- [ ] **Step 1: Write the failing tests**
  - `normalize_map_points_into_source`
  - `opening_mode_json_is_unchanged` (no new keys)
  - `model_coverage_flag_parses_and_rejects_unknown`
  - Ignored, with artifacts:
    - `full_coverage_on_bibb`: `token_coverage == 1.0`, `windows.len() >= 2` for desklib and conpara, `raw_output` equal to opening mode to 1e-6, and `full_coverage_output` present.
    - `tail_only_edit_moves_only_full_coverage_output`
    - `short_input_still_abstains_in_full_mode`
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models-encoders`
Expected: FAIL

- [ ] **Step 3: Implement.** After the unchanged opening-excerpt inference, and only in `Full` mode, map units into the prepared text (identity for Desklib, the normalization map for ConPara), plan windows, and run them with `|ids| session.infer(ids)`. A partial run returns `Incomplete { coverage: token_coverage }`.
- [ ] **Step 4: Run tests**

Run: `cargo test --locked --features models-encoders && NOBOTRS_MODELS_DIR=… cargo test --locked --release --features models-encoders --test model_parity -- --include-ignored`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config.rs src/cli/mod.rs src/models/mod.rs src/models/encoders.rs src/output.rs tests/local_model_contract.rs tests/model_parity.rs
git commit -m "feat(models): opt-in full-coverage windows for Desklib and ConPara"
```

---

### Task 4: Full coverage for DetectorScope

**Files:**
- Modify: `src/models/detectorscope.rs`
- Test: unit tests in that file; `tests/detectorscope_parity.rs` (ignored)

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces: the Task 3 fields for DetectorScope, with per-window `detectorscope` evidence (signed feature contributions and highlights per window).
- [ ] **Step 1: Write failing tests**
  - Unit: text under 1024 tokens plans exactly 1 window.
  - Ignored: `detectorscope_full_mode_bibb`: 1 window, coverage 1.0, `raw_output` equal to opening mode.
  - Ignored: `detectorscope_long_input_windows`: the fixture ×3 gives ≥2 windows, each worker `tokens` equals the planned `ids.len()`, and the document-level `top_features` are unchanged.
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models-detectorscope --lib models::detectorscope`
Expected: FAIL

- [ ] **Step 3: Implement.** Plan windows on the flattened text (unit ranges via `flatten_with_map`), make one `self.request` per window, and keep the existing token-count check per window.
- [ ] **Step 4: Run tests**

Run: `cargo test --locked --features models-detectorscope && NOBOTRS_MODELS_DIR=… NOBOTRS_MODEL_PYTHON=… cargo test --locked --release --features models-detectorscope --test detectorscope_parity -- --include-ignored`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/models/detectorscope.rs tests/detectorscope_parity.rs
git commit -m "feat(detectorscope): opt-in full-coverage windows"
```

---

### Task 5: Hotspots in `review`

**Files:**
- Create: `src/hotspots.rs`, `guidance/hotspot-validation.json` (`{"validated": false, "record": null}`)
- Modify: `src/review.rs` (with `--models`, `review` forces `Full` coverage and adds `hotspots`), `src/output.rs`, `src/lib.rs`
- Test: `src/hotspots.rs` tests (synthetic `ModelEvidence`), `tests/review.rs` (ignored, with artifacts)

**Interfaces:**
- Consumes: `ModelEvidence.windows` (Tasks 3–4).
- Produces:
  - `pub struct ModelRank { pub backend: String, pub raw_output: f64, pub z: f64, pub rank: usize }`
  - `pub struct Hotspot { pub rank: usize, pub heading: Option<String>, pub prose: Range<usize>, pub source_ranges: Vec<Range<usize>>, pub line: u32, pub end_line: u32, pub body_tokens: usize, pub mean_z: f64, pub per_model: Vec<ModelRank>, pub agreement: usize, pub features: Vec<HotspotFeature> }`. `agreement` = the number of models ranking this window in their top 3. `features` is filled in Task 7.
  - `pub struct HotspotReport { pub label: &'static str, pub ranking_policy: &'static str, pub validated: bool, pub reason: Option<String>, pub hotspots: Vec<Hotspot> }`
  - `pub fn rank(doc: &Document, evidence: &[&ModelEvidence]) -> HotspotReport`
  - `ReviewReport.hotspots: Option<HotspotReport>`
- Ranking:
  - Per model, z = (window output − mean over eligible windows) / population sd. Higher means more machine-like for all three models, per their `raw_units`.
  - A model with fewer than 2 eligible windows contributes nothing.
  - `mean_z` averages over the contributing models.
  - Windows are aligned across models by unit range: windows of different models covering the same units are merged on maximum unit overlap. Because the tokenizers differ, use Plan 2 unit ranges as the join key.
  - Output the top 5, or all windows if there are fewer.
- [ ] **Step 1: Write failing tests**
  - `ranks_by_within_doc_z`
  - `disagreement_is_visible`: model A's top window is model B's bottom one, so `agreement` is 1 and `per_model` shows both ranks.
  - `all_windows_too_short`: `hotspots: []` with `reason == "no window reaches 128 tokens"`.
  - `label_and_validated_flag_are_exact`
  - Ignored: `bibb_review_with_models_lists_hotspots_in_document_order_ranges`
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models --lib hotspots`
Expected: FAIL

- [ ] **Step 3: Implement.** Human output prints `label`, then `[unvalidated]` when `validated` is false, then each hotspot as `#rank lines L–E (heading): mean z +1.42, agreement 2/3`.
- [ ] **Step 4: Run tests**

Run: `cargo test --locked --features models`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hotspots.rs guidance/hotspot-validation.json src/review.rs src/output.rs src/lib.rs tests/review.rs
git commit -m "feat(review): ranked model hotspots with explicit validation flag"
```

---

### Task 6: Section deltas in `compare --models`

**Files:**
- Modify: `src/compare.rs`, `src/output.rs`
- Test: `src/compare.rs` tests (synthetic), `tests/compare.rs` (ignored)

**Interfaces:**
- Produces:
  - `pub struct SectionDelta { pub heading: Option<String>, pub before_lines: Option<(u32, u32)>, pub after_lines: Option<(u32, u32)>, pub before_mean_z: Option<f64>, pub after_mean_z: Option<f64>, pub status: &'static str }`, where `status` is one of `"matched" | "removed" | "added"`
  - `CompareReport.section_deltas: Vec<SectionDelta>` (skipped when empty)
  - `CompareReport.full_coverage_outputs: Vec<MetricDelta>` (one per model)
- Section matching: match on the heading text exactly. Unheaded sections match by maximum word-shingle Jaccard ≥0.3, and are otherwise `removed` or `added`.
- [ ] **Step 1: Write failing tests:** `deleted_section_is_removed_not_rematched`, `retitled_section_matches_by_content` and `unheaded_sections_match_by_shingles`.
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models --lib compare`
Expected: FAIL

- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run tests** (same command). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add src/compare.rs src/output.rs tests/compare.rs
git commit -m "feat(compare): per-section model deltas between versions"
```

---

### Task 7: DetectorScope features mapped to guidance (requires Task 1 PASS)

**Files:**
- Create: `scripts/survey_detectorscope_features.py`, `scripts/test_survey_detectorscope_features.py`
- Create: `guidance/detectorscope-features.json`
- Modify: `integrations/model_workers/detectorscope_worker.py` (report per-feature `active_tokens` and `highlight_limit`)
- Modify: `src/hotspots.rs`, `src/guidance.rs` (load the mapping)
- Test: `src/guidance.rs` tests, `src/hotspots.rs` tests

**Interfaces:**
- Produces:
  - The mapping file is `{ "schema_version": "1.0.0", "detectorscope_revision": str, "features": [{ "id": usize, "description": str, "guidance_id": str | null, "reviewed_by": str, "reviewed_on": "YYYY-MM-DD", "note": str }] }`. Only human-reviewed entries go in; the survey script never writes it.
  - `pub struct HotspotFeature { pub feature_id: usize, pub description: String, pub direction: i8, pub max_activation: f64, pub guidance_id: Option<String> }`, filled per hotspot from that window's DetectorScope evidence. There is no contribution value per window or sentence, so document contributions are never summed across windows.
  - The survey script runs the binary with `--models detectorscope --model-coverage full` over a corpus list (Plan 5 Task 1 registry). It counts how often each feature is active in the top-z windows of AI-labelled texts and of human-labelled texts, and writes a review sheet `evaluation/reports/detectorscope-feature-survey.csv` (feature, description, AI rate, human rate, lift, and up to 3 example spans taken **only** from the owner corpus). Example spans from local-only corpora such as Beemo (CC BY-NC) go in an uncommitted sidecar under `$NOBOTRS_INTERNAL_DIR/derived/`.
- [ ] **Step 1: Write failing tests**
  - `mapping_guidance_ids_exist`: every non-null `guidance_id` resolves to an entry.
  - `hotspot_features_carry_no_contribution_field`: the serialized `Hotspot` contains no `"contribution"` key.
  - `survey_lift_math` (Python, stub binary).
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --features models --lib guidance hotspots && python3 scripts/test_survey_detectorscope_features.py`
Expected: FAIL

- [ ] **Step 3: Implement.** Then run the survey on the owner corpus and Beemo, and have a human map the top 20 lift features (or record `guidance_id: null` with a note).
- [ ] **Step 4: Run tests** (same commands). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add scripts/survey_detectorscope_features.py scripts/test_survey_detectorscope_features.py guidance/detectorscope-features.json integrations/model_workers/detectorscope_worker.py src/hotspots.rs src/guidance.rs evaluation/reports/detectorscope-feature-survey.csv
git commit -m "feat(hotspots): map reviewed DetectorScope features to guidance"
```
