# Compression and entropy reference vectors

`tests/fixtures/compression-reference.json` contains seven original synthetic
plain-text vectors. They pin the native LZMA-Alone stream, compressed length,
ratio, and token entropy for the compression backend. These are regression
vectors, not an authorship corpus and not an independent accuracy reference.

Reference provenance:

- `lzma-rs` 0.3.0, Cargo.lock checksum
  `297e814c836ae64db86b36cf2a557ba54368d03f6afcd7d947c266692f71115e`.
- `lzma_rs::lzma_compress` with `compress::Options::default()`
  (`UnpackedSize::WriteToHeader(None)`).
- LZMA-Alone container: properties byte `0x5d` (lc=3, lp=0, pb=2), dictionary
  size `0x00800000`, unknown unpacked size `0xffffffffffffffff`, range-coded
  payload, and end-of-stream marker.
- The crate's `encode::dumbencoder` is a literal-only range coder. It has no
  LZ77 match finder and no preset/level control. Its output is **not**
  numerically interchangeable with Python `lzma.compress(..., preset=6)` or
  another LZMA implementation's compression ratio.

| Vector | Whitespace tokens | Document words | Entropy (bits/token) | LZMA ratio | Backend |
|---|---:|---:|---:|---:|---|
| Empty | 0 | 0 | 0.0 | 1.0 sentinel | abstained |
| Below floor | 149 | 149 | 7.219168520462161 | 0.4760357432981316 | abstained |
| Floor boundary | 150 | 150 | 7.228818690495881 | 0.4834862385321101 | scored |
| Repetition | 150 | 150 | 0.0 | 0.38 | scored |
| Mixed repetition | 150 | 150 | 1.703306214009066 | 0.4790697674418605 | scored |
| Unicode mixed | 160 | 184 | 4.321928094887363 | 0.7040540540540541 | scored |
| Varied prose | 180 | 180 | 3.584962500721156 | 0.5823529411764706 | scored |

The empty case has no encoded stream; the helper returns the documented `1.0`
sentinel and the backend abstains before compression. The below-floor case also
abstains, but its helper ratio and stream remain pinned. The Unicode vector
contains multi-byte words; document words use Unicode word segmentation while
entropy uses case-sensitive whitespace tokens, so the two counts differ.

Entropy is Shannon entropy over the prepared prose's case-sensitive
whitespace-separated tokens: `-sum p * log2(p)`, with no tokens yielding `0.0`.
It does not stem, lemmatize, strip punctuation, or merge case variants. The
compression ratio is `compressed_bytes / prepared_prose_bytes`; plain-text
preparation appends one block-boundary newline to nonempty prose.

Reproduce the independent checks with the Python standard library:

```sh
python3 scripts/check-compression-reference.py
```

The checker verifies the pinned crate version/checksum against `Cargo.lock`,
recomputes entropy with `collections.Counter` and `math.log2`, checks the
LZMA-Alone header, decompresses each pinned stream with `lzma.FORMAT_ALONE`,
and verifies the exact raw bytes, compressed length, SHA-256, and ratio. It never
rewrites expectations. The native encoder bytes are rechecked through the
production helper by:

```sh
cargo test --locked pinned_compression_reference
```

That Rust test is a regression check against the pinned native goldens, not
independent compression parity. The Python checker validates the container and
decompression independently, but it does not reproduce the native encoder's
compression decisions.

Limits: the literal-only encoder makes these ratios a byte-level range-coding
measurement rather than a general-purpose LZMA compression benchmark. Ratios
depend on the pinned crate and container, not on Python preset-6 behavior.
Entropy is a token-frequency summary, not a language model or calibrated
predictor. Compression and entropy remain informational, contribute no vote,
and do not establish authorship. The vectors are synthetic and do not measure
detection accuracy.
