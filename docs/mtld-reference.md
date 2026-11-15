# MTLD reference comparisons

`tests/fixtures/mtld-reference.json` contains six original synthetic token vectors
with outputs captured from LexicalRichness 0.5.1 at threshold 0.72. The fixture
records the SHA-256 of that package's `LexicalRichness.mtld` implementation.
Reproduce external values with:

```sh
uv run scripts/check-mtld-reference.py
```

The development-only checker verifies both package version and implementation
hash before evaluating the explicit token lists. It never rewrites expectations.
Ordinary Rust tests consume the checked-in JSON and require no Python packages,
downloads, or network access.

| Vector | Tokens | Reference MTLD |
|---|---:|---:|
| Repeated word | 180 | 2.0 |
| All unique | 160 | 160.0 |
| Exact threshold | 200 | 25.0 |
| Partial factor | 164 | 6.848654708520179 |
| Directional variation | 180 | 4.295454545454545 |
| Unicode and contractions | 180 | 6.0 |

Reference calls explicitly use `preprocessor=None, tokenizer=None`. The Rust
tests compare the same normalized tokens, then join them with spaces and check
the production document/backend path under an explicit English assertion. This
separates MTLD arithmetic from the Python library's default text cleaning. It
does not establish general Rust/Python preprocessing parity.

The exact-threshold vector has 18 types per 25 tokens, exercising factor closure
at TTR **equal to** 0.72. The directional vector places unequal unique prefixes
and suffixes around a repeated run to exercise forward/reverse averaging. The
all-unique case pins the reference's finite fallback when no factor closes.
Numeric comparisons use absolute tolerance `1e-12`; this is a regression
tolerance, not evidence that MTLD detects authorship. All six cases must produce
a scored backend outcome and no vote; abstention or failure cannot silently
satisfy the evidence-only assertion.
