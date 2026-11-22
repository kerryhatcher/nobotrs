# Humanize 1: Guidance Core Implementation Plan

## Reconciled implementation contract (2026-11-21)

The revised roadmap overrides the historical task details below. Implementation is single-agent within the assigned scope. Guidance and its brief ship together in the Cargo archive. Guide JSON retains the legacy `guide` field and adds canonical data with serialized leverage. Review uses unsliced suppressed outcomes, computes counts/checklists before limiting once, and emits one logical finding with an optional location. Document metrics retain their messages and have no invented coordinates. Review rejects SARIF and external services.

Structure runs only in editorial analysis (`review` and the shared compare API), even though it is a configurable backend. Legacy detect/lint/analyze/scan execution and budgets remain unchanged. All structure observations are low severity and non-voting, require asserted English, and are unvalidated for editorial usefulness. A short-unit annotation is not a grammar judgment. Deliberate repetition, dialogue and factual lists may be retained.

Editorial units carry normalized display text separately from original UTF-8 navigation ranges. Statistical sentence segmentation is unchanged. Markdown ancestry preserves list identity through loose/nested items and inline-code gaps. Equivalent dictionary/structure contrasts are reconciled by overlapping ranges after suppression, with the active dictionary match taking precedence. Disabled, abstained and incomplete checks remain visible and cannot imply a passing checklist item.

The tests in `tests/guidance.rs`, `tests/review.rs`, `tests/bibb_fixture.rs` and unit modules implement the corrected examples (valid suppression syntax and Markdown code-only input). Package verification must install from an extracted archive and run its guidance, review and fixture tests. Skills and evaluation are owned separately; this implementation does not mark their tasks complete.

---

**Goal:** Give agents one canonical, machine-readable guidance set linked to every rule ID, reconcile the writing guides around reader-first quality, and add an advisory `nobotrs review` command that returns findings ordered by leverage, each with why, fix and keep-when.

**Architecture:**
- An embedded JSON guidance file (`guidance/guidance.json`), loaded by `src/guidance.rs`, maps rule IDs to guidance entries with a category and a leverage rank.
- `lint` JSON gains two additive fields per finding.
- A new `review` subcommand reuses the existing pipeline. It collects selected candidates from every scored backend, joins guidance, sorts by leverage, evaluates an automatable pre-send checklist, and exits 0 on completed analysis.
- `guide` gains a structured JSON form, and its human form becomes the agent brief.

**Tech Stack:** Rust 2021, `serde`/`serde_json`, `clap`, `include_str!` embedding (as `dictionary/entries.json` already is).

**Spec:** `docs/superpowers/plans/2026-11-21-humanize-roadmap.md`

## Global Constraints

- Reader first. No guidance text may advise inventing experience, personas, credentials, names, sources or numbers, maximum temperature, or detector evasion as a goal. Specificity means using the writer's real facts, or asking for them. When none exist, cut the generic claim.
- `lint`, `detect`, `analyze`, `scan`, quorum, thresholds, verdicts and exit codes are unchanged. `lint` JSON changes only additively. SARIF is byte-identical.
- Leverage values (exact): `content` 1, `structure` 2, `rhythm` 3, `punctuation` 4, `formatting` 4, `vocabulary` 5.
- Every rule ID nobotrs can emit maps to exactly one guidance entry: the 46 dictionary IDs, `punctuation.em-dash-density`, `statistics.burstiness`, and later the `structure.*` IDs from Plan 2. A test enforces this.
- Version strings: guidance file `schema_version` `"1.0.0"`, `guidance_version` `"2026.11.21"`; review output `review_version` `"review-v1"`.
- `review` exits 0 when complete, 2 on operational error or incomplete analysis, and never 1 or 3.
- Google's documented position is quoted with links to Search Central (`developers.google.com/search/docs/fundamentals/using-gen-ai-content`, `…/creating-helpful-content`, and the March 2024 spam-policies post), not to SEO blogs.

## Review Focus

- A rule ID with no guidance entry, added later by a dictionary update, must fail the coverage test rather than ship a finding with null guidance. Test in Task 1.
- `review` on stdin Markdown (`review - --markdown`) must report Markdown source locations. Test in Task 4.
- `review` on empty or code-only input must exit 0 with `findings: []` and every checklist item `not_applicable`, not exit 3. Test in Task 4.
- A suppressed finding (`nobotrs-ignore-next-line`) must appear in `review` as `suppressed: true` and sort after the active findings, not vanish silently. Test in Task 4.
- `review` must not send text anywhere even when `gptzero` or `openrouter_judge` is set in config. External flags are rejected for `review` as they are for `lint`. Test in Task 4.

---

### Task 1: Guidance schema, data and loader

**Files:**
- Create: `guidance/guidance.json`, `guidance/README.md` (authoring rules: the constraints above, the leverage scale, sources required, `time_bound` meaning)
- Create: `src/guidance.rs`
- Modify: `src/lib.rs`
- Test: `src/guidance.rs` (`#[cfg(test)]`)

**Interfaces:**
- Produces:
  - `pub enum Category { Content, Structure, Rhythm, Punctuation, Formatting, Vocabulary }` (serde snake_case), with `pub fn leverage(self) -> u8` returning the constraint values above
  - `pub struct Example { pub before: String, pub after: String }`
  - `pub struct GuidanceEntry { pub id: String, pub rules: Vec<String>, pub category: Category, pub title: String, pub why: String, pub fix: String, pub keep_when: String, pub examples: Vec<Example>, pub sources: Vec<String>, pub time_bound: bool }`
  - `pub struct Guidance { pub schema_version: String, pub guidance_version: String, pub brief: String, pub entries: Vec<GuidanceEntry> }`
  - `impl Guidance { pub fn embedded() -> &'static Guidance; pub fn for_rule(&self, rule_id: &str) -> Option<&GuidanceEntry>; pub fn validate(&self) -> Result<(), String> }`
  - `brief` is the agent brief text (Task 2 writes it). It is stored in `guidance/brief.md` and embedded through `include_str!` from `Guidance::embedded`, not inline in the JSON.
- Initial entries (ids exact; `rules` lists every rule ID they cover):
  - `content.vague-attribution` (`studies-show`, `experts-agree`), category content
  - `structure.negative-parallelism` (`not-just-x-but-y`), structure
  - `structure.signposting-filler` (`important-to-note`, `worth-noting`, `heres-the-thing`, `let-me-be-clear`, `uncomfortable-truth`, `thats-it-thats-the-x`), structure
  - `structure.significance-inflation` (`cannot-be-overstated`, `a-testament-to`, `plays-a-role`, `rapidly-evolving`, `embark-on-a-journey`, `paradigm-shift`), structure
  - `rhythm.uniform-sentence-length` (`statistics.burstiness`), rhythm
  - `punctuation.em-dash-connectors` (`punctuation.em-dash-density`), punctuation
  - `vocabulary.tell-word` (the remaining 31 single-word IDs), vocabulary, `time_bound: true`

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn embedded_guidance_validates() { Guidance::embedded().validate().unwrap(); }

#[test]
fn every_emittable_rule_has_exactly_one_entry() {
    let g = Guidance::embedded();
    let mut ids: Vec<String> = crate::dictionary::Dictionary::embedded().entries.iter().map(|e| e.id.clone()).collect();
    ids.extend(["punctuation.em-dash-density".into(), "statistics.burstiness".into()]);
    for id in &ids {
        let n = g.entries.iter().filter(|e| e.rules.contains(id)).count();
        assert_eq!(n, 1, "rule {id} covered {n} times");
    }
}

#[test]
fn leverage_scale_is_fixed() {
    use Category::*;
    assert_eq!([Content, Structure, Rhythm, Punctuation, Formatting, Vocabulary].map(Category::leverage), [1, 2, 3, 4, 4, 5]);
}

#[test]
fn no_entry_advises_fabrication_or_evasion() {
    // Phrases that only occur in fabrication or evasion advice. "never invent" style warnings are allowed.
    let banned = ["lived experience", "temperature", "evade", "bypass", "fool the detector", "adopt a persona", "make up a"];
    for e in &Guidance::embedded().entries {
        let text = format!("{} {} {}", e.why, e.fix, e.keep_when).to_lowercase();
        for b in banned { assert!(!text.contains(b), "{}: {b}", e.id); }
    }
}

#[test]
fn entries_are_complete() {
    for e in &Guidance::embedded().entries {
        assert!(!e.why.is_empty() && !e.fix.is_empty() && !e.keep_when.is_empty() && !e.examples.is_empty() && !e.sources.is_empty(), "{}", e.id);
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --lib guidance`
Expected: FAIL (module not found)

- [ ] **Step 3: Write the data and the loader.** The content comes from the `nobots` `humanize-writing` skill, the "Practical implications" and structural sections of `ai-writing-signatures-evolution.md`, and `docs/ai-writing-guide.md`, filtered through the Global Constraints. Each `keep_when` names a real legitimate use: for example, `robust` as a statistics term, an em dash in a list separator, "studies show" followed immediately by a named study. `validate` checks for unique IDs, that every `rules` entry is non-empty, and that `schema_version == "1.0.0"`.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked --lib guidance`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add guidance src/guidance.rs src/lib.rs
git commit -m "feat(guidance): add canonical rule-linked guidance data with leverage ranks"
```

---

### Task 2: Reconcile the writing guides

**Files:**
- Create: `guidance/brief.md` (the agent brief, ≤120 lines)
- Modify: `docs/writing-guide.md` (becomes a pointer to the brief plus the existing editing principles)
- Modify: `docs/ai-writing-guide.md` (the "Practical instructions for producing genuinely human text" section only; the research sections are untouched)
- Modify: `src/cli/mod.rs` (`guide` prints `brief`; `guide --format json` returns `{schema_version, guidance_version, brief, entries}`)
- Test: `tests/guidance.rs`

**Interfaces:**
- Consumes: `Guidance::embedded()` (Task 1).
- Produces: the `brief` has these exact H2 sections, in order: `## Before you write`, `## While you write`, `## Revising an existing draft`, `## When to stop`, `## Reader-first and search`, `## Never do this`. The `## Never do this` section lists fabricated experience, persona, credentials, sources, names and numbers, and iterating against a detector score.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn guide_human_is_the_brief_with_required_sections() {
    let out = run(&["guide"]);
    let text = String::from_utf8(out.stdout).unwrap();
    let order = ["## Before you write", "## While you write", "## Revising an existing draft", "## When to stop", "## Reader-first and search", "## Never do this"];
    let pos: Vec<_> = order.iter().map(|h| text.find(h).unwrap_or_else(|| panic!("missing {h}"))).collect();
    assert!(pos.windows(2).all(|w| w[0] < w[1]));
    assert!(text.contains("developers.google.com/search"));
}

#[test]
fn guide_json_carries_entries() {
    let v = json(&["guide", "--format", "json"]);
    assert_eq!(v["guidance_version"], "2026.11.21");
    assert!(v["entries"].as_array().unwrap().len() >= 7);
    assert!(v["brief"].as_str().unwrap().starts_with("# "));
}

#[test]
fn field_guide_practical_section_has_no_fabrication_advice() {
    let g = include_str!("../docs/ai-writing-guide.md");
    let practical = &g[g.find("## Practical instructions").unwrap()..g.find("## Detector advances").unwrap()];
    for bad in ["Henderson's place", "Set temperature to maximum", "persona with lived experience", "avoid curly quotation marks"] {
        assert!(!practical.contains(bad), "{bad}");
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test guidance`
Expected: FAIL

- [ ] **Step 3: Write the brief and edit the guides.**
  - **Fragments:** say that one punchy fragment for emphasis is fine and that a pattern of them is a current tell. GPTZero ranked "Still short." in the fixture third.
  - **Specificity:** use the writer's real facts, or ask for them.
  - **Search section:** state Google's documented position (people-first, original, E-E-A-T; scaled content abuse; no fabricated creator details; disclosure encouraged) with Search Central links. Add that the same edits that serve readers serve search.
  - **Generation settings:** replace the "maximum temperature" advice with "decoding settings change surface statistics, not substance; revise instead".
  - Update the `ai-writing-guide` byte-equality assertion in `tests/cli_smoke.rs` only if it compares against a copied string (it uses `include_str!`, so it should pass unchanged).

- [ ] **Step 4: Run tests**

Run: `cargo test --locked --test guidance --test cli_smoke`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add guidance/brief.md docs/writing-guide.md docs/ai-writing-guide.md src/cli/mod.rs src/guidance.rs tests/guidance.rs
git commit -m "docs(guidance): reader-first agent brief; remove fabrication and evasion advice"
```

---

### Task 3: Guidance on lint findings

**Files:**
- Modify: `src/score.rs` (`Evidence` gains `guidance_id: Option<String>` and `leverage: Option<u8>`, both `skip_serializing_if = "Option::is_none"`)
- Modify: `src/pipeline.rs` (fill both after scoring, from `Guidance::embedded().for_rule`)
- Modify: `src/output.rs` (human lint line appends ` (leverage N)`; SARIF unchanged)
- Test: `tests/guidance.rs`

**Interfaces:**
- Consumes: Task 1.
- Produces: every serialized `Evidence` from a known rule carries `guidance_id` and `leverage`.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn lint_findings_carry_guidance() {
    let v = json_stdin(&["lint", "-", "--format", "json"], b"Studies show we must delve into robust solutions.");
    let ev: Vec<_> = all_evidence(&v);
    let by = |id: &str| ev.iter().find(|e| e["rule_id"] == id).unwrap().clone();
    assert_eq!(by("studies-show")["guidance_id"], "content.vague-attribution");
    assert_eq!(by("studies-show")["leverage"], 1);
    assert_eq!(by("delve")["leverage"], 5);
}

#[test]
fn sarif_is_unchanged_by_guidance() {
    let s = run_stdin(&["lint", "-", "--format", "sarif"], b"Studies show we must delve.");
    assert!(!String::from_utf8_lossy(&s.stdout).contains("guidance_id"));
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test guidance lint_findings_carry_guidance`
Expected: FAIL

- [ ] **Step 3: Implement.** Do the join in one place in the pipeline, after backends return, over both `evidence` and `candidates`.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked`
Expected: PASS (all existing tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/score.rs src/pipeline.rs src/output.rs tests/guidance.rs
git commit -m "feat(lint): attach guidance id and leverage to findings"
```

---

### Task 4: `nobotrs review`

**Files:**
- Create: `src/review.rs`
- Modify: `src/lib.rs`, `src/cli/mod.rs` (`Command::Review` with the same path/stdin handling as `lint`; rejects `--gptzero` and `--openrouter-judge`)
- Test: `tests/review.rs`

**Interfaces:**
- Consumes: the pipeline `Report` (existing), Task 1.
- Produces:
  - `pub struct ReviewFinding { pub rule_id: String, pub guidance_id: String, pub category: Category, pub leverage: u8, pub severity: Severity, pub suppressed: bool, pub line: u32, pub column: u32, pub end_line: u32, pub end_column: u32, pub source_ranges: Vec<Range<usize>>, pub matched_text: String, pub sentence: Option<String>, pub suggestion: Option<String>, pub why: String, pub fix: String, pub keep_when: String }`
  - `pub enum CheckStatus { Pass, Fail, Unknown, NotApplicable }`; `pub struct CheckItem { pub id: &'static str, pub status: CheckStatus, pub detail: String }`
  - `pub struct ReviewReport { pub schema_version: &'static str, pub review_version: &'static str, pub path: String, pub guidance_version: String, pub complete: bool, pub prose_words: usize, pub leverage_counts: BTreeMap<u8, usize>, pub findings: Vec<ReviewFinding>, pub document: Vec<ReviewFinding>, pub checklist: Vec<CheckItem> }`
  - `pub fn review(report: &Report, doc: &Document) -> ReviewReport`
  - Checklist ids, in order:
    - `no-tell-vocabulary`: fail if any active vocabulary-category finding remains.
    - `no-em-dash-connectors`: fail if em-dash density is flagged.
    - `sentence-length-varies`: fail if any 3 consecutive sentences have word counts within ±3 of each other. Plan 2 switches this to sentence units.
    - `has-checkable-specific`: pass if there is at least one digit-bearing token or a month name followed by a day or year.
    - `no-vague-attribution`
    - `no-negative-parallelism`
    - `facts-are-real`: always `Unknown`, with the detail "confirm every name, number and source is the writer's own".
    - `read-aloud`: always `Unknown`.
    - `tone-shifts`: always `Unknown`.
  - Ordering: active findings by `(leverage, raw_offset.start)`, then suppressed findings in the same order. Document-level findings (burstiness) go in `document`.
  - Human output: one header line, then the `leverage_counts`, then findings grouped under `Leverage 1 — content`, and so on, each finding with its fix. Then the checklist as `[pass] id`.

- [ ] **Step 1: Write the failing tests**

```rust
#[test]
fn review_orders_by_leverage_and_explains() {
    let v = json_stdin(&["review", "-", "--language", "en", "--format", "json"],
        b"We must delve into this. Studies show it matters. It's not just a tool, it's a shift.");
    let lev: Vec<u64> = v["findings"].as_array().unwrap().iter().map(|f| f["leverage"].as_u64().unwrap()).collect();
    assert!(lev.windows(2).all(|w| w[0] <= w[1]));
    assert_eq!(v["findings"][0]["rule_id"], "studies-show");
    assert!(!v["findings"][0]["fix"].as_str().unwrap().is_empty());
    assert_eq!(v["review_version"], "review-v1");
}

#[test]
fn review_is_advisory() {
    let o = run_stdin(&["review", "-"], b"We must delve into robust, seamless synergy.");
    assert_eq!(o.status.code(), Some(0));
}

#[test]
fn empty_input_is_not_applicable() {
    let v = json_stdin(&["review", "-", "--format", "json"], b"```\ncode\n```\n");
    assert_eq!(v["findings"].as_array().unwrap().len(), 0);
    assert!(v["checklist"].as_array().unwrap().iter().all(|c| c["status"] == "not_applicable"));
}

#[test]
fn suppressed_findings_sort_last_and_are_marked() {
    let v = json_stdin(&["review", "-", "--markdown", "--format", "json"],
        b"<!-- nobotrs-ignore-next-line -->\nWe delve.\n\nStudies show robust gains.\n");
    let f = v["findings"].as_array().unwrap();
    assert_eq!(f.last().unwrap()["suppressed"], true);
    assert_eq!(f.last().unwrap()["line"], 2);
}

#[test]
fn checklist_specific_and_external_rejection() {
    let v = json_stdin(&["review", "-", "--format", "json"], b"The levy rose 1.7 mills on June 2.");
    let c = v["checklist"].as_array().unwrap().iter().find(|c| c["id"] == "has-checkable-specific").unwrap().clone();
    assert_eq!(c["status"], "pass");
    assert_eq!(run_stdin(&["review", "-", "--gptzero"], b"x").status.code(), Some(2));
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test review`
Expected: FAIL (unknown subcommand)

- [ ] **Step 3: Implement.** Run the same pipeline as `analyze` with `minimum_severity` forced to `Low` (unless the user passed one explicitly) and `quorum` irrelevant. Build the `ReviewReport`, then map completion to exit 0/2.

- [ ] **Step 4: Run tests**

Run: `cargo test --locked && cargo clippy --locked --all-targets -- -D warnings`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/review.rs src/lib.rs src/cli/mod.rs tests/review.rs
git commit -m "feat(review): advisory leverage-ordered review with guidance and checklist"
```

---

### Task 5: Positioning and docs

**Files:**
- Modify: `README.md` (open with the intent: detection plus guidance for agents, reader-first; then `review`/`guide`; keep the accuracy disclosure; add the owner-corpus result "0 of 28 AI-drafted posts flagged" as a dated measurement linked to Plan 5's report once it exists)
- Modify: `HANDOFF.md` ("Resume here": humanization is back in scope as of 2026-11-21 by owner decision; link the roadmap)
- Modify: `docs/rule-catalog.md` (add a `Guidance` column with `guidance_id` and leverage)
- Modify: `skills/nobotrs/SKILL.md` (add `nobotrs review` as the first command for agents; full workflows land in Plan 3)

**Interfaces:** none new.

- [ ] **Step 1: Make the edits.**
- [ ] **Step 2: Verify**

Run: `cargo test --locked && python3 scripts/acceptance.py --skip-package`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add README.md HANDOFF.md docs/rule-catalog.md skills/nobotrs/SKILL.md
git commit -m "docs: position nobotrs as detection plus reader-first guidance for agents"
```
