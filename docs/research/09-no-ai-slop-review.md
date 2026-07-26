# Research 09: Review of `github.com/petergyang/no-ai-slop`

**Date:** 2026-07-26
**Purpose:** Assess whether the `no-ai-slop` skill offers anything worth borrowing for `nobotrs`'s design (`docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`).
**Sources fetched:**
- https://github.com/petergyang/no-ai-slop (repo overview)
- https://raw.githubusercontent.com/petergyang/no-ai-slop/main/README.md
- https://raw.githubusercontent.com/petergyang/no-ai-slop/main/SKILL.md
- https://raw.githubusercontent.com/petergyang/no-ai-slop/main/eval.md
- https://raw.githubusercontent.com/petergyang/no-ai-slop/main/agents/openai.yaml
- `gh api repos/petergyang/no-ai-slop` and `.../commits` (stars, forks, license, commit history)
- Compared against `/home/kwhatcher/projects/nobots/hooks/scripts/check_ai_tells.py` (existing tell-word/phrase list)

## 1. What it is, concretely

`no-ai-slop` is **not a program**. It contains zero executable code. The entire repo is four Markdown/YAML files:

- `README.md` — pitch, install instructions, pattern summary
- `SKILL.md` — the actual instruction set: editing principles, banned words, 14 named patterns, a workflow the LLM should follow
- `eval.md` — a self-check rubric (24 yes/no questions) the LLM is told to re-run against its own output before finishing
- `agents/openai.yaml` — a thin interface registration (`display_name`, `default_prompt`) so the same instructions can be wired into an OpenAI/Codex-style agent tool registry, not just Claude Code

"Install" means literally telling an agent "Install this skill globally: [URL]" — the agent fetches and internalizes the Markdown as a system prompt. There is no parser, no word-list file consumed by code, no scoring function. Every "detection" and every "fix" is performed by an LLM reading `SKILL.md`'s prose instructions and holistically judging the text, then self-grading against `eval.md`'s checklist. It has two modes: **Edit** (rewrite + "What changed" summary) and **Detect** (name each pattern found, quote the offending line, suggest a fix — explicitly told *not* to score or claim AI authorship).

## 2. Detection approach

Purely prompt-driven, qualitative LLM judgment — no deterministic string matching, no statistics, no ML classifier, nothing programmatic at all. This is a materially different category from `nobotrs`'s plan:

| | `no-ai-slop` | `nobotrs` (planned) |
|---|---|---|
| Mechanism | LLM reads instructions, applies judgment | `aho-corasick`/`regex` exact matching, hand-rolled stylometric math, optional ML classifier/perplexity, optional commercial APIs |
| Runs without an LLM in the loop? | No — requires an agent harness | Yes — standalone binary, offline-capable |
| Output | Prose findings / rewritten draft | Line-anchored evidence + confidence tier + quorum verdict |
| Reproducible/deterministic | No (LLM judgment varies by model/run) | Yes for the default tier |
| Validated against a corpus | No (rubric is self-graded, not benchmarked) | Planned (§8 of spec — eval corpus, quorum calibration) |

So on the "detection approach" axis, `nobotrs` is already the more rigorous, more portable design — `no-ai-slop` is closer to a well-written prompt/style guide than a detector.

## 3. Genuinely worth borrowing

Despite the architecture gap, the *content* — its banned-word list and named pattern taxonomy — is worth mining. Cross-checked against `check_ai_tells.py`'s existing `TELL_WORDS`/`TELL_PHRASES`:

**New tell-words not already in nobots' list** (nobots has: delve, tapestry, multifaceted, nuanced, leverage, utilize, seamless, foster, pivotal, paramount, holistic, streamline, transformative, meticulous, intricate, embark, beacon, testament, plethora, myriad, moreover, furthermore, nevertheless, underscores, showcase, emphasize):
- `facilitate`, `empower`, `robust`, `cutting-edge`, `paradigm shift`, `harness` — all listed by `no-ai-slop` as "outright cuts," none currently in nobots' `TELL_WORDS` regex. Straightforward additions.

**New tell-phrases not already in nobots' list** (nobots has: "it's not just X, it's Y", "it is important to note that", "in today's rapidly evolving", "cannot be overstated", "embark on a journey", "a testament to", "plays a crucial/vital/pivotal role", "it's worth noting"):
- Throat-clearing openers: "here's the thing", "let me be clear", "the uncomfortable truth is"
- Weasel attribution: "experts agree", "studies show" (unsourced-authority phrasing — a genuinely different signal category than nobots currently has: it's about *unsupported claims of consensus*, not vocabulary inflation)
- Dramatic fragmentation: "that's it. that's the [whole thing/point]" (recurring template)

**Structural pattern ideas** (no-ai-slop names 14 patterns total; most require semantic judgment an LLM applies at read time and don't reduce to a simple regex — e.g. "superficial analysis," "fake-strong verbs," "synonym cycling," "fake-profound kicker lines" — but three are concrete enough to be worth a look for a future deterministic rule, not adopted wholesale here):
1. **"Colon reveals"** ("The best part: it learns.") — a sentence-final colon followed by a short dramatic clause. Detectable via a cheap structural regex (colon near sentence end, followed by capitalized short clause), distinct from nobots' existing em-dash punctuation family. Plausible new `Punctuation`-family sub-signal.
2. **"Negative listing"** ("Not a tool. Not a gimmick. A necessity.") — consecutive short sentences starting with "Not a/an X." This is a recognizable, regex-able template.
3. **"Formatting slop"** (emoji headings, decorative bold, bullets-that-should-be-prose, headers over one-sentence sections) — this one is a particularly good fit for `nobotrs` specifically, because `Document`'s markdown-aware segmentation (spec §2.1) already parses headings/bullets/bold spans to *exclude* them from prose scoring. The infrastructure to also *flag* them as a lint signal (e.g. "3+ emoji in headings," "header directly followed by <20 words") is nearly free to add on top of that existing segmentation, unlike the other 11 patterns which need real semantic judgment.

None of these three warrant a new signal family on their own — they're better framed as additional deterministic rules feeding the existing `Vocabulary`/`Punctuation` families (or a small new `Formatting` family, gated on `content_type == Markdown`), consistent with the spec's existing quorum design.

**Not worth adopting:** the "often-empty adverbs" list (just, literally, honestly, simply, actually) — the source's own rubric requires judgment ("keep only when expressing genuine uncertainty") that a bare word match can't apply; this would need LLM-style reasoning to avoid heavy false positives on ordinary prose, cutting against `nobotrs`'s deterministic-tier design goals. Skip it, or treat as a `lint`-only low-confidence flag if pursued at all.

**Licensing:** MIT — no obstacle to reusing individual words/phrases (which are almost certainly not independently copyrightable as a bare list regardless). No need to vendor or attribute code since there is no code, only prose instructions.

## 4. Maturity and credibility

- **Stars:** 2,748. **Forks:** 217. **Open issues:** 9.
- **Created:** 2026-07-07. **Last push:** 2026-07-22. **8 commits total** — essentially a single burst of activity over ~2 weeks, then quiet for the ~4 days up to this review. Not abandoned, but very young (repo is under 3 weeks old) and low-commit-count; reads as a finished v1 rather than an actively iterated tool.
- **No tests, no CI, no code** — nothing to break, so "maturity" here really means "prompt wording has stabilized," not "battle-tested software."
- **Author:** Peter Yang (`petergyang`), writer of the "Behind the Craft" newsletter — a well-known product/growth commentator with a large following, which plausibly explains the fast star/fork growth (audience-driven virality) rather than technical adoption signal (e.g. citation in other tools, dependency usage). Not a credibility signal specific to NLP/AI-detection expertise.
- **License:** MIT, permissive, no reuse obstacle.

## 5. Bottom line

`nobotrs`'s plan is not threatened or outdated by this repo — it already covers far more ground (deterministic + stylometric + optional ML/perplexity/commercial-API tiers, quorum aggregation, line-anchored evidence, offline operation) than `no-ai-slop`'s pure-prompt, LLM-in-the-loop, unscored approach. `no-ai-slop` isn't a competing detector to benchmark against; it's closer to a style guide.

That said, there are **three concrete, low-effort items worth adopting**:
1. Add six new tell-words to the deterministic list: `facilitate`, `empower`, `robust`, `cutting-edge`, `paradigm shift`, `harness`.
2. Add a small set of new tell-phrases: `"here's the thing"`, `"let me be clear"`, `"the uncomfortable truth is"`, `"experts agree"`, `"studies show"`, `"that's it, that's the"`.
3. Consider two new structural regex rules (colon-reveal, negative-listing) and one markdown-formatting rule (emoji headings / decorative bold / tiny-section headers) as candidates for the `Punctuation`/new `Formatting` family — the formatting rule in particular piggybacks cheaply on `Document`'s existing markdown segmentation (spec §2.1).

No change to the spec's architecture, scope, or non-goals is warranted.
