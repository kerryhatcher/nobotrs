# Limited RAID pilot v1

`evaluation/corpora/raid-pilot-v1` is a small, versioned pilot built from copied
Hugging Face datasets-server responses for `liamdugan/raid` at immutable revision
`865cac74188466cb0c3b7574a10204007b57a459`. It exists to exercise curation,
grouping, freeze/preflight, and development/validation reporting.

It is **not** the complete RAID benchmark, not a representative sample of RAID,
and not an accuracy certification. Historically no independent detector run
occurred and no access record was claimed; the independent-test split is now
retired as exposed selection data. No threshold or default was changed.

## Retirement status (supersedes unopened claim)

After commit `993956a`, the supervisor ran `git diff --cached --check` on the
staged raw corpus. Git printed trailing-whitespace passages from raw sample
payloads; the output was large and some passages were visible. Conservatively,
**all 218 RAID v1 independent-test samples are retired as exposed selection
data**. The historical facts that no independent detector run occurred and no
access record was ever claimed remain true, but any claim that the held-out set
is unopened is superseded. Original manifests, splits, results, and audits are
preserved, not reset, reshuffled, or whitespace-normalized. Reviewers must not
display held-out payloads.

The permanent ledger is `retirement.json` (SHA-256
`917de1bc74a23248738512e17951c6307f86ac4509d359ef42a61bf2e96783c1`).
Preflight refuses `--freeze`, and the evaluator refuses
`--split independent-test`, for this retired corpus. Development and validation
remain usable.

## Source snapshot and license

The portable snapshot under `source/` preserves:

- a portable `acquisition.json` with relative `responses/<file>` paths and the
  original acquisition record's SHA-256;
- exact copied response bytes for all 35 successful queries, with per-response
  hashes;
- the copied upstream dataset card, which declares `license: mit`;
- the copied upstream `LICENSE`, the actual Liam Dugan MIT notice;
- `PROVENANCE.json`, which binds the original acquisition hash, card/license
  hashes, retrieval date/timezone, every response hash, and the 12 failed jobs.

The acquisition pins `retrieved: 2026-11-14` and
`retrieved_timezone: America/New_York`. The curator uses that fixed metadata by
default; it does not call `date.today()` or embed current timestamps. An explicit
override is possible and would be recorded as an override.

The 35 successful queries comprise 22 nonempty views and 13 empty views; 12
additional jobs failed. Every API view is partial: each query asked for at most
50 rows, while `available` counts are much larger. The snapshot contains 1,100
rows. No RAID test split was requested.

## Curation rules

Rows are rejected or recorded for malformed items, missing fields, invalid
identities, empty/empty-normalized generations, unsupported models, query
mismatches, truncated cells, or duplicate upstream row IDs. The real snapshot had
0 rejected rows, but the importer and synthetic tests cover each rejection path.

Accepted rows are unioned before splitting by:

1. the upstream `source_id`;
2. exact normalized text (lowercased Unicode word tokens);
3. token 5-shingle Jaccard similarity `>= 0.8`.

The resulting components are deterministic. Each component emits a
`source_group` and a `near_duplicate_group`; every member stays in one split. In
this snapshot, 250 source groups produced 250 components (no additional
exact/near-duplicate union was observed).

The five supervisor-identified previously viewed source IDs, plus one poetry
source displayed during schema inspection, were forced to development together
with all related component members:

```
e5e058ce-be2b-459d-af36-32532aaba5ff
f95b107b-d176-4af5-90f7-4d0bb20caf93
856d8972-9e3d-4544-babc-0fe16f21e04d
fbc8a5ea-90fa-47b8-8fa7-73dd954f1524
72c41b8d-0069-4886-b734-a4000ffca286
527dc536-7b69-4c2f-94af-afeb85894a07   (session inspection)
```

After forced development assignment, remaining components are ordered by
`SHA-256("raid-pilot-v1-2026-11-14:" + component_id)` and assigned to the split
with the largest remaining target capacity at 60/20/20. This is a deterministic
source-group split, not a random shuffle.

## Labels and provenance

The manifest keeps the original `source_id`, upstream row identity, model,
domain, attack, decoding, repetition penalty, row index, response file/hash,
query URL, and upstream split. `label` is the upstream model assertion mapped as:

- `model=human` -> `human`;
- another known RAID model -> `generated`.

This is provenance, not universal authorship truth. RAID does not provide
independent authorship verification in these rows.

## Counts

| Split | Samples | Components | Human | Generated |
|---|---:|---:|---:|---:|
| development | 662 | 146 | 116 | 546 |
| validation | 220 | 62 | 54 | 166 |
| independent-test (retired; historically unopened/unrun) | 218 | 42 | 30 | 188 |
| **total** | **1,100** | **250** | **200** | **900** |

| Dimension | Counts |
|---|---|
| domain | abstracts 250, books 200, czech 200, german 150, news 200, poetry 100 |
| generator | human 200, chatgpt 200, gpt4 400, mistral-chat 300 |
| attack | none 950, paraphrase 150 |
| language hint | unknown 750, czech-domain 200, german-domain 150 |
| length | <100 words 33, 100-249 631, 250-499 391, 500+ 45 |
| upstream split | train 750, extra 350 |

`language_hint` is a coarse upstream-domain hint, not a per-row language
assertion. The canonical `dimension_values` are emitted in the manifest, and the
runner reports `dimension_metrics` for development/validation output. Native
speaker status is not present in RAID and is not inferred.

## Language policy

The pilot does not freeze per-sample language overrides. The detector runs with
its default unknown-language policy. `language_hint` is reporting metadata only;
`language_policy` records `runtime_default: "unknown"`,
`per_sample_overrides: false`, and an empty overrides list. Readability and MTLD
therefore continue to abstain unless the runtime is explicitly configured
otherwise in a future, separately recorded design.

## Coverage gaps

The pilot omits RAID domains `code`, `recipes`, `reddit`, `reviews`, and `wiki`.
It contains only `chatgpt`, `gpt4`, `human`, and `mistral-chat`; other RAID
generators are absent. Only abstracts, books, and news have GPT-4 paraphrase rows.
German and news have no human rows because those queries failed or were absent.
The label mix is imbalanced (900 generated, 200 human). These are disclosures, not
values to fill by inference.

## Development/validation results

The small pilot was run only on development and validation with the frozen
default configuration and the debug binary. These are selection/plumbing
observations, not independent performance:

| Split | n | TP | FP | FN | TN | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| development | 662 | 22 | 1 | 524 | 115 | 0.957 | 0.040 | 0.077 | 0.0086 |
| validation | 220 | 1 | 0 | 165 | 54 | 1.000 | 0.006 | 0.012 | 0.000 |

Abstentions and operational failures were both 0 in these runs. The low recall is
a property of the current uncalibrated rules on this partial pilot, not a
justification to retune on held-out data. The evaluator did not open the
independent-test split and lists its 218 IDs as `held_out_not_read`; the Git-diff
exposure subsequently retired all 218 as exposed selection data, so no
independent assessment may use them.

A cached validation quorum sweep is persisted as
[`raid-pilot-selection.md`](raid-pilot-selection.md) and
`selection/validation-cached-sweep-v1.json`. It reused cached family
votes without rerunning the detector: quorum 1 raised recall to 0.398 but produced
an observed FPR of 0.259; quorum 3 abstained on 54 of 220 samples; quorum 2
remains the unchanged conservative default. This is selection evidence on a
biased pilot, not independent-test performance, and no threshold was changed.

Result files are under `results/`. They contain no sample text and cover only
development/validation. Detector subprocesses now run with all `NOBOTRS_*`
environment variables removed and an explicit config path; both
`configuration_sha256` and the resolved `effective_settings_sha256` are recorded.

## Freeze and preflight

The preflight command verifies the manifest, portable source snapshot, response
hashes, development/validation bytes, grouping metadata, curation audit, config,
release criteria, and binary identity without opening independent-test text:

```sh
python3 scripts/raid_pilot_preflight.py \
  --corpus evaluation/corpora/raid-pilot-v1 \
  --config evaluation/config/raid-pilot-v1-defaults.json \
  --release-criteria evaluation/release-criteria/raid-pilot-v1.json \
  --binary target/debug/nobotrs \
  --output evaluation/corpora/raid-pilot-v1/preflight.json
```

The output is a binding record and includes the exact one-shot access-record
identity for a future supervisor decision. It does **not** claim the access
record. A supervisor may explicitly add `--freeze --access-record-out PATH` to
write a `frozen-unopened` record; that still does not claim it. **For this retired
corpus, preflight refuses `--freeze` and reports `refused-retired`; the evaluator
refuses `--split independent-test` before claiming any access record.**
Preflight rejects absolute response paths, missing/tampered source files, stale
manifest/source bindings, forced sources outside development, non-default
language overrides, and held-out text reads.

Current preflight identity:

```text
manifest_sha256         dcc538e2fe6dcbb7ad5ff99dc0886d235f105297be161ee77f40745d8ed3ddfa
corpus_content_sha256   349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d
curation_sha256         a965a4bd2ed0669a47caf17a8d4ba9437c491935781b051729db4865e1619f28
config_sha256           e7ec5e1872cc2ffcbf9a9617f7ce9c8bf1a0d09213be8d5b6779b74b70092cc2
criteria_sha256         37fe7c018722016090f4e305b3d97d5b0a403cf8c78c5154b5667414b6cf5abb
criteria_id             raid-pilot-v1-supervisor-release-assessment
binary_sha256           2a606f3b92ad4d0e717102cbabb4e1cced4d2b35aff98a6828e2484fb0807aae
```

## Reproducibility

The corpus can be regenerated from the portable snapshot even if the original API
or `/tmp` cache disappears:

```sh
python3 scripts/curate_raid_pilot.py \
  --cache evaluation/corpora/raid-pilot-v1/source \
  --out /tmp/raid-pilot-replay
```

A replay in a second temporary directory reproduced the same manifest bytes,
curation audit bytes, summary bytes, `corpus_content_sha256`, manifest hash,
source-snapshot binding, split counts (662/220/218), component counts (146/62/42),
and grouping counts. The curator refuses any nonempty or symlinked output
directory and never deletes or replaces existing data; use a fresh output path
for each replay or corpus version. The portable acquisition contains no absolute temporary or
project paths; response paths are relative to `source/responses/` and every
response byte/hash is preserved.

## Independence audit

`independence-audit.json` (generated by
`scripts/audit_raid_pilot_independence.py`) records the split-stability and
evaluated-sample audit. It preserves the complete development and validation evaluated sample-ID lists,
with per-ID content hashes and ID-set hashes, so those samples cannot later be
moved into the held-out set. It records the held-out set hash and count. The
retirement ledger supersedes the audit's historical unopened status; the
historical fields are retained. No independent detector run occurred and no
access record was claimed.

The manifest hash changed three times while provenance metadata was fixed:

| Generation | Manifest SHA-256 | Corpus content SHA-256 | Splits | Components |
|---|---|---|---|---|
| 1 | `9af3b652…e346` | `349a0c64…858d` | 662/220/218 | 146/62/42 |
| 2 | `24fea295…ab63` | `349a0c64…858d` | 662/220/218 | 146/62/42 |
| 3 | `dcc538e2…ddfa` | `349a0c64…858d` | 662/220/218 | 146/62/42 |

Only generation metadata changed: original absolute-path acquisition, then
portable relative-path acquisition plus fixed retrieval metadata, then upstream
retrieval provenance fields. `corpus_content_sha256` includes each sample's ID,
file, split, source group, label, slice, and content hash. Its invariance across
all three generations is cryptographic evidence that no sample ID or split
assignment changed. The audit also reconstructs the deterministic split from
current manifest metadata and verifies it matches every sample, and verifies the
development/validation result ID sets match the manifest and are disjoint from
the independent set. No split was reshuffled to improve counts or results.

The additional poetry source `527dc536-7b69-4c2f-94af-afeb85894a07` was displayed
during schema inspection and was added to the initial curator's session-viewed
list before the first corpus generation and before any detector predictions. The
first generation already contained it in development and had the same 662/220/218
split counts and `349a0c64…858d` content hash. All of its samples remain in
development. This timing is recorded in the audit.

Current audit hash:

```text
independence_audit_sha256  8da025ff4f9deb03ef9fe7978c5fc5e03f308331ce38661554dc73bb1c67c3ec
retirement_ledger_sha256   917de1bc74a23248738512e17951c6307f86ac4509d359ef42a61bf2e96783c1
development_result_sha256   da226f9851d312c2a6f112a1b385d34dae9723a97dde9f08ae5ebe128ff93051
validation_result_sha256    15651fe2c4579f2cbdbbe292ae0432b4a8f12451521597f241207f9e5a05556a
```

The first development/validation predictions were produced after generation 1.
The earlier manifest and result files were overwritten during the metadata-only
regenerations, so the retained evidence is the recorded generation identities,
the invariant content hash, the unchanged deterministic split inputs, and the
current result files bound to generation 3. No independent detector result was
read and no access record was claimed. The Git-diff exposure displayed some raw
held-out passages, so all 218 held-out samples are retired as exposed selection
data.

## Non-claims

This pilot does not establish general detector accuracy, calibrated
probabilities, native-speaker behavior, or complete RAID coverage. Do not report
development/validation selection results as held-out performance. The RAID v1
held-out split is retired as exposed selection data and cannot be frozen or
assessed as independent. Any future independent assessment requires a fresh,
separate corpus, supervisor freeze/review, and must not reuse or reset the
one-shot access record after seeing results.
