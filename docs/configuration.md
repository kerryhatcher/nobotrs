# Configuration and suppression

The JSON file accepts these settings (defaults shown):

```json
{
  "quorum": 2,
  "minimum_severity": "medium",
  "max_bytes": 1048576,
  "max_candidates": 10000,
  "timeout_ms": 5000,
  "display_limit": 200,
  "language": null,
  "enabled_backends": ["vocabulary", "punctuation", "burstiness", "lexical-diversity", "readability", "compression"],
  "ignore_rules": [],
  "path_ignores": { "docs/examples/*": ["embark-on-a-journey"] }
}
```

Path patterns use `*` (any sequence, including `/`) and `?` (one character); matching uses the displayed input path, so absolute invocation paths require absolute patterns. Scans skip symlinks and do not follow them. Direct file commands follow a supplied file symlink normally.

CLI settings replace the corresponding environment/file setting. Environment names are `NOBOTRS_QUORUM`, `NOBOTRS_MINIMUM_SEVERITY`, `NOBOTRS_MAX_BYTES`, `NOBOTRS_MAX_CANDIDATES`, `NOBOTRS_TIMEOUT_MS`, `NOBOTRS_DISPLAY_LIMIT`, `NOBOTRS_LANGUAGE`, and `NOBOTRS_IGNORE_RULES` (comma-separated). Configuration path precedence is `--config` > `NOBOTRS_CONFIG` > platform path. Origins are per setting. Environment variables with malformed values produce errors. CLI global ignore IDs replace, rather than append to, configured global IDs; path and inline scopes still apply.

```markdown
<!-- nobotrs-ignore-file statistics.burstiness -->
<!-- nobotrs-ignore-next-line embark-on-a-journey -->
We embark on a journey tomorrow.

This paragraph <!-- nobotrs-ignore-block embark --> contains a prompt to embark.
```

IDs are comma-separated; unknown IDs/scopes or malformed directives fail clearly. Comments in code fences are inert. A next-line directive covers exactly the next source line and cannot suppress a phrase extending beyond that line. Block directives cover a containing retained prose block or the next retained block after a standalone comment. Table cells and list items remain separate boundaries.

Pipeline order is candidate enumeration → boundary validation → suppression → longest eligible overlap selection → family votes → aggregation → display limits. Candidate audit records distinguish `selected`, `suppressed`, and `overlap_excluded`, with original source ranges and suppression reason. Selected evidence is the effective finding set. Display omission counts disclose incomplete rendering; losing policy-relevant candidates is incomplete analysis and status 2.

A document-wide burstiness rule can be suppressed globally/per-path/whole-file. A next-line/block directive does not remove that document metric or invent a new measurement. Punctuation retains its raw document measurements; occurrence suppression disables suppressed actionable occurrences. If every occurrence is suppressed its vote becomes None. The effective density vote uses unsuppressed occurrences over the original prose word denominator, while raw document metrics remain unchanged. Remaining occurrences become non-actionable if the effective density no longer meets the heuristic threshold.
