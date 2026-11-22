# nobotrs Humanization Roadmap: Plan Index

This index governs the five existing implementation plans and two additional milestones. Where a task sheet differs from the acceptance criteria below, use this index and reconcile the affected task before implementing it.

## Intent

nobotrs helps people and AI agents write clear English while preserving the author's facts, purpose, voice and qualifications. A portable drafting skill should help an agent write from the author's brief before it runs any command. The offline Rust CLI should help an editor locate grammar, spelling, readability, complexity, formatting and prose problems, compare revisions, and check claims against sources in the same document or repository.

Each suggested edit should identify what a reader might misunderstand, how to improve it, and when the original wording works. Authorship detection is advisory. The frozen independent assessment detected 2 of 104 generated texts and flagged 2 of 89 human texts. General authorship qualification **failed**. Editorial releases are judged by fidelity, comprehension and usefulness to writers. [Independent assessment](../../evaluation/final-assessment.md)

## Evidence that set the direction

- **Owner corpus.** The archive contains 27 posts from 2025-03-10 onward plus “The Crossover Ceremony,” for 28 AI drafts, and 15 human posts. Detection flagged zero in either group, with one AI draft inconclusive. Lint produced 49 findings in 14 AI drafts (1.37 per 1,000 words) and six in three human posts (0.75 per 1,000). The full-archive figures include the medium-confidence human post in decision 2. The human tutorials are older and shorter. These data cannot separate authorship from genre or era.
- **Shipped capability.** Three offline families supply voting signals through vocabulary (32 word entries and 14 phrase patterns), punctuation and burstiness. Three more report lexical diversity, readability and compression. The Bibb fixture earned a Clean verdict despite containing a doubled article. Both the typo and the merged list described in the baseline are useful editing tests.
- **Guidance.** The archived Python drafting skill and op-ed guide supply pre-draft questions and genre-specific examples. Retain the author's real evidence and voice. Remove inherited advice to invent specifics or lived experience. Treat vocabulary lifetimes and the durability of structural tells as hypotheses. Record rule provenance, counterexamples and validation separately. Internal sources live under `$NOBOTRS_INTERNAL_DIR`, including `nobot-python/main/skills/humanize-writing/`, `writing-guides/` and `research/ai-text-detection-2026/`.
- **Evaluation sources.** Beemo pairs drafts with expert edits. APT-Eval supplies human drafts polished by AI. GAO 2008 supplies historical civic controls and WI+LOCNESS supplies learner and native writing. CoAuthor is registered for event-level provenance research without a planned performance measure. Include contemporary human civic prose and unchanged passages as controls. Neither a model score nor an editor changing a passage establishes that a particular suggestion improves it.

## Plans and dependencies

Numbers identify the existing task sheets. The delivery order below puts core editing ahead of optional model experiments.

| Plan | Deliverable and acceptance | Dependencies and status |
|---|---|---|
| 1. [Guidance core](2026-11-21-humanize-1-guidance.md) | Canonical brief, rule-linked guidance and an advisory human/JSON review. Each finding explains the problem, possible edit and legitimate exceptions. | Start here. Task sheet needs the packaging and output corrections below. |
| 2. [Structure and formatting](2026-11-21-humanize-2-structural-tells.md) | Pin the Bibb fixture, build a parallel sentence/block index and report located structural patterns. Preserve justified fragments, dialogue, lists and deliberate repetition in control cases. | Guidance IDs from 1. Fixture preparation can start separately. |
| 3. [Drafting and revision](2026-11-21-humanize-3-revision-loop.md) | Installable drafting and revision skills, CLI reference, advisory hook and before/after comparison. Demonstrate an offline draft from notes and an edit that preserves the author's intent. | Brief and review from 1, unit-aware checks from 2. |
| 6. English copyediting | Pilot offline Rust grammar and spelling support. Evaluate Harper against annotated prose for precision, dialect handling, size and latency. Support project vocabulary. Use Plan 2 units for passage-level reading difficulty, overloaded sentences, heading hierarchy and list consistency. Explain findings in ordinary English with original source locations. | New milestone requiring a task sheet. Reuse 1–2. Test the Bibb doubled article, seeded typos, a proper name, British spelling, quoted text and code. Report insufficient text for unstable reading estimates. [Harper documentation](https://writewithharper.com/docs/integrations/language-server) |
| 7. Project fact consistency | Compare checkable claims within a document and across explicit repository sources. Render both locations, entity, attribute, period, unit, qualifier and evidence status. Begin with tightly scoped quantities and dates. | New milestone requiring a task sheet. Reuse source mapping from 2 and fidelity cases from 3. The worktree design is a draft. Acceptance covers a conflicting FY27 total, a compatible FY26 figure, a missing required fact and an ambiguous alias. [Facts design](../specs/2026-11-21-nobotrs-facts-design.md) |
| 4. [Optional model hotspots](2026-11-21-humanize-4-model-hotspots.md) | Section-aware windows and diagnostics for three local models. Promote hotspots only after blinded editors find more actionable passages than with section-level heuristics at comparable review effort. | After the core editorial milestones. Requires 1–3 and Plan 5 validation. |
| 5. [Evaluation](2026-11-21-humanize-5-evaluation.md) | Corpus registry, baselines, per-rule utility, editor alignment, blind reader study, hotspot validation and a separate scoring decision. | Task 1 can start alongside 1. Task 2 needs the pinned fixture and review output, and its full-model run needs 4. Task 3 needs the rules under test. Tasks 4–5 follow their editing workflows, Task 6 follows 4, Task 7 follows the frozen protocol in decision 4. |

## Implementation and release criteria

- **Package and CLI contracts (1–2).** Ship the embedded brief with its loader. Include guidance and test fixtures in the Cargo archive and verify installation and fixture tests from the archive. Preserve existing guide JSON fields, SARIF semantics and voting behavior or version the affected contract. Check suppression before ranking, compute counts before truncation, then apply the display limit once. One logical finding gets one result, with an optional location for document-wide findings. Distinguish completed, skipped and incomplete checks. Test limits zero and one, a deadline, overlapping rules and a disabled family. Bound structural analysis so adding it to review cannot change legacy detection exits or budgets.
- **Source mapping (2, 6, 7).** Preserve the statistical baseline's sentence segmentation. Keep normalized display text separate from navigation ranges in original UTF-8 bytes. Test CRLF, Unicode punctuation, escaped Markdown, nested lists, inline code and table headers. Keep fact anchors within their logical block and carry row and column context when comparing table values.
- **Skills and fidelity (1, 3).** Bundle the brief as a relative Markdown reference and exercise copied skill directories in Pi, Claude and Codex with no checkout, executable or network. Start from purpose, audience, supplied facts and requested action. Offer optional publishing guidance only where relevant. With the CLI installed, exercise the same example through review, compare and the hook, including stdin and error exits. Preserve link targets, fenced code, quotes and approximate quantities. Test swapped budget attributions, dropped negation and “may” becoming “will.” Where automation cannot decide, direct the editor to the source and record unresolved questions or author-approved changes. [Agent Skills specification](https://agentskills.io/specification) · [Google publishing guidance](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)
- **Facts (7).** Define supported file types, source authority, exact numeric normalization, stable ordering and bounded comparisons. An absent source, unresolvable entity or unsupported claim must remain visible. A missing claim requires an identified expectation, such as a source brief or prior draft. Human adjudication distinguishes an error from a legitimate disagreement. Evaluate precision and missed conflicts using independently annotated pairs. Keep raw local fact indexes private by default.
- **Reader outcomes (5).** Compare drafting from notes and revision of existing prose against a competent ordinary editing prompt as well as the naive condition. Blind readers to conditions. Count unsupported additions, omissions and changes to meaning as fidelity failures. Test comprehension with a source-grounded question. Track length, ties, accepted findings and uncertainty across sources and readers. At 70 readers, 12 substantive ratings each exactly fill the 120 × 7 assignments. Budget attention checks separately and replace excluded ratings before claiming coverage. [Paraphrase testing](https://digital.gov/guides/plain-language/test/paraphrase-testing)
- **Optional diagnostics (4–5).** Verify tokenizer and normalized-to-source offset parity, opening versus full coverage, short-document handling, partial-window failures and latency against the configured deadline. Record model, license, settings, guide revision and coverage. Compare stable report fields explicitly and version schema changes that affect frozen-run identity. Keep score-ranked hotspots out of drafting instructions and automatic revision loops.

## Cross-plan decisions

- **The reader is the objective.**
  - Guidance never advises fabricating experience, personas, sources, names or numbers.
  - Specificity means surfacing the writer's real facts, or asking the writer for them.
  - When no real fact exists, the guidance says to cut the generic claim rather than invent one.
  - For publication, follow the applicable venue and provider disclosure requirements.
- **Advisory, not gating, for agents.** `review` and `compare` exit 0 on completed analysis and 2 on errors. The exception is `compare`, which exits 1 when a hard fact invariant (numbers, quotes, URLs, code) is broken. `lint`, `detect`, quorum, thresholds and exit semantics stay unchanged unless Plan 5 Task 7 approves a change.
- **Leverage order is part of the data.** Every guidance entry carries `leverage` 1–5 (1 = content and specificity, 2 = structure, 3 = rhythm and voice, 4 = punctuation and formatting, 5 = vocabulary). `review` sorts by it, so agents fix high-leverage issues first and don't chase vocabulary zero.
- **Stop criteria beat zero findings.** Allow a justified keep at any leverage and record deliberate factual corrections. Stop when priority findings are resolved or accepted and fidelity questions are answered. Bound the loop and return outstanding questions to the author when another pass makes no substantive improvement.
- **External detectors are second opinions.** GPTZero and the OpenRouter judge stay opt-in, informational and never voting. Rewrite loops must not iterate against a detector score.
- **Local corpora stay local, and Beemo content is never committed (owner rule, 2026-11-21).** Beemo, APT-Eval, CoAuthor, GAO and WI+LOCNESS are read from `$NOBOTRS_INTERNAL_DIR` (default `/mnt/storage/projects/nobotrs/docs/internal`) and never committed.
  - This covers raw text, excerpts, example spans, agent rewrites of Beemo samples, reader-study packets and responses, and vendor responses about them.
  - Commits may carry only counts, rates, intervals, rule IDs and hashed sample IDs.
  - `scripts/check_no_local_corpora.py` (Plan 5 Task 1) will check this. It should fail if any tracked or staged file shares a 12-word shingle with a local corpus, and run in `scripts/acceptance.py` whenever `$NOBOTRS_INTERNAL_DIR` exists.
  - The owner approved publication of the 43 owner posts. Their [manifest](../../../evaluation/corpora/owner-posts-v1/manifest.json) records byte hashes, provenance and publication review. Check staged bytes and allowed public report fields. Report explicitly when the local corpus guard could not run.
- **No new default runtime dependencies.** Model features stay behind `models-*` features.

## Baseline

Fixture: `evaluation/fixtures/bibb-fy27.txt`, an excerpt of the owner's AI-drafted post "Out of Runway: The FY27 BCSD Budget" (minimal human edits). SHA-256 `5c45d6d3edb1f09cf567915a1ea14699316fdeefe7576d9ac805aa7d69aa23d4`, 2,236 bytes, 2,192 characters. Preserve its bytes, including the headings, plain list lines, curly quotes, the "That’s a the state" typo and final punctuation.

Offline results reproduced in the worktree at `aef3b23` with the fixture above (untracked at review time):

- **Offline:** Clean, with three participating families.
- **Vocabulary:** zero matches.
- **Punctuation:** votes strong on 9.0 effective em dashes (2.59 per 100 words), all of them list separators. The verdict stays Clean only because the quorum is 2.
- **Other metrics:** sentence-length CV 0.9920, MTLD 199.3117, Flesch–Kincaid grade 9.2849, LZMA ratio 0.6544, entropy 7.6634 bits/token.
- **Segmentation:** 21 sentences. The current segmenter merges the first heading into the first sentence, and the "The categories, roughly:" lead-in plus twelve following lines into one 631-byte sentence (prose bytes 846–1477).

**Historical GPTZero observation.** The original run returned AI_ONLY with AI probability 1.0000. It ranked the gerund series ("After consolidating schools, freezing pay, packing…, and contracting out…") first, the $8 million shortfall sentence second and "Still short." third.

**Local model opening outputs on the plain fixture.** The [new opening run](../../../evaluation/baselines/bibb-fy27-models-opening/run.json) reproduced the historical outputs below.

| Model | Output | Tokens | Coverage | Truncated |
|---|---|---|---|---|
| Desklib | −6.1111 logit | 512 | 99.91% | yes |
| ConPara | −9.7562 logit margin | 512 | 97.99% | yes |
| DetectorScope | −0.4390 logit | 530 | 100% | no |

All three leaned human, which is wrong for this text. The pinned DetectorScope runtime emitted a tokenizer-regex warning (Plan 4 Task 1 gates on it).

In the [full-coverage run](../../../evaluation/baselines/bibb-fy27-models-full/report.json), each model covered 100% of the tokens in four windows. The aggregate outputs were −4.1073 for Desklib, −6.7434 for ConPara and −0.1077 for DetectorScope. The models use different score scales.

Five OpenRouter judge runs returned HUMAN at reported confidence 85–90. The new GPTZero request returned HTTP 403. The historical GPTZero observation above remains the only successful GPTZero measurement recorded here. [External baseline summary](../../../evaluation/baselines/bibb-fy27-external/summary.json)

**Reproduction:**

```sh
cargo run --locked -- analyze evaluation/fixtures/bibb-fy27.txt --language en --format json
cargo run --locked --release --features models-encoders,models-detectorscope -- analyze evaluation/fixtures/bibb-fy27.txt --language en --format json --models desklib,conpara,detectorscope --models-dir "$NOBOTRS_MODELS_DIR"
```

For all eleven backends (six offline, three local models, two external), build with `--features models,api-clients` and append `--gptzero --openrouter-judge`. Set `GPTZERO_API_KEY`, `OPENROUTER_API_KEY` and `NOBOTRS_MODEL_PYTHON`.

## Owner decisions and outstanding work

1. **Owner posts corpus: resolved.** The owner approved committing the posts (2026-11-21). They go under `evaluation/corpora/owner-posts-v1/samples/`. The repo is public.
2. **"Better Python Logging" (2025-03-07): resolved.** The owner recalls writing it, but it may have been edited during later site migrations. It is labelled `human` with `provenance_note: "possibly edited during migration"` and `confidence: "medium"`. It is excluded from primary metrics and included only in a sensitivity analysis.
3. **Vendor baselines.** Plan 5 Task 2 runs external analysis only on the Bibb fixture. The five repeats apply to the OpenRouter judge. Owner-corpus baselines use offline and local models.
   - Raw GPTZero responses stay local. Its published terms restrict systematic retrieval to compile a collection without permission. Verify the applicable agreement before expanding retrieval or publishing output. [GPTZero terms](https://gptzero.me/terms-of-use.html)
   - **Done 2026-11-21, with owner approval:** the two raw live captures in `tests/fixtures/gptzero/` were removed from git history. Both unpushed local branches (`gptzero`, `openrouter`) were rewritten from the spike commit onward, so every commit now carries hand-written synthetic fixtures with the observed schema (marked `_synthetic`, all-zero IDs). The spike-notes line was corrected. Backup refs and branch reflogs were expired and the repo was pruned, and the old blobs and commits no longer exist. The new hashes are spike `9a054ed`, comparison `cc47e35`, docs `6712e28`, judge `bf3e5e9` and cap fix `6a0b21b`. The GPTZero tests (12) and default-build tests (2) pass with the synthetic fixtures. The hand-written essay used as test *input* in `tests/gptzero_backend.rs` and `tests/openrouter_judge.rs` is not vendor output and stays.
   - The history purge above completes the rewrite instruction in Plan 5 Task 2. Skip that obsolete step.
   - For owner texts, Task 2 already records the serving provider and `ai_generated: true`. Verify the applicable route and model terms before publishing replies and carry disclosures into reader-facing exports. OpenRouter defers output ownership to model terms. DeepSeek's Open Platform terms address AI-output disclosure in §8.1. [OpenRouter terms](https://openrouter.ai/terms) · [DeepSeek Open Platform terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html)
4. **Error budgets: accepted (2026-11-21).**
   - Human false-positive rate: the upper bound of the 95% Wilson interval must be ≤ 5% overall and per genre, and no worse than the current release.
   - Recall: must exceed the current release, with the difference's interval excluding 0, and by at least 10 percentage points.
   - Apply these gates only to changes in detection votes or thresholds. Before selecting candidates, pin the comparator commit, features and configuration. Freeze source-disjoint held-out membership, genre counts, exclusions, paired recall analysis and the handling of underpowered groups in a protocol separate from the post-run decision report. Compare observed false positives on the same held-out examples.
   - With a two-sided 95% Wilson interval and zero false positives, the upper bound is 20.4% at 15 independent human documents and just under 5% at 73. Plan 5's ten-document reporting threshold cannot establish a passing genre. Collect sufficient independent sources for each claimed genre. If evidence is insufficient, retain the informational outcome. Any relaxation of the accepted budget requires a separate owner decision.
5. **Readers: resolved.** The study uses 70–350 blind readers (Plan 5 Task 5). The participant budget, collection platform, recruitment and consent wording are **TBD (deferred by the owner, 2026-11-21)**. They must be settled before Plan 5 Task 5 Step 4.
6. **Beemo excerpts in the reader study: TBD (deferred by the owner, 2026-11-21).** Showing Beemo excerpts to readers is distribution, not a commit (CC BY-NC 4.0 human outputs; generating-model terms on model outputs). Plan 5 Task 5 is written for 40 sources including 12 Beemo samples. If this is declined, it falls back to the 28 owner drafts alone (84 pairs). Settle before Plan 5 Task 5 Step 4.

## Status

The offline CLI implements review, compare, copyedit and project fact checks. The drafting and revision skills ship with relative guides. Plans [6](2026-11-21-humanize-6-copyediting.md) and [7](2026-11-21-humanize-7-facts.md) have implementation sheets. See the [copyediting pilot](../../evaluation/copyediting-pilot.md) and [fact-checking pilot](../../evaluation/project-facts-pilot.md) for measured coverage and known limitations.

The [scoring decision](../../evaluation/humanize-v1-decisions.md) retains the released defaults. The owner development set had 14 high-confidence human documents. Even zero false positives leaves an upper confidence bound above the release budget. Five external judge runs on the pinned Bibb text returned HUMAN. GPTZero returned HTTP 403. Neither vendor supplies an authorship label for evaluation.

The offline rule evaluation reviewed 7,157 local corpus texts with zero operational failures. Located findings overlapped expert edits at 1.23 times the matched random-span rate (95% interval 1.17–1.30). The blinded reader study and editorial validation of model rankings are follow-up research. The offline editing workflows can ship before those studies, with model passage rankings labeled diagnostic. [Evaluation methods and results](../../evaluation/README.md)

The local-corpus release gate uses the 12-token exact-match rule with 29 owner-approved historical exceptions. Each exception is tied to frozen fixture bytes and a specific corpus sample. [Guard audit](../../evaluation/guard-audit-2026-11-21.md)

Opening and full coverage completed on the Bibb fixture for all three local models. The resumed owner-corpus sweeps each fully scored 41 of 43 posts and skipped two for insufficient context, with zero failures or missing results. Owner-corpus AUROC and the DetectorScope feature survey are available as development diagnostics. [Coverage and reports](../../../evaluation/reports/owner-model-diagnostics-status.json) · [Model evaluation and recovery](../../local-models.md)
