# Final assessment and release limitations

## Outcome

The **engineering default-core/evaluation/integration milestone is complete**.
The **general authorship qualification is FAILED / NOT QUALIFIED**. The current
heuristic detector is not a useful general authorship detector and no calibrated
probability, general accuracy, or authorship determination is claimed.

This conclusion is descriptive for one fixed-policy pilot assessment, not a
certification of the detector on RAID, HC3, or a general population.

## Frozen candidate and evidence

| Item | Value |
|---|---|
| Candidate checkpoint | `aad622a` |
| Reporting commit | `9d47db0` |
| Release binary | `1d9af3d2f3b14e995853a3749e665626b21aa382700db458d6a352480a2a879d` |
| Effective settings SHA-256 | `336b12d549cb709b3335d2ae7e8fed8e46b4ef7bffd2b038ab11351754864239` |
| Final criteria | `evaluation/release-criteria/assessment-pilot-v1-final.json` |
| Criteria ID | `assessment-pilot-v1-fixed-policy-descriptive-assessment` |
| Criteria SHA-256 | `9c8f5059a0c228a7de56efa65c2d8abcde862d482915cccfc02b2b0954f5bab5` |
| Independent result SHA-256 | `13e772464f950fcc9fb3e7c14c925955c8d97ada47bbcfd9d9c2dbde48ecc8fa` |
| Independent summary SHA-256 | `dbd0fa76d66e329b14699d04034a463dc89a8ef0da33063549434e24a1abbf94` |
| Independent access record SHA-256 | `bc2437275e597e04694d68f3a943d62c2c24ce32c9a9efc7bf19c443a83c6e08` |
| Independent access | one `accessed` claim; no reset |
| Qualification status | `not-qualified` |

The independent set was frozen before access and was used exactly once. No
detector rerun, independent sweep, access reset, threshold/rule/label change, or
candidate revision followed. Results at
`evaluation/corpora/assessment-pilot-v1/results/independent-test.json` and
metadata-only summary at `.../independent-test-summary.json`.

## Independent result

193 samples: 89 human, 104 generated.

| Measure | Value |
|---|---:|
| TP / FP / FN / TN | 2 / 2 / 102 / 87 |
| Precision | 0.500 |
| Recall | 0.01923 |
| F1 | 0.03704 |
| False-positive rate | 0.02247 |
| Coverage | 1.000 |
| Operational failures / abstentions | 0 / 0 |

Source-component cluster bootstrap (86 clusters, fixed seed, 2,000 replicates):

| Metric | Estimate | 95% cluster interval | Valid replicates |
|---|---:|---|---:|
| Recall | 0.01923 | [0.000, 0.04763] | 2000 |
| False-positive rate | 0.02247 | [0.000, 0.06025] | 2000 |
| F1 | 0.03704 | [0.000, 0.09009] | 2000 |
| Precision | 0.500 | [0.000, 1.000] | 1957 |
| Coverage | 1.000 | null (degenerate) | 2000 |

Coverage has no observed replicate variation and therefore null bounds with an
explicit degenerate reason. The intervals are exploratory clustered-pilot
uncertainty, not zero-risk evidence, binomial certification, or a statement that
FPR is acceptable.

## Aggregate slice outcomes and known failure cases

| Slice | n | TP | FP | FN | TN | Recall | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| HC3 | 132 | 0 | 0 | 67 | 65 | 0.000 | 0.000 |
| fresh RAID | 61 | 2 | 2 | 35 | 22 | 0.0541 | 0.0833 |
| chatgpt | 67 | 0 | 0 | 67 | 0 | 0.000 | — |
| gpt4 | 10 | 2 | 0 | 8 | 0 | 0.200 | — |
| human | 89 | 0 | 2 | 0 | 87 | — | 0.02247 |
| mistral | 27 | 0 | 0 | 27 | 0 | 0.000 | — |
| length <100 | 51 | 0 | 0 | 9 | 42 | 0.000 | 0.000 |
| length 100-249 | 98 | 1 | 2 | 66 | 29 | 0.0149 | 0.0645 |
| length 250-499 | 39 | 1 | 0 | 27 | 11 | 0.0357 | 0.000 |
| length 500+ | 5 | 0 | 0 | 0 | 5 | — | 0.000 |

Domain slices are available in the metadata-only summary. The clearest failure
cases are aggregate: HC3 produced no true positives and 67 false negatives;
chatgpt and mistral produced no true positives; abstracts produced no true
positives and two false positives. No raw payloads are included here.

## Selection and frozen policy

Development/validation selection retained **quorum 2 and all existing default
rules/thresholds**. Cached sweeps showed lower quorum raised recall but with an
unacceptable observed pilot FPR, while quorum 3 lost coverage. No threshold,
rule, label, or policy was changed. Numeric backend thresholds remain fixed
compiled constants deliberately; only quorum and caching/reporting paths were
parameterized.

The old RAID v1 split remains retired as exposed selection data. The assessment
independent split is now a consumed independent assessment; results must not be
reused as fresh held-out evidence. If the candidate is revised, retire this
assessment as selection evidence and obtain fresh independent data.

## Engineering gates passed

- 51 Python tests under root review.
- 66 Rust tests; `cargo fmt --check`; Clippy with warnings denied.
- 4 real-executable integration groups, including pinned official SARIF schema
  and Unicode `columnKind`.
- 9 package/install acceptance groups; release binary 2,577,616 bytes.
- Named-host observation: AMD Ryzen 7 5800X, `detect README.md --format json`
  below 0.01-second timer resolution at 5,308 KiB peak RSS.
- CI regression baseline unchanged; exact manifest/config/criteria/binary binding
  and one-shot independent access verified.

## Remaining evidence scope and deferred work

- Representative coverage is not established: partial first-window HC3 and RAID
  views, missing domains/generators/attack cells, uneven lengths and generators.
- No independently labeled nonnative-speaker or human-edited material exists;
  native-speaker status is not inferred.
- Mixed controls are mechanical development-only concatenations, not verified
  real-world human editing.
- Broad numeric-backend parameterization and calibration were not performed;
  fixed compiled constants are intentional.
- The source/provenance audit is limited: 46 origins, 206 snapshot entries, 34
  unsupported claims at supervisor commit `f6979ad`, not a full external
  revalidation.
- Optional model scoring, SAEs, MCP/TUI, and humanization remain deferred by the
  user.
- No AUC or calibrated probability is reported; Clean does not prove human
  authorship.

See the [auditable-detector paper note](building-auditable-notes.md) for the
hard-negative, ablation, OOD/low-FPR, and domain-shortcut lessons that motivate
these limitations. Do not display raw questions, answers, samples, or payloads.
