# Offline Rust-Native Cross-Document Fact Consistency Design for `nobotrs`

**Status:** Design specification. Not implemented; reviewed in
`docs/research/reviews/factcheck-design-review.md`.
**Target:** `nobotrs` (`src/facts/` module + `facts` CLI subcommand)
**Invariants:** 100% offline, deterministic, bounded by `Deadline` (`src/deadline.rs:8-24`) and `max_bytes` (`src/config.rs:17`), never enters authorship `SignalFamily` quorum (`src/backend.rs:11-23`, `src/aggregate.rs:35-42`), and preserves `Document` source-range fidelity (`src/document.rs:124-162`).

---

## 1. Checkable Facts and Normalization

Every extracted `FactMention` stores: `kind`, `raw_text`, `normalized` (`NormalizedValue`), `polarity` (`Affirmative | Negated | Approximate`), `qualifier` (e.g., `~`, `about`, `at least`, `projected`), `doc_path`, `prose_offset`, `source_ranges`, `sentence_idx`, and `block_idx`.

| Fact Kind | Surface Examples (`evaluation/fixtures/bibb-fy27.txt:1-27`) | Canonical Normalization |
|---|---|---|
| `Number` | `80`, `six`, `200+`, `1,250` | `Decimal { mantissa: i128, scale: u8 }` + `word_to_num` (`zero`–`ninety-nine`, `hundred`/`thousand`/`million`/`billion`), comparator (`Exact`, `AtLeast`, `Approx`) |
| `Money` | `$23M`, `~$1.25M`, `$15.8 million`, `EUR 4.2k` | `Money { currency: ISO4217 ("USD" default for bare $ if config sets), amount_minor_or_scaled: i128, scale: u8 }` (`$23M` -> `USD 23_000_000`) |
| `Percentage` | `7.8%`, `15–20%`, `negative 14.3%` | `Percent { min: f64, max: f64 }` (basis points / `1e-4` integer for exact equality; `-14.3%` for `negative 14.3%`) |
| `Date` | `FY27`, `FY28`, `2026-10-10`, `Thursday`, `Q3 2025` | `DateNorm { kind: IsoDate | FiscalYear(u16) | Quarter(u16, u8) | MonthYear | RelativeWeekday, iso_range }` |
| `Duration` | `six years`, `5000 ms`, `18 months` | `Duration { value_num: i128, unit: Sec|Min|Hour|Day|Week|Month|Year }` (keep original unit + base seconds/days where exact; never equate 1 month = 30 days) |
| `Unit` | `12 GB`, `64 MiB`, `250 km`, `98.6 °F` | `Quantity { value: f64, unit_canonical: String, si_family }` (SI prefix scaling; binary `MiB` vs decimal `MB` kept distinct) |
| `Name` | `James Freeman`, `Dublin City Schools`, `Bibb` | `EntityName { canonical: lowercase_fold, tokens, kind_hint: Person|Org|Unknown }` (strip honorifics `Mr.`/`Dr.`/`Board member`) |
| `Role` | `Superintendent`, `Board member`, `CEO` | `Role { title_norm, holder_ref: Option<EntityId> }` |
| `Place` | `Bibb`, `Dublin`, `Georgia` | `Place { name_norm, admin_hint }` |
| `Quote` | `“Here I am six years in and we haven’t consolidated...”` | `Quote { text_norm: smart_quote_ascii_ws_collapsed, speaker_ref }` |
| `Citation` | `[1]`, `(Smith, 2024)`, `RFC 9110`, `DOI:10.1000/xyz` | `Citation { scheme: Bracket|AuthorYear|Doi|Rfc|Isbn, key_norm }` |
| `Url` | `https://example.com/a/?x=1#top` | `Url { scheme, host_lower, path_trimmed, query_norm }` (strip trailing slash, fragment `#...` optional) |
| `CodeId` | `` `Document::source_ranges` ``, `NOBOTRS_CONFIG`, `E0382` | `CodeId { symbol, scope_hint }` (extracted from raw Markdown `Event::Code` / fenced blocks before prose stripping) |
| `Claim` | `X costs $3M`, `Bibb is projected to drop to 7.8%` | `ClaimTriple { subject, predicate_norm, object: FactValue, time_scope, negated: bool }` |

---

## 2. Extraction Heuristics and Ambiguity

Offline extraction uses zero-ML deterministic passes over `Document::prose` (`src/document.rs:23`), plus a lightweight raw-Markdown pass for `Event::Code` / `Tag::Link` / YAML front matter (`src/document.rs:191-260`) since `prepare_markdown` excludes `CodeBlock` and `Event::Code` from `prose`.

1. **Token & Regex Pass (`regex` + `aho-corasick`, already in `Cargo.toml:26-27`):**
   - Bounded regexes (`REGEX_SIZE_LIMIT`, cf. `src/backends/vocabulary.rs:12`) match money, percentages, ISO/fiscal dates, durations, units, URLs, citations, and quoted spans (`"..."` / `“...”`).
   - Polls `deadline.expired()` per block/sentence (`src/deadline.rs:15-17`).
2. **Dependency-Free Clause & Entity Heuristics (per sentence in `Document::sentences`, `src/document.rs:26`):**
   - **Capitalized-span NER:** Consecutive TitleCase tokens not at sentence start (or matched in `entity_lexicon` / repeated >=2x across corpus) form `Name`/`Place` candidates; trailing corporate/civic suffixes (`Schools`, `Inc.`, `LLC`, `District`, `Department`) bias to `Org`.
   - **Appositive & Copular Role Binding:** Patterns `<Role> <Name>` (`Board member James Freeman`) and `<Name>, <Role>,` bind `Role -> Name` within the same sentence.
   - **Predicate-Argument Claims:** Within each sentence, split on clause boundaries (`,`, `;`, `—`, `and`, `but`), locate finite copula/action verbs (`is`, `was`, `costs`, `totals`, `dropped to`, `projected to`, `has`, `employs`, `outsources`) and attach nearest left NP (`subject`) + right `FactValue` (`object`).
   - **Polarity & Hedging:** Scan 4-token pre-verb/pre-value window for negation (`not`, `never`, `no`, `without`, `failed to`) and hedging/approximation (`~`, `about`, `roughly`, `projected`, `proposed`, `floor`, `not a recommendation`).
3. **Ambiguity Handling (Explicit `AmbiguityFlag`s):**
   - *Bare numbers / pronouns:* `80` or `It is $3M` without a local subject or unit gets `Ambiguity::Unanchored` (low confidence; never triggers `High` conflict alone).
   - *Scale/unit omission:* `$23M` vs `23` (`Ambiguity::MissingUnit`), `FY27` vs `27` (`Ambiguity::CalendarType`).
   - *Acronym/alias collision:* `VIP` / `TRS` (`evaluation/fixtures/bibb-fy27.txt:19-22`) or `Bibb` vs `Bibb County School District` -> emit `CandidateAliases` rather than hard-merging without evidence.
   - *Markdown vs Prose boundary:* `Document::prose_spans` (`src/document.rs:25`) prevents facts from merging across headings, list items, or table cells.

---

## 3. Cross-Document Linking (`Entity + Attribute + Context`)

Facts across documents are grouped into `FactCluster`s keyed by a 3-tuple `(EntityKey, AttributeKey, ContextKey)`:

- **EntityKey:** Normalized canonical entity (`bibb` / `bibb_district`, `james_freeman`), resolved via:
  1. Exact normalized match;
  2. Suffix/prefix alias table (`X` <-> `X City Schools` / `X County`, `James Freeman` <-> `Freeman` within same corpus if unambiguous);
  3. Explicit aliases in `.nobotrs-facts.json` (created by `facts init`).
- **AttributeKey:** Normalized predicate/noun-head (`fund_balance_ratio`, `consolidation_savings`, `paraprofessional_outsource_count`, `budget_shortfall`, `role_of(james_freeman)`, `url_target(...)`). Derived from the 3-word head noun/verb window around the value, stopword-stripped and stemmed via a small static suffix table (`-ing`, `-ed`, `-s`, `-tion`).
- **ContextKey:** Temporal/scope qualifier `(time_scope, polarity_scope, scenario_scope)`:
  - `time_scope`: `FY27`, `FY28`, `FY30`, `2026`, or `Unspecified`.
  - `scenario_scope`: `Actual | Projected | Proposed | CutMenu | Negated` (so `FY27` vs `FY28` or `Projected` vs `Actual` are separated by context, not falsely conflated!).
- **Blocking & Matching:** Invert index by `(EntityKey, AttributeKey)` for O(N) average linking across `scan`-scale directories (`Cargo.toml` needs no new crates). Pairs with fuzzy attribute Jaccard >= 0.6 and matching `EntityKey` enter candidate comparison.

---

## 4. Conflict Detection vs. Legitimate Variation

Each `FactCluster` with >= 2 mentions across >= 1 document (cross-doc prioritized; intra-doc optional) is classified into:

| Classification | Criteria | Severity / Action |
|---|---|---|
| `Consistent` | Normalized values equal within tolerance (e.g., `~$3.0M` == `$3M`) | Info (only shown in `facts explain`) |
| `LegitimateVariation` | Values differ *but* `ContextKey` differs (`FY27: 7.8%` vs `FY28: 0.5%`), or rounding within explicit approximation (`~$15.8M` vs `$15.84M`, `~` / `about` within 5% tolerance), or subset/superset (`total cuts ~$15.8M` vs `itemized $3.0M`), or `Quote` paraphrase vs verbatim flagged separately | `Low` / `Note` (suppressed by default in `check`; visible in `--verbose` / `explain`) |
| `AmbiguousOverlap` | Same `(Entity, Attribute)` with `Ambiguity::Unanchored` or mismatched `scenario_scope` (`Proposed` vs `Unspecified`) | `Low` or `Medium` (`needs-review`) |
| `DirectConflict` | Same `(EntityKey, AttributeKey, ContextKey)` with incompatible normalized values beyond tolerance (e.g., `FY27 shortfall: $8M` vs `$12M`, `James Freeman` role `Board member` vs `Superintendent`, broken/altered `Quote` with same attribution, `URL` host/path drift for same citation key, `CodeId` signature/name drift) | `High` (`Medium` if one side is `Approximate`) |

**Numeric & Range Rules:**
- Exact/scaled integers: `|$a - $b| <= max(abs_tol, rel_tol * max(|a|, |b|))` when either side has `Approximate` qualifier (`~`, `about`, `roughly`; default `rel_tol = 0.02`, configurable). Strict equality when both are exact.
- Ranges (`15–20%`): conflict only if intervals are disjoint; partial overlap -> `LegitimateVariation` (`narrowed_range`).
- Code identifiers & URLs: exact string equality after scheme/trailing-slash normalization; case or path mismatch -> `DirectConflict`.

---

## 5. Commands and UX

Add `Facts` subcommand to `Command` in `src/cli/mod.rs:58-77`:

- **`nobotrs facts init [DIR]`**
  Scans `DIR` (default `.`), extracts candidate entities, aliases, code identifiers, and recurring metrics, and writes `.nobotrs-facts.json` (corpus config: `entity_aliases`, `default_currency`, `numeric_tolerance`, `waiver_file: ".nobotrs-waivers.json"`, `include_intra_doc: false`). Never overwrites without `--force`.
- **`nobotrs facts check <DIR>`**
  Walks `DIR` using `walkdir` with the same symlink guard, `.git`/`target`/`node_modules`/`vendor`/`.venv`/`venv` filter, `.md`/`.markdown`/`.txt` filter, and deterministic path sort as `Command::Scan` (`src/cli/mod.rs:226-267`). Supports `--format human|json|sarif`, `--waiver <PATH>`, `--strict` (fail on `AmbiguousOverlap`), and `--min-confidence`.
- **`nobotrs facts explain <CLUSTER_ID_OR_QUERY>`**
  Prints all `FactMention`s in a cluster, their normalized forms, entity/attribute/context keys, why a pair was marked `DirectConflict` vs `LegitimateVariation`, exact file:line:col, and matching waiver/suppression state.

**Exit Codes** (aligned with `Report::exit_code` at `src/pipeline.rs:63-74`):
- `0`: Checked >= 1 document, zero unwaived `DirectConflict`s (and zero `AmbiguousOverlap` if `--strict`).
- `1`: One or more unwaived conflicts found.
- `2`: I/O, config/waiver parse error, symlink root, or `Deadline` timeout (`complete: false`).
- `3`: No supported files or zero checkable facts extracted (`inconclusive`).

**JSON Schema (`schema_version: "1.0.0"`):**
```json
{
  "schema_version": "1.0.0",
  "engine_version": "0.1.0",
  "root": "docs/",
  "complete": true,
  "documents_checked": 12,
  "facts_extracted": 184,
  "clusters": [{
    "cluster_id": "fc_bibb_fund_balance_fy27",
    "entity": "bibb",
    "attribute": "fund_balance_ratio",
    "context": { "time": "FY27", "scenario": "projected" },
    "status": "direct_conflict",
    "severity": "high",
    "waived": false,
    "mentions": [{
      "path": "docs/brief.md",
      "line": 4, "column": 31,
      "source_ranges": [{ "start": 142, "end": 146 }],
      "raw_text": "7.8%",
      "normalized": { "kind": "percent", "value": 0.078 },
      "sentence": "Bibb is projected to drop to 7.8% by the end of FY27."
    }]
  }],
  "errors": [],
  "exit_code": 1
}
```

**Suppression & Waiver File:**
- **Inline:** Extend `src/suppression.rs:76-119` with `facts.*` rule IDs (e.g., `facts.conflict`, `facts.numeric`, `facts.quote`, `facts.url`, `facts.code`) via existing `<!-- nobotrs-ignore-next-line facts.numeric -->`, `nobotrs-ignore-block`, `nobotrs-ignore-file`, and `ignore_rules`/`path_ignores` in `Settings` (`src/config.rs:38-39`). Note: `suppression.rs:88` currently errors on unknown rule IDs, so `Engine::known` (`src/pipeline.rs:81-84`) must register `facts.*` IDs.
- **Waiver file (`.nobotrs-waivers.json`):** Cross-document conflicts cannot always be suppressed in a single file. Waivers match by `cluster_id` or `(entity, attribute, context, values_hash)` with required `reason`, optional `expires` (ISO date; expired waivers warn and stop suppressing), and `author`.

---

## 6. Integration with `Document`, Sentence Units, Source Ranges, Guidance, Review/Compare

- **`Document` & `prose_spans` (`src/document.rs:22-32, 191-260`):** Reuse `Document::from_path` / `from_stdin_text_with_deadline` so YAML front matter and Markdown AST boundaries (`Heading`, `Paragraph`, `TableCell`, `Item`) are respected. Add an optional `raw_spans` or lightweight `MarkdownArtifacts` struct (capturing `Event::Code`, `CodeBlock`, `Tag::Link` URLs, and YAML front matter keys) so `CodeId`, `Url`, and `Date` metadata are not lost when `prepare_markdown` strips them from `prose`.
- **Sentence units (`src/document.rs:270-322`):** `Document::sentences` already handles abbreviations (`Mr.`, `Dr.`, `e.g.`, `i.e.`) and decimals (`7.8%` won't split!). Fact extraction operates per sentence index (`sentence_context`) so cross-sentence false links are avoided.
- **Source ranges (`src/document.rs:124-162`):** Every `FactMention` maps back via `doc.source_ranges(prose_offset)` and `doc.location(start)`, producing `score::Evidence`-compatible `raw_offset`, `source_ranges`, `line`, `column`, `end_line`, `end_column`, and `sentence_context` (`src/score.rs:34-49`). SARIF output (`src/output.rs:201-249`) works out of the box with `relatedLocations` pointing to the conflicting peer document(s).
- **Guidance (`docs/writing-guide.md:7`):** Reinforces *"Preserve factual claims, names, numbers, quotations, URLs, citations, and code"* — when `nobotrs lint` flags prose tells, `facts check` verifies edits did not introduce factual drift against source notes.
- **Review / Compare:** Mirror `src/external/gptzero/mod.rs:64-75` (`compare` informational pattern) or add `nobotrs facts check --baseline <REF_DIR_OR_DOC> <TARGET>`: treats `<REF>` as ground-truth source (e.g., board deck / `bibb-fy27.txt`) and reports `DirectConflict`s in `<TARGET>` against `<REF>` during human/LLM editing review.

---

## 7. Evaluation on Internal Corpora

Test and calibrate precision/recall offline using existing repo fixtures and corpora (no external data needed):

1. **`evaluation/fixtures/bibb-fy27.txt` (`1-27`):** Smoke-test extractor on dense real-world civic prose: `$23M`, `7.8%`, `15–20%`, `0.5%`, `negative 14.3%`, `FY27`/`FY28`/`FY30`, `~$1.25M`–`$3.8M`, `~$15.8 million`, `$8 million`, `six years`, `James Freeman` (`Board member`), `Superintendent`, and direct quote. Verify `FY27` vs `FY28` vs `FY30` are *not* flagged as conflicts (`LegitimateVariation` by `time_scope`).
2. **Synthetic Perturbation Suite over `evaluation/corpora/`:**
   - `assessment-pilot-v1/manifest.json` (964 samples; `finance: 107`, `medicine: 100`, `wiki_csai: 100`): Pair each sample with a perturbed clone (1-digit number flip, unit swap `MB`->`GB`, date shift, negated claim, altered quote) to measure **conflict recall** and **false-positive rate** on unperturbed pairs.
   - `mixed-controls-v1/manifest.json` (156 human-prefix + generated-suffix samples): Measure intra-document consistency where an LLM continuation contradicts a fact established in the human prefix.
   - `raid-pilot-v1/manifest.json` (1,100 samples; `news: 200`, `abstracts: 250`, `paraphrase: 150`): Evaluate `paraphrase` attacks for `LegitimateVariation` vs `DirectConflict` false positives, and verify non-English (`czech: 200`, `german: 150`) graceful abstention when `language != "en"` (`src/document.rs:115-117`).
3. **Metrics:** Cluster precision, conflict recall, false-positive rate per 1k words, and p95 latency under `timeout_ms: 5000` (`src/config.rs:48`).

---

## 8. Risks

- **False positives from coreference/scope blindness:** Without full neural coreference, `"the figure"` or `"it"` in sentence N+1 may fail to link or mislink to the wrong entity, or `"projected"` vs `"actual"` may be missed if hedging is two sentences away. *Mitigation:* Require explicit `EntityKey` or local appositive; downgrade unanchored links to `AmbiguousOverlap`.
- **Markdown stripping blind spots:** `Document::prepare_markdown` (`src/document.rs:226-253`) drops `CodeBlock`, `Event::Code`, and link URLs from `prose`. *Mitigation:* Extract `CodeId`/`Url` from `pulldown-cmark` events alongside `prose`, not solely from `doc.prose`.
- **Cross-document O(N²) blowup on large `DIR`:** Pairwise comparison across thousands of mentions could exceed `timeout_ms`. *Mitigation:* Bucket by `(EntityKey, AttributeKey)` before comparing, cap `max_candidates` (`src/config.rs:17`), and poll `Deadline` (`src/deadline.rs:15`).
- **Over-trusting heuristic extraction:** As with `nobotrs` authorship heuristics (`docs/writing-guide.md:9`), fact-check findings are editing prompts, not ground-truth verification against external reality — only internal consistency across the provided documents.
