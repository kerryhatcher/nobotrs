---
name: review-writing
description: Edit an existing English draft for a human reader. Use source-aware review and comparison to retain the author's purpose, facts and voice.
---

# Revise a draft

Read the draft and the [writing brief](references/writing-brief.md). Identify the intended reader and preserve an original copy under an unused path. Before changing a passage, say what the reader could misunderstand. Start with missing context, questionable evidence or an unclear action. Address structure and rhythm before individual words. Never fabricate a detail to make a sentence more specific.

## Review and compare

```sh
nobotrs review draft.md --language en --format json
nobotrs copyedit draft.md --language en
nobotrs compare original.md draft.md --language en --format json
```

Review ranks findings by leverage. Read the rationale and legitimate exceptions. Keep a deliberate repetition or parallel list when it helps the reader. For project facts, compare explicit sources with `nobotrs facts check draft.md --reference source.md`.

For each missing value, check whether the edit accidentally removed evidence. Restore it or record the author's correction. To acknowledge an intentional removal in a subsequent comparison, use the exact original text, for example `--accept-missing 'number=$8 million'`. Verify added claims against a source. Always check who did what, under which conditions and when. Two departments can exchange budget figures while every number survives. If the analysis is incomplete, report the unchecked material.

## CLI fallback

If the binary is not installed, use the bundled brief and compare the two drafts manually. Read quotes, code and link targets against the original. Explain substantive changes and flag unresolved questions. Detector scores have no role in deciding whether a rewrite is ready.

## When to stop

1. Resolve or consciously accept each priority finding in context.
2. Verify changed facts, attribution, uncertainty and requested actions against the sources. Record author-approved corrections and outstanding questions.
3. Stop after a pass yields no substantive improvement, or after three passes. Return unresolved questions to the author.
