# Humanization scoring decision

**Retain the shipped voting policy.** On the 42 high-confidence owner development posts, the list-separator and editorial-unit experiments each changed recall by 0 percentage points. Giving the structural family a vote increased observed recall by 25 points (7/28 additional generated drafts, paired bootstrap interval 10.7–42.9 points). Each candidate flagged 0/14 human controls, for a two-sided Wilson upper bound of 21.5%. The accepted ceiling is 5%. All three candidates remain informational. The medium-confidence human post was excluded. These posts share an author, genres are provisional, and writing era differs by label. No independent assessment was opened.

The historical baseline was built from commit `aef3b239c6266ae53f09f0b2a5d8f54e8f1de680` with the locked default release build. Candidate scoring used the default build with exactly one named experiment and asserted English, with the same empty JSON configuration on both binaries. The frozen neural models remain informational pending validation. [Development counts](../../evaluation/reports/humanize-v1-development.json) · [Release criteria](../../evaluation/release-criteria/humanize-v1.json)

## Reproduce development

Build the old binary from an independent checkout. With an empty JSON object in `baseline-config.json`, run the following once for each candidate ID in the criteria.

```sh
python3 scripts/humanize_decide.py development \
  --dev evaluation/corpora/owner-posts-v1/manifest.json \
  --baseline /path/to/baseline/nobotrs --binary target/release/nobotrs \
  --config baseline-config.json --candidate structure-votes --genres technical civic
```

## Prospective independent assessment

Before looking at independent text or predictions, declare genres and one candidate configuration. Supply a fresh manifest with id, source_group, content sha256, path, genre and verified human/ai label per document. Include one independently sourced document per group, verify authorship and near-duplicate grouping at curation, exclude reused development sources and keep source text local. At zero observed false positives each target genre needs at least 73 independent human documents. A smaller group remains underpowered.

The `freeze` operation takes the development arguments plus `--manifest PATH --record PATH`. It first reruns the candidate on development and requires it to qualify. A receipt alongside the independent manifest prevents re-freezing the same membership under a different record name in that directory. It binds membership, both executable hashes, the config, release criteria, genres and candidate into an exclusively created record. Only `evaluate` claims that record and reads held-out text. Failure consumes the access. Use a fresh independent set for another assessment. Record all abstentions and operational failures. Shipping also requires preserved editing behavior and all release checks.
