---
name: nobotrs
description: Use the offline nobotrs CLI to review plain text or Markdown for heuristic writing issues, interpret lint findings, or retrieve the full AI writing field guide.
---

# Review prose with nobotrs

Use an installed `nobotrs` on PATH. From a nobotrs checkout, use
`cargo run --locked -- <args>` or install with `cargo install --locked --path .`.
From another workspace, Cargo can install the repository version with
`cargo install --locked --git https://github.com/kerryhatcher/nobotrs.git nobotrs`.
If the installed binary lacks `ai-writing-guide`, use or install a newer checkout.

- Run `nobotrs lint draft.md --format json` for structured findings with rule IDs
  and source locations. For Markdown on stdin, use
  `nobotrs lint - --markdown --format json`. Plain-text stdin needs only `lint -`.
  For `lint`, exit status 1 means at least one editing finding met the minimum
  severity, and `actionable_finding_count` gives the number of those findings.
  The JSON `verdict` is a separate detection-quorum decision, so it can be
  `clean` while the exit status is 1 and `actionable_finding_count` is greater
  than 0. Report lint results from the exit status and that count, not from
  the verdict. Lint findings are editorial prompts; they are not authorship
  judgments.
- Run `nobotrs analyze draft.md --format json --language en` for document metrics
  and backend outcomes. Use `--language en` when the document is English.
- Run `nobotrs scan docs --format sarif` for a directory-level code scanning report.
- Run `nobotrs ai-writing-guide` when you need the full writing field guide.
  Read its stdout as Markdown. Use `--format json` to retrieve the text in the
  `guide` field. For a short overview, run `nobotrs guide`.

For prose analysis, exit status 0 means completed and unflagged, 1 means findings
or a flagged verdict, 2 means an error or incomplete analysis, and 3 means
inconclusive. Read the report on status 1 and check diagnostics and coverage on
status 2. Review the surrounding prose before recommending edits. Findings are
heuristic prompts for editing. Treat authorship as undetermined, including when
`detect` flags a document or returns a clean result.

## Related skills

- **`humanize-writing`** (`skills/humanize-writing/SKILL.md`): Draft tell-free prose
  from notes or a brief, with or without the nobotrs CLI. See that skill for the
  stand-alone drafting guide, leverage priorities and stop criteria.
- **`review-writing`** (`skills/review-writing/SKILL.md`): Revise an existing draft
  to remove AI tells while preserving facts, meaning and voice. Runs `review`
  and `compare` to track findings and fact invariants.

Both skills share the same stop criteria and are usable together: draft with
`humanize-writing`, then revise with `review-writing`.
