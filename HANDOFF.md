# nobotrs remediation handoff

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
