# Humanize 3: Revision Loop and Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agent revise a draft safely and know when to stop. `nobotrs compare BEFORE AFTER` reports which tells were removed, kept or introduced and whether facts survived. Two skills teach the drafting and revising workflows with explicit stop criteria.

### Implemented command contract

Run `nobotrs compare before.md after.md --language en --format json`. The report includes removed, retained and introduced findings, missing and added invariants, and a checklist. Confirm an intentional removal with the exact `--accept-missing 'kind=text'` value. Missing numbers, quotes, code and links affect the exit code. Changes to names, qualifications and subject–value associations require source review. Matching the extracted facts cannot establish that a rewrite preserved meaning. The drafting and revision skills carry standalone guidance and a stop condition based on the author’s purpose and factual fidelity.

**Architecture:**
- `src/cli/invariants.rs` extracts checkable facts from prepared prose.
- `src/cli/compare.rs` runs the `review` pipeline (Plan 1) on both texts, diffs findings and metrics, and checks invariants.
- Skills under `skills/` drive `guide`, `review` and `compare`.
- The existing advisory hook switches from `lint` to `review` and never blocks.

**Tech Stack:** Rust 2021 (`regex`, `serde_json`), Python 3 stdlib for the hook, Markdown skills in the skills.sh layout already used by `skills/nobotrs/`.

**Spec:** `docs/superpowers/plans/2026-11-21-humanize-roadmap.md`. Depends on Plan 1 (`review`, guidance). It uses Plan 2's structure findings and sentence units when present, and runs without them.

## Global Constraints

- `compare` exits 0 when complete with no missing hard invariant, 1 when any hard invariant from BEFORE is missing in AFTER, and 2 on error.
- Hard invariant kinds (exact): `number`, `url`, `quote`, `code`. The soft kind is `name`.
- Facts added in AFTER that were not in BEFORE (hard or soft) are never silently accepted. They are listed under `added` with `status: "confirm_source"`, and they make the `facts-are-real` checklist item `fail`. The skills tell agents to confirm such facts with the writer or remove them.
- Matching tells across versions uses the `(rule_id, normalized matched_text)` multiset, with normalization = lowercase plus collapsed whitespace. Positions are not used, because edits move text.
- No skill may instruct iterating against GPTZero, OpenRouter or any model score. An external check is allowed once, at the end, only if the user asked for it, and is reported as a second opinion.
- Stop criteria (exact wording reused in both skills):
  1. No active leverage-1 or leverage-2 findings remain, or each remaining one is covered by its `keep_when`.
  2. `compare` exits 0 and `added` is empty or confirmed by the writer.
  3. The read-aloud pass is done.
  4. At most 3 revision passes. Then stop and report what remains.

## Review Focus

- "$1.25M" in BEFORE and "$1.25 million" in AFTER must count as the same number, not as one missing and one added. Test in Task 1.
- A quotation re-punctuated from curly to straight quotes must still match. Test in Task 1.
- A revision that moves a paragraph without changing it must report every tell as `kept`, none removed or introduced. Test in Task 2.
- BEFORE and AFTER in different formats (`.md` and `.txt`) must each be prepared by their own extension. Test in Task 2.
- The hook must exit 0 and stay silent when `nobotrs` is missing or times out (advisory silence with a diagnostic on stderr), matching current behaviour. Test in Task 4.

---

### Task 1: Fact invariants

**Files:**
- Create: `src/cli/invariants.rs`
- Modify: `src/lib.rs`
- Test: `src/cli/invariants.rs` (`#[cfg(test)]`)

**Interfaces:**
- Produces:
  - `pub enum InvariantKind { Number, Url, Quote, Code, Name }` (serde snake_case); `pub fn is_hard(self) -> bool` (all except `Name`)
  - `pub struct Invariant { pub kind: InvariantKind, pub text: String, pub normalized: String, pub source_ranges: Vec<Range<usize>> }`
  - `pub fn extract(doc: &Document) -> Vec<Invariant>`
  - `pub fn diff(before: &[Invariant], after: &[Invariant]) -> (Vec<Invariant>, Vec<Invariant>)`, returning `(missing_in_after, added_in_after)` as multiset differences on `(kind, normalized)`
- Normalization:
  - **number:** strip `,` and `~`; map `k`/`thousand` → `e3`, `M`/`million` → `e6`, `B`/`billion` → `e9`, `percent` → `%`; keep `$`; the fiscal-year form `FY27` stays as is; ranges `15–20%` become `15-20%`.
  - **quote:** straight quotes, collapsed whitespace, lowercase, only quotes of ≥2 words.
  - **url:** lowercase scheme and host, drop the trailing `/`.
  - **code:** exact (Markdown inline code only, captured during preparation as `Document.code_spans`).
  - **name:** a sequence of ≥2 capitalized words not at a unit start, or a single capitalized word that appears ≥2 times not at unit starts.

- [ ] **Step 1: Write the failing tests**

```rust
#[test] fn money_forms_normalize_equal() { assert_eq!(norm_numbers("~$1.25M and $8 million"), norm_numbers("$1.25 million and $8M")); }
#[test] fn bibb_numbers_are_extracted() {
    let d = en_fixture();
    let n: Vec<_> = extract(&d).into_iter().filter(|i| i.kind == InvariantKind::Number).map(|i| i.normalized).collect();
    for want in ["7.8%", "$23e6", "15-20%", "$15.8e6", "$8e6", "FY27"] { assert!(n.contains(&want.to_string()), "{want}"); }
}
#[test] fn curly_and_straight_quotes_match() { let (m, a) = diff(&ex("He said “we are short.”"), &ex("He said \"we are short.\"")); assert!(m.is_empty() && a.is_empty()); }
#[test] fn dropped_and_added_facts_are_reported() {
    let (m, a) = diff(&ex("The gap is $8 million, says James Freeman."), &ex("The gap is large, says Henderson Smith."));
    assert!(m.iter().any(|i| i.kind == InvariantKind::Number) && m.iter().any(|i| i.kind == InvariantKind::Name));
    assert!(a.iter().any(|i| i.kind == InvariantKind::Name && i.text == "Henderson Smith"));
}
#[test] fn urls_and_inline_code() { /* Markdown: `cargo test` and https://Example.com/ survive as code and url "https://example.com" */ }
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --lib invariants`
Expected: FAIL

- [ ] **Step 3: Implement.** Extract from `doc.prose` with regexes compiled once, and map ranges via `doc.source_ranges`. Record `code_spans` in `prepare_markdown` at `Event::Code` (prose stays excluded).

- [ ] **Step 4: Run tests**

Run: `cargo test --locked --lib invariants`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/invariants.rs src/lib.rs src/document.rs
git commit -m "feat(invariants): extract and diff numbers, quotes, urls, code and names"
```

---

### Task 2: `nobotrs compare`

**Files:**
- Create: `src/cli/compare.rs`
- Modify: `src/lib.rs`, `src/cli/mod.rs` (`Command::Compare { before: PathBuf, after: PathBuf }`; `-` allowed for at most one side; rejects external flags)
- Test: `tests/compare.rs`, `tests/fixtures/revision/` (`before.md`, `good-after.md`, `drops-number.md`, `adds-name.md`, `moved-paragraph.md`)

**Interfaces:**
- Consumes: `review::review` (Plan 1), `invariants` (Task 1).
- Produces:
  - `pub struct TellDelta { pub rule_id: String, pub guidance_id: String, pub leverage: u8, pub matched_text: String, pub before: usize, pub after: usize }`
  - `pub struct MetricDelta { pub name: String, pub before: Option<f64>, pub after: Option<f64> }`, for `sentence_length_cv`, `em_dashes_per_100_words`, `mtld`, `flesch_kincaid_grade` and `prose_words`
  - `pub struct AddedFact { pub invariant: Invariant, pub status: &'static str }` (`"confirm_source"`)
  - `pub struct CompareReport { pub schema_version: &'static str, pub compare_version: &'static str, pub before: String, pub after: String, pub complete: bool, pub removed: Vec<TellDelta>, pub kept: Vec<TellDelta>, pub introduced: Vec<TellDelta>, pub leverage_before: BTreeMap<u8, usize>, pub leverage_after: BTreeMap<u8, usize>, pub metrics: Vec<MetricDelta>, pub missing: Vec<Invariant>, pub added: Vec<AddedFact>, pub checklist_after: Vec<CheckItem> }`, with `compare_version` = `"compare-v1"`
  - `pub fn compare(before: (&Report, &Document), after: (&Report, &Document)) -> CompareReport`
  - Human output: `Removed N tells (by leverage …), kept M, introduced K`, then the missing facts (prefixed `MISSING`), the added facts (prefixed `CONFIRM`), the metric deltas and the after-checklist.

- [ ] **Step 1: Write the failing tests**

```rust
#[test] fn good_revision_removes_tells_and_keeps_facts() {
    let (code, v) = compare_json("tests/fixtures/revision/before.md", "tests/fixtures/revision/good-after.md");
    assert_eq!(code, 0);
    assert!(v["removed"].as_array().unwrap().iter().any(|t| t["leverage"].as_u64().unwrap() <= 2));
    assert_eq!(v["missing"].as_array().unwrap().len(), 0);
    assert_eq!(v["compare_version"], "compare-v1");
}
#[test] fn dropped_number_exits_1() { assert_eq!(compare_json(BEFORE, "tests/fixtures/revision/drops-number.md").0, 1); }
#[test] fn added_name_needs_confirmation() {
    let (code, v) = compare_json(BEFORE, "tests/fixtures/revision/adds-name.md");
    assert_eq!(code, 0);
    assert_eq!(v["added"][0]["status"], "confirm_source");
    let f = v["checklist_after"].as_array().unwrap().iter().find(|c| c["id"] == "facts-are-real").unwrap().clone();
    assert_eq!(f["status"], "fail");
}
#[test] fn moved_paragraph_keeps_everything() {
    let (_, v) = compare_json(BEFORE, "tests/fixtures/revision/moved-paragraph.md");
    assert!(v["removed"].as_array().unwrap().is_empty() && v["introduced"].as_array().unwrap().is_empty());
}
#[test] fn mixed_formats_and_stdin() { /* before.md vs a .txt rendering of good-after; and `compare - after.md` with stdin */ }
```

The fixtures are short (≤250 words) civic paragraphs written for the test. `before.md` contains a coordinated series, a negative parallelism, a rule-of-three, "$8 million", a quote and a named person. `good-after.md` is a careful human-style revision that keeps every fact.

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test compare`
Expected: FAIL (unknown subcommand)

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run tests**

Run: `cargo test --locked && cargo clippy --locked --all-targets -- -D warnings`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/compare.rs src/lib.rs src/cli/mod.rs tests/compare.rs tests/fixtures/revision
git commit -m "feat(compare): tell and fact-invariant diff between draft versions"
```

---

### Task 3: Skills

**Files:**
- Create: `skills/humanize-writing/SKILL.md` (drafting from scratch)
- Create: `skills/review-writing/SKILL.md` (revising an existing draft)
- Modify: `skills/nobotrs/SKILL.md` (CLI reference; points to the two skills)
- Modify: `README.md` (install all three with `npx skills add . --skill <name>`)
- Test: `tests/skills.rs`

**Interfaces:**
- Content requirements:
  - **humanize-writing** (trigger: long-form prose for people):
    1. Run `nobotrs guide` and read it before drafting.
    2. Collect the writer's real facts first (ask if missing).
    3. Draft by leverage priorities.
    4. Run `nobotrs review draft.md --language en --format json`.
    5. Fix leverage 1–2 findings.
    6. Apply the stop criteria.
    7. Run the read-aloud pass.
  - **review-writing** (trigger: "make this sound less like AI", "edit this draft", "review this post"):
    1. Copy the original to `<name>.before.<ext>`.
    2. Run `review`.
    3. Plan edits by leverage, starting with a real rewrite of the worst section rather than word swaps.
    4. Edit.
    5. Run `nobotrs compare <name>.before.<ext> <name>.<ext> --language en`.
    6. Resolve any `MISSING` (restore) and `CONFIRM` (ask the writer, or remove).
    7. Loop until the stop criteria are met.
    8. Report removed and kept tells, and the facts confirmed.
  - Both carry the stop criteria verbatim, the "never fabricate" rule, the "don't iterate against detector scores" rule, and one line on search: "Google rewards original, helpful content and penalizes scaled low-value content and fabricated authorship; the same edits that help readers help search."

- [ ] **Step 1: Write the failing test**

```rust
#[test]
fn skills_reference_real_commands_and_share_stop_criteria() {
    let stop = include_str!("../skills/review-writing/SKILL.md").split("## When to stop").nth(1).unwrap().split("\n## ").next().unwrap().trim().to_string();
    for path in ["skills/humanize-writing/SKILL.md", "skills/review-writing/SKILL.md", "skills/nobotrs/SKILL.md"] {
        let text = std::fs::read_to_string(path).unwrap();
        assert!(text.starts_with("---\nname: ") && text.contains("\ndescription: "), "{path}");
        for cap in regex::Regex::new(r"`nobotrs ([a-z-]+)").unwrap().captures_iter(&text) {
            assert!(run(&[&cap[1], "--help"]).status.success(), "{path}: nobotrs {}", &cap[1]);
        }
        if !path.ends_with("nobotrs/SKILL.md") { assert!(text.contains(&stop), "{path} stop criteria differ"); }
        for banned in ["lived experience", "temperature", "until the detector", "lower the score"] { assert!(!text.contains(banned), "{path}: {banned}"); }
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test skills`
Expected: FAIL (files missing)

- [ ] **Step 3: Write the skills.** Port the useful parts of the `nobots` `humanize-writing` skill (`/mnt/storage/projects/nobotrs/docs/internal/nobot-python/main/skills/humanize-writing/SKILL.md`): the leverage order, the tone shifts across sections and the pre-send checklist. Leave out the decoding-settings advice and the invented-specifics wording. Keep each file under 150 lines and point to `nobotrs guide --format json` for the full entries.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked --test skills`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills README.md tests/skills.rs
git commit -m "feat(skills): humanize-writing and review-writing agent workflows"
```

---

### Task 4: Advisory hook on `review`

**Files:**
- Modify: `scripts/advisory-hook.py`
- Create: `scripts/test_advisory_hook.py` (unittest, with a stub `nobotrs` on `PATH`)
- Modify: `docs/superpowers/plans/2026-07-26-nobotrs-plugin-packaging.md` (Task 4: the hook calls `review --format json`, not `detect`; record the reason)

**Interfaces:**
- Behaviour:
  - Read stdin (≤1,048,577 bytes as now) and run `nobotrs review - --format json` with a 10 s timeout.
  - If any active finding has `leverage <= 2`, print a nudge of at most 6 lines: `nobotrs: N high-leverage writing patterns; top: <rule_id> at line L — <fix first sentence>` for up to 3 findings, then `Run the review-writing skill to revise.` Exit 2, the host's non-blocking feedback code, as the current adapter does for findings.
  - Otherwise stay silent and exit 0.
  - If the binary is missing, times out, or `review` exits 2, print a diagnostic on stderr and exit 0.

- [ ] **Step 1: Write the failing tests:** `test_nudges_on_high_leverage`, `test_silent_on_vocabulary_only` (leverage-5 findings produce no nudge), `test_missing_binary_is_silent_exit_0` and `test_timeout_is_silent_exit_0`.

- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_advisory_hook.py`
Expected: FAIL

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run tests**

Run: `python3 scripts/test_advisory_hook.py && python3 scripts/acceptance.py --skip-package`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/advisory-hook.py scripts/test_advisory_hook.py docs/superpowers/plans/2026-07-26-nobotrs-plugin-packaging.md
git commit -m "feat(hook): nudge on high-leverage review findings only"
```
