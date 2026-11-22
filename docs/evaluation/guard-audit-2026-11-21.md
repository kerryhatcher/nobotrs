# Local corpus guard audit (2026-11-21)

Sanitized audit of the 12-word leak guard (`scripts/check_no_local_corpora.py`). It records
counts, classifications and how to reproduce them. It contains no matched text and no local
corpus content. The owner approved the exact exceptions on 2026-11-22.

## Result

Full coverage: Beemo was read through the local-AI venv's pyarrow, and CoAuthor through
`scripts/corpora.py`. The raw scan finds 29 hits. The table uses the reproduced
file-and-sample counts from 2026-11-22.

| Source | Hits | Corpus | Files affected |
|---|---|---|---|
| Legacy hits from the APT-Eval and GAO corpora | 17 | APT-Eval (6), GAO 2008 (11) | 10 tracked files |
| Hits from the Beemo corpus | 12 | Beemo (4 samples, 3 files) | 3 tracked files |

All 29 hits are in tracked files that predate the guard. These are `assessment-pilot-v1`
and `mixed-controls-v1`: `samples/`, `curation.json`, `manifest.json`, and `source/hc3/`.
These frozen corpus bytes were not modified.

## Classification

Each hit was measured on the local archive, under the same tokenisation as the guard:

- **Longest contiguous shared run:** 12 to 14 tokens in every case. None is a copied
  passage. A verbatim import would produce a run well beyond 14 tokens.
- **Shared 12-grams per file:** 2 to 9.
- **Corpus document frequency:** no shared 12-gram appears in more than two corpus samples.
- **Content of the shared runs** (described, not quoted):
  - a standard chatbot closing line (APT-Eval and Beemo hits);
  - a run of consecutive integers in a table (GAO hits);
  - a list of U.S. state names (GAO hits).

The audit classifies the hits as incidental overlaps of generic phrasing and enumerations.
The [allowlist](../../scripts/local-corpus-guard-allowlist.json) binds each of the 29
exceptions to the repository path, SHA-256 of the fixture bytes, corpus ID, and hashed
sample ID. The guard still scans those files. Changed fixture bytes, new paths and
matches against other samples are subject to the same 12-token rule.

## Staged-bytes check

The guard checks the index by default (`--source index`), exporting the staged blobs with
`git checkout-index`. `--source worktree` checks working-tree files. Tests in
`scripts/test_check_no_local_corpora.py` also verify that the allowlist is read from
the same snapshot as the checked files.

## Reproduce

```sh
# Run from the repository root. Beemo needs an interpreter with pyarrow.
NOBOTRS_INTERNAL_DIR=/mnt/storage/projects/nobotrs/docs/internal \
  ~/.cache/nobotrs-local-ai/venv/bin/python scripts/check_no_local_corpora.py
# Exit codes: 0 clean, 1 leak, 2 incomplete (a corpus could not be checked).
```

The same check runs in `scripts/acceptance.py` when the internal corpus directory exists.
Set `NOBOTRS_GUARD_PYTHON` to the pyarrow interpreter so Beemo is not reported as unchecked.
