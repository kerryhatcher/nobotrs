# nobotrs review remediation and development plan

Date: 2026-10-10

This plan addresses the code review of `nobotrs` at `eb02215c03d119f1ca698dd84f718c37a3530d73`, using the Python `nobot` branch `worktree-cli` at `0981b9501b7dd2fb37803cf43298e83edfd508e9`, the imported research, and the issue discussions in both repositories. The immediate objective is a functional offline CLI with correct prose extraction and honest, actionable reports. Evaluation, suppression, and integrations follow; optional model analysis and humanization are later milestones.

Implementation status updated 2026-10-10. Checked items below reflect implemented behavior; unchecked items remain acceptance work. Core CLI, prose preparation, reporting, matching/resource controls, suppression, SARIF and integrations are implemented. Evaluation infrastructure is hardened and shared-fixture Python comparison plus burstiness references are implemented. Independent authorship evaluation, source-by-source parity, and corpus acquisition remain open. The user explicitly deferred choosing optional models and revisions; phases 8–9 remain unimplemented. No upstream issues were closed.

See [HANDOFF.md](../../../HANDOFF.md) and [validation evidence](../../core-validation.md) for the baseline, checks and measurements.

## Baseline and relationship to previous plans

- The reviewed Rust checkout contains six backends and an aggregator, but all four CLI commands return success without performing their advertised work.
- The baseline was reconfirmed with `cargo test --locked --offline`: 60 unit tests and one CLI smoke test passed. Temporary probes also reproduced discarded exact-match candidates, an invalid longer match hiding a valid shorter match, a missed phrase across a Markdown soft break, and Welsh prose being accepted for English readability analysis. Passing the existing suite does not establish end-to-end correctness.
- The newer Python branch introduces shared prose preparation, a reusable engine, CLI/TUI/MCP adapters, optional model scoring, and Ollama-backed humanization. It is a reference implementation, not an oracle for parsing, statistics, thresholds, or error handling.
- Existing July plans and the [design specification](../specs/2026-07-26-nobotrs-rust-cli-design.md) remain historical context. This plan proposes revisions to their probability representation, quorum participation, prose extraction, and validation requirements. Reconcile those documents during implementation rather than following conflicting requirements simultaneously.
- The current `HANDOFF.md` describes an interrupted July workflow. Update it when implementation starts so it points to the actual state and this plan. Do not treat its instruction to avoid revisiting earlier tasks as evidence that the reproduced bugs are resolved.
- Keep the single-crate layout, offline default build, embedded dictionary, and existing code/data license separation. A library target does not require a Cargo workspace.
- No subagent workflow or unavailable skill is required to execute this plan.

## Source material

- [Python reference branch](https://code.kerryhatcher.com/kerryhatchergithub/nobot/src/commit/0981b9501b7dd2fb37803cf43298e83edfd508e9).
- [Imported research collection](../../research/thor-ai-writing/ai-text-detection-2026/README.md), especially [source verification](../../research/thor-ai-writing/ai-text-detection-2026/source-verification.yaml), the team findings, and bibliography.
- [RAID paper](https://aclanthology.org/2024.acl-long.674/): evaluate generalization across domains, generators, decoding strategies, and perturbations rather than relying on headline accuracy.
- [CommonMark fenced code specification](https://spec.commonmark.org/0.31.2/#fenced-code-blocks): delimiter length and container context matter.
- [CommonMark soft breaks](https://spec.commonmark.org/0.31.2/#soft-line-breaks) and [character references](https://spec.commonmark.org/0.31.2/#entity-and-numeric-character-references): rendered-equivalent inline prose needs consistent normalization and source mapping.
- [Aho-Corasick match semantics](https://docs.rs/aho-corasick/latest/aho_corasick/enum.MatchKind.html): overlapping searches require `MatchKind::Standard`; the pinned `1.1.4` implementation was checked locally.
- [Whichlang](https://github.com/quickwit-oss/whichlang): the pinned `0.1.1` API selects one of 16 languages without exposing an unknown result or confidence. Unsupported-language handling requires an additional policy or a different detector.
- [Python issue tracker](https://github.com/kerryhatcher/nobot/issues): issues are requirements and historical reports; verify them against the pinned branch before treating them as missing functionality.

The original review recorded 12 open GitHub `nobot` issues, no GitHub `nobotrs` or authenticated Forgejo issues in either repository, and hosted Rust `main` matching the local commit. These are historical observations: live issue status was not independently reconfirmed during the follow-up plan review because GitHub page fetches failed. Recheck branch and issue state at implementation time.

## Findings and coverage

| ID | Finding or recommendation | Planned work |
|---|---|---|
| F01 | CLI stubs return success for nonexistent inputs | Phases 1, 2, 7 |
| F02 | Punctuation includes code/front matter; statistics use raw word counts | Phase 2 |
| F03 | Four-backtick fences hide subsequent prose | Phase 2 |
| F04 | Measurements are lost or mapped to uncalibrated human probabilities | Phase 3 |
| F05 | Empty input becomes Clean; evidence-only families satisfy participation; abstentions disappear | Phase 3 |
| F06 | Readability changes syllable counts with punctuation and miscounts sentences | Phase 2 |
| F07 | Deadlines are ignored; vocabulary reporting has quadratic paths, including long single-line Unicode input | Phase 4 |
| F08 | Candidate enumeration loses overlapping/boundary-valid alternatives; exact rules ignore case sensitivity | Phase 4 |
| F09 | Need one reusable engine and thin CLI/plugin/MCP adapters | Phases 1, 7, 8 |
| F10 | Thresholds, new signals, and claims lack evaluation | Phase 5 |
| F11 | Stable IDs, localized findings, suppression, and SARIF are missing | Phases 3, 6, 7 |
| F12 | Python model implementations and parsing must not be copied without validation | Phases 2, 8 |
| F13 | Humanization should preserve meaning and support targeted edits | Phase 9 |
| F14 | Documentation, research provenance, and stale planning need reconciliation | Phases 0, 1, 4, 5, 7 |
| F15 | A closed-set language guess cannot establish supported-language applicability | Phase 2 |
| F16 | Markdown normalization and semantic boundaries are underspecified | Phase 2 |
| F17 | Suppression after overlap removal can hide an independently enabled rule | Phases 3, 4, 6 |
| F18 | Backend outcomes must remain separate from the single voting contribution per family | Phases 3, 8 |
| F19 | Repeated held-out selection can leak evaluation data into tuning | Phase 5 |
| F20 | Candidate limits, display truncation, and incomplete analysis need distinct semantics | Phases 1, 3, 4, 6 |
| F21 | Release gates mix milestones and defer essential first-release documentation | Phases 1, 4, 7; milestone gates |

## Delivery order

1. **Functional core milestone:** phases 0–4 and the functional-core release gates below, including installation and limitations documentation. Finish the CLI early, but do not call it release-ready until preprocessing, result semantics, and resource controls pass their acceptance checks. This milestone ships an explicitly uncalibrated heuristic linter/detector.
2. **Evaluated linting milestone:** phases 5–7. Establish baselines, add suppression and CI output, then document the actual guarantees.
3. **Optional capabilities milestone:** phases 8–9. Add model analysis, additional adapters, and humanization without expanding the default runtime requirements.

Dependencies: phase 1 establishes the shared pipeline; phase 2 precedes reliable metrics and calibration; phase 3 supplies IDs, backend/family separation, and report semantics needed by phases 6–8. Phase 4 must preserve match candidates for phase 6's suppression-before-selection policy, even though suppression itself ships later. Phase 5 establishes the development/validation and independent release-evaluation process for threshold changes, new voting signals, and calibrated model verdicts. Phase 8 is not required to ship a useful offline linter. Phase 9 can use an external local generation service without requiring all detection models. Each milestone has its own release gates; later-feature checks do not block the functional-core milestone.

## Phase 0 — Record the baseline and reconcile requirements

**Likely files:** `HANDOFF.md`, the July design/specification documents, `docs/research/`, and test fixtures.

- [x] Record reviewed commit IDs, the active branch, existing local changes, and baseline test results. Preserve imported research and unrelated work.
- [x] Convert temporary reproductions into permanent regression fixtures as the relevant fixes land. Retain the original input and expected behavior in each test.
- [x] Document proposed contract changes: raw metrics instead of heuristic probabilities; explicit voting eligibility and family reduction; insufficient/uncertain-language handling; structured backend outcomes; candidate/suppression ordering; analysis completeness versus display truncation; versioned output.
- [x] Reconcile the old plan's unconditional probability field and inaccurate compression parity claim. Rust `lzma-rs` output is not numerically interchangeable with Python `lzma.compress(..., preset=6)`.
- [x] Record the distinction between CLI errors and advisory hook behavior. Do not inherit Python's broad CLI fail-open policy.

**Acceptance:** the active plan and handoff agree; each F01–F21 item has an implementation phase and regression or acceptance check. Historical documents are labeled or linked, not silently treated as current contracts.

## Phase 1 — Make the CLI functional through a shared library

**Likely files:** `src/lib.rs`, `src/main.rs`, `src/cli/*.rs`, new pipeline/config/output modules, `tests/cli_smoke.rs`, CLI integration tests, `README.md`, and basic configuration/limitations documentation.

- [x] Expose the existing engine through `src/lib.rs`; make the binary a thin argument and I/O adapter. Initialize the dictionary/backend registry once per invocation and reuse it for directory scans.
- [x] Implement a shared analysis entry point used by `detect`, `lint`, and `scan`. Keep filesystem access and process exit decisions outside the backends.
- [x] Implement file and `-` stdin loading. Infer Markdown from file extension; support an explicit Markdown hint for stdin. Report invalid UTF-8 and read failures rather than discarding bytes silently.
- [x] Implement `detect` with an ensemble report, `lint` with individual findings regardless of quorum, and `scan` as batch detection. Correct the current contradictory scan help text.
- [x] Implement platform-resolved configuration and `config` diagnostics: effective settings, origins of overrides, enabled backends, and availability. Redact secrets if optional providers are added later.
- [x] Define and document precedence: CLI options over environment over config file over defaults. Invalid configuration produces a diagnostic, not a silent fallback.
- [x] Add deterministic human and versioned JSON output. Diagnostics go to stderr; stdout stays machine-readable in JSON mode. Honor `NO_COLOR` and nonterminal output.
- [x] Replace the smoke test with assertions that prove stdin is read, output exists, findings affect status, and nonexistent inputs fail.
- [x] Document installation, file/stdin and Markdown usage, configuration precedence, exit codes, and JSON output as the commands land. Before the first release, include raw metric semantics, English/unknown-language applicability, short-input limits, resource limits, and the uncalibrated nature of the heuristics. Describe Clean as no configured tells meeting policy, never proof of human authorship.

**Proposed exit contract:** preserve the July CLI meanings: `0` completed and unflagged, `1` actionable findings, `2` operational failure or incomplete execution, `3` inconclusive. Define precedence explicitly as operational failure first, then actionable findings, then inconclusive, then clean. For `scan`, retain every file outcome and use this precedence for the overall status; a clean file must not hide an unreadable or inconclusive file. For `lint`, quorum is irrelevant: the configured actionable severity determines status, with empty/no-prose inputs reported distinctly.

Stopping analysis because of input, candidate, or time limits produces status `2`, with partial findings and coverage retained. Limiting displayed findings alone does not change votes or status when analysis and policy evaluation completed; report omitted counts and the display limit separately. A report containing a failed enabled backend must expose incomplete execution even if enough other families produced an ensemble verdict.

**Acceptance:** file and stdin fixtures produce equivalent analyses; all commands perform their advertised work; missing paths and incomplete analysis return `2`; a batch reports individual failures; display-only truncation preserves completed policy results; the offline default runs without keys, model downloads, or network access. Final output must use phase 3's schema before release, and the core README/help must describe the shipped behavior.

## Phase 2 — Unify prose extraction and repair statistics

**Likely files:** `src/document.rs`, all `src/backends/*.rs`, Markdown and statistical fixtures.

- [x] Build one reusable prepared-document representation containing original text, extracted prose, source mappings, prose word count, sentence spans, paragraph/block boundaries, excluded-region gaps, and language applicability information.
- [x] Use an offset-preserving Markdown parser or a rigorously tested parser layer. Record any new dependency and its justification. Account for variable-length fences, tildes, CRLF, container context, inline code, comments, links, headings, lists, and tables.
- [x] Specify what is excluded and what is retained. Keep visible link text, exclude destinations and code, and make treatment of quotations/tables explicit. Preserve plain-text mode rather than stripping Markdown-like characters from all input.
- [x] Define Markdown normalization before implementing backend matching: normalize soft breaks within a paragraph to word-separating whitespace; preserve text adjacency across emphasis/link markup; decode entity and numeric character references. Preserve paragraph, heading, list-item, and retained table-cell boundaries so phrase matching cannot bridge separate blocks. Treat excluded inline code as a gap that cannot fuse words or manufacture a phrase; specify inline-comment adjacency separately according to rendered text.
- [x] Preserve a mapping from normalized prose back to original byte ranges and human-readable line/column positions. Handle discontinuous source segments without inventing a contiguous replacement range.
- [x] Make every backend use prepared prose. Apply sample-size gates after extraction; code/front matter must not count toward the 150-word floor or sentence minimum.
- [x] Share word and sentence segmentation between burstiness and readability. Handle terminal punctuation, abbreviations, decimals, ellipses, Unicode whitespace, and contractions consistently.
- [x] Normalize word punctuation before syllable estimation. Document the remaining approximation and compare a varied fixture set against pinned reference outputs. Follow-up 2026-11-14: six Textstat comparisons, pinned dependency/corpus provenance, native regression expectations, and documented pronunciation/segmentation differences in `docs/readability-reference.md`.
- [x] Define language applicability as supported, unsupported, unknown/uncertain, or detection failure, with the language source and any explicit override recorded. Reuse the result across backends; abstain from English-specific judgments when applicability is unsupported or uncertain, and report detector failures explicitly.
- [x] Resolve the language-detector capability gap before claiming automatic unsupported-language handling. `whichlang 0.1.1` returns a closed-set guess, not a confidence or unknown result; the reviewed Welsh fixture is guessed as English. Validate an uncertainty/rejection mechanism or a replacement detector, and add an explicit language override such as `--language en`. An override is a user assertion recorded in the report, not evidence of automatic recognition. Define short-input and mixed-language behavior and list which backends require English applicability.

**Required regressions:**

- [x] Six em dashes inside fenced code contribute no prose punctuation evidence.
- [x] Adding 160 code words to the same 15-word paragraph does not enable statistical voting.
- [x] A valid four-backtick or longer fence preserves following prose; a shorter delimiter inside it does not close the block.
- [x] Code/front-matter-only input contains no analyzable prose.
- [x] `time`, `time.`, and quoted `time` receive the same syllable count.
- [x] Unicode and CRLF fixtures retain correct original-source locations after normalization.
- [x] `experts agree`, `experts\nagree`, and `experts *agree*` produce equivalent phrase evidence in Markdown mode; `experts\n\nagree` and separate list items do not create a cross-block phrase. Here `\n` denotes an actual newline in the fixture.
- [x] Literal em dashes, `&mdash;`, and `&#8212;` produce equivalent punctuation measurements in Markdown mode, with source locations pointing to the actual characters or references. Plain-text mode preserves literal entity spellings.
- [x] Removing inline-code contents does not concatenate surrounding word fragments or create a phrase across the excluded gap; emphasis and link markup do not insert artificial spaces inside retained words.
- [x] Retain the Welsh probe verbatim: repeat `Mae'r llyfr hwn yn disgrifio hanes y dref a bywyd y bobl sy'n byw yno. Rydym yn gweithio gyda'n gilydd i wella'r ysgol a helpu'r plant. ` ten times. Automatic analysis must abstain from English-specific judgments on this fixture rather than accept the existing English guess. Also test supported English, other supported languages, mixed-language prose, short ambiguous text, detector failure, and explicit override/reporting behavior.

**Acceptance:** inputs with equivalent retained prose and semantic boundaries produce equivalent metrics and votes despite inline markup differences. Changing only the contents of excluded regions cannot change prose metrics or votes. Normalization preserves reliable source mappings and block/gap boundaries. Unsupported or uncertain language cannot silently receive English-specific judgments. The Python cleaner supplies useful cases but is not copied wholesale: its regexes do not constitute complete Markdown parsing.

## Phase 3 — Redesign reports, participation, and finding identity

**Likely files:** `src/score.rs`, `src/backend.rs`, `src/aggregate.rs`, `src/dictionary.rs`, backend implementations, output/config modules.

- [x] Introduce typed document metrics: sentence-length coefficient of variation, MTLD, Flesch–Kincaid grade, compression ratio with algorithm/container metadata, and empirical word-frequency entropy in bits. Include sample sizes and applicability reasons.
- [x] Follow-up 2026-11-14: pin seven synthetic compression/entropy vectors with `lzma-rs` 0.3.0 provenance, exact LZMA-Alone streams, independently computed entropy, boundary/empty/Unicode/repetition cases, and production-backend regressions. See [compression references](../../compression-reference.md).
- [x] Remove arbitrary conversions such as `MTLD / 150` or `1 - grade / 20` into human probability. Represent heuristic strength separately. Future model scores carry method, direction, model revision, and calibration status; probabilities are optional and require identified calibration.
- [x] Reject or report nonfinite measurements explicitly instead of converting invalid computation into apparently valid neutral evidence.
- [x] Return one inspectable outcome per backend invocation, including stable backend identity, family, status, raw metrics, candidate findings/contributions, and abstention/failure reason. Do not discard entropy or abstentions. Multiple backends may belong to the same family.
- [x] Separate backend outcomes from family decisions. Reduce eligible, complete backend outcomes under a documented policy to at most one voting contribution per family; retain the original outcomes and reduction provenance. Informational measurements cannot satisfy the detection participation floor. Reject duplicate backend identities, mismatched score/family identities, duplicate family decisions, and invalid quorum bounds; correlated methods must not multiply participation or agreement.
- [x] Preserve the candidate information needed to rerun effective overlap selection after suppression in phase 6. Distinguish matched candidates, overlap-excluded candidates, rule-suppressed candidates, and selected findings; retain source ranges and rule IDs without counting the same occurrence twice.
- [x] Represent analysis completeness and display truncation separately. Include incomplete reasons and analyzed coverage for stopped work, and emitted/omitted finding counts for display limits. Do not infer complete analysis from a nonempty result or a valid quorum; counts are exact only when the corresponding computation completed.
- [x] Make empty/no-prose detection inconclusive. Document the short-prose policy: line-level lint findings remain useful, while a detection result states its limited coverage and must not imply verified human authorship.
- [x] Preserve dictionary IDs in findings, add stable IDs for punctuation and statistical rules, and publish an ID catalog. Prefer retaining existing IDs or explicitly documenting aliases over silently renaming them.
- [x] Include original locations, applicable sentence/paragraph context, severity, and suggestions. Do not attach a document-wide burstiness result to an arbitrary sentence as if it were local evidence.
- [x] Version the JSON schema and include engine, dictionary, configuration, and metric-method versions needed to reproduce a report.
- [x] If adding a graded heuristic score, document its formula and missing-family behavior; keep it separate from quorum and label it as severity, not authorship probability.

**Acceptance:** two informational outcomes alone cannot produce Clean; empty input is inconclusive; two backends in one family remain independently inspectable but cannot manufacture quorum. Duplicate identities/decisions are rejected. All outcomes remain inspectable; context metrics are emitted even when no tell fires; every actionable finding has a stable ID and reliable location where applicable. A backend failure or interrupted analysis remains explicit alongside any partial verdict, and display-only truncation cannot alter complete votes.

## Phase 4 — Fix dictionary matching and bound work

**Likely files:** `src/backends/vocabulary.rs`, `src/dictionary.rs`, `src/deadline.rs`, input/pipeline modules, dictionary tests and performance fixtures.

- [x] Separate candidate enumeration from overlap selection. For exact entries, use `MatchKind::Standard` with overlapping enumeration, or an equivalent complete candidate path. `LeftmostLongest` plus `find_iter` discards alternatives before boundary validation, so changing the final sort cannot fix the bug. Bound candidate work and memory during enumeration, not after collection.
- [x] Define deterministic overlap selection: choose the longest eligible candidate first, then stable tie-breakers such as original start offset and rule ID; return selected findings in source order. Apply boundary checks and, once available, rule suppression before selection. Preserve candidates for phase 6. Specify regex candidate semantics, including within-rule overlaps and alternation, before claiming general longest-match behavior; do not let one rule's search discard another rule's candidate.
- [x] Test unequal crossing overlaps through exact/exact, exact/regex, and regex/regex paths. On `abcdefghi`, candidates `abc` and `bcdefghi` must retain the latter, including when both are exact entries with `whole_word: false`. With whole-word exact patterns `foo bar` and `foo`, input `foo barx` must retain `foo` after rejecting `foo bar`. Add containment, equal-length tie, dictionary-order, and multi-candidate chain cases.
- [x] Honor exact-entry `case_sensitive` using separate matching paths, or reject unsupported configuration explicitly. Test `ONLYCAPS` against lowercase input.
- [x] Specify Unicode case and word-boundary behavior; validate empty patterns, duplicate IDs, schema versions, and family restrictions. Retain regex compilation size limits.
- [x] Replace repeated whole-prefix location scans with indexed line starts plus indexed character positions or a monotonic pass over sorted offsets. Line starts alone do not prevent quadratic Unicode-column calculation on one enormous line. Replace all-prior-hit overlap scans with an appropriate ordered interval algorithm.
- [x] Bound bytes read, not merely file metadata size. Apply limits to stdin and files. Bound candidate count, candidate-text allocation, and work while enumerating matches; avoid building an unbounded candidate vector before applying a final finding cap. Prefer source ranges over copying matched strings before selection.
- [x] Separate the analysis budget from the display limit. Input/candidate/time exhaustion stops analysis with an incomplete outcome and status `2`, retaining partial evidence and coverage. A display limit applies only after complete policy calculation and reports omitted counts without changing votes/status. If a cap prevents exact counting, suppression, or overlap resolution, it is analysis truncation, not merely shortened output. Audit output must disclose any omitted candidate/suppression records.
- [x] Poll cooperative deadlines before and during substantial loops. Expired work returns a timed-out/incomplete outcome rather than an apparently complete score. Follow-up 2026-11-14: preparation/mapping/segmentation, directive parsing, and statistical loops poll; expired preparation yields an incomplete report with zero coverage. Individual parser/library/allocation operations remain non-preemptible.
- [x] Document operations that cannot be preempted cooperatively. Use process isolation if later native model runtimes require hard timeouts or crash containment.
- [x] Give directory scans deterministic ordering, documented ignore rules, no default traversal of `.git`, build artifacts, or dependencies, and explicit handling of permission errors and symlinks.
- [x] Finish the first-release documentation introduced in phase 1. Remove obsolete scaffolding warnings/comments and unused dependencies, verify installation from the package, and record release-mode binary size and resource measurements. These core checks must not wait for phase 7 integrations.

**Acceptance:** expired-budget probes fail explicitly; large/repetitive and dense-overlap fixtures remain bounded during candidate enumeration; a long single-line Unicode fixture does not reintroduce repeated-prefix location scans. Input/candidate/time truncation reports incomplete execution; display-only truncation leaves completed votes/status unchanged. Unicode locations are correct; overlap, boundary, and case-sensitivity regressions pass. Record release-mode runtime and peak memory on named hardware rather than adding fragile millisecond unit-test limits. Installation and basic core documentation are ready before the first release.

## Phase 5 — Establish evaluation and reconcile research

**Likely files:** new `tests/fixtures/`, evaluation tooling and corpus manifest, `docs/research/`, threshold configuration.

- [x] Build one evaluation workstream covering Python issues [#2](https://github.com/kerryhatcher/nobot/issues/2) and [#9](https://github.com/kerryhatcher/nobot/issues/9), which substantially overlap.
- [ ] Create a versioned corpus with provenance and redistribution rights. Include human and generated prose across technical docs, informal writing, formal writing, lengths, and generators; add edited, mixed-origin, multilingual, and non-native-English slices where reliable labels exist. **Limited scope:** the RAID/HC3 pilots are versioned with provenance but remain partial, biased windows; representative domains/generators and independently labeled nonnative/human-edited data remain open evidence gaps.
- [x] Keep source-related samples and near-duplicates in the same split. Define development data for implementation/feature work, validation data for selecting thresholds and candidates, and a frozen independent test set for release assessment. Record split manifests and permitted uses; do not report validation selection or the best tuning sweep as independent test performance. **Limited pilot scope:** source/near-duplicate components were kept together; the assessment independent set was frozen once and consumed; old RAID v1 was retired after exposure.
- [x] Report precision, recall, F1, confusion matrix, false-positive rate, abstention/coverage, runtime, and slice counts. Report AUC only when a defined continuous score supports a meaningful sweep. **Limited pilot result:** descriptive metrics and source/domain/generator/length slices are reported; no AUC is claimed.
- [x] Parameterize thresholds and cache raw features so sweeps do not repeat extraction unnecessarily. Record confidence intervals or sampling uncertainty and the limitations of small slices. **Deliberate scope:** quorum/caching and reporting are parameterized; numeric backend thresholds remain fixed compiled constants. Cluster bootstrap and degenerate bounds are implemented.
- [x] Compare Rust and Python on shared fixtures. Separate intended differences in preprocessing, overlap deduplication, compression, and error semantics from actual porting regressions. Follow-up 2026-11-14: seven shared fixtures compared against commit `0981b9501b7dd2fb37803cf43298e83edfd508e9` with matched public PyPI core versions; 10 intended differences and 0 regression candidates. See [Python parity](../../evaluation/python-parity.md).
- [x] Follow-up 2026-11-14: harden the evaluation protocol with corpus/config/criteria identity binding, exact-byte content hashes, one-shot atomic independent access, source/near-duplicate grouping, unknown-label reporting, and cached-byte stdin analysis. See [evaluation protocol](../../evaluation/README.md).
- [x] Follow-up 2026-11-14: add external burstiness population-stdev/CV vectors, a standard-library checker, and a production-backend regression; all five vectors reproduced.
- [x] Limited follow-up 2026-11-14: supervisor-owned provenance commit `f6979ad` verified 46 origins, 206 snapshot entries, and 34 unsupported claims. Imported originals were preserved. This is a scoped provenance/source audit, not a full external revalidation; the broader research-claim audit remains limited to that recorded scope.
- [x] Select new signals and threshold changes using development/validation evidence, including false-positive tradeoffs. Freeze the candidate configuration and release criteria before independent test evaluation. Contractions, pronouns, passive-voice proxies, or structural repetition start as informational candidates until validated. **Decision:** adopt no new signals; retain quorum 2/defaults; frozen candidate and criteria were used for the one independent assessment.
- [x] Define test-set access and refresh/retirement rules. Repeatedly accepting or rejecting candidate changes from the same test results turns that set into selection data even without direct access to its text. If test results inform a revision, disclose that use and assess the revised candidate on fresh independent data before making fresh held-out claims; do not iterate toward passing the same test set.
- [x] Establish a versioned, reproducible CI regression corpus and baseline artifact, separate in purpose and reported results from independent release evaluation. CI fixtures are reusable development evidence. Define tolerances from measured variability and never present repeated CI performance as an unseen-test estimate.

**Acceptance:** an evaluation command or script reproduces the CI baseline, exports machine-readable results, supports a documented development/validation sweep, and reports abstentions separately. Split manifests, frozen candidate settings, release criteria, and test-set access/refresh records distinguish selection from independent release assessment. No new default voting rule is justified solely by folklore, a source summary, or parity with the Python constants.

Pilot follow-up 2026-11-14: a limited, MIT-licensed RAID pilot is available at
[`evaluation/corpora/raid-pilot-v1`](../../../evaluation/corpora/raid-pilot-v1),
with a portable source snapshot, 1,100 partial-view rows, deterministic
source/near-duplicate grouping, forced-development viewed sources, dimension
reporting, and freeze/preflight tooling. It does not satisfy the complete
versioned-corpus item above: five RAID domains and most generators are absent,
some cells failed, native-speaker attribution is unavailable, and the corpus is
not representative. Only development/validation evaluation has run. The 218
independent-test samples were later retired as exposed selection data after a Git
diff whitespace exposure; `retirement.json` binds that status, and preflight/
evaluation refuse freeze or independent assessment. No access record was claimed.
A cached
validation quorum sweep retained quorum 2/default thresholds because quorum 1
traded extremely low recall for an unacceptable observed pilot FPR and quorum 3
lost coverage; see the
[cached selection note](../../evaluation/raid-pilot-selection.md). See
[raid pilot](../../evaluation/raid-pilot.md).

Assessment follow-up 2026-11-14: a separate joint HC3 + fresh RAID pilot
(`evaluation/corpora/assessment-pilot-v1`) has 964 samples, 578/193/193 splits,
whole-component old-RAID exclusion, and HC3 viewed question IDs 0-14 forced
development. Authorized release-binary development/validation runs show
known-bad recall (0.0299/0.0550) and are selection evidence only; cached quorum
sweeps retain quorum 2/defaults. Root-owned final criteria/preflight were frozen
at checkpoint `aad622a`; exactly one independent assessment was consumed (193
samples, recall 0.01923, FPR 0.02247) and general authorship qualification is
FAILED / not-qualified. A separate
development-only mechanical mixed-control corpus
(`evaluation/corpora/mixed-controls-v1`, 156 null-label controls) and a
metadata-only cluster-bootstrap summary tool are prepared. See
[assessment pilot](../../evaluation/assessment-pilot.md),
[mixed controls](../../evaluation/mixed-controls.md), and
[summary reporting](../../evaluation/summary-reporting.md).

## Phase 6 — Add scoped suppression and actionable localization

**Likely files:** new suppression/postprocessing module, configuration, report types, CLI output, localization fixtures.

- [x] Implement global/per-path rule ignores and an explicit inline/file convention using stable IDs. Parse directives from original source before comments are excluded from prose.
- [x] Define scope precisely: next line, current block, or whole file. Reject malformed directives clearly and test interactions with code fences and quoted examples.
- [x] Apply the shared order explicitly: candidate enumeration → boundary validation → rule/scope suppression → effective overlap selection → family contributions → aggregation. Before phase 6, suppression is a no-op at this boundary. A rule-specific ignore applies to that rule's candidates, not every candidate overlapping the same source text.
- [x] Preserve candidate provenance, original findings, and suppression reason/scope in JSON. Distinguish suppression from overlap exclusion and produce a separate effective finding set for policy/exit decisions. Disclose display-limited audit records and counts; if candidate information needed to resolve policy was lost to a resource cap, mark analysis incomplete.
- [x] Rerun effective overlap selection from eligible unsuppressed candidates, then recompute affected family votes. Filtering previously selected findings cannot recover shorter candidates already discarded by overlap handling. Keep document-level metrics and local occurrence suppression semantics explicit; local suppression must not fabricate a new document metric by silently deleting text.
- [x] Add an embedded-dictionary regression for `embark on a journey`: ignoring `embark-on-a-journey` must leave the independently enabled `embark` candidate eligible. Test global, per-path, and inline rule-specific ignores; the inverse ignore; suppression of both IDs; and resulting family votes/status. Repeat the cases at display limits to prove rendering does not control policy.
- [x] Offer sentence/paragraph grouping for actual localized findings and targeted editing. Do not compute document-length statistics on isolated sentences just to manufacture local verdicts.

**Acceptance:** suppressed findings remain auditable but do not contribute to actionable status; unsuppressed overlapping rules can still contribute after effective reselection. Boundary tests prove suppression does not leak to adjacent prose or other rule IDs, and display limits cannot affect selection or votes. CLI and future adapters share identical postprocessing.

## Phase 7 — Ship useful output, integrations, and documentation

**Likely files:** output/rendering modules, `README.md`, configuration and limitations documentation, CI workflows, pre-commit configuration, plugin adapter.

- [x] Add SARIF 2.1.0 using stable rule IDs and original-source locations; validate against the schema and include rule metadata, severity mapping, and suppression information where supported.
- [x] Document optional severity-based CI gating and ship a pre-commit entry plus a code-scanning workflow example. Distinguish heuristic findings from operational failures.
- [x] Provide an advisory hook adapter around the installed binary. Map Rust CLI statuses to the host's nudge/silent contract explicitly: Rust status `2` means failure, whereas the legacy Python hook uses `2` for a nudge.
- [x] Embed or package the curated guide and expose it through a command, avoiding reliance on a plugin-root environment variable. Keep detector logic out of the hook.
- [x] Extend the first-release limitations documentation with evaluated performance, coverage, slice uncertainty, and known failure cases. Retain clear language about false positives, evasion, English/unknown-language applicability, and Clean not proving human origin. See [final assessment](../../evaluation/final-assessment.md).
- [x] Extend the existing installation, file/stdin, configuration, status, and JSON documentation with ignores, SARIF, hook translation, dictionary contributions, and integration setup. Document optional capabilities when their own milestones ship.
- [x] Repeat formatting, lint, test, packaging, and release-size checks for the integrated release; remove newly obsolete comments/dependencies and enforce a budget based on phase 4 measurements rather than an unmeasured size claim.

**Acceptance:** the README describes actual commands; integrations exercise the same core; no hidden network calls occur in default operation; default-path tests assert usable output, not merely a nonpanic exit.

## Phase 8 — Add optional model analysis and additional adapters

**Likely files:** optional backend modules and Cargo features, model-management commands, model metadata, model tests, optional MCP/TUI adapters.

- [ ] Keep `lint` for editing findings, `analyze` for raw statistics, and optional model scoring distinct in the CLI. Reuse the same library and report schema.
- [ ] Before porting Python `models.py`, validate formulas and labels against the methods' primary implementations. Label substituted model pairs as adaptations; published thresholds do not automatically transfer.
- [ ] Pin model/tokenizer revisions, record checksums and licenses, require explicit installation/download actions, and support cached offline execution. Make model size and device requirements visible.
- [ ] Use token-aware windows with original-source mapping. Report analyzed coverage and truncation. Define aggregation weights; do not claim averaging when the implementation only returns a list of windows.
- [ ] Preserve typed per-model success, abstention, and failure instead of mixed dictionaries and error strings. Reject nonfinite scores, validate classifier label mappings, and expose unavailable devices/backends clearly.
- [ ] Retain raw model outputs until the phase 5 evaluation process supports calibration. Keep each model's outcome inspectable, then use phase 3's explicit family reducer if voting is enabled. Correlated methods in one family contribute at most one vote; test mixed success, failure, abstention, and disagreement without dropping individual results or inflating quorum. Freeze model/threshold choices before independent release evaluation.
- [ ] Add deterministic mocked failure tests and separately opt-in real-model tests. Enabled real-model tests must fail if every detector errors, rather than accepting a report containing only error strings.
- [ ] Add MCP/TUI surfaces only as thin library adapters, with cross-surface parity tests. TUI analysis needs debouncing and stale-result cancellation; MCP returns structured outcomes without duplicating policies.

**Acceptance:** default builds remain lightweight/offline; missing weights cannot become a clean verdict; long inputs have explicit coverage; model scores identify their method and calibration status. Heavy tests are opt-in but meaningful when enabled.

## Phase 9 — Add meaning-preserving humanization

**Likely files:** optional humanization/provider module, CLI adapter, edit/diff representation, preservation tests, guide documentation.

- [ ] Start with explicit user-invoked, local-provider generation. Expose provider/model/endpoint configuration and clear connection/authentication errors; never silently switch to a remote service.
- [ ] Use localized findings and a curated writing guide to request targeted edits. Preserve factual claims, quotations, names, numbers, citations, URLs, code, and intended voice. Do not instruct the model to invent lived experience or insert errors to resemble human writing.
- [ ] Return proposed edits or rewritten output with a preview/diff by default. Make in-place replacement explicit, atomic, and recoverable; validate response shape before writing.
- [ ] Check protected spans and report uncertain semantic changes. A lower heuristic score is supporting feedback, not the acceptance criterion for a rewrite.
- [ ] Bound rewrite iterations, input size, and provider timeouts. Preserve the original on empty, malformed, failed, or rejected output.
- [ ] Evaluate fidelity and editing usefulness with documented examples and human review, separately from detector scores. Do not promise detector evasion.

**Acceptance:** preservation fixtures retain protected content; failures leave originals intact; proposed changes are reviewable; successful rewrites are assessed for meaning and readability as well as style.

## Issue reconciliation

| Python issue | Treatment in this plan |
|---|---|
| [#1 Plugin-root paths](https://github.com/kerryhatcher/nobot/issues/1) | The pinned branch uses packaged-guide/CLI commands; carry this design into phase 7 and test installation independently of plugin-root variables. |
| [#2 Evaluation](https://github.com/kerryhatcher/nobot/issues/2), [#9 Calibration](https://github.com/kerryhatcher/nobot/issues/9) | Consolidated in phase 5; avoid duplicate evaluation projects. |
| [#3 Duplicate hook engine](https://github.com/kerryhatcher/nobot/issues/3) | The pinned branch has a thin shim; phases 1 and 7 preserve single-engine architecture. Verify behavior rather than assuming the open issue is still wholly unimplemented. |
| [#4 Graded score](https://github.com/kerryhatcher/nobot/issues/4) | Phase 3 allows documented heuristic severity without relabeling it as calibrated authorship probability. |
| [#5 Localization](https://github.com/kerryhatcher/nobot/issues/5) | Phases 2, 3, and 6 preserve source mappings and expose actionable spans. |
| [#6 Limitations](https://github.com/kerryhatcher/nobot/issues/6) | Phases 1 and 4 document core capabilities and bounds before the first release; phase 7 adds evaluation and integration details. |
| [#7 New signals](https://github.com/kerryhatcher/nobot/issues/7) | Phase 5 gates adoption on evaluation; no automatic extra quorum votes. |
| [#10 Stable IDs](https://github.com/kerryhatcher/nobot/issues/10) | Phase 3; prerequisite for suppression and SARIF, as confirmed in issue comments. |
| [#11 Suppression](https://github.com/kerryhatcher/nobot/issues/11) | Phase 6; effective votes and status must reflect suppression, not just rendered findings. |
| [#12 Hidden metrics](https://github.com/kerryhatcher/nobot/issues/12) | Python JSON/TUI already expose context in the pinned branch. Phase 3 brings that capability to Rust with explicit metric semantics. |
| [#13 SARIF and CI](https://github.com/kerryhatcher/nobot/issues/13) | Phase 7, after IDs and source locations are stable. |

## Verification and release gates

### Checks for every implementation milestone

- [x] Run focused regression tests as each bug is fixed, then `cargo test --locked` for the default build.
- [x] Require `cargo fmt --check` and `cargo clippy --all-targets -- -D warnings` once obsolete scaffolding warnings are resolved. Test supported feature combinations separately as optional capabilities appear.
- [x] Confirm repository source changes are scoped to the milestone, preserve unrelated research, and update the handoff with completed work and remaining phases.
- [x] Update documentation for the behavior shipped in that milestone. No command or adapter may silently present a backend failure or incomplete analysis as a successful clean analysis.

### Functional core release, phases 0–4

- [x] Pass phases 0–4 acceptance checks and the common formatting/lint/test checks. Verify the default runtime works without keys, downloads, or network access.
- [x] Exercise the real executable for file/stdin, Markdown hints, JSON, invalid configuration, missing paths, invalid encoding, empty/no-prose input, unknown/unsupported language, explicit language overrides, and mixed-success directories.
- [x] Verify soft-break/entity normalization, block/gap boundaries, exact/regex candidate enumeration, rejected-boundary alternatives, stable IDs, family reduction, and Unicode source locations, including a long single-line fixture.
- [x] Exercise timeouts, oversized inputs, candidate-budget exhaustion, and display limits. Partial analysis returns `2`; display-only truncation preserves complete votes/status and reports omitted counts. Validate JSON completeness fields and deterministic output ordering.
- [x] Preserve candidates and the suppression-before-selection pipeline boundary for phase 6, without requiring suppression syntax or SARIF in this milestone.
- [x] Verify packaging and installation from a clean temporary destination, usable CLI help/README examples, and documentation of configuration precedence, status codes, JSON, language limits, short inputs, resource limits, and uncalibrated heuristics. Record release binary size, runtime, and peak memory on named hardware.

Evidence: `python3 scripts/acceptance.py` passed 9 real-executable checks, including package/install verification; see [core validation](../../core-validation.md). The installed binary was 2,577,328 bytes on the named host. This marks the documented functional-core gates, not the evaluated or optional milestones.

### Evaluated linting and integrations release, phases 5–7

- [x] Keep all functional-core checks passing and pass phases 5–7 acceptance checks. **Scoped acceptance:** engineering checks passed; general authorship qualification failed and is explicitly not claimed.
- [x] Store corpus provenance, split manifests, a reproducible CI baseline, development/validation results, frozen candidate settings, and independent release-evaluation results. Document test-set access/refresh decisions and intentional Python differences. **Limited pilot:** one independent assessment was consumed; old RAID v1 was retired after exposure.
- [x] Exercise suppression through the real executable, including overlapping IDs, scope boundaries, effective votes/status, and audit/display-limit behavior.
- [x] Validate SARIF 2.1.0 schema, source locations, Unicode column kind, severity mapping, and suppression metadata, plus the JSON additions for suppression.
- [x] Verify advisory hook status translation, pre-commit/code-scanning examples, guide packaging, and shared-engine parity. Document the evaluated limitations and actual integration guarantees. See [integration validation](../../integration-validation.md).

### Optional capability releases, phases 8–9

- [x] Keep core and any shipped integration checks passing. Gate phase 8 and phase 9 independently on their own acceptance checks; humanization does not require all detection models. **Optional phases 8–9 remain deferred by user decision.**
- [ ] For phase 8, test supported feature combinations, explicit model installation, cached offline execution, per-model failures, analyzed coverage, family reduction, adapter parity/cancellation, and meaningful opt-in real-model tests. Require phase 5's independent evaluation process before advertising calibrated model verdicts.
- [ ] For phase 9, verify protected-span preservation, reviewable edits/diffs, bounded provider work, and atomic/recoverable explicit writes. Failed, empty, malformed, or rejected output leaves originals intact; fidelity assessment is separate from detector-score improvement.

The first releasable milestone requires the common checks and functional-core gates only. Suppression, independent evaluation, SARIF, and hooks gate the phases 5–7 release; optional capabilities meet their own gates before being advertised. Claims of improved detection require phase 5 evidence, with development/validation selection distinguished from independent test assessment.
