# Mixed controls v1 (development only)

`evaluation/corpora/mixed-controls-v1` is a separate, development-only corpus of
mechanical HC3 mixed controls. It does **not** modify, split, or rebuild the
assessment manifest.

## Construction

For each HC3 question that has both human and generated answers in the
**assessment development split only**:

1. select the deterministic first human answer and first generated answer by
   answer index;
2. concatenate exact bytes as `human_prefix + 0x0a0a + generated_suffix`;
3. assign `label: null` and
   `generator: mixed-human-prefix-generated-suffix`.

No validation or independent-test sample is read. The source assessment
manifest/content hashes, source sample IDs/content hashes, separator hex, and
operator version are recorded per sample and in `curation.json` /
`source/PROVENANCE.json`.

## Counts and identity

```text
controls            156
source questions    156
split               development only
labels              all null (mixed origin)
manifest_sha256     f2130c03e4de3a27c8cf7b6628177ef8f30be04db237eebc21bef6e91778a4a1
corpus_content_sha256 d101fd6dcf291d0ec7b3744fbc6aee3b89cbf64584a93ff9f5111a9a5e8803c0
curation_sha256     49587de251826f3ec1be1c30354f861b351d3a0b27f03bcd9f9070cedda1b756
summary_sha256      b31db0aaa7acb8b7e401321db7e790d6fa247ae724f0ae6098d0254ff9bb8539
```

The controls are CC-BY-SA-4.0, with Hello-SimpleAI / Guo et al. attribution and
ShareAlike obligations. See `NOTICE` and the copied HC3 source card.

## Use and non-claims

- Mixed-origin labels are `null`; unknown labels are excluded from
  precision/recall denominators and reported separately.
- No native-speaker, nonnative-speaker, or human-edited evidence is available or
  inferred.
- No detector has been run.
- This is not independent-test evidence, a complete HC3 benchmark, or an
  authorship accuracy certification.
- Reviewers must not display source questions, answers, or payloads.
