# Stable rule catalog

Dictionary version: 2026.07.26. All vocabulary matches are medium severity editing prompts, with uncalibrated family thresholds. English vocabulary matching uses ASCII case folding; boundaries use Unicode alphanumeric characters plus underscore.

Reviewed code origins and dates for all stable IDs are recorded in the
[provenance sidecar](../dictionary/provenance.json). Code provenance and prior-art
style advice do not establish empirical authorship validity.

| Rule ID | Pattern | Matching | Guidance (leverage) |
|---|---|---|---|
| `delve` | `delve` | exact | `vocabulary.tell-word` (5) |
| `tapestry` | `tapestry` | exact | `vocabulary.tell-word` (5) |
| `multifaceted` | `multifaceted` | exact | `vocabulary.tell-word` (5) |
| `nuanced` | `nuanced` | exact | `vocabulary.tell-word` (5) |
| `leverage` | `leverage` | exact | `vocabulary.tell-word` (5) |
| `utilize` | `utilize` | exact | `vocabulary.tell-word` (5) |
| `seamless` | `seamless` | exact | `vocabulary.tell-word` (5) |
| `foster` | `foster` | exact | `vocabulary.tell-word` (5) |
| `pivotal` | `pivotal` | exact | `vocabulary.tell-word` (5) |
| `paramount` | `paramount` | exact | `vocabulary.tell-word` (5) |
| `holistic` | `holistic` | exact | `vocabulary.tell-word` (5) |
| `streamline` | `streamline` | exact | `vocabulary.tell-word` (5) |
| `transformative` | `transformative` | exact | `vocabulary.tell-word` (5) |
| `meticulous` | `meticulous` | exact | `vocabulary.tell-word` (5) |
| `intricate` | `intricate` | exact | `vocabulary.tell-word` (5) |
| `embark` | `embark` | exact | `vocabulary.tell-word` (5) |
| `beacon` | `beacon` | exact | `vocabulary.tell-word` (5) |
| `testament` | `testament` | exact | `vocabulary.tell-word` (5) |
| `plethora` | `plethora` | exact | `vocabulary.tell-word` (5) |
| `myriad` | `myriad` | exact | `vocabulary.tell-word` (5) |
| `moreover` | `moreover` | exact | `vocabulary.tell-word` (5) |
| `furthermore` | `furthermore` | exact | `vocabulary.tell-word` (5) |
| `nevertheless` | `nevertheless` | exact | `vocabulary.tell-word` (5) |
| `underscore` | `underscores` | exact | `vocabulary.tell-word` (5) |
| `showcase` | `showcase` | exact | `vocabulary.tell-word` (5) |
| `emphasize` | `emphasize` | exact | `vocabulary.tell-word` (5) |
| `facilitate` | `facilitate` | exact | `vocabulary.tell-word` (5) |
| `empower` | `empower` | exact | `vocabulary.tell-word` (5) |
| `robust` | `robust` | exact | `vocabulary.tell-word` (5) |
| `cutting-edge` | `cutting-edge` | exact | `vocabulary.tell-word` (5) |
| `paradigm-shift` | `paradigm shift` | exact | `structure.significance-inflation` (2) |
| `harness-verb` | `harness` | exact | `vocabulary.tell-word` (5) |
| `not-just-x-but-y` | `it'?s not just [a-z ]+, it'?s` | regex | `structure.negative-parallelism` (2) |
| `important-to-note` | `it is important to note that` | regex | `structure.signposting-filler` (2) |
| `rapidly-evolving` | `in today'?s rapidly evolving` | regex | `structure.significance-inflation` (2) |
| `cannot-be-overstated` | `cannot be overstated` | regex | `structure.significance-inflation` (2) |
| `embark-on-a-journey` | `embark on a journey` | regex | `structure.significance-inflation` (2) |
| `a-testament-to` | `a testament to` | regex | `structure.significance-inflation` (2) |
| `plays-a-role` | `plays a (crucial&#124;vital&#124;pivotal) role` | regex | `structure.significance-inflation` (2) |
| `worth-noting` | `it'?s worth noting` | regex | `structure.signposting-filler` (2) |
| `heres-the-thing` | `here'?s the thing` | regex | `structure.signposting-filler` (2) |
| `let-me-be-clear` | `let me be clear` | regex | `structure.signposting-filler` (2) |
| `uncomfortable-truth` | `the uncomfortable truth is` | regex | `structure.signposting-filler` (2) |
| `experts-agree` | `experts agree` | regex | `content.vague-attribution` (1) |
| `studies-show` | `studies show` | regex | `content.vague-attribution` (1) |
| `thats-it-thats-the-x` | `that'?s it, that'?s the [a-z ]+` | regex | `structure.signposting-filler` (2) |

`punctuation.em-dash-density`: medium severity, localized occurrences with a document-density heuristic. `statistics.burstiness`: low severity, document-wide sentence-length variation; has no invented source location. Readability, MTLD, compression and entropy remain informational metrics without actionable rules or votes.

Exact patterns enumerate overlapping candidates before Unicode boundary checks. Regex rules enumerate distinct starting positions but use the Rust regex leftmost-first alternation at each start; alternatives at the same start are not an exhaustive language enumeration. Empty patterns, duplicate IDs and non-vocabulary dictionary families are rejected. Regex compilation is limited to 64 KiB per expression.

## Experimental structure observations

The `structure` family runs in `review` and shared editorial analysis (including compare), not `detect`, `lint`, `analyze` or `scan`. It requires asserted English. Every observation is low severity, non-voting and unvalidated for editorial utility. Sentence units are separate from the frozen statistical segmenter. A finding is a prompt to inspect the passage, never an automatic correction or evidence of authorship. Repeated patterns retain their own locations; document patterns have one representative anchor and are counted once.

| Rule | Definition | Legitimate cases / false positives | Guidance (leverage) |
|---|---|---|---|
| `structure.negative-parallelism` | Short “not only … but …”, “isn’t … it’s …” and “not because … but because” contrasts. Equivalent active dictionary matches win after suppression. | Contrasts correcting misunderstandings. | `structure.negative-parallelism` (2) |
| `structure.rule-of-three` | Comma/and triad with at least two abstract nouns or members of a closed evaluative adjective lexicon; numeric, currency and proper-name lists excluded. | Deliberate rhetoric and technical categories; this is not a grammatical parser. | `structure.rule-of-three` (2) |
| `structure.coordinated-series` | Three or more coordinated -ing heads; optional after/before/by/while/when prefix; determiner-led nouns excluded. | Actual sequences and deliberate cumulative rhythm. | `structure.coordinated-series` (2) |
| `structure.significance-inflation` | Closed significance phrase patterns such as “marks a pivotal moment”; overlapping equivalent dictionary evidence wins. | Specific supported significance. | `structure.significance-inflation` (2) |
| `structure.copula-avoidance` | Serves/stands/functions/acts as or boasts with a short following phrase. | Temporary roles and functional descriptions. | `structure.copula-avoidance` (2) |
| `structure.cheerful-opener` | Paragraph-initial acknowledgement such as “Certainly!” | Dialogue and relational acknowledgements. | `structure.cheerful-opener` (1) |
| `structure.short-fragment` | Sentence unit of at most three words; annotation only, not a grammar judgment. | Complete short sentences, dialogue and emphasis. | `structure.short-fragment` (3) |
| `structure.summary-close` | Generic summary at final paragraph opening, or future-facing closing formula. | Useful recaps, teaching material and literal discussion of the future. | `structure.summary-close` (2) |
| `structure.challenges-future-formula` | Heading or paragraph opening using a challenges/future formula. | Literal future planning and required headings. | `structure.challenges-future-formula` (2) |
| `structure.repeated-opening` | At least three sentence units sharing their first two words within five units; one result per repeated opening. | Intentional repetition, procedures and learner exercises. | `structure.repeated-opening` (2) |
| `structure.fragment-pattern` | At least two short units and at least three per 500 prose words. | Dialogue, slogans, complete short sentences and emphasis. | `structure.fragment-pattern` (2) |
| `structure.uniform-paragraphs` | At least five paragraphs with two sentence units and word-count CV below 0.25. | Parallel reference entries and technical explanations. | `structure.uniform-paragraphs` (2) |
| `structure.bold-inline-headers` | At least three Markdown logical paragraphs/items beginning with a strong label ending in a colon. | Forms and compact reference labels. | `structure.bold-inline-headers` (4) |
| `structure.title-case-headings` | At least three headings of three words, with all words of four or more letters capitalized. | Publication style and proper names. | `structure.title-case-headings` (4) |
| `structure.list-heavy` | Markdown list units contain over half the prose words and at least 60% end in terminal punctuation. | Procedures, accessible reference material and factual lists. | `structure.list-heavy` (4) |

The 40 evaluative adjectives are explicit in `src/backends/structure.rs`. Unit display text normalizes CRLF carriage returns; `location.source_ranges` always refers to original UTF-8 bytes. Markdown entities and escapes can therefore differ from the raw slice. Inline code, fenced code and HTML are excluded from prepared prose. A dash in a list is labelled `list_separator` only when followed by a numeric or currency value; other list membership is labelled `list_item`.

`punctuation.em-dash-density` maps to `punctuation.em-dash-connectors` (4); `statistics.burstiness` maps to `rhythm.uniform-sentence-length` (3). The latter has no fabricated source location. Canonical guidance, exceptions, examples and heuristic provenance are in [guidance.json](../guidance/guidance.json). There is no claim of validated structural durability.
