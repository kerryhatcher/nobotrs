# Humanize 5: Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure what matters for the product:
- Do nobotrs rules fire more on AI drafts than on human writing?
- Do they flag what expert editors change?
- Does an agent following the skills produce revisions that keep their facts and that readers prefer?
- Do model hotspots point where editors intervene?

Only then decide, through a predeclared single held-out run, whether any vote or threshold changes.

**Architecture:**
- Standard-library Python tools in `scripts/`, tested with `unittest` (pattern: `scripts/test_evaluation_protocol.py`). They reuse `scripts/evaluation_protocol.py` (`validate_manifest`, `validate_grouping`, `wilson`, `sweep_rows`, `claim_independent_access`).
- Local corpora are read from `$NOBOTRS_INTERNAL_DIR` (default `/mnt/storage/projects/nobotrs/docs/internal`) and verified against its `test-artifacts/SHA256SUMS`.
- Only derived aggregates are committed, under `evaluation/reports/`.

**Tech Stack:** Python ≥3.11 stdlib (`csv`, `json`, `difflib`, `hashlib`, `zipfile`, `tarfile`); `pyarrow` only for reading the Beemo Parquet shard, imported lazily, with a clear error if missing. The `nobotrs` binary is built from Plans 1–4.

**Spec:** `docs/superpowers/plans/2026-11-21-humanize-roadmap.md`

## Global Constraints

- Labels come only from provenance:
  - Owner posts: `ai_drafted` if the date is ≥ 2025-03-10 or the slug contains `crossover`, otherwise `human` (28 / 15).
  - Beemo: `human_output` is human, `model_output` is ai, `human_edits` is ai_edited_by_human.
  - APT-Eval: the original is human and the polished version is ai_polished.
  - GAO 2008 and WI+LOCNESS are human.

  Detector outputs (nobotrs, GPTZero, OpenRouter, local models) never become labels.
- Confounds are reported, never hidden. The owner human posts are 2011–2025 technical tutorials averaging 535 words, while the AI drafts average 1,279 words and are mostly civic. Every owner-corpus result is stratified by genre where possible and carries this caveat.
- Rates with a denominator below 10 documents, or below 10,000 words, are `null` with their counts.
- No content from Beemo, APT-Eval, CoAuthor, GAO or WI+LOCNESS is committed: no raw text, excerpts, example spans, agent rewrites of their samples, reader packets or responses, or vendor responses about them. Reports may contain counts, rates, intervals, rule IDs and hashed sample IDs only. Owner-post text is allowed (roadmap decision 1). `scripts/check_no_local_corpora.py` (Task 1) enforces this.
- Rewrite loops are never run against a detector score. External detectors appear only as reported second opinions.
- Any change to votes, thresholds or default severities goes through Task 7. Guidance text and `keep_when` edits informed by Tasks 3–5 are allowed without Task 7, because they don't change scoring.

## Review Focus

- A checksum mismatch in a local corpus must stop the run with the file name, not evaluate stale data. Test in Task 1.
- Beemo variants of one `prompt_id` must stay together in any split or bootstrap resample. Test in Task 1.
- A Beemo editor change that only reflows whitespace must not count as an edit. Test in Task 4.
- A rewrite that silently drops a number must count as a fidelity failure even if readers prefer it. Test in Task 5.
- Re-running the held-out decision after it is claimed must fail. Test in Task 7.

---

### Task 1: Corpus registry and owner-posts manifest

**Files:**
- Create: `evaluation/corpora/registry.json`
- Create: `evaluation/corpora/owner-posts-v1/manifest.json` (texts under `samples/` only if open decision 1 approves; otherwise the manifest points to `$NOBOTRS_INTERNAL_DIR`)
- Create: `scripts/corpora.py`, `scripts/test_corpora.py`
- Create: `scripts/check_no_local_corpora.py`, `scripts/test_check_no_local_corpora.py`
- Modify: `scripts/acceptance.py` (runs the guard when `$NOBOTRS_INTERNAL_DIR` exists, and prints "skipped: no local corpora" otherwise)

**Interfaces:**
- Produces:
  - Registry entries: `{ "id", "root": "test-artifacts/<dir>", "checksums": "test-artifacts/SHA256SUMS", "licence", "labels", "group_key", "use" }` for `owner-posts-v1`, `beemo`, `apt-eval`, `coauthor`, `govinfo-gao-2008` and `wi-locness`.
  - `@dataclass class Sample: corpus: str; id: str; group: str; label: str; genre: str; date: str | None; text: str; markdown: bool`
  - `def iter_samples(corpus_id: str, internal_dir: Path | None = None) -> Iterator[Sample]` (verifies checksums first)
  - `def owner_label(filename: str) -> str`, applying the label rule exactly
  - Guard: `def leaked(paths: list[Path], corpora: list[str], shingle: int = 12) -> list[tuple[Path, str, str]]`. It returns `(file, corpus, hashed sample id)` for every tracked or staged file (`git ls-files` plus `git diff --cached --name-only`) that shares a 12-word lowercase shingle with any non-owner local corpus. The CLI exits 1 on any hit. Corpus shingles are hashed with SHA-256 truncated to 8 bytes and cached under `$NOBOTRS_INTERNAL_DIR/derived/shingles/` (local only).
  - The owner manifest records per post: file, date, label, `genre` (`civic|technical|personal|review`; assigned by hand in the manifest and reviewed by the owner), words, `label_source: "owner statement 2026-11-21"` and `confidence` (`high`, or `medium` with a `provenance_note`).
  - `2025-03-07-better-python-logging.md` is `human`, `confidence: medium`, `provenance_note: "owner recalls writing it; possibly edited during site migrations"`.
  - `def primary(samples) -> list[Sample]` drops `confidence: medium` samples. Every owner-corpus report gives primary results plus a sensitivity line that includes them.
  - Texts are committed under `evaluation/corpora/owner-posts-v1/samples/` (approved by the owner).

- [ ] **Step 1: Write failing tests**
  - `test_owner_label_rule`: `2025-03-10-using-rust…` → ai_drafted, `2025-03-07-crossover-2025.md` → ai_drafted, `2025-03-07-better-python-logging.md` → human with `confidence: medium`. The manifest totals are 28/15, and `primary()` returns 28/14.
  - `test_checksum_mismatch_stops`, using a temp copy with one byte changed.
  - `test_beemo_groups_by_prompt_id`, using a 6-row stub table.
  - `test_registry_entries_have_licence_and_use`
  - `test_guard_flags_beemo_excerpt`: a temp repo with a staged file containing a 15-word Beemo excerpt (stub corpus) gives exit 1 with the file named. The same file containing only counts and a hashed id gives exit 0.
  - `test_guard_ignores_owner_corpus`: owner-post text never triggers the guard.
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_corpora.py`
Expected: FAIL

- [ ] **Step 3: Implement.** Read Beemo through `pyarrow.parquet`, read APT-Eval CSV with `csv`, and stream the GAO reports and WI+LOCNESS archives from their packed form without extracting into the repo.
- [ ] **Step 4: Run tests**

Run: `python3 scripts/test_corpora.py && python3 scripts/corpora.py verify --all`
Expected: PASS, and `verify` prints each corpus as OK

- [ ] **Step 5: Commit**

```bash
git add evaluation/corpora/registry.json evaluation/corpora/owner-posts-v1 scripts/corpora.py scripts/test_corpora.py
git commit -m "feat(eval): local corpus registry and owner-posts manifest with provenance labels"
```

---

### Task 2: Baseline recorder

**Files:**
- Create: `scripts/record_baseline.py`, `scripts/test_record_baseline.py`, `evaluation/baselines/README.md`

**Interfaces:**
- Produces:
  - CLI: `record_baseline.py --input PATH | --corpus ID --out DIR [--models …] [--model-coverage opening|full] [--external] [--judge-repeats N]`
  - Per input, `run.json` records: `git_revision`, `git_dirty`, `input_sha256`, bytes and chars, binary features, settings, manifest hashes, preprocessing revisions, devices, `backend_completion`, `external` (`gptzero`, `openrouter_repeats`, `openrouter_label_agreement`, `openrouter_failed_repeats`) and `commands` (the exact argv used). A raw `report.json`, `review.json` and the `lint`/`detect` exit codes are stored alongside.
  - `def judge_stability(reports: list[dict]) -> tuple[float | None, int]`
- [ ] **Step 1: Write failing tests**
  - `test_run_json_fields_offline` (stub binary)
  - `test_judge_stability`: `[AI, AI, MIXED, failed, AI]` gives `(0.75, 1)`, and all failed gives `(None, 5)`.
  - `test_refuses_external_without_keys`
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_record_baseline.py`
Expected: FAIL

- [ ] **Step 3: Implement.**
- Vendor output policy (from the roadmap's decision 3), enforced by `record_baseline.py`:
  - **GPTZero:** the raw response is written only to `$NOBOTRS_INTERNAL_DIR/derived/baselines/…`. The committed `run.json` records `external.gptzero` as `{ "status", "date", "local_path", "response_sha256" }` and nothing from the response body.
  - **OpenRouter:** the committed record keeps the verdict, confidence, reply text, model, serving `provider`, tokens and cost, plus the field `"ai_generated": true`. The `inputText`/prompt is never stored in the committed file.
  - `test_gptzero_body_never_committed`: the committed `run.json` from a stub GPTZero response contains none of `inputText`, `sentences`, `class_probabilities` or `scanId`.
The roadmap records the GPTZero fixture cleanup as complete. Use the synthetic fixtures for backend tests and keep live responses in private storage.
- [ ] **Step 4: Record baselines (manual):**
  - The Bibb fixture: offline, all models opening, all models full, and `--external --judge-repeats 5`.
  - The whole owner corpus, offline and models full.

  Commit everything allowed by the policy above.
- [ ] **Step 5: Commit**

```bash
git add scripts/record_baseline.py scripts/test_record_baseline.py evaluation/baselines
git commit -m "feat(eval): reproducible baseline recorder; Bibb and owner-corpus baselines"
```

---

### Task 3: Rule lift against human controls

**Files:**
- Create: `scripts/rule_lift.py`, `scripts/test_rule_lift.py`
- Create: `evaluation/reports/rule-lift-v1.json`, `evaluation/reports/rule-lift-v1.md` (generated)

**Interfaces:**
- Consumes: Task 1 samples; `nobotrs review --format json` output per sample.
- Produces:
  - `def rates(rows: list[dict], label: str, genre: str | None) -> dict[str, dict]`: per rule, `{docs_with, docs, hits, words, per_10k, ci}`. The CI is a document-level bootstrap with 2,000 resamples, seed 0, grouped by `group`.
  - `def lift(ai: dict, human: dict) -> dict[str, dict]`: `{lift, ci, ai_per_10k, human_per_10k}`, with `null` under the small-denominator rule.
  - Comparison sets:
    - (a) owner AI vs owner human, overall and by genre
    - (b) Beemo `model_output` vs `human_output` (same prompts)
    - (c) owner AI vs GAO 2008, a civic human control from before LLMs
    - (d) all AI sets vs WI+LOCNESS native and learner, separately, as a non-native false-positive check
  - In the report markdown, rules are sorted by lift with flags `weak` (CI includes 1) and `human-common` (human per-10k ≥ AI per-10k). The flags are input to owner review of guidance `keep_when` and severities.
- [ ] **Step 1: Write failing tests**
  - `test_bootstrap_keeps_groups_together`
  - `test_small_denominator_is_null`
  - `test_lift_math_on_hand_example`: AI 6 hits in 10k words against human 2 in 10k gives lift 3.0.
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_rule_lift.py`
Expected: FAIL

- [ ] **Step 3: Implement, then generate the report**

Run: `python3 scripts/rule_lift.py --out evaluation/reports/rule-lift-v1`

- [ ] **Step 4: Run tests** (Step 2 command). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add scripts/rule_lift.py scripts/test_rule_lift.py evaluation/reports/rule-lift-v1.*
git commit -m "feat(eval): per-rule lift against owner, Beemo, GAO and LOCNESS controls"
```

---

### Task 4: Editor alignment (Beemo and APT-Eval)

**Files:**
- Create: `scripts/editor_alignment.py`, `scripts/test_editor_alignment.py`
- Create: `evaluation/reports/editor-alignment-v1.json`, `.md` (generated)

**Interfaces:**
- Produces:
  - `def changed_spans(before: str, after: str) -> list[tuple[int, int]]`: byte spans in `before` whose words are deleted or replaced in `after` (word-level `difflib.SequenceMatcher` on whitespace tokens). Whitespace-only differences are ignored.
  - `def alignment(findings: list[dict], spans, text_len: int, seed: int = 0) -> dict`:
    - `edited_rate`: the share of findings overlapping a changed span
    - `baseline_rate`: the same, for 200 random spans of matched lengths per document
    - `lift = edited_rate / baseline_rate`, with a bootstrap CI grouped by `prompt_id`
  - Reported per rule and per guidance category for Beemo `model_output → human_edits`.
  - `introduced_by_editors`: rules present in `human_edits` but not in `model_output`.
  - APT-Eval: `introduced_by_polish`, the rules that appear after AI polishing of human drafts.
- [ ] **Step 1: Write failing tests**
  - `test_whitespace_only_is_not_an_edit`
  - `test_overlap_counts_once`
  - `test_baseline_uses_matched_lengths`
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_editor_alignment.py`
Expected: FAIL

- [ ] **Step 3: Implement and generate**

Run: `python3 scripts/editor_alignment.py --out evaluation/reports/editor-alignment-v1`

- [ ] **Step 4: Run tests** (Step 2 command). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add scripts/editor_alignment.py scripts/test_editor_alignment.py evaluation/reports/editor-alignment-v1.*
git commit -m "feat(eval): do expert editors change what nobotrs flags"
```

---

### Task 5: Agent-rewrite evaluation and blind reader study

**Files:**
- Create: `scripts/rewrite_eval.py`, `scripts/test_rewrite_eval.py`
- Create: `docs/evaluation/rewrite-study-v1.md` (protocol: inputs, the two rewrite conditions, reader instructions, predeclared success criteria filled in by the owner before ratings are imported)
- Create: `evaluation/reports/rewrite-study-v1.json`, `.md` (generated after ratings)

**Interfaces:**
- Scale: 70–350 blind readers (owner decision, 2026-11-21).
- Inputs:
  - **Sources:** 40 AI drafts: all 28 owner AI drafts (one ≤400-word excerpt per post, cut at paragraph boundaries, seed 0) plus 12 Beemo `model_output` samples.
  - **Conditions,** produced outside the harness by an agent:
    - `original`: the AI draft unchanged.
    - `naive`: the prompt "Rewrite this so it sounds less like AI," with no nobotrs.
    - `guided`: the `review-writing` skill (Plan 3).
  - **Comparisons:**
    - Primary: `guided` vs `naive`.
    - Secondary: `guided` vs `original` and `naive` vs `original`.
    - Total: 120 pairs.
  - **Design:** each reader gets 12 pairs (about 20 minutes), drawn so that every pair receives ≥7 ratings at 70 readers and ≥35 at 350. Each reader sees at most one pair per source. The set also includes 2 attention-check pairs, where one side has injected obvious errors.
  - **Layout:** `$NOBOTRS_INTERNAL_DIR/derived/rewrite-study-v1/rewrites/<condition>/<sample_id>.<ext>`, local only. Rewrites of Beemo samples are Beemo content and are never committed. Rewrites of owner posts may be committed after the study.
- Produces:
  - `def fidelity(source: Path, rewrite: Path) -> dict`, from `nobotrs compare --format json`: `{missing_hard, added_facts, removed_by_leverage, introduced_by_leverage, length_ratio, exit}`
  - `def assign(readers: int, pairs: list, per_reader: int = 12, seed: int = 0) -> dict[str, list]`: a balanced incomplete assignment with the constraints above.
  - `def export_packets(assignment, out_dir, seed) -> None`. It writes one CSV row per (reader slot, pair), importable into a form platform, plus the static texts. A/B order is randomized, ids are hashed, condition names never appear, and the protocol's instruction text is included. For each version readers rate clarity (1–5) and how much the writing distracts from its message (1–5), then pick a preference.
  - `def import_ratings(path) -> list[dict]`. It drops readers who fail an attention check and keeps only an opaque reader id. Names, emails and IP addresses are never imported or committed.
  - `def summarize(ratings, fidelity_rows) -> dict`. It gives win rates with reader-clustered bootstrap CIs (2,000 resamples), mean rating differences, per-genre breakdowns, and the fidelity failure rate per condition. A rewrite with `missing_hard > 0` counts as a fidelity failure, whatever readers prefer.
  - Predeclared success, written into `docs/evaluation/rewrite-study-v1.md` before any rating is imported:
    - `guided` beats `naive` with a win-rate CI lower bound above 0.5.
    - `guided` is not worse than `original` on clarity.
    - `guided` has a fidelity failure rate ≤ `naive`'s.
- [ ] **Step 1: Write failing tests**
  - `test_dropped_number_is_fidelity_failure_even_if_preferred`
  - `test_packets_hide_condition_and_randomize_order`: over 100 seeds, A is guided in 40–60% of the packets that involve guided.
  - `test_assignment_balance`: at 70 and at 350 readers, every pair meets its minimum rating count, and no reader sees two pairs from one source.
  - `test_attention_check_failures_dropped`
  - `test_reader_clustered_bootstrap`: resampling by reader, not by rating, on a hand example.
  - `test_no_pii_columns_survive_import`
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_rewrite_eval.py`
Expected: FAIL

- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the study (manual).**
  1. **TBD before this step:** the form platform, recruitment and consent wording (roadmap decision 5), and whether Beemo excerpts may be shown to readers (roadmap decision 6; the fallback is 28 owner drafts and 84 pairs).
  2. Commit the protocol with its success criteria.
  3. Produce the rewrites and run fidelity.
  4. Assign readers and export the packets.
  5. Collect the ratings, then import and summarize.

  Raw responses stay in `$NOBOTRS_INTERNAL_DIR/derived/rewrite-study-v1/`. Only the summary is committed.
- [ ] **Step 5: Commit**

```bash
git add scripts/rewrite_eval.py scripts/test_rewrite_eval.py docs/evaluation/rewrite-study-v1.md evaluation/reports/rewrite-study-v1.*
git commit -m "feat(eval): agent rewrite fidelity and blind reader preference study"
```

---

### Task 6: Hotspot validity (Plan 4)

**Files:**
- Create: `scripts/hotspot_validity.py`, `scripts/test_hotspot_validity.py`
- Create: `evaluation/reports/hotspot-validity-v1.json`, `.md` (generated)
- Modify: `guidance/hotspot-validation.json` (written by the script only if criteria pass)

**Interfaces:**
- Produces:
  - `def doc_auroc(rows, score_key) -> dict`: AUROC with a bootstrap CI, for each model's `raw_output` (opening) and `full_coverage_output`, on the owner corpus (AI vs human, overall and by genre) and on Beemo (`model_output` vs `human_output`).
  - `def editor_overlap(hotspots, changed_spans) -> dict`: for Beemo, whether the top-ranked hotspot window overlaps changed spans more than the other windows of the same document (paired, grouped by `prompt_id`): `{lift, ci, docs}`.
  - Criteria, recorded in the report **before** the run and confirmed by the owner. Proposed: editor-overlap lift CI lower bound > 1.0 on Beemo, and at least one model's full-coverage AUROC CI lower bound > 0.6 on the owner corpus.
  - On pass, the script writes `{"validated": true, "record": "evaluation/reports/hotspot-validity-v1.json", "criteria": …}` to `guidance/hotspot-validation.json`. On fail it leaves `validated: false` and records why.
- [ ] **Step 1: Write failing tests**
  - `test_auroc_hand_example`
  - `test_editor_overlap_is_paired_within_document`
  - `test_validation_file_untouched_on_fail`
- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/test_hotspot_validity.py`
Expected: FAIL

- [ ] **Step 3: Implement, confirm the criteria, and run**

Run: `python3 scripts/hotspot_validity.py --out evaluation/reports/hotspot-validity-v1`

- [ ] **Step 4: Run tests** (Step 2 command). Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add scripts/hotspot_validity.py scripts/test_hotspot_validity.py evaluation/reports/hotspot-validity-v1.* guidance/hotspot-validation.json
git commit -m "feat(eval): hotspot validity against owner labels and Beemo editor changes"
```

---

### Task 7: Scoring decisions through a single held-out run

**Files:**
- Modify: `src/config.rs`, `src/pipeline.rs` (hidden `experiment: Vec<String>`, env `NOBOTRS_EXPERIMENT`; never shown in `--help`; echoed in `settings.experiment`; `metric_contract` gets the suffix `+experimental` when the list is non-empty; unknown ids exit 2)
- Modify: `src/backends/burstiness.rs` (`burstiness-units`), `src/backends/punctuation.rs` (`punctuation-skip-list-separators`), `src/score.rs` (`structure-votes`: lets `Structure` count as a voting family)
- Create: `evaluation/release-criteria/humanize-v1.json`, `scripts/humanize_decide.py`, `scripts/test_humanize_decide.py`, `tests/experiments.rs`, `docs/evaluation/humanize-v1-decisions.md` (filled after the run)

**Interfaces:**
- Candidates (exact ids):
  - `burstiness-units`
  - `punctuation-skip-list-separators`
  - `structure-votes`
  - `model-full-coverage-thresholds` (re-selected thresholds on `full_coverage_output`)
- Each candidate records its metrics (human FP by genre, recall at the FP budget, lift, abstentions, latency), `error_budget` and `must_improve_on: "release-<current version>"`. The freeze refuses a `null` budget.
- The default `error_budget` was accepted by the owner on 2026-11-21:
  - `human_fp_wilson_upper_95 <= 0.05`, both overall and in every genre with ≥10 human documents.
  - `human_fp <= current_release_human_fp`.
  - `recall_gain_ci_lower > 0` and `recall_gain >= 0.10`.
- Data:
  - Dev: owner corpus, Beemo and APT-Eval.
  - Held-out: a fresh source-disjoint set collected per `docs/evaluation/humanize-v1-decisions.md`, plus GAO 2008 human controls not used in Tasks 3–6 (split by report with `validate_grouping`).
- `def select_on_dev(rows, candidate) -> dict`, `def freeze(criteria_path, selections) -> Path`, `def evaluate_heldout(record_path, rows) -> dict` (via `claim_independent_access`), and `def decide(result, criteria) -> Literal["ship", "informational"]`.
- [ ] **Step 1: Write failing tests**
  - `tests/experiments.rs`:
    - the default run equals the `tests/bibb_fixture.rs` pins
    - `punctuation-skip-list-separators` gives effective dashes 0.0 on the fixture
    - `burstiness-units` changes the CV
    - `structure-votes` makes `structure` voting-eligible
    - `bogus` exits 2
  - Python:
    - `test_heldout_second_claim_fails`
    - `test_freeze_rejects_null_budget`
    - `test_decide_requires_budget_and_improvement`
    - `test_dev_selection_never_reads_heldout`
- [ ] **Step 2: Run to verify failure**

Run: `cargo test --locked --test experiments && python3 scripts/test_humanize_decide.py`
Expected: FAIL

- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run tests**

Run: `cargo test --locked && python3 scripts/test_humanize_decide.py`
Expected: PASS

- [ ] **Step 5: Commit tooling**

```bash
git add src/config.rs src/pipeline.rs src/backends/burstiness.rs src/backends/punctuation.rs src/score.rs evaluation/release-criteria/humanize-v1.json scripts/humanize_decide.py scripts/test_humanize_decide.py tests/experiments.rs
git commit -m "feat(eval): experiment hooks and predeclared single held-out decision"
```

- [ ] **Step 6: Decide (manual, after budgets are set and the held-out set exists).** Select on dev, freeze, claim the held-out set once, and write the decision record. Each `ship` candidate gets its own follow-up PR that removes its experiment gate.
