# Project fact consistency

1. Accept explicit text and Markdown sources. Extract anchored label/value assertions and Markdown tables with row and column labels. Support exact decimal amounts, percentages and dates. Retain entity, attribute, time and qualifier as part of the comparison key.
2. Compare matching keys in source order. Report conflict, corroboration, missing expected source claim, or insufficient evidence. A reference file establishes expected claims only when explicitly designated.
3. Report path, original line and column for every mention. Bound reads, extraction and comparisons. Avoid silently treating partial inputs as complete. Use human-readable and JSON output.
4. Exercise budget conflicts in a single source and across documents, different fiscal years, equivalent decimal amounts, absent claims, and unsupported ambiguous prose. Expand extraction against independently annotated examples before making broader coverage claims.
