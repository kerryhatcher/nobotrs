# Joint assessment pilot v1 (HC3 + fresh RAID)

`evaluation/corpora/assessment-pilot-v1` is a limited, joint assessment pilot
curated from pinned HC3 and fresh RAID API responses. The old RAID v1 corpus
remains immutable and retired at
[`raid-pilot-v1`](../../evaluation/corpora/raid-pilot-v1) with its `retirement.json` ledger.

Status: **curation, metadata-only preflight, and authorized
development/validation detector runs complete. No independent-test detector run,
freeze record, or access record exists. A root-owned final criteria/preflight pair
is prepared, but no frozen access record or independent run exists at this
moment.** This is not a complete HC3 or RAID benchmark and not an authorship
accuracy certification.

## Pinned sources and licenses

| Source | Pin | License/attribution | Copied responses |
|---|---|---|---|
| `Hello-SimpleAI/HC3` | `4d0ff18143b5a7e1b1e79beb540c04549d1e59d3` | CC-BY-SA-4.0 declared on the dataset card; Hello-SimpleAI / Guo et al. 2023 | first 50 records each of finance, medicine, open_qa, reddit_eli5, wiki_csai |
| `liamdugan/raid` | `865cac74188466cb0c3b7574a10204007b57a459` | MIT declared on the dataset card; upstream Liam Dugan MIT `LICENSE` | 350-row fresh API window including 100 human rows |

HC3-derived content retains CC-BY-SA-4.0 attribution and ShareAlike
obligations. See the repository `NOTICE` and the copied source cards/hashes.
The repository code MIT license does not replace those data terms.

## Curation rules

- HC3 question groups are qualified as dataset + source + local question ordinal
  (`hc3@<revision>:<source>:q<id>`). All human/chatgpt answers for a question
  stay in one group. HC3 has no stable row id, so the ordinal is the nonempty
  record position in the pinned first-50 view.
- HC3 question IDs 0-14 are forced to development across all five source files.
- Metadata-only question audit: 250 normalized question hashes are unique across
  the five first-50 files; 0 duplicate question hashes were found, so no
  question-hash union was required for this snapshot.
  This is the conservative interpretation of the externally viewed source IDs
  because the viewer numbering was not source-qualified.
- Fresh RAID groups use the upstream `source_id`; all rows sharing it stay
  together.
- Exact normalized text and 5-word-shingle Jaccard `>= 0.8` links are unioned
  before splitting, within and across HC3/RAID.
- Old retired RAID v1 exclusion is applied to the **entire connected fresh
  component**, not individual rows. If one answer/row overlaps old source IDs,
  exact normalized text, or near-duplicate text, all siblings and transitively
  related HC3/RAID records are excluded. Old manifest/content/retirement hashes
  and every old sample content hash are verified before exclusion.
- Remaining components receive deterministic 60/20/20 splits using seed
  `assessment-pilot-v1-2026-11-14`. Related cross-corpus components cannot cross
  splits.
- No mixed human-prefix/generated-suffix controls are included in this version.

## Counts

| Split | Samples | Components | Human | Generated |
|---|---:|---:|---:|---:|
| development | 578 | 251 | 277 | 301 |
| validation | 193 | 80 | 84 | 109 |
| independent-test (unread) | 193 | 86 | 89 | 104 |
| **total** | **964** | **417** | **450** | **514** |

| Dimension | Counts |
|---|---|
| corpus source | HC3 707, fresh RAID 257 |
| domain | finance 107, medicine 100, open_qa 200, reddit_eli5 200, wiki_csai 100, abstracts 157, books 100 |
| generator | human 450, chatgpt 357, gpt4 50, mistral 100, llama-chat 7 |
| attack | none 964 |
| HC3 question band | 0-14: 211, 15-49: 496, not-applicable: 257 |
| language hint | unknown 964 |
| length | <100: 240, 100-249: 505, 250-499: 197, 500+: 22 |
| pairing | single 964 |

Rejections: 0 malformed/empty/duplicate HC3 answers or RAID rows. The accepted
fresh RAID rows are 257 of 350; 93 rows were excluded because their `source_id`
overlaps old RAID v1. No accepted HC3/RAID sample overlapped old RAID v1 by exact
normalized text or 5-shingle Jaccard `>= 0.8` in this snapshot. Those rules are
implemented and tested, including whole-component propagation and cross-corpus
transitive links.

There are 9 exact-normalized duplicate links and 37 near-duplicate links among
accepted samples; 2 accepted components contain multiple base groups. No accepted
component crosses HC3/RAID sources in this snapshot.

## Old-corpus exclusion identity

```text
old_manifest_sha256          dcc538e2fe6dcbb7ad5ff99dc0886d235f105297be161ee77f40745d8ed3ddfa
old_corpus_content_sha256    349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d
old_retirement_sha256        917de1bc74a23248738512e17951c6307f86ac4509d359ef42a61bf2e96783c1
old_retirement_status        retired-exposed-selection-data
excluded_rows                93
excluded_components          47
```

## Artifact hashes

```text
manifest_sha256              7d6ffed1ea1172221b98ed650b0c79d78364646355d74f8a8089973c0e6ecf06
corpus_content_sha256        c0ba2e11a2921aaa9e6957f12f94f35cad9fb472027e455ca486690af9c2c140
curation_sha256              ad89bf0ea3822e7001ca6cc2ec5dab48c51abb534b1283712094bf675cfc1fba
summary_sha256               52a7de0ff8a332c83b80f187391957c5c3073d911181f54f72a7541e33d063bb
preflight_sha256             6e26190cbbf7cfa1c50398c9e55cc607c80454aa865cf29ab3e85287ad9467ca
configuration_sha256         e7ec5e1872cc2ffcbf9a9617f7ce9c8bf1a0d09213be8d5b6779b74b70092cc2
release_criteria_sha256      44c06553e77ef7800c8b7b58f563f8984418e2e7b81aa9b260814b031a8391dc
binary_sha256                1d9af3d2f3b14e995853a3749e665626b21aa382700db458d6a352480a2a879d
```

Source snapshot bindings are recorded in the manifest and preflight output:
HC3 portable acquisition `1573b641…`, upstream acquisition `5824493a…`, dataset
card `ce119f7f…`; fresh RAID portable acquisition `06c8117e…`, upstream
acquisition `c8234b91…`, dataset card `54df4f23…`, LICENSE `b21e877a…`.

## Preflight and safeguards

Preflight verifies manifest/content/source snapshots/config/criteria/binary,
development/validation bytes, grouping metadata, and the old-corpus identity. It
does not open independent-test files; the output lists 193 held-out IDs as
`held_out_not_read`. It writes no access/freeze record.

```sh
python3 scripts/assessment_preflight.py \
  --corpus evaluation/corpora/assessment-pilot-v1 \
  --config evaluation/config/assessment-pilot-v1-defaults.json \
  --release-criteria evaluation/release-criteria/assessment-pilot-v1.json \
  --binary target/debug/nobotrs \
  --output evaluation/corpora/assessment-pilot-v1/preflight.json
```

The root-owned final criteria/preflight pair is
`assessment-pilot-v1-fixed-policy-descriptive-assessment` /
`preflight-final.json`; this worker did not modify either. No freeze or independent
assessment may be claimed until the supervisor creates a frozen-unopened access
record and runs the single authorized independent assessment.

## Development/validation results (metadata only)

Authorized runs used `target/release/nobotrs` (`1d9af3d2…`), the frozen defaults
config (`e7ec5e18…`), and proposed criteria (`44c06553…`). No independent-test
sample was read or run.

| Split | n | TP | FP | FN | TN | Precision | Recall | F1 | FPR | Coverage | Abstentions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 578 | 9 | 1 | 292 | 276 | 0.900 | 0.0299 | 0.0579 | 0.00361 | 1.000 | 0 |
| validation | 193 | 6 | 1 | 103 | 83 | 0.857 | 0.0550 | 0.1034 | 0.01190 | 1.000 | 0 |

The recall is known-bad for a general authorship detector. Cluster-bootstrap
summaries use the same seed/replicates across slices
(`evaluation-cluster-bootstrap-v1-2026-11-14`, 2,000): development has 251
clusters and validation 80. Coverage is all-identical (degenerate, null bounds);
FPR/recall/F1 intervals are cluster-aware, not binomial certification. Slices are
reported for source, domain, generator, and length bucket.

Cached quorum sweeps (no detector rerun) retain **quorum 2/defaults unchanged**:

| Split | q1 recall/FPR | q2 recall/FPR | q3 coverage/abstentions |
|---|---|---|---|
| development | 0.382 / 0.105 | 0.0299 / 0.00361 | 0.557 / 256 |
| validation | 0.358 / 0.107 | 0.0550 / 0.01190 | 0.534 / 90 |

Lower quorum raises recall but has unacceptable observed pilot FPR; q3 loses
coverage. These are biased-pilot selection observations, not independent-test
performance. Artifact SHA-256 values:

```text
development result        c0ec52e5ca9043b44e074da9978e52041905c55c4248e7e3f1cef95027cbc698
validation result         0ae8470109cb93475adabff8c6883f6e533265e57926ce0457a72b79ee0afd98
development summary       126c7587ad002e8c15becc7e686675a57702781420e62ab94b9a82087ca36165
validation summary        5b657e1a6d7a8755706799438a24becf5e204559144e736a071a69a9fea337eb
development sweep         411876503cafd3a5f12539d7fdbca0eda5a895aaea5acecf442162925f6734d9
validation sweep          1cb4bd608bdd2675c5c44b24b6b28d31b244b6fe248b6dff803e0993c57d8bb7
```

No thresholds, rules, labels, or production policy changed.

## Limitations

- HC3 is the first 50 records per source, not the complete corpus.
- HC3 question ordinals are local record positions, not upstream stable IDs.
- Fresh RAID is a 350-row partial API window; only abstracts/books and four
  models appear, with no attacks/paraphrases.
- 93 fresh RAID rows were removed by old source-group exclusion.
- No native-speaker, nonnative-speaker, or human-edited independently labeled
  evidence is available; none is inferred.
- Mixed controls are kept in a separate development-only corpus
  (`mixed-controls-v1`), not this assessment manifest.
- The language policy remains default-unknown with no per-sample overrides.
- Development/validation detector results exist and show known-bad recall; no
  independent-test result exists and no tuning/freeze was performed.
- Reviewers must not display raw questions, answers, or response payloads.
  `.gitattributes` marks sample text and nested source response JSON/JSONL as
  `-text -diff`.
