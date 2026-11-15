# Evaluation protocol

Run the reusable CI baseline after building:

```sh
python3 scripts/evaluate.py \
  --binary target/release/nobotrs \
  --manifest tests/fixtures/evaluation/manifest.json \
  --output /tmp/results.json \
  --check docs/evaluation/ci-baseline.json
```

The regression fixtures are synthetic and have unknown authorship labels. Their
pass rate is never detector precision or accuracy. The prior regression manifest
and baseline remain compatible; the runner adds identity and grouping fields
without changing the compared `regression_results`.

## Manifest identity and content

A corpus manifest is JSON with `schema_version: "1.0.0"`, `corpus_version`,
optional `corpus_revision` (defaults to `corpus_version`), `purpose`, optional
`near_duplicate_threshold` (default `0.8`), and `samples`. Each sample requires:

- a unique safe `id`, relative `file` path without `..`, `split`, `slice`, and
  `source_group`;
- `license` as an SPDX-like expression, not a placeholder such as `unknown`;
- `provenance` as a verifiable object with `source` and `retrieved: YYYY-MM-DD`
  for development, validation, and independent data. The legacy regression
  manifest may use a descriptive string;
- `label` equal to `human`, `generated`, or `null`. Null means unknown or
  mixed-origin, is preserved in output, and is excluded from precision, recall,
  F1, and false-positive-rate denominators. Unknown-label coverage and failures
  are reported separately;
- `content_sha256` over the exact file bytes. Development, validation, and
  independent manifests must also provide `near_duplicate_group` and a top-level
  `corpus_content_sha256` computed from the canonical sample identities and
  content hashes.

A manifest may also declare `dimensions` (name -> description) and give every
sample a `dimension_values` object. When present, the runner emits
`dimension_metrics` in addition to `slice_metrics`; this is how the RAID pilot
reports domain, generator, attack, language-hint, length, upstream-split, and
label counts without changing verdicts or thresholds. Dimension values are
metadata assertions, not authorship truth.

Hashes are over raw bytes, not newline-normalized decoded text. CRLF/LF changes
are therefore tampering, not equivalent content.

## Grouping

`source_group`, `near_duplicate_group`, exact `content_sha256`, exact normalized
text, and token 5-gram Jaccard similarity are checked across splits. Any group,
duplicate, or near-duplicate crossing splits is rejected. Near-duplicate review
remains a curation responsibility; the exact-hash and Jaccard checks are
deterministic guards, not proof that a corpus has no related samples.

## Independent-test access

An independent run requires `--config`, `--release-criteria`, and
`--release-access-record`. The access record must contain `status:
"frozen-unopened"` and bind all of:

- `schema_version`, `split`;
- `corpus_revision`, `manifest_sha256`, `corpus_content_sha256`;
- `configuration_sha256`;
- `release_criteria_sha256` and `release_criteria_id`;
- `binary_sha256`, so a different executable cannot pass the frozen record.

The runner validates the identity before reading any independent text, claims a
sibling `.lock` file with exclusive create, re-reads the record under the lock,
and atomically replaces it with `status: "accessed"` plus `access_id` and
`accessed_at`. Already accessed, stale, reused, mismatched, or concurrently
locked records are rejected. A lock left by a crash is a conservative refusal;
do not reset it to iterate toward passing. If results inform a revision, retire
the test set into selection data and obtain fresh independent data.

The verified file bytes are passed to the detector through stdin, with Markdown
inferred from the sample's file extension. The subprocess does not reread the
path after hash verification. Development, validation, and regression runs read
only non-independent samples; they validate source/near-duplicate/content-hash
metadata for the full manifest but do not open held-out text. The
`content_verification` output lists verified sample IDs/splits, held-out IDs not
read, the verified subset hash, the manifest corpus hash, and whether independent
held-out text was verified after a claim.

## Output identity

Output records `corpus_identity` (corpus revision, manifest/content/configuration/
criteria hashes, configuration source, access ID), `effective_configuration`
(resolved `report.settings`, its SHA-256, supplied config keys, and sanitized
environment variable names), `engine_identity` (binary SHA-256, engine and
dictionary versions, metric contract), `metric_versions` (backend metric method
strings), and `grouping` counts. Raw feature cache rows retain families, metrics,
completeness, status, and runtime.

Detector subprocesses run with every `NOBOTRS_*` environment variable removed and
an explicit `--config` path. Without `--config`, a temporary empty `{}` config is
passed so the binary resolves its own defaults; platform config and
`NOBOTRS_CONFIG` lookup are isolated. For an explicit partial config, every
supplied key is checked against the detector's resolved `settings`; the complete
resolved settings hash is recorded. This prevents an inherited environment
override from silently changing policy under the same config and binary hashes.

## Metrics and sweeps

The runner reports labeled and unknown-label counts, coverage, abstentions,
operational failures, confusion matrix, precision, recall, F1, false-positive
rate, Wilson sampling interval, and slice metrics. Empty denominators are null.
No AUC is produced without a meaningful continuous ensemble score.

Use development data for feature work and validation data for threshold choices.
`--split validation --sweep-quorum 1 2 3` recomputes quorum verdicts from cached
family contributions without rerunning extraction. Sweeps are rejected for
regression and independent-test splits. Selection results are not independent
test performance. The pilot's cached validation selection note is
[raid-pilot-selection.md](raid-pilot-selection.md).

## Python reference and burstiness references

The pinned Python comparison and its known intended differences are documented
in [python-parity.md](python-parity.md). The external population-stdev vectors are
in `tests/fixtures/burstiness-reference.json` with
`scripts/check-burstiness-reference.py` and `tests/burstiness_reference.rs`.

A limited, licensed RAID pilot is available at
[`evaluation/corpora/raid-pilot-v1`](../../evaluation/corpora/raid-pilot-v1) and is
documented in [raid-pilot.md](raid-pilot.md). It is a partial API view with
1,100 samples, is not the complete RAID benchmark, and is not an accuracy
certification. Its independent-test split has not been opened or run. The
evaluated-release gate remains open. There are no independently measured
accuracy, false-positive, or calibrated probability claims. Optional models,
SAEs, MCP/TUI, and humanization remain deferred.
