# Readability reference comparisons

The six original, synthetic English passages in
`tests/fixtures/readability-reference.json` compare the current readability
heuristic with Textstat 0.7.10. They exercise simple prose, multisyllabic words,
contractions, quotation/punctuation, pronunciation exceptions, and varied sentence
lengths. Each sentence group is repeated twenty times to exceed the backend's
150-word floor. These are reusable behavior fixtures, not an authorship corpus.

Reference outputs were captured with Textstat 0.7.10, Pyphen 0.18.1, NLTK
3.10.4, and language `en_US`. Textstat uses the first CMU dictionary pronunciation
when available and Pyphen as a fallback. The exact CMU dictionary content hash
is recorded in the fixture. Reproduce the external outputs with:

```sh
uv run scripts/check-readability-reference.py
```

If the NLTK corpus is absent, explicitly install it with
`uv run --with nltk==3.10.4 python -m nltk.downloader cmudict`.
The checker rejects different dependency versions or dictionary content and does
not update expected values. Python packages and the corpus are development-only
dependencies; normal Rust operation and `cargo test --locked` stay offline.

| Passage | Textstat grade | Native grade | Native minus reference |
|---|---:|---:|---:|
| Simple | -1.190000 | -1.190000 | 0.000000 |
| Multisyllabic | 14.515000 | 16.727500 | 2.212500 |
| Contractions | -0.077895 | -0.077895 | 0.000000 |
| Punctuation | 2.375769 | 2.438462 | 0.062692 |
| Exceptions | 5.105556 | 3.138889 | -1.966667 |
| Varied sentences | 4.823333 | 3.755000 | -1.068333 |

The native algorithm trims surrounding nonletters, lowercases, counts transitions
into `a/e/i/o/u/y` vowel groups, subtracts a terminal `e` when the count exceeds
one, and returns at least one syllable. It does not consult a pronunciation
dictionary. Silent vowels, pronounced terminal `e`, vowel hiatus, and irregular
pronunciations can disagree with the reference. Segmentation also differs:
Textstat discards some very short sentences, whereas the shared native segmenter
retains them. A negative grade is a possible formula output and is not clamped.

Tests pin native grades and the recorded differences at absolute tolerance
`1e-9`; this is a numeric regression tolerance, not a claim of linguistic
accuracy or an acceptable error for arbitrary prose. The multisyllabic example
already exceeds the old single-fixture 1.5-grade tolerance. Readability remains
informational, requires an explicit English assertion, and contributes no vote.
