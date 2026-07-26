# nobotrs tell dictionary

This directory is licensed **CC BY-SA 4.0** (see `LICENSE` in this directory),
separately from the rest of the `nobotrs` repository, which is MIT-licensed
(see the root `LICENSE`). See the root `NOTICE` file for why.

## Schema

`entries.json` holds one JSON document: `schema_version`, `dictionary_version`,
and an `entries[]` array. Each entry:

- `id` (string): unique identifier.
- `kind` (`"word"` | `"phrase"`).
- `match_type` (`"exact"` | `"regex"`): `exact` entries are matched via
  `aho-corasick`; `regex` entries via the `regex` crate.
- `pattern` (string): the literal string (`exact`) or regex pattern (`regex`).
- `variants` (string array, `exact` entries only): morphological forms sharing
  this entry's `id`/`family`/`suggested_replacements`.
- `case_sensitive` (bool, default `false`).
- `whole_word` (bool, default `true`, `exact` entries only): word-boundary
  matching — without it, `"harness"` would match inside `"harnessed"`.
- `family`: the `SignalFamily` this entry votes into. Every entry in v1 is
  `"Vocabulary"` — `Punctuation` is code-only, not dictionary-driven.
- `category` (string): descriptive/organizational metadata for humans browsing
  the dictionary — not consumed by the aggregator.
- `suggested_replacements` (string array): feeds `lint`'s suggested-fix output.
- `model_era` (string array): optional, reserved for future per-era weighting.
- `source`, `notes`: optional free-text provenance/context.

## Contributing

**Before any external contribution is accepted**, contributors must license
their contribution under `CC-BY-SA-4.0 OR MIT`, mirroring this directory's
outbound terms. This is required so `nobotrs` can continue to embed the
dictionary in its MIT-licensed binary without needing per-contributor
renegotiation later. By opening a pull request that modifies `entries.json`,
you agree your changes are licensed `CC-BY-SA-4.0 OR MIT`.
