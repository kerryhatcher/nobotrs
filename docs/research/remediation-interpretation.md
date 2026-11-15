# Research interpretation for the Rust core

Reviewed 2026-10-10 against the imported source-verification snapshot. Imported originals were preserved. This is an interpretation of that audit, not a fresh verification of every external source.

Snapshot status counts: `does-not-support-claim`: 34, `not-checked`: 15, `unreachable`: 12, `verified`: 145.

Vendor reports do not establish independent detector accuracy. Reachable sources can still fail to support the claim attributed to them. Disputed/does-not-support-claim/unverified entries are not evidence for a new default vote. A source summary, folklore about contractions/pronouns/passive voice, or parity with Python constants is not validation. No default voting signal was added on those grounds.

RAID-style cross-domain/generator/decoding/perturbation evaluation is a required direction, not completed work. Repeated CI fixtures are development evidence; independent test reuse after a result-informed revision is selection leakage. English-specific metrics abstain automatically because no validated open-set language detector is currently present.

Raw MTLD, Flesch-Kincaid approximation, LZMA ratio and entropy are measurements, not calibrated human probabilities. Compression uses lzma-rs defaults and is not numerically equivalent to Python preset 6.

Follow-up review 2026-11-14: [the snapshot audit](source-audit-2026-11-14.json)
binds the imported YAML by SHA-256 and preserves all 34 unsupported claim
descriptions for review. It records 152 sources marked independent, 52 marked
not independent, and 2 without a flag. These are the snapshot's classifications,
not fresh determinations that every non-independent source is a vendor report.
The original 206-source verification snapshot and imported files remain intact.

[Per-rule provenance](../../dictionary/provenance.json) now records reviewed dates
and pinned code-origin URLs for all 46 stable IDs, including correspondence to the
pinned Python reference where present. This closes the code-provenance gap, while
explicitly preserving the empirical-evidence gap: no rule is validated as an
authorship indicator by code ancestry or prompt/style guidance. No rule patterns,
family thresholds, or defaults changed. The [auditable-detector paper review](../evaluation/building-auditable-notes.md)
adds hard-negative, ablation, and domain-shift requirements; it supplies no blanket
validation for this dictionary.
