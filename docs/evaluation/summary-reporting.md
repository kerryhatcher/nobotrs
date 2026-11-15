# Metadata-only evaluation summary and cluster bootstrap

`scripts/summarize_evaluation.py` reads an existing `evaluate.py` result file. It
does not run the detector, read corpus text, or inspect held-out payloads. The
output contains counts, metrics, uncertainty, and identity metadata only.

```sh
python3 scripts/summarize_evaluation.py \
  --result /path/to/result.json \
  --output /path/to/summary.json \
  --replicates 2000
```

## Cluster bootstrap

The resampling unit is `source_group`, not the individual answer/row. This keeps
correlated HC3 human/chatgpt answers from the same question and related RAID rows
together. The fixed default seed is
`evaluation-cluster-bootstrap-v1-2026-11-14`; 2,000 replicates are the default.
Reported intervals are percentile 2.5/97.5 confidence intervals.

For precision, recall, F1, false-positive rate, and coverage the summary reports:

- point estimate;
- lower/upper interval;
- `valid_replicates` and `total_replicates`;
- the denominator identity.

A metric with a zero denominator is `null`, with `valid_replicates: 0`. Unknown
labels (including mixed controls) are excluded from precision/recall/FPR
denominators and reported separately. If every valid replicate has the same value
(especially boundary 0 or 1), the bootstrap interval is **degenerate**: bounds
are `null` with an explicit reason. This is not evidence of zero risk; clustered
bootstrap cannot establish small-FPR certification from tiny or biased samples.
No pseudo-independent binomial interval is substituted for clustered rows.

Input rows are validated: labels must be `null`/`human`/`generated`, verdicts must
be `clean`/`flagged`/`inconclusive`, `complete` must be boolean, `source_group`
must be present, and any runtime must be finite and nonnegative.

## Slices

Overall metrics and `source` (`corpus_source`), `domain`, and `generator` slices
are always produced. Additional `attack`, `language_hint`, and `length_bucket`
slices are emitted when more than one value exists. The requested `--seed` and
`--replicates` propagate to every slice. Per-slice bootstrap resamples the source
components present in that slice; a generator slice necessarily separates
correlated human/generated answers, while overall and source/domain slices
preserve the source-component clustering.

Runtime total/mean/p95 and labeled, unknown-label, and operational-failure
abstention counts are reported. `evaluation_protocol.metrics` also emits a
`false_positive_rate_wilson_95` interval; its adjacent assumption metadata marks
it as an exploratory individual-row binomial interval. It assumes independent
rows and must not certify clustered HC3/RAID data. Final reporting relies on the
cluster-aware summary and discloses degenerate bounds instead.

**No AUC is reported** because there is no continuous calibrated ensemble score;
discrete verdicts do not support one.

## Explicit limitations

The summary embeds the pilot limitations: biased/partial source selection,
missing domains/generators/cells/attacks, no independently labeled
nonnative-speaker or human-edited material, and no native-speaker inference.
Cluster bootstrap is uncertainty over this result's source components, not a new
corpus or independent validation.

No threshold, rule, label, or production policy is selected by this tool. It is
reporting infrastructure only.
