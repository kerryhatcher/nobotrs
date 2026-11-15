# RAID pilot v1 cached validation selection note

Selection ID: `raid-pilot-v1-validation-cached-sweep-v1`

Artifact:
`evaluation/corpora/raid-pilot-v1/selection/validation-cached-sweep-v1.json`
(SHA-256
`f21547733dc7921799f109336b51cc36b23f157d02ba4a53408dab114bd8c9dd`).

This is a **selection observation** on the limited RAID pilot validation split.
It is not independent-test performance, not a general accuracy claim, and not a
release certification. It did not rerun the detector, open held-out text, or
tune against held-out data. It reused the cached family votes in the existing
validation result.

## Source identity

```text
source validation result  results/validation.json
result_sha256             15651fe2c4579f2cbdbbe292ae0432b4a8f12451521597f241207f9e5a05556a
manifest_sha256           dcc538e2fe6dcbb7ad5ff99dc0886d235f105297be161ee77f40745d8ed3ddfa
corpus_content_sha256     349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d
configuration_sha256      e7ec5e1872cc2ffcbf9a9617f7ce9c8bf1a0d09213be8d5b6779b74b70092cc2
effective_settings_sha256 336b12d549cb709b3335d2ae7e8fed8e46b4ef7bffd2b038ab11351754864239
binary_sha256             2a606f3b92ad4d0e717102cbabb4e1cced4d2b35aff98a6828e2484fb0807aae
criteria_id               raid-pilot-v1-supervisor-release-assessment
criteria_sha256           37fe7c018722016090f4e305b3d97d5b0a403cf8c78c5154b5667414b6cf5abb
```

The runner sanitizes all `NOBOTRS_*` variables for detector subprocesses and
passes an explicit config path. The validation result therefore records the
effective resolved settings hash in addition to the frozen config file hash.

## Cached sweep

| Quorum | TP | FP | FN | TN | Coverage | Abstentions | Precision | Recall | F1 | FPR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 66 | 14 | 100 | 40 | 1.000 | 0 | 0.825 | 0.398 | 0.537 | 0.259 |
| 2 | 1 | 0 | 165 | 54 | 1.000 | 0 | 1.000 | 0.006 | 0.012 | 0.000 |
| 3 | 0 | 0 | 114 | 52 | 0.755 | 54 | — | 0.000 | 0.000 | 0.000 |

Quorum 2 is the actual cached validation policy; the artifact verifies that its
recomputed confusion matrix, coverage, abstentions, and operational failures
match the recorded validation result before writing the sweep.

## Decision

**Retain quorum 2 and the existing default thresholds unchanged.** Treat the
default detector as a conservative lint policy, not a useful general authorship
detector.

- Quorum 1 increases recall on this pilot but produces an unacceptable observed
  pilot false-positive rate (14/54 human validation samples).
- Quorum 3 loses coverage and abstains on 54 validation samples while detecting
  no additional positives.
- Quorum 2 preserves the existing conservative behavior. It is not useful as a
  general authorship detector on this pilot, and its low recall is disclosed.

No threshold or default was changed from this sweep. Lowering quorum was not
accepted. The pilot is biased and partial: it omits five RAID domains and most
generators, German and news lack human rows, only abstracts/books/news contain
paraphrase rows, and the label mix is imbalanced. These numbers must not be
presented as independent-test performance.

## Non-claims and next step

- No held-out data was opened, run, swept, or used for tuning during this sweep.
- No access record was claimed or reset.
- The RAID v1 independent-test split was later retired as exposed selection data
  after a Git diff whitespace exposure. The retirement ledger
  `retirement.json` binds that status. This selection artifact predates the
  retirement; its no-held-out claim refers to the sweep event.
- Independent assessment of this corpus is refused. Any future assessment needs
  a fresh, separate corpus and a supervisor freeze/review.
