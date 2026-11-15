# nobotrs remediation handoff

## CURRENT: RAID pilot v1 retired; corpus checkpoint 993956a is committed

The limited RAID pilot `evaluation/corpora/raid-pilot-v1` is committed at
checkpoint `993956a`. Its 218-sample independent-test split is **retired as
exposed selection data**. After that checkpoint, a supervisor
`git diff --cached --check` on the staged raw corpus printed trailing-whitespace
passages; the output was large and some passages were visible. Conservatively all
218 held-out samples are retired. `retirement.json` binds the current manifest/
content identity, records the exposure, and disables independent assessment and
freeze. Preflight reports `preflight-passed-retired` and refuses `--freeze`; the
evaluator refuses `--split independent-test`; development and validation remain
usable. No independent detector run occurred and no access record was claimed.
Original manifests, splits, results, and audits are preserved; nothing was reset,
reshuffled, or whitespace-normalized. `.gitattributes` marks raw corpus samples
and source response JSON/JSONL payloads `-text -diff`. Reviewers must not display
held-out payloads.

The continuation text below is a historical pre-exposure record retained for
audit. Statements about an "unopened" independent split describe the state before
the exposure and are superseded by this retirement status.

Continuation 2026-11-14 (limited RAID pilot, curation, preflight; corpus
checkpoint `993956a` committed, later retirement/safeguard edits uncommitted):
added `scripts/curate_raid_pilot.py`, `scripts/raid_pilot_preflight.py`, and
`scripts/test_curate_raid_pilot.py`, and generated
`evaluation/corpora/raid-pilot-v1` outside the Cargo package include. The pilot is
built from the copied datasets-server responses at pinned revision
`865cac74188466cb0c3b7574a10204007b57a459`: 35 successful queries (22 nonempty,
13 empty), 12 failed jobs, 1,100 rows, all partial views. The portable source
snapshot copies the exact response bytes, dataset card (MIT declaration), and
upstream Liam Dugan MIT `LICENSE`; `source/acquisition.json` uses relative
`responses/<file>` paths and retains the original acquisition SHA-256. Fixed
metadata `retrieved=2026-11-14`, `retrieved_timezone=America/New_York` is bound
through manifest, audit, and provenance; no wall-clock date is used.

Rows are rejected/recorded for malformed fields, empty text, unsupported model,
truncated cells, query mismatch, or duplicate upstream ID. The real snapshot had
0 rejects. Accepted rows are unioned by upstream `source_id`, exact normalized
text, and 5-word-shingle Jaccard >= 0.8 before deterministic source-group splits.
The five supervisor-identified viewed source IDs and one source displayed during
schema inspection were forced to development with all component members. The
stable seed is `raid-pilot-v1-2026-11-14`; splits are 662 development / 220
validation / 218 independent-test (146/62/42 components). Labels are the upstream
assertion (`human` for model=human, `generated` otherwise), not universal truth.
Dimensions cover domain, generator, attack, language hint, length, upstream split,
and label; native-speaker status is absent and not inferred. The language policy
remains default-unknown with no per-sample overrides.

Hashes: manifest `dcc538e2fe6dcbb7ad5ff99dc0886d235f105297be161ee77f40745d8ed3ddfa`,
corpus content `349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d`,
curation `a965a4bd2ed0669a47caf17a8d4ba9437c491935781b051729db4865e1619f28`.
Preflight binds manifest/content/config/criteria/binary and passed for
`target/debug/nobotrs` (`2a606f3b92ad4d0e717102cbabb4e1cced4d2b35aff98a6828e2484fb0807aae`);
no access record was claimed. A replay from the copied portable source in a second
temporary directory reproduced identical manifest/audit/summary bytes, both
content IDs, source binding, split counts, component counts, and grouping counts.
Development (662) and validation (220) evaluation ran only; independent-test text
and results were not opened. The low pilot recall and imbalanced label mix are
disclosed as limited-selection observations, not accuracy certification. No
defaults/thresholds changed, no commit or push was made. Details:
`docs/evaluation/raid-pilot.md`.

Cached validation selection: `scripts/raid_pilot_cached_sweep.py` reused the
existing validation family votes without rerunning the detector and persisted
`evaluation/corpora/raid-pilot-v1/selection/validation-cached-sweep-v1.json`
(SHA-256 `f21547733dc7921799f109336b51cc36b23f157d02ba4a53408dab114bd8c9dd`),
documented in `docs/evaluation/raid-pilot-selection.md`. Quorum 1: TP66 FP14
FN100 TN40, recall 0.398, FPR 0.259. Quorum 2: TP1 FP0 FN165 TN54, recall 0.006,
FPR 0. Quorum 3: covered 166/220, TP0 FP0 FN114 TN52, 54 abstentions. The
selection decision retains quorum 2 and existing default thresholds unchanged:
quorum 1 trades extremely low recall for an unacceptable observed pilot FPR, and
quorum 3 loses coverage. This is biased-pilot selection evidence, not independent
test performance; no tuning used held-out data.

Evaluation environment isolation: `scripts/evaluate.py` now removes every
`NOBOTRS_*` variable from detector subprocess environments, always passes an
explicit config path, and uses a temporary empty `{}` config when no `--config`
is supplied so the binary resolves its own defaults without platform or
`NOBOTRS_CONFIG` lookup. For a supplied partial config, it verifies supplied keys
against `report.settings` and records the complete resolved settings and hash.
The hostile `NOBOTRS_QUORUM`/`NOBOTRS_CONFIG` synthetic regression and a real
CI-baseline hostile-environment run both passed.

Retirement (supersedes unopened claim): after commit `993956a`, the supervisor
ran `git diff --cached --check` on the staged raw corpus. Git printed
trailing-whitespace passages from raw payloads; output was large and some
passages were visible. Conservatively all 218 independent-test samples are retired
as exposed selection data. `evaluation/corpora/raid-pilot-v1/retirement.json`
(SHA-256 `917de1bc74a23248738512e17951c6307f86ac4509d359ef42a61bf2e96783c1`)
binds the current manifest/content hashes and records the exposure. Original
manifests, splits, results, and audits are preserved; nothing was reset,
reshuffled, or whitespace-normalized. Preflight refuses freeze; the evaluator
refuses `--split independent-test`; development/validation remain usable. A new
`.gitattributes` marks raw corpus samples and source response JSON/JSONL payloads
`-text -diff` to preserve bytes and prevent whitespace/content diff dumps.
Reviewers must not display held-out payloads. No independent detector run
occurred and no access record was claimed.

Independence audit: `scripts/audit_raid_pilot_independence.py` generated
`evaluation/corpora/raid-pilot-v1/independence-audit.json` (SHA-256
`8da025ff4f9deb03ef9fe7978c5fc5e03f308331ce38661554dc73bb1c67c3ec`). It
preserves the complete evaluated development (662) and validation (220)
sample-ID lists with per-ID content hashes and ID-set hashes, asserts they are
disjoint from the 218 held-out IDs, and reconstructs the deterministic split from
manifest metadata. The manifest hash changed three times for provenance metadata
only (`9af3b652...`, `24fea295...`, `dcc538e2...`), while
`corpus_content_sha256` stayed `349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d`
and split/component counts stayed 662/220/218 and 146/62/42. Because the content
hash includes every sample's ID, file, split, source group, label, slice, and
content hash, this is cryptographic evidence that no sample ID or split
assignment changed after the first development/validation predictions. No split
was reshuffled. The additional poetry source
`527dc536-7b69-4c2f-94af-afeb85894a07` was added to the initial session-viewed
list before the first corpus generation and before any detector predictions; the
first generation already had it in development. Earlier manifest/result files
were overwritten during metadata-only regeneration, so the audit records the old
generation identities and relies on the invariant content hash plus unchanged
deterministic inputs; current result files bind generation 3. The curator now
refuses nonempty/symlinked output directories and never rmtree()s experiment
history; replay/versioning requires a fresh path. The audit retains its historical
"no text or detector result opened" fields but adds the superseding retirement
status: the Git-diff exposure displayed some raw held-out passages, all 218 are
retired, and independent assessment/freeze are refused. No independent detector
result was read and no access record was claimed or reset.

Continuation 2026-11-14 (evaluation protocol, Python parity, burstiness reference):
the first functional-core milestone was committed as `d15b767` after supervisor
verification. New evaluation work is uncommitted. `scripts/evaluation_protocol.py`
and the rewritten `scripts/evaluate.py` bind corpus revision, manifest/content/
configuration/release-criteria hashes and criteria ID; require SPDX-like licenses
and verifiable provenance; verify exact file-byte hashes (including CRLF/LF);
preserve null/unknown labels outside accuracy denominators; reject source-group,
near-duplicate-group, content-hash, normalized-text, and 5-gram near-duplicate
leakage across splits; and bind the binary SHA-256 into the frozen access record.
Independent access is claimed before reading test text via an exclusive lock
plus atomic record replace. Stale, reused, mismatched, and locked access records
are rejected. Verified bytes are analyzed through stdin with Markdown inferred
from the file extension; development/validation/regression runs do not open
held-out independent text and report the verified subset separately. Output
records binary SHA-256, engine/dictionary/metric-contract versions, and metric
methods. A held-out file may be absent while its declared metadata participates
in grouping. The legacy regression manifest and `docs/evaluation/ci-baseline.json`
still pass unchanged. Cargo now includes only `scripts/*.py`; `.gitignore` covers
Python caches, and package acceptance rejects `__pycache__`, `.pyc`, `.pyo`, and
`.pytest_cache` entries. Verified with caches present after the Python tests.

`python3 scripts/test_evaluation_protocol.py` passed 18 unittests. The pinned
Python comparison harness (`scripts/compare_python_reference.py`) compared the
seven shared fixtures against commit `0981b9501b7dd2fb37803cf43298e83edfd508e9`
using matched public PyPI versions (textstat 0.7.13, lexicalrichness 0.5.1, nltk
3.10.0, pyphen 0.17.2, typer 0.26.8) because the archived private registry was
unavailable (401). It pins expected reference-file SHA-256 values from the supervisor's trusted
`git archive` capture, rejects modified or mislabeled archives, and found 10
intended differences, 0 regression candidates. The three archive-identity/tamper
regressions passed. See `docs/evaluation/python-parity.md`.

Added external population-stdev/CV burstiness vectors in
`tests/fixtures/burstiness-reference.json`, `scripts/check-burstiness-reference.py`,
and `tests/burstiness_reference.rs`; all five vectors reproduced, with the
below-word-floor case abstaining. Added `docs/evaluation/building-auditable-notes.md`
with hard-negative, ablation/collateral, OOD/FPR, and Table 4 hypothesis-only
lessons. SAEs/models/MCP/TUI/humanization remain deferred. The supervisor is
acquiring a small versioned RAID subset; no independent release evaluation or
access record was run or consumed.

Continuation 2026-11-14 (compression/entropy and functional-core acceptance):
added seven pinned synthetic compression/entropy vectors in
`tests/fixtures/compression-reference.json`, a standard-library checker
`scripts/check-compression-reference.py`, and a production-backend regression
`pinned_compression_reference`. The fixture pins the `lzma-rs` 0.3.0 checksum,
LZMA-Alone header, exact stream hex/SHA-256, length, ratio, and independently
computed token entropy. The checker decompresses every stream with Python
`lzma.FORMAT_ALONE`; this is container/regression evidence, not Python preset-6
parity. See `docs/compression-reference.md`.

Added `scripts/acceptance.py`, a repeatable real-executable runner for the
documented functional-core gates: file/stdin, Markdown normalization and source
locations, candidate disposal/boundaries, stable IDs, family reduction, language
policy, failures, mixed scans, budgets, display truncation, long Unicode lines,
and package/install verification. It passed 9 checks; the installed binary was
2,577,328 bytes. Packaging now anchors root include patterns with `/`, fixing an
untracked imported-research `README.md` that Cargo had matched at nested depth.
The imported research was not modified. See `docs/core-validation.md`.

Remaining: licensed authorship corpus/evaluation, Python parity, burstiness
external reference, and optional phases 8–9. No thresholds, accuracy claims, or
calibrated probabilities changed. No commit or push was made by this worker.

Continuation 2026-11-14: the readability/deadline follow-up is committed as
`7592e89`. Added six pinned LexicalRichness 0.5.1 MTLD vectors, a development-only
reference checker, and production-backend comparisons; see `docs/mtld-reference.md`.
Fixed the MTLD and readability evidence-only tests to assert English applicability
and require a scored result, rather than passing silently on abstention. Pi/Ornith
performed the MTLD test work under supervision, with context resets between tasks.
Licensed corpus evaluation, Python parity, and the broader release checklist
remain open. No pushes were made.

Follow-up 2026-11-14: six pinned Textstat readability comparisons and a reproducible
development-only checker now cover varied English prose, including pronunciation
and segmentation differences. See `docs/readability-reference.md`. Added cooperative
polling during document preparation, sentence segmentation, suppression parsing,
and statistical backend loops. Expired preparation discards unfinished prose and
returns an incomplete report/status 2 with zero analyzed coverage. Native parser,
segmentation, allocation, regex and compression operations remain non-preemptible
between polls. Pi/Ornith performed supervised readability/lexical-diversity edits;
the supervisor corrected a faulty fixture draft and implemented the supporting
reference checker and preprocessing/other backend changes. This follow-up was
committed locally at the user's request; see Git history. It was not pushed.
Imported research remains untouched. Broader statistical references
beyond readability, licensed authorship evaluation, Python parity, and the
unchecked release gates remain open. The October record below is historical.

Updated 2026-10-10. Active plan: `docs/superpowers/plans/2026-10-10-nobotrs-review-remediation.md`. The July handoff is superseded; reviewed code can be revisited when a regression demonstrates a defect. Work is on `main`, starting at `eb02215c03d119f1ca698dd84f718c37a3530d73`. Implementation and documentation are committed together; consult Git history for the commit ID.

Starting local changes were untracked imported research under `docs/research/thor-ai-writing/` and the active plan itself. Those originals are preserved. Baseline: `cargo test --locked --offline` passed 60 unit tests and one CLI smoke test; commands were stubs. Python reference in the plan is `0981b9501b7dd2fb37803cf43298e83edfd508e9`, but the adjacent local Python checkout is `main` at `27e6ce0f65c28ef563db7aa2fd997aff4d86724d`; do not treat it as the pinned reference. On 2026-10-10, GitHub public API returned Rust main at the reviewed commit, 0 Rust open issues and 13 Python open issue entries. No issues were closed or externally modified.

Implemented: shared library/engine; working detect/lint/analyze/scan/config/guide; bounded UTF-8 file/stdin loading; JSON configuration with CLI/environment/file precedence and origins; deterministic human/JSON/SARIF output; prepared Markdown/prose source mappings and shared segmentation; conservative unknown language policy with explicit overrides; raw versioned metrics; informational/voting separation and family reduction; overlapping exact/regex candidates and case handling; candidate/deadline/display budgets; stable IDs, context references and suppression before overlap selection; integration adapters and initial evaluation tooling/documentation.

Tests replace obsolete probability and raw-span contracts with executable regression coverage. Permanent probes include code/frontend matter exclusion, long fences, soft-break/emphasis/link equivalence, entities/CRLF/Unicode locations, Welsh uncertainty, overlapping/boundary-valid dictionary candidates, named family outcomes, input/candidate/time budgets, display independence, suppression, config precedence and mixed directory errors. See `docs/core-validation.md` for final checks and measurements.

Remaining gates: phases 5–7 require a curated licensed authorship corpus, development/validation tuning evidence, independent frozen release assessment, more varied pinned statistical reference fixtures, and Python parity against the specified branch. The CI baseline is behavior evidence only. Model/tokenizer choices, revisions/checksums/licenses, optional model runtime, MCP/TUI, and humanization are not implemented (phases 8–9). The user explicitly chose to select models and revisions later, deferring these optional phases. No threshold improvements, accuracy, calibrated probabilities, semantic-preservation or release-ready optional capabilities are claimed.

Use `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked`. Packaging excludes imported research without deleting it. Default operation is offline. Continue from the active plan's unchecked items; do not reset the independent test-set access policy or report synthetic CI fixtures as authorship truth.
