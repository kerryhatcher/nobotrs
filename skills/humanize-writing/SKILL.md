---
name: humanize-writing
description: Draft clear English from a person's notes or brief while preserving their meaning, evidence, qualifications and voice. Works offline without the nobotrs executable.
---

# Draft from the author's brief

Read the [stand-alone writing brief](references/writing-brief.md) before any tool. Identify the audience, the question the reader came to answer, and the action the author wants them to take. Write down the supplied evidence and any limits on what it establishes. Ask for a missing detail if the argument depends on it. Never fabricate a quote, source, number or personal experience.

Choose a structure that serves the material.

- **Civic explanation.** If the notes say the council *may* vote on repairs Friday, lead with the possible vote. Keep “may.” Give the cost only if the notes supply it. Approval and completion dates would be separate claims. A decision deadline also gives no date for a public announcement. Promise an update only when the notes say who will give it and when.
- **Tutorial.** State prerequisites, put commands in execution order, preserve the supplied flags and show the expected result. Parallel steps often make a tutorial easier to follow.
- **Opinion.** Lead with the author's position, give their strongest evidence and identify the inference. Use first person only for an experience or judgment the author supplied.

Draft an opening that answers the reader's question. Give each following paragraph a purpose. Read the result aloud and check whether the vocabulary and rhythm suit the author. A technical term, short fragment or repeated phrase can earn its place.

## Optional CLI pass

Run the following after drafting. Read the surrounding passage before applying a suggestion.

```sh
nobotrs review draft.md --language en
nobotrs copyedit draft.md --language en
```

If you revise, save the original under an unused path and run `nobotrs compare original.md draft.md --language en`. The CLI fallback is a manual comparison with the notes and the brief. Check each changed claim and identify anything the writer must confirm.

## When to stop

1. Resolve or consciously accept each priority finding in context.
2. Verify changed facts, attribution, uncertainty and requested actions against the sources. Record author-approved corrections and outstanding questions.
3. Stop after a pass yields no substantive improvement, or after three passes. Return unresolved questions to the author.
