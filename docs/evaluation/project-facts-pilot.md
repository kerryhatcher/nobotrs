# Project facts checker: developer-annotated pilot

**Date:** 2026-11-21
**Author:** Developer (no prior inspection of `src/cli/facts.rs`)
**Scope:** 12 labelled cases (4 conflicts, 4 compatible, 4 missing/ambiguous)
**Fixture:** `tests/fixtures/facts-pilot.json`
**Binary:** `nobotrs facts check - --format json --language en`

---

## Method

Each case was authored from the external interface only — by reading `--help`
output and running the CLI against probe inputs. No source code in
`src/cli/facts.rs` was inspected before writing the labels. The 12 cases were
then run against the production binary and the results were compared to the
pre-written expected status.

---

## Results summary

| Case | Type | Scenario | Expected | Actual | Match? |
|------|------|----------|----------|--------|--------|
| C01 | conflict | Same FY, same $, different amount | conflict | conflict | ✓ |
| C02 | conflict | Table, same agency, different $ | conflict | conflict | ✓ |
| C03 | conflict | Decimal vs integer (same value) | compatible | compatible | ✓ (normalisation works) |
| C04 | compatible | Exact duplicate | compatible | compatible | ✓ |
| C05 | compatible | Comma-grouped vs million | compatible | compatible | ✓ |
| C06 | compatible | Percentage repetition | compatible | compatible | ✓ |
| C07 | compatible | Different attribute words ("shortfall" vs "deficit") | compatible | **unresolved** (2 groups) | ✗ |
| C08 | missing | Single claim | unresolved | unresolved | ✓ |
| C09 | ambiguous | Same label, different currency ($ vs £) | ambiguous | **2 unresolved groups** | △ |
| C10 | ambiguous | Approximate qualifier (~) | ambiguous | **compatible** (tilde preserved) | ✗ |
| C11 | missing | % vs raw count | unresolved | unresolved (2 groups) | △ |
| C12 | missing | Two programmes, same FY, same $ amount | unresolved | unresolved (2 groups) | △ |

**Legend:** ✓ = matches expectation exactly; △ = acceptable divergence; ✗ = expectation was wrong.

---

## Key findings

### 1. Label anchoring is strict (C07, C12)

The checker groups facts by the extracted label string. "FY27 shortfall" and
"FY27 deficit" produce labels `fy27 shortfall` and `fy27 deficit` — two groups,
both unresolved. A human would likely see these as the same FY with the same
$8 million figure and mark them compatible.

Similarly, "FY27 food aid" and "FY27 fuel aid" produce separate `fy27 food aid`
and `fy27 fuel aid` groups even though both are $5 million. The tool is
conservative: different attribute words → different groups. This is correct
design (it avoids merging unrelated things) but misses a compatibility
relationship a human would spot.

**Recommendation:** Add a proximity or overlap heuristic: if two labels share
a fiscal-year anchor and the difference is only in the attribute word, and the
normalised values are identical, note the compatibility.

### 2. Unit mismatch is invisible (C09, C11)

When the same label appears with different units (C09: $ vs £, C11: % vs count),
the checker creates separate groups per unit. Both groups get status
`unresolved` (one mention each). There is no cross-unit warning.

A human seeing "FY27 grant: $8 million" and "FY27 grant: £8 million" would ask:
are these the same grant converted, or two different grants? The tool currently
offers no opinion.

**Recommendation:** When exactly one label appears under multiple units with
the same numeric magnitude, emit a `unit_mismatch` advisory.

### 3. Approximate qualifier is handled, not skipped (C10 — surprise)

Contrary to my assumption, the `~` prefix does NOT prevent extraction. The
checker parses `~$8 million` into unit `"approximate $"` and normalised value
`8e6`. Two identical approximate values are `compatible`. This is better than I
expected — the tool preserves the approximation in metadata rather than
silently dropping it or refusing to extract.

The only risk: if one source says `$8 million` (exact) and another says
`~$8 million` (approximate), they form separate groups (units `$` vs
`approximate $`) and are never compared. An unsuspecting user might not notice
the split.

### 4. Decimal and comma normalisation works correctly (C03, C05)

`$7.2 million` → normalized `72e5`; `$7,200,000` → normalized `72e5`.
`$8 million` → normalized `8e6`; `$8,000,000` → normalized `8e6`.
All compatible with exit 0. No false conflicts.

### 5. Single-claim groups exit 3 (C08, C07, C09, C11)

Any group with only one mention exits 3 (inconclusive). This is consistent
and documented but means multi-group inputs regularly exit 3 even when the
user only wanted to verify one fact.

---

## Cases that confused the author

**C10** — I incorrectly labelled it `ambiguous` expecting `~` to block
extraction. The tool handles it. I should have checked this before writing the
label.

**C07** — I expected "shortfall" and "deficit" to merge under `fy27`. The tool
treats them as separate labels. My expectation was wrong about label merging.

**C12** — When the two sentences are on the same line (`. ` separator),
extraction fails entirely (0 facts). On separate lines both are extracted but
as separate groups. This was reproduced and corrected after the pilot. The regression test now checks adjacent assertions with decimal amounts and Unicode source columns in plain text and Markdown.

---

## Recommendations for users

1. For reliable fact comparison, ensure comparable claims share the **exact
   same label wording**. "FY27 shortfall" and "FY27 deficit" won't be compared.
2. When mixing currencies, verify that separate `$` and `£` groups are
   intentional.
3. Single-claim files always produce exit 3. Use `--reference` to supply
   expected values.
4. Check that table headings correctly propagate into fact labels
   (they do for simple cases; test your layout).
