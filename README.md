# nobotrs

An offline Rust editor and heuristic detector for clear English that preserves the author’s facts, purpose, voice and qualifications. Start with the [canonical writing brief](guidance/brief.md), then use advisory `review` for located editing prompts. Each finding explains the reader concern, a possible edit and legitimate reasons to keep the original. The default build uses an embedded dictionary and six deterministic backends. The default build makes no network requests and requires no keys or model downloads. An opt-in build feature (`api-clients`) plus an explicit `--gptzero` flag can send the analyzed text to GPTZero for an informational comparison; that text leaves your machine, and the result never changes the nobotrs verdict (see [GPTZero comparison](#gptzero-comparison-opt-in)). Findings are editing prompts, not proof of authorship.

**Authorship detection did not qualify:** the independent pilot detected 2 of
104 generated samples and falsely flagged 2 of 89 human samples. Use findings
for contextual editing review. See the [full assessment](docs/evaluation/final-assessment.md).

The 2026-11-21 offline owner-archive baseline flagged **0 of 28 AI-drafted posts** (27 Clean, one inconclusive) and zero of 15 human-labelled posts. These are development measurements; the human posts are older and shorter. Full-archive counts include one medium-confidence human post, which primary analyses exclude. See the [baseline records](evaluation/baselines/owner-posts-v1-offline/run.json) and [provenance labels](evaluation/corpora/owner-posts-v1/manifest.json).

Install the humanization release with `cargo install --locked --git https://github.com/kerryhatcher/nobotrs --tag v0.2.0`. From a checkout, run `cargo install --locked --path .`. Rust 1.85 or newer is required. Code is MIT licensed; dictionary data retains its separate CC BY-SA 4.0 license (see `NOTICE` and `dictionary/LICENSE`).

```sh
# Draft, edit and check sources
nobotrs review draft.md --language en
nobotrs copyedit draft.md --language en --dialect american
nobotrs compare draft.before.md draft.md --language en
nobotrs facts check draft.md --reference budget-notes.md

# Read-only queries
nobotrs guide --format json
nobotrs ai-writing-guide
nobotrs config

# Detection
nobotrs detect README.md
printf 'delve leverage\n' | nobotrs lint - --format json
nobotrs lint docs/one.md docs/two.md --minimum-severity high
printf 'experts\nagree\n' | nobotrs lint - --markdown
nobotrs analyze essay.txt --language en --format json
nobotrs scan docs --format sarif > prose.sarif
```

`review` exits 0 for completed advisory analysis and 2 for incomplete analysis or operational errors. It rejects external services and SARIF. `--display-limit` applies once after suppression, ranking, counts and checklist calculation; limits 0 and 1 retain full counts. Checks explicitly report completed, skipped and incomplete states. Structural observations require `--language en` and remain experimental, low severity and non-voting. They run only in editorial analysis, preserving legacy detection budgets.

`copyedit` runs the full editorial analysis pipeline plus the native grammar/spelling
engine (src/copyediting.rs) and merges both into a single report.
`--dialect american|british` controls variant spelling rules.
`--allow-word` (repeatable) suppresses findings for project-specific vocabulary.
`--language en` is required for structural and readability checks.

`compare BEFORE AFTER` diffs two drafts: it reports which tells were removed, kept
or introduced (grouped by leverage), diffs metrics (sentence-length CV, em-dash density,
MTLD, Flesch–Kincaid grade), and checks hard fact invariants (numbers, quotes, URLs,
inline code). Exit 0 when complete with all hard facts preserved; exit 1 when a hard
fact from BEFORE is missing in AFTER; exit 2 on error. Added facts without a source
are listed with ``status: "confirm_source"``. Use ``--language en`` for English-specific
checks and ``--markdown`` when comparing Markdown files.

`facts check` compares labelled quantities, percentages and ISO dates across text files, Markdown tables and directories. For example, it can flag a draft that gives the Parks FY27 budget as $4 million when the reference gives $8 million. Findings include the original path, line and column. Different fiscal periods, currencies and approximate amounts are grouped separately. For labels shaped like “Parks FY27 budget,” JSON separates the entity, period, attribute, unit and qualifier. A pronoun or a possible short name or acronym receives an ambiguous status and needs source review. Other label shapes retain their original wording. The command exits 1 for conflicts or missing reference claims, 2 for errors, 3 when every group is unresolved, and 0 when at least one group is compatible and no conflict or required claim is outstanding.

`guide` prints the canonical brief. Its JSON includes `brief`, rule-linked `entries` with leverage, and guidance versions, while retaining the legacy `guide` field. `ai-writing-guide` prints the
[full AI writing field guide](docs/ai-writing-guide.md) as Markdown. Use
`--format json` for a JSON object with the full text in `guide`.

## Portable agent skills

Three skills are available. Install with the skills.sh CLI:

| Skill | File | Purpose |
|-------|------|---------|
| `nobotrs` | `skills/nobotrs/SKILL.md` | CLI reference and exit-code semantics |
| `humanize-writing` | `skills/humanize-writing/SKILL.md` | Draft from notes with no binary needed (stand-alone guide) |
| `review-writing` | `skills/review-writing/SKILL.md` | Revise a draft using `review`, `copyedit` and `compare` |

From a checkout:

```sh
npx skills add . --skill nobotrs
npx skills add . --skill humanize-writing
npx skills add . --skill review-writing
```

Install from GitHub with `npx skills add kerryhatcher/nobotrs --skill <name>`. The `nobotrs` skill
requires the separately installed binary. The other two work with or without it,
with a fallback to their embedded stand-alone guides.

## GPTZero comparison (opt-in)

To compare nobotrs with [GPTZero](https://gptzero.me) on the same text, build with the `api-clients` feature and pass `--gptzero` with `GPTZERO_API_KEY` set:

```sh
cargo build --release --features api-clients
GPTZERO_API_KEY=... ./target/release/nobotrs detect --gptzero essay.md
```

- **What is sent:** the full analyzed text, to `https://api.gptzero.me/v2/predict/text`. A notice with the character count is printed to stderr before the request. Nothing is sent without `--gptzero` (or `NOBOTRS_GPTZERO=true` / `"gptzero": true` in config) and a key.
- **What comes back:** a separate "GPTZero comparison" block (human output) or an `external` object (JSON) with GPTZero's predicted class, confidence category and class probabilities. It is labeled informational and is never part of nobotrs's verdict, families, quorum or exit status.
- **Failures** (missing key, rejected key, quota or rate limit, network error, text over 150,000 characters) are recorded in that block and never change the heuristic result or exit code.
- **Scope:** `detect` and `analyze` only. Using `--gptzero` with `lint` or `scan` is an error. Requests time out after 30 seconds.
- **Caveats:** GPTZero's terms, plan limits and pricing apply to your key. Both tools make probabilistic claims that have not been validated against each other; a single agreement or disagreement on one sample is not evidence about either tool's accuracy.

## CLI behavior

`detect` uses quorum (default 2) across independent eligible vocabulary, punctuation and burstiness families. `lint` reports individual findings and gates by minimum severity (default medium), regardless of quorum. `analyze` exposes the same raw metrics and typed backend outcomes, using detection status semantics. MTLD, readability, compression and entropy are informational and never satisfy participation. Each eligible family contributes at most one vote; backends in a family reduce to their strongest complete contribution. Current thresholds remain inherited, uncalibrated heuristics.

Exit status precedence is `2` (operational error/incomplete analysis), then `1` (actionable lint findings or a flagged ensemble), then `3` (inconclusive), then `0` (completed and unflagged). Empty/code-only input is inconclusive. A clean detection means configured tells did not meet the policy; it does not establish human origin. Short prose can produce useful lint findings even when document statistics abstain. Detection of short text has limited statistical coverage, reported through per-backend abstentions.

Markdown is inferred from `.md`/`.markdown`, or selected with `--markdown`. Plain-text stdin is the default. Variable-length/container fences, indented/inline code, front matter, HTML blocks, image alt text and link destinations are excluded. Visible links, headings, list items, quotations and table cells are retained. Soft breaks become spaces; entities are decoded; emphasis/link text stays adjacent. Paragraphs, headings, list items, table cells and excluded code create matching boundaries. Inline HTML comments retain rendered adjacency. Locations refer to original UTF-8 source and one-based Unicode scalar columns. Discontinuous findings provide explicit `source_ranges`; their bounding range is for navigation, not a safe contiguous edit. Context IDs reference the report's block/sentence source ranges.

Automatic language applicability is **unknown**. The old closed-set whichlang guess could accept Welsh as English, so it was removed. English-specific readability and MTLD abstain unless `--language en` is supplied. Other language overrides are reported as unsupported. An override is the user's assertion, not validated recognition; short/mixed text receives no automatic supported-language guarantee. Word/sentence segmentation and syllable counts are documented approximations, not a linguistic parser. See the [pinned readability comparisons](docs/readability-reference.md) for measured pronunciation and segmentation differences, [MTLD comparisons](docs/mtld-reference.md) for arithmetic and tokenization checks, and [compression/entropy references](docs/compression-reference.md) for native LZMA-Alone stream and token-entropy regression vectors.

Configuration is JSON at the platform `directories::ProjectDirs` path (`$XDG_CONFIG_HOME/nobotrs/config.json` on Linux, normally `~/.config/nobotrs/config.json`). Select another file with `--config` or `NOBOTRS_CONFIG`. Precedence is CLI > environment > file > defaults. Invalid files, unknown fields, backend names, rule IDs or numeric settings are errors. `config` reports effective values and origins. See [configuration](docs/configuration.md).

JSON uses schema version `1.0.0`, preserves metrics/method versions and backend abstention/failure details, and separates backend outcomes from family decisions. `complete`, `incomplete_reasons` and `analyzed_coverage` describe execution. Incomplete coverage is conservative, and oversized streams have unknown total size rather than a fabricated fraction. `emitted_findings`, `omitted_findings`, candidate audit counts, and `display_limit` describe rendering. Limiting display never changes completed policy or status. Diagnostics go to stderr. Human output is always uncolored, respecting `NO_COLOR` and pipes.

Default resource budgets: 1 MiB actual input bytes, 10,000 vocabulary candidates (including rejected boundaries), 8 MiB total vocabulary candidate text, 10,000 punctuation occurrences, 5 seconds cooperative analysis, and 200 displayed findings/audit records. Use `--max-bytes`, `--max-candidates`, `--timeout-ms` and `--display-limit`. Prefix analysis, candidate exhaustion, and expired work produce status 2; retained evidence is partial. Reads can block waiting for stdin; the budget does not preempt syscalls, parser calls, regex searches, sorting, or a native computation between checks. Document preparation and statistical loops poll cooperatively. If preparation expires, unfinished prose is discarded and the report is incomplete with zero analyzed coverage. Compression polls its reader; no hard timeout or sandbox is claimed. Scans process supported text extensions in sorted order, skip symlinks, `.git`, `target`, dependencies and virtual environments, and retain file/traversal errors.

Suppression uses stable [rule IDs](docs/rule-catalog.md). `--ignore-rule embark-on-a-journey` leaves `embark` eligible at the same occurrence. Global/per-path configuration and HTML comments (`nobotrs-ignore-file`, `nobotrs-ignore-next-line`, `nobotrs-ignore-block`) suppress rules before overlap selection and family reduction. Code-fenced examples are inactive. Next-line scope is the next physical source line; block scope is the containing retained block or the next retained block for a standalone comment. Local directives affect occurrences; document-wide burstiness only supports whole-file ignores. See [configuration](docs/configuration.md) for examples and audit semantics.

SARIF 2.1.0 uses original source locations, stable IDs and suppression metadata; document metrics do not get invented line locations. `runs[].columnKind` declares `unicodeCodePoints`, matching the Unicode scalar columns used by the source map. Result levels use a deliberate evidence-severity mapping: `low` → `note`, `medium` → `warning`, `high` → `error`, consistent with each rule's default level. These are heuristic warning levels, not calibrated probabilities or authorship determinations. Display limits also limit SARIF audit results, disclosed in run properties. [Code scanning](integrations/code-scanning.yml), the pre-commit hook definition and [advisory hook](scripts/advisory-hook.py) call the same installed binary. The advisory adapter translates Rust status 1 to the host's status 2 nudge; Rust status 2 is a tool failure and remains advisory silence with diagnostics. Install the binary before using the system pre-commit hook.

There is no validated authorship accuracy or calibrated probability claim. Common vocabulary, uniform rhythm or em dashes can occur in human prose; generated text can evade these rules. The [evaluation runner](docs/evaluation/README.md) separates reusable behavior regressions from licensed development/validation selection and frozen independent release evaluation. A limited RAID pilot now exists at [`evaluation/corpora/raid-pilot-v1`](evaluation/corpora/raid-pilot-v1): it is a partial API view of 1,100 rows, not the complete RAID benchmark. Its 218-sample independent-test split was retired as exposed selection data after a Git diff whitespace exposure; `retirement.json` records the retirement, and preflight/evaluation refuse freeze or independent assessment. See the [pilot documentation](docs/evaluation/raid-pilot.md). A separate joint HC3 + fresh RAID assessment pilot at [`evaluation/corpora/assessment-pilot-v1`](evaluation/corpora/assessment-pilot-v1) completed one frozen independent assessment. General authorship qualification is **FAILED / not-qualified**: independent recall was 0.019 and the detector is not useful as a general authorship detector. Engineering default-core/evaluation/integration gates passed, but no calibrated probability or general accuracy claim is made. See the [assessment pilot documentation](docs/evaluation/assessment-pilot.md) and [final assessment](docs/evaluation/final-assessment.md). Optional local evidence models are documented separately in [local model evidence](docs/local-models.md); they are opt-in, require external pinned artifacts, and never enter the heuristic quorum. A more representative corpus and independently labeled nonnative/human-edited evidence remain open evidence gaps; MCP/TUI and local-provider humanization remain deferred in the [remediation plan](docs/superpowers/plans/2026-10-10-nobotrs-review-remediation.md).

Dictionary contributions should retain IDs, metadata and licensing, pass schema/regex validation, and include boundary/overlap regressions. Changing voting thresholds or adding default voting signals requires development/validation evidence and a fresh independent release assessment when test results inform a revision.

Verify with `cargo fmt --check`, `cargo clippy --all-targets --locked -- -D warnings` and `cargo test --locked`. Run `python3 scripts/acceptance.py` for the real-executable functional-core checks, including package/install verification; use `--skip-package` for a faster local pass. See [release measurements](docs/core-validation.md) and [handoff](HANDOFF.md) for the implemented milestone and remaining gates.
