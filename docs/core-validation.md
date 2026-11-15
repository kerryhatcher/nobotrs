# Core validation record

## Compression/entropy references and functional-core acceptance: 2026-11-14

Seven original synthetic compression/entropy vectors are pinned in
`tests/fixtures/compression-reference.json`. They cover empty input, the 149/150
word boundary, repetition, mixed repetition, multi-byte Unicode, and varied
prose. The fixture records the `lzma-rs` 0.3.0 Cargo.lock checksum, default
options, LZMA-Alone header, exact encoded stream hex/SHA-256, compressed length,
ratio, and independently computed token entropy. See
[compression reference provenance and limits](compression-reference.md).

`python3 scripts/check-compression-reference.py` reproduced all seven entropy
values with the Python standard library, verified the pinned crate checksum,
checked each LZMA-Alone header, decompressed every pinned stream with
`lzma.FORMAT_ALONE`, and matched the exact raw bytes, length, hash, and ratio.
The production-backend Rust test `pinned_compression_reference` rechecks the
native encoder bytes and scored/abstained outcomes. This is regression evidence,
not Python preset-6 parity or an accuracy claim.

A repeatable real-executable runner now covers the documented functional-core
release gates:

```sh
python3 scripts/acceptance.py
```

It exercises help/guide/config, file/stdin equivalence, Markdown soft breaks,
entities, fences, gaps and source locations, candidate disposal and rejected
boundaries, stable IDs, family reduction, language policy, missing/invalid
inputs, empty prose, mixed scans and deterministic ordering, input/timeout/
candidate budgets, display-only truncation, and a long single-line Unicode
fixture. It also packages the crate, verifies imported research is absent,
installs from the unpacked package into a clean temporary root, and exercises
the installed binary. The run passed 9 checks. The installed stripped binary was
2,577,328 bytes, within the 8,000,000-byte budget. On the named host (AMD Ryzen
7 5800X, 16 logical CPUs), `/usr/bin/time -v` measured `detect README.md` below
the 0.01-second timer resolution and about 5.7 MiB peak RSS. These are named-host observations,
not portable guarantees.

Packaging previously included one untracked imported-research `README.md`
because Cargo's unanchored `README.md` include pattern matched nested files.
Root package files are now anchored with leading `/`; the package list contains
no `docs/research/` entries. The imported research itself was not modified.

## Follow-up: 2026-11-14

Readability now has six pinned external Textstat comparisons, production-backend
regressions, and explicit punctuation/case probes. See
[reference provenance and known differences](readability-reference.md). The
development-only `uv run scripts/check-readability-reference.py` reproduced all
six external values using the recorded package versions and CMU dictionary hash.

Cooperative deadline polling now covers document construction, source-position
indexing, sentence segmentation, suppression-directive parsing, statistical
word/sentence loops, MTLD reverse-copy preparation, and entropy frequency/reduction
loops. Expired preprocessing discards unfinished prose and preserves the ordinary
incomplete-report contract. Direct expired-helper probes and bounded/unbounded
Unicode/Markdown source-map comparisons passed. No hard preemption is claimed.

Verified `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`,
`cargo test --locked` (43 unit/backend, 5 CLI, 13 remediation tests),
`cargo build --release --locked`, and `git diff --check`. The release executable
reproduced the seven-fixture CI behavior baseline. Real plain-text and Markdown
stdin probes with `--timeout-ms 0` returned status 2, `complete: false`, zero
coverage, zero prepared words, and failed backend outcomes. The release binary
was 2,576,608 bytes, within the existing 8,000,000-byte budget. Corpus evaluation,
broader statistical references, Python parity, and other release gates remain
separate work. No authorship accuracy or calibrated probability claim was added.

### MTLD continuation

Six explicit normalized token lists now match LexicalRichness 0.5.1 at threshold
0.72 within absolute tolerance `1e-12`. The reference checker verifies the package
version and implementation-source hash, disables external preprocessing/tokenizing,
and reproduces all six values. Rust regressions require matching prepared tokens,
scored production-backend metrics, and no vote. Existing MTLD/readability
evidence-only tests now assert English and fail on abstention or failure instead
of skipping their assertions. See [MTLD provenance](mtld-reference.md).

Verified formatting, Clippy with warnings denied, `cargo test --locked` (44 unit,
5 CLI, 13 remediation tests), and `git diff --check`. This continuation changes
tests, reference fixtures/tooling, and documentation; production algorithms and
thresholds are unchanged. Pi/Ornith applied the test changes; the supervisor
replaced a faulty draft with reviewed code and independently ran the full checks.

## Original core milestone

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

Compression/entropy reference coverage is now pinned; burstiness still has native regression tests but no external reference. Parser calls, sorting/regex searches and blocked input are not hard-preemptible. Empirical authorship corpus/evaluation and Python parity/source-by-source review remain later release gates. Optional models/revisions and humanization were deferred by the user. This record does not declare the full nine-phase plan or evaluated release complete.
