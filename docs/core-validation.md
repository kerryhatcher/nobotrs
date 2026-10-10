# Core validation record

Date: 2026-10-10. Baseline: main at `eb02215c03d119f1ca698dd84f718c37a3530d73`, 60 unit tests + 1 stub CLI smoke test passing. Imported research and the original remediation plan were untracked before implementation and were preserved.

The implemented core was verified with `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked --offline`: 40 backend/unit tests, 5 executable tests, and 13 remediation tests passed. Old probability/raw-span tests were replaced when their contracts changed; test count is not an accuracy measure. Source modifications were reviewed with `git diff --check`.

The seven-fixture behavior baseline is `docs/evaluation/ci-baseline.json`, reproduced with `scripts/evaluate.py --check`. All fixture authorship labels are unknown. It provides regression evidence, not independent precision/recall/false-positive estimates. Raw metric caches and run timings are recorded separately from the stable fields compared by CI.

SARIF outputs for findings, rule suppression, Unicode/discontinuous Markdown locations, and empty input passed JSON Schema validation using jsonschema 4.26.0 and the SARIF 2.1.0 schema from `https://json.schemastore.org/sarif-2.1.0.json`. The temporary validator is a development check, not a runtime dependency. The output embeds rule metadata and omits fake locations for document-wide findings.

`cargo package --locked --offline --allow-dirty` verified the packaged crate. It was unpacked to `/tmp/nobotrs-install-test`, installed with `cargo install --locked --offline --path ... --root ...` in a fresh build directory for the final package, and exercised for stdin JSON findings, packaged guide, missing-file diagnostics, and advisory status translation. The package explicitly excludes imported research; code/data license separation remains intact. Validation did not change upstream issues, upload integration results, or install a global binary. The user subsequently authorized committing and pushing the implementation.

Release measurements were taken with `/usr/bin/time -v` on an x86_64 AMD Ryzen 7 5800X 8-Core Processor host (16 logical CPUs), optimized release profile, Rust 1.98.1 toolchain:

| Workload | Elapsed | Peak RSS |
|---|---:|---:|
| `detect README.md --format json` | below 0.01-second timer resolution | 5,592 KiB |
| 165,000-byte single-line Unicode fixture, `display-limit 0` | 0.02 seconds | 14,128 KiB |

The Unicode fixture was `("é " * 50000) + ("delve leverage " * 1000)`. Both runs completed with status 0 and full analysis coverage. Display suppression did not remove the effective finding count or family contribution. The stripped release binary was approximately 2.57 MB. CI uses a measured-envelope budget of 8,000,000 bytes, with headroom for compiler/target variation. These are named-host observations, not portable timing/RSS guarantees or fragile unit-test thresholds.

Remaining core acceptance work includes a broader set of pinned statistical reference outputs and more cooperative polling inside preprocessing/statistical operations. Parser calls, sorting/regex searches and blocked input are not hard-preemptible. Empirical authorship corpus/evaluation and Python parity/source-by-source review remain later release gates. Optional models/revisions and humanization were deferred by the user. This record does not declare the full nine-phase plan or evaluated release complete.
