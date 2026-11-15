# Joint assessment pilot v1 (HC3 + fresh RAID)

`evaluation/corpora/assessment-pilot-v1` is a limited, joint assessment pilot
curated from pinned HC3 and fresh RAID API responses. The old RAID v1 corpus
remains immutable and retired at
[`raid-pilot-v1`](../../evaluation/corpora/raid-pilot-v1) with its `retirement.json` ledger.

Status: **curation and metadata-only preflight complete. No detector has been
run. The independent-test split has not been read by curation preflight. No
freeze record or access record exists. The release criteria are proposed, not
frozen.** This is not a complete HC3 or RAID benchmark and not an authorship
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
preflight_sha256             29bc77560c6025a946025937e9d3ea8fb643f365ab18f1c9121f5b54d28694c8
configuration_sha256         e7ec5e1872cc2ffcbf9a9617f7ce9c8bf1a0d09213be8d5b6779b74b70092cc2
release_criteria_sha256      44c06553e77ef7800c8b7b58f563f8984418e2e7b81aa9b260814b031a8391dc
binary_sha256                5ae810e65cc5f5b33502783f7bae2fd5ad2882a04e53abb0dd8a808f786eee49
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

Criteria are **proposed/not frozen**; no freeze or independent assessment may be
claimed until the supervisor creates a freeze record and reviews the corpus.

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
- No detector results, development/validation tuning, or independent-test
  performance exist for this pilot yet.
- Reviewers must not display raw questions, answers, or response payloads.
  `.gitattributes` marks sample text and nested source response JSON/JSONL as
  `-text -diff`.
