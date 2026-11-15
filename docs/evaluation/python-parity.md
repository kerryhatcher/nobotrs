# Pinned Python reference comparison

This report compares shared behavior fixtures with the pinned Python `nobot`
commit `0981b9501b7dd2fb37803cf43298e83edfd508e9`. It is a development
comparison, not an authorship evaluation and not a release gate.

Reproduce it with:

```sh
python3 scripts/compare_python_reference.py
```

The harness reads the untouched archive at
`/tmp/nobotrs-python-reference/0981b9501b7dd2fb37803cf43298e83edfd508e9`.
The supervisor created this archive directly with `git archive` from the exact
commit, so it is the trusted capture. The harness pins SHA-256 values for every
Python source under `src/nobots` plus `pyproject.toml` and `uv.lock`; a modified
or mislabeled archive is rejected before comparison. It never modifies the
archive or the neighboring checkout.

`python3 scripts/test_compare_python_reference.py` passes three regressions:
the verified archive matches the pinned hashes, a modified `detect.py` is
rejected, and a mislabeled directory is rejected.

## Environment difference

The archived `uv.lock` points `textstat`, `lexicalrichness`, `nltk`, `pyphen`,
and `typer` at an inaccessible private Artifactory registry (HTTP 401). The
harness installs the matching public PyPI versions in an isolated `uv`
environment and records this substitution:

| Package | Version |
|---|---:|
| textstat | 0.7.13 |
| lexicalrichness | 0.5.1 |
| nltk | 3.10.0 |
| pyphen | 0.17.2 |
| typer | 0.26.8 |

No model weights and no `analyze`/spaCy extra are required. The archive's core
`clean_prose` and `detect_text` paths are the comparison target.

## Fixture results

The harness runs both implementations on the seven reusable fixtures in
`tests/fixtures/evaluation/`. It records prose-word counts, tells/verdicts,
non-`none` family votes, and MTLD/Flesch–Kincaid/LZMA context. Differences are
classified from the known implementation boundaries. The current run found
**10 expected differences and 0 regression candidates**.

| Fixture | Python tells | Rust verdict | Family votes | Differences | Classification |
|---|---|---|---|---|---|
| code-only | false | inconclusive | match | none | — |
| flagged | true | flagged | match | prose words; LZMA | Python whitespace tokens count em dashes; Rust compresses only above its word floor |
| long-fence | false | clean | match | prose words; LZMA | Python regex fence cleaning differs from the Rust Markdown parser |
| no-cross-block | false | clean | match | LZMA | Rust compression abstains below its word floor; Python computes unconditionally |
| plain | false | clean | match | LZMA | same word-floor/context coverage difference |
| softbreak | false | clean | match | LZMA | same word-floor/context coverage difference |
| welsh | false | clean | match | MTLD; Flesch–Kincaid; LZMA | Rust abstains from English-specific metrics without an override; Python computes on Welsh; compression algorithms differ |

The `flagged` prose-word difference is 10 Python whitespace tokens versus 4 Rust
Unicode words; the em dashes are not words. The `long-fence` difference is 5
versus 4 because Python's regex cleaner removes a narrower fence span than the
Rust Markdown parser. These are intended parser/tokenization differences, not
regressions.

The Welsh family votes match: Python reports burstiness vote 2 and Rust reports
`strong`. The LZMA values differ because Python uses `lzma.compress(...,
preset=6)` while Rust uses `lzma-rs` 0.3's literal-only LZMA-Alone encoder; see
[compression references](../compression-reference.md). MTLD and readability are
Python-only on this fixture because Rust requires an explicit English assertion.

## Burstiness reference

The harness also checks `tests/fixtures/burstiness-reference.json`, an external
population-standard-deviation reference generated from explicit sentence-length
vectors. Python `statistics.pstdev` and the Rust production backend agree on all
five vectors (uniform, low variation, suspicious, varied, and below-word-floor
abstention). Reproduce the arithmetic separately with:

```sh
python3 scripts/check-burstiness-reference.py
cargo test --locked --test burstiness_reference
```

## What is not claimed

- No Python/Rust parity is forced for known Python prose-cleaning, threshold,
  language-policy, compression, readability, or error-handling behavior.
- The fixtures have no reliable authorship labels. Match rates are not detector
  precision, recall, or false-positive estimates.
- This is not an independent release evaluation. No corpus access record is
  claimed or consumed.
- Optional models, SAEs, MCP/TUI, and humanization remain deferred.
