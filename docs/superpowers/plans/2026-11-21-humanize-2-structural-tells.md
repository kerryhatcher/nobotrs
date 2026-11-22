# Humanize 2: Structural Tells Implementation Plan

## Reconciled implementation contract (2026-11-21)

The revised roadmap overrides the historical task details below. Implementation is single-agent within the assigned scope. Guidance and its brief ship together in the Cargo archive. Guide JSON retains the legacy `guide` field and adds canonical data with serialized leverage. Review uses unsliced suppressed outcomes, computes counts/checklists before limiting once, and emits one logical finding with an optional location. Document metrics retain their messages and have no invented coordinates. Review rejects SARIF and external services.

Structure runs only in editorial analysis (`review` and the shared compare API), even though it is a configurable backend. Legacy detect/lint/analyze/scan execution and budgets remain unchanged. All structure observations are low severity and non-voting, require asserted English, and are unvalidated for editorial usefulness. A short-unit annotation is not a grammar judgment. Deliberate repetition, dialogue and factual lists may be retained.

Editorial units carry normalized display text separately from original UTF-8 navigation ranges. Statistical sentence segmentation is unchanged. Markdown ancestry preserves list identity through loose/nested items and inline-code gaps. Equivalent dictionary/structure contrasts are reconciled by overlapping ranges after suppression, with the active dictionary match taking precedence. Disabled, abstained and incomplete checks remain visible and cannot imply a passing checklist item.

The tests in `tests/guidance.rs`, `tests/review.rs`, `tests/bibb_fixture.rs` and unit modules implement the corrected examples (valid suppression syntax and Markdown code-only input). Package verification must install from an extracted archive and run its guidance, review and fixture tests. Skills and evaluation are owned separately; this implementation does not mark their tasks complete.

---

**Goal:** Detect the durable structural and formatting tells that the project's research identifies, at sentence and document level, each with guidance, so agents revise the patterns that matter rather than swapping words.

**Architecture:**
- A sentence-unit index (`src/sentences.rs`) segments prepared prose into units, including line-terminated headings and list items. `doc.sentences` stays unchanged.
- A new heuristic backend, `structure` (`src/backends/structure.rs`, family `SignalFamily::Structure`, never voting), emits sentence-level evidence and document-level findings with stable `structure.*` rule IDs.
- Findings flow through the existing pipeline, so `lint`, `analyze`, `review` (Plan 1) and SARIF see them. Rule thresholds are unvalidated, so the backend emits at `Severity::Low`. Plan 5 Task 3 measures lift.

**Tech Stack:** Rust 2021, `unicode-segmentation`, `regex`, `pulldown-cmark` (already used for Markdown preparation).

**Spec:** `docs/superpowers/plans/2026-11-21-humanize-roadmap.md`. Depends on Plan 1 Task 1 (guidance coverage test) and Task 4 (`review`).

## Global Constraints

- Scoring is unchanged. `SignalFamily::Structure` is excluded from `voting_eligible` in `Score::new`. Verdicts, quorum and `detect` exit codes on every existing test and on the fixture baseline stay identical.
- All `structure.*` findings are `Severity::Low`, so `lint` with the default `--minimum-severity medium` exits as before. `review` shows them.
- Structural rules require `--language en` (or English config). Without it the backend abstains with `"structural rules require --language en"`.
- Every `structure.*` rule ID has exactly one guidance entry (Plan 1's coverage test is extended to include them).
- Every finding's `source_ranges` round-trip to `doc.raw`.
- The fixture's bytes never change: SHA-256 `5c45d6d3edb1f09cf567915a1ea14699316fdeefe7576d9ac805aa7d69aa23d4`.

## Review Focus

- CRLF plain text must segment exactly like LF, and no unit text may contain `\r`. Test in Task 2.
- Hard-wrapped prose (a line break followed by a lowercase continuation) must stay one unit. Test in Task 2.
- A legitimate three-item list of facts ("the 2023, 2024 and 2025 budgets") must not fire the rule-of-three tell. Only the short abstract-noun or adjective triads described below should fire. Test in Task 3.
- Markdown code blocks containing "In conclusion" or `**Bold:**` must not produce findings (prepared prose excludes code). Test in Task 4.
- Non-English input must abstain, not emit English-pattern findings. Test in Task 3.

---

### Task 1: Commit the fixture and pin the baseline

**Files:**
- Create: `evaluation/fixtures/README.md` (source: excerpt of the owner's post "Out of Runway: The FY27 BCSD Budget", 2026-05-27; label: AI-drafted with minimal human edits, per the owner, 2026-11-21; do not edit the bytes)
- Create: `evaluation/fixtures/SHA256SUMS`
- Add: `evaluation/fixtures/bibb-fy27.txt`
- Test: `tests/bibb_fixture.rs`

**Interfaces:**
- Produces: the spawn helpers `run`, `json` and `json_stdin` (copied per test file, matching `tests/cli_smoke.rs`'s env scrubbing).

- [ ] **Step 1: Write the baseline test** `bibb_fixture_offline_baseline_is_pinned`. Assert:
  - the fixture is 2,236 bytes and 2,192 chars
  - `analyze --language en --format json` gives verdict `clean`, `sentence_count` 21 and `prose_words` 348
  - punctuation votes `strong` with `effective_em_dash_count` 9.0
  - `sentence_length_cv` 0.9920, `mtld` 199.3117, `flesch_kincaid_grade` 9.2849, `lzma_ratio` 0.6544 and `token_entropy` 7.6634, each to ±5e-5

  Extend the test after Task 3 to assert that the `structure` backend is present and `voting_eligible: false`.

- [ ] **Step 2: Verify the checksum and run**

Run: `(cd evaluation/fixtures && sha256sum -c SHA256SUMS) && cargo test --locked --test bibb_fixture`
Expected: `bibb-fy27.txt: OK`, then PASS

- [ ] **Step 3: Commit**

```bash
git add evaluation/fixtures tests/bibb_fixture.rs
git commit -m "test(fixtures): pin AI-drafted Bibb FY27 fixture and offline baseline"
```

---

### Task 2: Sentence-unit index

**Files:**
- Modify: `src/document.rs` (record `block_kinds`)
- Create: `src/sentences.rs`
- Modify: `src/lib.rs`
- Test: `src/sentences.rs` (`#[cfg(test)]`)

**Interfaces:**
- Produces, in `src/document.rs`: `pub enum BlockKind { Paragraph, Heading, ListItem, TableCell }` (serde snake_case) and `pub block_kinds: Vec<BlockKind>`, parallel to `prose_spans`. Plain text yields one `Paragraph`.
- Produces, in `src/sentences.rs`:
  - `pub enum UnitKind { Sentence, Heading, ListItem }`
  - `pub enum Boundary { Terminal, LineBreak, BlockEnd }`
  - `pub struct SentenceUnit { pub id: usize, pub prose: Range<usize>, pub source_ranges: Vec<Range<usize>>, pub block: usize, pub paragraph: usize, pub kind: UnitKind, pub boundary: Boundary, pub uncertain: bool, pub words: usize }`. `paragraph` increments at each blank line in plain text and at each block in Markdown.
  - `pub fn sentence_units(doc: &Document) -> Vec<SentenceUnit>`
  - `pub fn paragraphs(units: &[SentenceUnit]) -> Vec<Range<usize>>`: unit-index ranges per paragraph

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn bibb_fixture_lines_become_units() {
    let (d, u) = units(include_str!("../evaluation/fixtures/bibb-fy27.txt"), false);
    let count = |k: UnitKind| u.iter().filter(|x| x.kind == k).count();
    assert_eq!(count(UnitKind::Heading), 4);   // "Why 7.8%…", "The cut menu", two colon lead-ins
    assert_eq!(count(UnitKind::ListItem), 9);
    let t = texts(&d, &u);
    assert!(t.contains(&"Still short.".to_string()));
    assert!(t.iter().any(|s| s.starts_with("After consolidating schools,") && s.ends_with("together.")));
    for (i, _) in d.prose.match_indices('—') {
        assert_eq!(u.iter().find(|x| x.prose.contains(&i)).unwrap().kind, UnitKind::ListItem);
    }
}

#[test]
fn units_round_trip_to_source_in_order() { /* concatenated doc.raw[source_ranges] trimmed == prose text trimmed; starts strictly increasing */ }

#[test]
fn decimals_abbreviations_ranges_and_quotes_do_not_split() {
    let (d, u) = units("FY27 needs 7.8% and 15–20% from Dr. Smith. She said “Still short.” Then left.", false);
    assert_eq!(texts(&d, &u), ["FY27 needs 7.8% and 15–20% from Dr. Smith.", "She said “Still short.”", "Then left."]);
}

#[test]
fn hard_wrap_stays_joined_and_crlf_matches_lf() {
    let (d, u) = units("This sentence wraps\nonto a second line.\n", false);
    assert_eq!(texts(&d, &u), ["This sentence wraps\nonto a second line."]);
    let kinds = |s: &str| units(s, false).1.iter().map(|x| x.kind).collect::<Vec<_>>();
    assert_eq!(kinds("Heading\nBody text.\n"), kinds("Heading\r\nBody text.\r\n"));
    let (d2, u2) = units("Heading\r\nBody text.\r\n", false);
    assert!(texts(&d2, &u2).iter().all(|t| !t.contains('\r')));
}

#[test]
fn markdown_block_kinds_drive_unit_kinds() {
    let (_, u) = units("# Title\n\n- first item\n- second item\n\nA *real* sentence.\n", true);
    assert_eq!(u.iter().map(|x| x.kind).collect::<Vec<_>>(), [UnitKind::Heading, UnitKind::ListItem, UnitKind::ListItem, UnitKind::Sentence]);
}

#[test]
fn long_uppercase_line_break_is_uncertain() {
    let (_, u) = units("Board members met for three hours on Thursday to discuss the cuts\nThey adjourned.\n", false);
    assert!(u[0].uncertain && u[0].boundary == Boundary::LineBreak);
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --lib sentences`
Expected: FAIL

- [ ] **Step 3: Implement.**
  - `boundary(kind)` records the kind for every pushed span. `prepare_markdown` passes `Heading`, `ListItem` or `TableCell` for the closing boundary of those tags, and `Paragraph` otherwise.
  - `sentence_units` reuses the existing terminal-punctuation scan per block (unchanged). Inside `Paragraph` blocks it also splits at a line break (`\r\n` or `\n`) when the line's last non-space char is `:`, or when that char is not in `.!?"”’)` and the next line's first non-space char is not lowercase. Empty lines are skipped.
  - Classify kinds:
    - A Markdown heading or list-item block takes that kind.
    - A line-break unit ending in `:` is a `Heading`.
    - A line-break unit adjacent to another line-break unit, or containing ` — `, is a `ListItem`.
    - Any other line-break unit is a `Heading`.
    - Everything else is a `Sentence`.
  - `uncertain = boundary == LineBreak && words >= 12 && kind != ListItem`.
  - Trim whitespace, including `\r`, before mapping `source_ranges`.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked --lib sentences && cargo test --locked --test bibb_fixture`
Expected: PASS, with `sentence_count` still 21

- [ ] **Step 5: Commit**

```bash
git add src/document.rs src/sentences.rs src/lib.rs
git commit -m "feat(sentences): source-mapped sentence units including headings and list lines"
```

---

### Task 3: Structure backend, sentence-level rules

**Files:**
- Modify: `src/backend.rs` (`SignalFamily::Structure`), `src/score.rs` (not voting-eligible), `src/pipeline.rs` and `src/config.rs` (register `structure` in default `enabled_backends`)
- Create: `src/backends/structure.rs`
- Modify: `src/backends/mod.rs`
- Modify: `guidance/guidance.json` (entries for every rule below), and Plan 1's coverage test to include `structure::RULE_IDS`
- Test: `src/backends/structure.rs` (`#[cfg(test)]`)

**Interfaces:**
- Consumes: `sentence_units` (Task 2), `Document::finding` (existing).
- Produces:
  - `pub struct Structure;` implementing `DetectorBackend` (name `"structure"`)
  - `pub const RULE_IDS: &[&str]`, listing every rule ID in this task and Task 4
  - Metric `structure_findings_per_1k_words` (unit `"findings/1k words"`, method `"structure-v1"`)
  - Sentence-level rule IDs and their definitions (all English, `Sentence` units only unless stated):
    - `structure.negative-parallelism`: `\bnot (just|only|merely) [^,.;]{1,60}[,;—-]+ (but|it'?s|they'?re|this is)\b`, `\bisn'?t [^,.;]{1,40}[,;—-]+ it'?s\b`, `\bnot because [^,.;]{1,60}, but because\b`. Evidence covers the match. Overlap with the dictionary rule `not-just-x-but-y` is resolved by keeping the dictionary finding and skipping the structure finding at the same start.
    - `structure.rule-of-three`: `A, B(,)? and C`, where each item is 1–3 words and none contains a digit, a capitalized non-initial word or `$`. Emit when at least 2 of the 3 items are single adjectives or abstract nouns ending in `-ity|-ness|-tion|-ment|-ance|-ence`, or all three items are adjectives from a fixed list of 40 common evaluative adjectives in `structure.rs`.
    - `structure.coordinated-series`: at least 3 comma- or `and`-coordinated segments whose first word is an `-ing` form of ≥5 letters, not preceded in its segment by a determiner (`the a an this that these those our their its`). The first segment may follow `after|before|by|while|when`. Evidence is the span from the first gerund to the last segment end.
    - `structure.significance-inflation`: phrase list (case-insensitive, word-bounded): `serves as a (testament|reminder|beacon)`, `marks a (pivotal|significant|major) (moment|step|milestone)`, `underscores the (importance|need)`, `highlights the (importance|need)`, `reflects a broader`, `stands as a`, `a (crucial|vital|pivotal) (step|role|moment)`, `in the (ever-)?(evolving|changing) (world|landscape)`.
    - `structure.copula-avoidance`: `\b(serves|stands|functions|acts) as\b` and `\bboasts\b` when the following noun phrase is ≤4 words. Low severity.
    - `structure.cheerful-opener`: the first `Sentence` unit of the document or of a paragraph that matches `^(great question|certainly|absolutely|of course|i'?d be happy to|sure thing)[!,.]`.
    - `structure.short-fragment`: a `Sentence` unit of ≤3 words. Value = words. This is an annotation: its guidance says a single fragment is fine and a pattern is the tell (see `structure.fragment-pattern` in Task 4).

- [ ] **Step 1: Write the failing tests**

```rust
#[test] fn negative_parallelism_variants() { for s in ["It isn't a budget, it's a warning.", "Not because they care, but because they must.", "This is not merely a tool; it's a shift."] { assert_eq!(count(s, "structure.negative-parallelism"), 1, "{s}"); } }
#[test] fn rule_of_three_fires_on_abstract_triads_only() {
    assert_eq!(count("We value transparency, accountability, and excellence.", "structure.rule-of-three"), 1);
    assert_eq!(count("The 2023, 2024 and 2025 budgets differ.", "structure.rule-of-three"), 0);
    assert_eq!(count("Macon, Warner Robins and Perry voted.", "structure.rule-of-three"), 0);
}
#[test] fn bibb_gerund_series_has_four_heads() { /* fixture: one coordinated-series finding; heads consolidating, freezing, packing, contracting */ }
#[test] fn determiner_led_ing_nouns_are_not_a_series() { assert_eq!(count("The building, the funding, and the staffing all lag behind.", "structure.coordinated-series"), 0); }
#[test] fn inflation_copula_and_openers() {
    assert_eq!(count("This serves as a testament to our resolve.", "structure.significance-inflation"), 1);
    assert_eq!(count("The library serves as a hub.", "structure.copula-avoidance"), 1);
    assert_eq!(count("Certainly! Here is the plan.", "structure.cheerful-opener"), 1);
    assert_eq!(count("The plan certainly helps.", "structure.cheerful-opener"), 0);
}
#[test] fn still_short_is_annotated() { /* fixture: a short-fragment finding whose matched_text is "Still short." with value 2 */ }
#[test] fn abstains_without_english() { /* Document without assert_language → ScoreOutcome::Abstained with the exact reason */ }
#[test] fn findings_round_trip_and_are_low_severity() { /* every evidence: severity Low; source text equals matched_text modulo whitespace */ }
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --lib backends::structure`
Expected: FAIL

- [ ] **Step 3: Implement.** Compile the regexes once (`std::sync::OnceLock`). Respect the deadline and candidate cap the same way `punctuation.rs` does. Write guidance entries, one per rule ID, with leverage from the category: `structure` = 2. `cheerful-opener` uses category `content` (1).

- [ ] **Step 4: Run tests**

Run: `cargo test --locked`
Expected: PASS, including `bibb_fixture` (verdict still `clean`) and Plan 1's coverage test

- [ ] **Step 5: Commit**

```bash
git add src/backend.rs src/score.rs src/pipeline.rs src/config.rs src/backends guidance/guidance.json src/guidance.rs
git commit -m "feat(structure): non-voting structural tell backend with sentence-level rules"
```

---

### Task 4: Document-level and formatting rules

**Files:**
- Modify: `src/backends/structure.rs`, `guidance/guidance.json`
- Test: `src/backends/structure.rs`

**Interfaces:**
- Produces document findings (`DocumentFinding`, plus evidence ranges where one exists):
  - `structure.summary-close`: the last paragraph's first unit starts with `in conclusion|in summary|ultimately|overall|to sum up|all in all`, or the last paragraph contains `as we (move|look) (forward|ahead)` or `the future of`. Evidence is that unit.
  - `structure.challenges-future-formula`: a heading or paragraph opening matching `challenges and (future|opportunities)|despite (these|its) challenges|looking ahead`.
  - `structure.repeated-opening`: at least 3 `Sentence` units within any 5 consecutive units whose first two lowercase words match. Evidence is the first unit.
  - `structure.fragment-pattern`: at least 3 `structure.short-fragment` units per 500 words, with at least 2 present. Message names the count.
  - `structure.uniform-paragraphs`: at least 5 paragraphs of ≥2 sentences each whose word-count CV is < 0.25.
  - `structure.bold-inline-headers` (Markdown only): at least 3 paragraphs or list items whose prose starts with strong-emphasis text ending in `:`. Requires recording the strong-emphasis start offsets during Markdown preparation, as `Document.strong_spans: Vec<Range<usize>>`.
  - `structure.title-case-headings`: at least 3 headings in which every word of ≥4 letters is capitalized and the headings are at least 3 words long.
  - `structure.list-heavy` (Markdown only): list-item words exceed 50% of prose words, and at least 60% of the list items are full sentences (end in `.!?`).
  - Context annotation, not a rule: punctuation evidence inside a `ListItem` unit gets `Evidence.context = Some("list_separator")` (new optional field, skipped when `None`). The em-dash guidance `keep_when` names this case, and `review` shows it.

- [ ] **Step 1: Write failing tests,** one per rule with a minimal positive and a near-miss negative. Also:
  - `code_block_contents_never_fire`: a fenced block containing `In conclusion` and `**Bold:**` produces no findings.
  - `bibb_list_dashes_are_list_separators`: all 9 punctuation evidence items have `context == "list_separator"`.

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --lib backends::structure`
Expected: FAIL

- [ ] **Step 3: Implement.** Add guidance entries: `bold-inline-headers`, `title-case-headings` and `list-heavy` are category `formatting`; the rest are `structure`.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backends/structure.rs src/document.rs src/score.rs guidance/guidance.json
git commit -m "feat(structure): document-level and formatting tells; list-separator context"
```

---

### Task 5: Review integration

**Files:**
- Modify: `src/review.rs` (Plan 1)
- Test: `tests/review.rs`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces:
  - `ReviewFinding.sentence` is filled from the containing unit's text.
  - `ReviewFinding.context: Option<String>` passes through `Evidence.context`.
  - Checklist `sentence-length-varies` uses `Sentence` units (headings and list items excluded).
  - New checklist ids: `no-summary-close`, `no-rule-of-three`.
  - Findings with `context == "list_separator"` sort after other leverage-4 findings and show `keep_when` first in human output.

- [ ] **Step 1: Write failing tests**
  - `bibb_review_puts_structure_before_vocabulary_and_marks_list_dashes`: `review` on the fixture lists `structure.coordinated-series` before any punctuation finding. Every em-dash finding has `context: "list_separator"`, and `sentence-length-varies` is computed over the non-heading, non-list units.
  - `summary_close_checklist`: text ending "In conclusion, budgets matter." fails `no-summary-close`.

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test review`
Expected: FAIL

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run tests**

Run: `cargo test --locked`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/review.rs tests/review.rs
git commit -m "feat(review): structure findings, sentence context and list-separator handling"
```

---

### Task 6: Snapshot and docs

**Files:**
- Create: `tests/fixtures/review/bibb-fy27.json` (generated)
- Modify: `tests/review.rs` (snapshot, regenerated with `NOBOTRS_UPDATE_SNAPSHOTS=1`)
- Modify: `docs/rule-catalog.md` (every `structure.*` rule: definition, severity low, non-voting, known false positives, guidance id)

- [ ] **Step 1: Write the snapshot test.** Compare `review --language en --format json` on the fixture, minus `path`, to the snapshot as parsed `serde_json::Value`.
- [ ] **Step 2: Generate and read it**

Run: `NOBOTRS_UPDATE_SNAPSHOTS=1 cargo test --locked --test review snapshot`
Expected: the file is written. A human confirms that the coordinated series, the "Still short." annotation and the nine list-separator dashes appear with source locations, and that no finding has empty `fix`.

- [ ] **Step 3: Full verification**

Run: `cargo test --locked && cargo test --locked --features api-clients && cargo clippy --locked --all-targets -- -D warnings`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/review tests/review.rs docs/rule-catalog.md
git commit -m "docs(structure): catalog structural rules and snapshot fixture review"
```
