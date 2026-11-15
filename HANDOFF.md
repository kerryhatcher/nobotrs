# nobotrs remediation handoff

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
