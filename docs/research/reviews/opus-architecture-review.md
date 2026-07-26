# Architecture & feasibility review — nobotrs design spec

**Reviewer role:** senior architecture / ML-systems review (critical pass)
**Spec under review:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`
**Also consulted:** `docs/research/00-consolidated-summary.md`; the Python original at
`/home/kwhatcher/projects/nobots/hooks/scripts/check_ai_tells.py` (198 LOC) and
`/home/kwhatcher/projects/nobots/scripts/deep_stylometry.py`
**Date:** 2026-07-26

---

## Verdict (up front)

**Needs another design pass before implementation planning — but a narrow, targeted one, not a
restart.** Sections 3–6 (CLI surface, config/secrets, packaging, plugin integration) are genuinely
solid: well-researched, decisions are made rather than deferred, and they could go to planning
today with only the exit-code and `full`-feature corrections below. The problem is concentrated in
§2.3–2.4 and in the trait signature in §2.1. The spec claims to carry forward
`check_ai_tells.py`'s quorum rule, but the Rust design changes *what the voters are* — from
feature families inside one detector to whole backends — without acknowledging the change or
re-deriving the rule for the new voter set. The consequence is not cosmetic: as specified, the
default two-backend build makes `QUORUM = 2` mean unanimity, a `full` build with four commercial
API vendors gets four strongly-correlated votes that trivially satisfy quorum, and there is no
defined mapping from "3 tell-words found" to a `human_probability` float in the first place. On
top of that, the single largest risk in the project — that the detector's accuracy and
false-positive rate are entirely unmeasured, with no eval corpus, no FPR target, and no
calibration plan — does not appear in §9's risk register at all, while a trivially-mitigated
license question about a crate the architecture does not even use (§7.3) does. The empirical
unknowns that *are* named are mostly well-hedged; the ones that aren't named are the dangerous
ones.

---

## Findings

Severity key: **blocker** = fix before planning starts, because getting it wrong forces a
breaking refactor or ships a detector that doesn't work; **important** = fix during planning;
**minor** = fix whenever.

---

### Group A — The `Score` / quorum design (§2.3–2.4)

This is the weakest part of the spec and the reason for the verdict.

#### A1. The quorum counts backends, but the rule it cites counts signal families. These are not the same partition. — **blocker** (§2.4, §2.1, §2.3)

§2.4 says the ensemble uses "the same **quorum rule** `check_ai_tells.py` already uses: a verdict
only fires when a minimum number of *independent signal families* agree." I read the Python. Its
families are `vocabulary`, `punctuation` (em-dash density), and `burstiness`
(`check_ai_tells.py:123–151`), and aggregation is literally `agree = len(families); if agree <
QUORUM: return 0` — a count of *feature families that fired*, all computed inside a single
detector.

The Rust design's voters are `DetectorBackend` implementations. Map the Python families onto the
tiers in §2.2 and the partition collapses:

| Python family | nobotrs tier (§2.2) |
|---|---|
| vocabulary | `deterministic` |
| punctuation (em-dash density) | `stylometric` |
| burstiness | `stylometric` |

Two of the three Python families are now the *same voter*. The default build (§2.2:
`deterministic` + `stylometric`, both always-on) therefore has exactly **two** voters, so
`QUORUM = 2` degenerates from "2 of 3 families agree" into "both backends must agree" —
unanimity. And the Python behaviour of firing on punctuation + burstiness *without* any
vocabulary hit becomes unreachable in Rust, because those two signals now live inside one vote.
The default nobotrs build is strictly less sensitive than the Python hook it is porting, in a way
the spec does not mention.

The type system makes this unfixable as written: `Score` (§2.3) carries `backend: String` and no
family identifier, so an aggregator *cannot* count families even if it wanted to. The
`DetectorBackend` trait returns one `Score` per backend, structurally forcing one vote per
backend.

**Recommendation:** decide explicitly whether the voting unit is a backend or a signal family. I'd
argue family, since that's what the false-positive lesson was actually about. That means `Score`
needs to carry a `Vec<FamilySignal>` (each with a family tag) rather than a single scalar, and the
`stylometric` backend emits several family signals rather than one. This is a change to the
central shared type — cheap now, expensive after five backends implement the trait.

#### A2. A fixed absolute `QUORUM` over a voter pool whose size is set by Cargo features means the same text gets different verdicts from different builds. — **blocker** (§2.4, §2.2)

`QUORUM = 2` is inherited from a Python tool with a *fixed* three-family pool. In nobotrs the pool
size is a build-time property: 2 voters in the default build, up to 5 tiers (and more, see A3) in
a `full` build. Two agreeing voters out of 2 is unanimity; two out of 8 is a weak plurality. The
spec commits to one absolute integer across both.

This also undermines the stated tuning plan. §2.4 says the constant is "tunable via config, not
hardcoded... may warrant retuning once real data is in" — but a single scalar cannot be tuned to
be simultaneously correct for every feature-flag combination users can compile. And see D-group:
nothing in the plan actually produces the "real data."

**Recommendation:** make the rule a function of the available pool (a fraction, or a weighted sum
with per-family weights and a calibrated decision threshold), and state the intended behaviour for
the 2-voter default explicitly. If unanimity in the default build is actually the desired
conservative behaviour, say so as a decision rather than letting it fall out as an accident.

#### A3. Four commercial API vendors as four independent votes breaks the exact premise the quorum rule rests on. — **important** (§2.2, §2.4)

§2.2 gates Sapling, GPTZero, Copyleaks and Pangram behind one shared `api-clients` feature, "one
client module per vendor." If each vendor module is a `DetectorBackend`, then a user with four
keys configured contributes four votes — and those four are not independent signal families in any
meaningful sense. They are four commercial classifiers trained on overlapping web-scale corpora,
several of which are known to agree with each other far more than any of them agrees with a
stylometric measure. Four correlated votes satisfy `QUORUM = 2` on their own, drowning out every
local signal and inverting the tool's "local-first" goal (§1) at verdict time.

**Recommendation:** the API tier should contribute **one** vote (e.g. a consensus or
highest-confidence-vendor reduction inside the tier), not one per vendor. State this in §2.4.

#### A4. There is no defined mapping from a deterministic hit-count to a probability, and the spec's design requires one. — **blocker** (§2.3)

This is the specific ambiguity the assignment asked me to name. §2.3 declares `human_probability:
f32` "the canonical continuous representation," and §2.4 then quorum-votes over the resulting
`Score`s. That pipeline requires answering two questions the spec never answers:

1. **How does "3 tell-words in 800 words" become a float?** The Python never needed to know:
   it went straight from a raw count to a discrete vote via a hand-tuned threshold
   (`total_hits >= 4` → strong, `>= 2` → suspicious — `check_ai_tells.py:126–131`). The spec
   inserts a probability in the middle of that path with no stated calibration. Any monotonic
   squashing function you pick (`1 - min(1, hits/N)`, a logistic, a lookup table) is an
   unjustified invention, and it is not a probability in any calibrated sense — a `0.3` from the
   deterministic backend and a `0.3` from a DeBERTa classifier's softmax mean completely different
   things, yet §2.4 combines them as if they were commensurable.

2. **At what threshold does a `human_probability` become a "vote"?** Quorum counts *agreeing*
   voters. Agreement is a binary predicate. The spec defines neither the threshold nor whether it
   is per-backend or global. So the design as written is: threshold a raw feature into a
   probability (§2.3), then threshold the probability back into a vote (§2.4) — a lossy
   double-thresholding whose only effect is to discard the per-feature threshold tuning that the
   Python version's accuracy actually came from.

There's a smaller instance of the same problem inside the `stylometric` tier: §2.2 lists lexical
diversity (MTLD) and readability (Flesch-Kincaid) as detection signals, but in the Python they are
**not voting families at all** — they are appended as human-readable context after the verdict is
already decided (`check_ai_tells.py:165–169`). The spec promotes two metrics that have never had a
decision threshold into a voting backend, and defines no threshold for them.

**Recommendation:** either (a) drop `human_probability` as the aggregation currency and keep the
Python's discrete `{abstain, suspicious, strong}` per-family vote — which is honest about what
these signals are and needs no calibration — or (b) keep the float but commit to a calibration
procedure and the labeled data to fit it (see D1). Option (a) is what I'd ship in v1; the float
can be reintroduced once there's data to calibrate against. Note that (a) is *not* a downgrade:
"3 tell-words" genuinely is ordinal, not probabilistic, and pretending otherwise is precision
theater.

#### A5. The trait has no way to abstain, and abstention is load-bearing. — **blocker** (§2.1, §2.3)

`fn score(&self, text: &str) -> Result<Score>` gives a backend exactly two outcomes: a `Score` or
an error. The Python explicitly needs a third: *"A family that cannot be measured (e.g. burstiness
on a short file) simply abstains"* (`check_ai_tells.py:122`), gated by `MIN_WORDS_FOR_STATS = 150`
and `MIN_WORDS_FOR_DIVERSITY = 50`. That abstention is a false-positive-avoidance mechanism, not
a convenience.

In Rust as specified, a backend that can't measure must either return `Err` — conflating "not
applicable to this input" with "the model failed to load," which are wildly different for a CI
exit code — or fabricate a `human_probability` of `0.5`, which is *not* abstention: `0.5` is an
affirmative claim about the text and would be counted as a participating voter, changing the
denominator in A2. There is no third option in the type.

Related: the Python header states *"Fails open on any unexpected error so a hook bug never breaks
a Write/Edit."* That's a deliberate safety property of the hook UX carried into §6, and
`Result<Score>` propagating an error out of one backend has no defined effect on the ensemble.
Does one failed backend fail `detect`, or is it dropped from the pool (again changing the
denominator)?

**Recommendation:** `fn score(&self, doc: &Document) -> Result<Option<Score>>` or an explicit
`ScoreOutcome { Scored(Score), Abstained { reason }, Failed(Error) }`. Define the ensemble's
denominator rule for each. This is a one-line change now and a cross-cutting refactor later.

#### A6. `ConfidenceTier` is defined but has no role in aggregation, and the ensemble's own confidence tier is never derived. — **important** (§2.3, §2.4, §1)

§2.3 gives every `Score` a `confidence: ConfidenceTier`. §2.4 never mentions it. So: does a
`Low`-confidence vote count the same as a `High`-confidence one in the quorum? Presumably not, but
it's undefined. And §1's goals promise the user "a confidence tier and reasons" as the top-level
output — yet there is no stated rule for reducing N per-backend tiers into one ensemble tier.

**Recommendation:** either use confidence as a vote weight (and say so) or drop it from `Score`
and derive the output tier solely from the quorum margin. Define the reduction either way.

---

### Group B — The `DetectorBackend` trait (§2.1)

The trait is sound *as a plugin seam* — feature-gated backends behind one trait is standard Rust
and the `sccache` precedent cited in §2.1 is apt. The problems are all in the signature.

#### B1. `text: &str` cannot carry both prose segmentation and original-file offsets, and every backend needs both. — **blocker** (§2.1, §2.3, §3)

Two requirements collide:

- `Score.evidence` is "line/offset-anchored" (§2.3) and `lint` produces a "line-anchored tells
  report" (§3) — so offsets must refer to the **original file**.
- Every stylometric measure in §2.2 is meaningless over non-prose. Burstiness over a bulleted
  list, em-dash density over a Markdown table, MTLD over a fenced code block, Flesch-Kincaid over
  YAML frontmatter — all garbage. The Python sidestepped this crudely but effectively by only ever
  running on `PROSE_EXTENSIONS = {".md", ".markdown", ".txt"}` written by a hook
  (`check_ai_tells.py:34`); nobotrs adds `scan <dir>` (§3) across arbitrary trees, which makes it
  far worse, and drops the extension gate entirely (see E3).

You cannot satisfy both with `&str`: stripping code fences to get clean prose destroys the offsets
that `Evidence` needs to point back at. You need a preprocessing stage producing a document that
owns the original text, the extracted prose spans, and the offset map between them — and that type
must be the trait's input, because every backend consumes it.

Markdown/code-fence handling is not mentioned anywhere in the spec. It looks like an
implementation detail and isn't: it determines the trait's input type. Discovering this after five
backends exist means touching all of them.

**Recommendation:** introduce a `Document` type (original text + prose spans + offset map +
detected content type) in §2 and make it the trait input. Decide the segmentation strategy
(Markdown-aware at minimum) before planning.

#### B2. The trait has no model lifecycle, and the spec drops the download mechanism the research identified. — **important** (§2.1, §2.2, §3, §5)

`score(&self, text)` implies the model is already loaded when the backend exists. For the
`classifier` and `perplexity` tiers that means construction has to handle: locating a local cache,
downloading multi-GB weights, verifying integrity, and allocating 8–10GB. None of that is in the
trait, and none of it is in §2.2's crate columns — the research's `hf-hub` recommendation
(consolidated summary, "Recommended stack") does not appear anywhere in the spec. §3 lists
`nobotrs config` as managing "model downloads," which is the only acknowledgement that this
problem exists, and it names no mechanism.

Concretely unanswered: does a first `detect` run block for a multi-GB download with no progress
UI? What happens behind a corporate proxy, or air-gapped — given §1's "local-first,
offline-capable" goal? Where are checksums? Is HuggingFace a hard runtime dependency for these
tiers, and what's the behaviour when it rate-limits?

**Recommendation:** add `fn availability(&self) -> Availability` (Ready / NeedsDownload{size} /
Unavailable{reason}) to the trait, name the download crate, and make model acquisition an explicit
`nobotrs config` step that `detect` refuses to trigger implicitly.

#### B3. `score(&self, text: &str) -> Result<Score>`, one file at a time, sequential, with no timeout, is the wrong shape for `scan <dir>` in CI. — **important** (§2.1, §2.4, §3)

Three separate consequences of the signature:

- **No batching.** Transformer throughput comes almost entirely from batching. A per-call
  single-text signature structurally forbids it, so `scan` over a 500-file docs tree with
  `classifier` enabled runs 500 independent forward passes.
- **No parallelism.** The trait declares no `Send + Sync` bound, so `scan` can't `rayon` across
  files without a later breaking change to the trait.
- **No time budget.** §2.4 says `detect` "runs every enabled backend." A twin-model perplexity
  pass on CPU is seconds-to-minutes; it gates the entire verdict, in a tool whose primary UX
  surface is a `PostToolUse` hook that fires on every file write (§6).

**Recommendation:** add `Send + Sync`, add an optional `score_batch`, and state explicitly which
tiers `scan` is allowed to run (I'd restrict `scan` to `deterministic` + `stylometric` by default
and require an opt-in flag for ML tiers).

#### B4. Three distinct kinds of "this backend isn't running" collapse into silence. — **minor** (§2.2, §3, §4)

A backend can be absent because it was compiled out (feature flag), disabled in config (§3
`nobotrs config`), or enabled-but-keyless (§4: "No commercial API is ever called without an
explicit key"). These are indistinguishable in the output as specified, yet they change the quorum
denominator (A2). A user seeing a weak verdict cannot tell whether the tool is under-powered or
misconfigured.

**Recommendation:** report the active voter roster and the reason for each abstention in both human
and `--format json` output.

---

### Group C — Are the named empirical unknowns adequately hedged? (§9)

Assessed one by one. Short answer: the named ones are mostly fine; the register is missing the
important ones.

#### C1. candle + `desklib` checkpoint (§9.1) — genuinely swappable, but the fallback is priced too cheaply. — **important**

This one is *correctly* identified as a swappable implementation detail: `DebertaV2SeqClassificationModel`
is confirmed to exist, `ort` + ONNX is a real fallback, and the `classifier` tier sits behind its
own feature flag so failure doesn't cascade into the default build. The architecture does not
depend on candle specifically — good hedging.

But "documented fallback" understates what taking the fallback costs:

- Binary size goes from ~50–80MB to ~100–150MB (§5's own figures) — a ~2× change to a number §5
  presents as a distribution-strategy input.
- Producing the `.onnx` artifact requires a **Python + PyTorch export toolchain**, which the spec
  never mentions. A project whose whole premise is a self-contained Rust binary quietly acquires a
  Python build-time dependency for artifact generation.
- Someone must then host, version, and integrity-check that artifact. §5's `cargo-dist` pipeline
  distributes *binaries*; it does not distribute models. There is no model-artifact distribution
  design anywhere in the spec (see also B2).

So the failure of §9.1 doesn't force an architecture redesign, but it does force a
build-and-distribution redesign that the spec has no section for.

**Recommendation:** keep the fallback, but write the model-artifact distribution story now
(hosting, versioning, checksums, offline install) since both branches need it.

#### C2. Model and checkpoint **licensing** is completely absent — and this is a real gap, not a hedge. — **blocker** (§9, §10, §7)

The spec's license diligence is impressively thorough for crates: §10 and the research
cross-checked ~20 crates against crates.io and caught the `rust_readability` GPL problem. §7.3 and
§9.2 track a single unconfirmed crate license as a first-class open item.

Not one word anywhere asks under what license `desklib/ai-text-detector-v1.01` may be
redistributed or used, or what the Falcon-7B / Falcon-7B-Instruct pair's terms are for the
perplexity tier. Model weights carry their own licenses, frequently with use restrictions
(non-commercial, acceptable-use, attribution, derivative-model clauses) that are materially more
restrictive than MIT/Apache and that apply to exactly the artifacts doing the actual detecting.

This is the clearest asymmetry in the document: meticulous about a 200-line stylometry crate,
silent about multi-GB model checkpoints that are the product's core value.

**Recommendation:** add checkpoint license verification for every model named in §2.2 to §9,
at the same priority as §9.1. Do it before prototyping, not after — it can eliminate a candidate
outright.

#### C3. `stylometry` crate license (§7.3, §9.2) — a non-risk being tracked as a risk. — **minor**

Note that `stylometry` does not appear in §2.2's crate column for the `stylometric` tier at all —
that tier is built on `unicode-segmentation` + `statrs` + `xz`. So §9.2 flags a license risk for a
dependency the architecture does not currently use. And the features it would provide (Mendenhall,
Kilgariff, hapax legomena) are each a few dozen lines, the same class of thing the spec already
decided to hand-roll for MTLD and Flesch-Kincaid (§2.2, §10).

The concern isn't the item, it's the register: this sits in §9 at the same visual priority as the
candle prototype, which distorts the risk picture.

**Recommendation:** decide now — hand-roll, don't depend — and delete the item.

#### C4. `postagger.rs` accuracy (§9.3) — correctly de-risked. — **minor, no action**

POS features are already scoped out of v1 (§7.2), so nothing in §2 depends on this. Keeping it in
§9 as a revisit-later note is appropriate. This is the one open item that's handled exactly right.

---

### Group D — The risks that aren't in §9 at all

#### D1. There is no evaluation corpus, no accuracy target, no false-positive-rate target, and no calibration plan. This is the project's largest risk and it is unlisted. — **blocker** (§8, §9, §2.4)

§8's testing strategy tests **code**, not **detection quality**: unit tests against "known-AI and
known-human text fixtures," mocked HTTP for API clients, feature-gated integration tests for ML
tiers. All correct and all orthogonal to the only question that matters for a detector — how often
is it wrong, and in which direction?

The gap has teeth throughout the spec:

- §2.4 says `QUORUM` is "tunable... once real data is in." **Nothing in the spec produces real
  data.** The tuning plan is circular.
- A4's calibration problem is unsolvable without labeled data.
- §2.2's stylometric thresholds are inherited from the Python's hand-tuned constants
  (`LOW_BURSTINESS_THRESHOLD = 0.35`, `VERY_LOW_BURSTINESS = 0.25`), which were tuned for a
  3-family vote, not a 5-backend ensemble.
- The whole point of the quorum rule is false-positive avoidance, and there is no FPR measurement
  anywhere.

**Recommendation:** add to §8 (and to the plan, early): a held-out labeled corpus, a stated target
FPR on human text, a per-backend and ensemble evaluation harness, and a rule that no threshold
constant ships without a number attached to it. This should be sequenced *before* the ML tiers, not
after — it's the thing that tells you whether the ML tiers are worth their weight at all.

#### D2. The primary UX surface feeds the detector exactly the inputs where all these methods are weakest, with no input gating. — **important** (§6, §3, §1)

§6's `PostToolUse` hook fires on file writes in a coding agent. That corpus is short diffs,
technical Markdown, code-adjacent prose, config files, changelogs — the regime where perplexity,
burstiness, and lexical-diversity signals are least reliable and where a tool like this generates
the most noise. Worse, the text was frequently *written by an LLM on purpose and that's fine* —
the user asked for it.

The Python guarded this with `PROSE_EXTENSIONS` and `MIN_WORDS_FOR_STATS = 150`
(`check_ai_tells.py:34–35`). Neither guard appears in the spec. `scan <dir>` (§3) removes even the
implicit hook-driven gating.

**Recommendation:** carry forward explicit content-type and minimum-length gates as first-class,
configurable parts of §2, and state the hook's intended precision/recall posture (I'd argue a
write-time nudge should be tuned for very high precision and accept poor recall).

#### D3. No stated position on the known false-positive profile of AI-text detection. — **important** (§1, §8)

AI-text detectors are documented to over-flag non-native-English writers and formulaic/edited
prose. The spec's tell-word list is English-only by construction (the Python's `TELL_WORDS` regex
is 35 English lemmas), and nothing detects or rejects non-English input. A tool whose output is a
verdict about whether a human wrote something needs an explicit statement of what it must not be
used for, and a documented behaviour on out-of-scope input.

**Recommendation:** add an explicit scope/limitations statement and hard-gate on detected language.

---

### Group E — The twin-model perplexity tier in v1 (§2.2)

The assignment asked for my honest engineering opinion regardless of the prior decision, so:

#### E1. GGUF quantization invalidates the published Binoculars threshold, and there is no data to recalibrate against. — **blocker for shipping it as a voting backend** (§2.2, §9, §8)

This is the argument I'd lead with, and it isn't in the spec anywhere. Binoculars' entire value is
a *calibrated decision threshold* on the cross-perplexity ratio between a matched base/instruct
pair. That threshold was fit against full-precision logits. §2.2 proposes `llama-cpp-2` + GGUF
quantization as an option precisely to fit the pair in consumer RAM — but quantizing shifts the
logit distributions the ratio is computed from, so the published threshold no longer holds. You
would need to refit it. Refitting requires a labeled corpus, which per D1 does not exist.

Net: the tier as specified would ship an **uncalibrated implementation of a method whose only
value is its calibration**, contributing a vote to a quorum (A1–A4) on the basis of a number
nobody has validated. That's worse than not shipping it — a confidently-wrong heavy backend is a
liability, not a feature.

The RAM and download costs (~8–10GB, multi-GB fetch) are real but honestly, they're the *lesser*
objection; those are at least disclosed and opt-in behind a feature flag, which is defensible.
The calibration problem is the one that makes the feature not work rather than merely be expensive.

#### E2. `candle` vs `llama-cpp-2` is presented as a coin flip; it is actually a release-pipeline decision. — **important** (§2.2, §5)

§2.2 lists the perplexity tier's crates as "`candle` or `llama-cpp-2` (GGUF quantization)" and
leaves it there. These are not interchangeable from a distribution standpoint: `llama-cpp-2` is
C++ FFI with a build-time toolchain requirement, which directly complicates §5's `cargo-dist`
pipeline across five targets including Windows and aarch64 — the exact story that made pure-Rust
`candle` attractive in the first place. Picking it later means retrofitting the release pipeline.

Also worth noting on feasibility: a Binoculars-style ratio needs full-vocabulary logits per token
from *two* models. That is not a well-trodden high-level path in either crate (`llama-cpp-2`
exposes it via `logits_all`, at real cost; candle requires assembling it yourself). The single
table row §2.2 devotes to this tier is, by a wide margin, the largest engineering chunk in the
project — a proportionality mismatch that will distort effort estimates during planning.

#### E3. Recommendation — a middle path that keeps the owner's decision

I would not simply cut it, since the owner explicitly chose it. But I'd push back on shipping it
as a *voting* backend in v1. Concretely:

1. Keep `perplexity` as a `DetectorBackend` behind its own feature flag — the interface is right.
2. Ship it in v1 as **experimental and non-voting**: it reports the raw cross-perplexity ratio and
   its evidence, and is excluded from quorum aggregation until a calibration exists.
3. Promote it to a voting backend once D1's corpus exists and a threshold has been refit against
   the *quantized* numerics actually shipping.
4. In the meantime the stylometric tier already carries a cheap perplexity proxy (compression
   ratio, §2.2), which covers the same signal family at ~0GB RAM.

That preserves the feature, ships something real, and quarantines the one part that can't be
validated yet.

---

### Group F — Other risks a cold read surfaces

#### F1. The `full` meta-feature turns on third-party data egress behind a convenience alias. — **important** (§2.2, §4, §3)

§2.2: "A `full` meta-feature enables all five tiers." Tier five is `api-clients`. So `cargo install
--features full` plus configured keys means `detect` ships the user's text to four commercial
vendors. §4's guarantee ("No commercial API is ever called without an explicit key") is the right
guarantee but it's the *only* guard, and it makes the decision hinge on key configuration rather
than on informed intent.

The `scan <dir>` case is sharper: a CI job running `nobotrs scan` on a private repo with a `full`
build and keys in the environment uploads that repo's prose to four external services. That's a
data-exfiltration event triggered by a flag named "full."

This also quietly resolves the research's open decision #7 ("decide whether any commercial backend
ships in the default `full` feature set given the cost/privacy implications") in the affirmative,
via an alias definition rather than a stated decision.

**Recommendation:** exclude `api-clients` from `full` (or rename it), and require an explicit
per-invocation opt-in for any run that will send text off-machine, especially in `scan`.

#### F2. Exit codes conflate findings with errors, and collide with Claude Code's hook exit semantics. — **important** (§3, §6)

§3: "Exit codes follow standard linter convention (0 = clean, non-zero = tells found)." Two
problems:

- "Non-zero = tells found" leaves no code for *tool failure*. A model that failed to load and a
  detected tell-word are indistinguishable to CI. The actual standard linter convention is 0 =
  clean, 1 = findings, 2 = error.
- More seriously, this collides with §6's hook. The Python hook exits **2** to feed stderr back to
  Claude, and 0 silently (`check_ai_tells.py:14`); in Claude Code's hook protocol 1 is a
  non-blocking error while 2 is the feedback path. A `nobotrs lint` that returns 1 on findings
  would make the hook take the *error* path instead of the *nudge* path — i.e. the flagship UX
  silently doesn't work. The §6 wrapper has to translate, and the spec doesn't say so.

**Recommendation:** adopt 0/1/2 = clean/findings/error, and state the hook wrapper's exit-code
translation explicitly in §6.

#### F3. The relationship between `detect` and `lint` — and whether `lint` invokes the quorum — is unstated. — **minor** (§3, §2.4)

`detect` runs the ensemble and produces a verdict; `lint` produces a line-anchored report from
overlapping engines. Does `lint` apply the quorum, or is it a pure reporter that shows every hit
regardless? This matters because the hook's entire behaviour in the Python version *is* the quorum,
and §6 doesn't say which command the hook calls.

**Recommendation:** state that `lint` reports without gating and `detect` gates, or vice versa —
and name the command the hook invokes.

#### F4. `candle` is pre-1.0 with a churning transformers API; no pinning strategy is stated. — **minor** (§2.2, §5)

`candle-transformers` breaks across minor versions. For a tool distributing prebuilt binaries via
`cargo-dist` *and* offering `cargo install` (where users resolve dependencies themselves), a
pinning and MSRV policy is worth one line.

#### F5. Mocked API-client tests can't detect vendor schema drift. — **minor** (§8)

§8's "no live network calls in the test suite" is the right call. The consequence is that mocked
responses will keep passing forever after a vendor changes its response shape. Worth a manually-run
contract-test tier, or at minimum a documented periodic re-verification.

---

## Verdict (restated)

**Needs another design pass — targeted, not a rewrite.** My confidence in §§3–6 is high; the CLI
surface, config/secrets precedence, `cargo-dist` pipeline, and the locate-don't-bundle plugin
decision are well-grounded in the research, decisive, and I'd hand them to planning as-is (modulo
F1 and F2). The research underneath the whole document is unusually good — the verification pass
that caught the `rust_readability` GPL issue and the `is-it-slop` misattribution is exactly the
diligence this kind of spec usually lacks.

What blocks planning is §2. The design does not yet answer the central question the tool exists to
answer: *how do heterogeneous signals combine into a verdict?* §2.4 answers it by citation —
"the same quorum rule `check_ai_tells.py` uses" — but the Rust design changed the voters from
feature families to backends (A1), which breaks the rule's arithmetic in the default build, breaks
its independence premise in the `full` build (A3), and requires a probability calibration the
Python original deliberately never needed (A4). Those aren't refinements to defer into
implementation; they determine the shape of `Score`, the shape of the trait's return type (A5),
and the trait's input type (B1) — the three things every backend touches. Getting them wrong is a
five-backend refactor.

The empirical-unknown handling is the other half. §9's *named* items are mostly well-managed:
the candle/desklib prototype is genuinely swappable behind a feature flag with a real fallback
(C1), `postagger.rs` is correctly deferred (C4), and the `stylometry` license item is a non-risk
that can be closed today (C3). The problem is what's absent: model-checkpoint licensing (C2), and
above all the total absence of an evaluation corpus, FPR target, or calibration plan (D1). D1 is
load-bearing for §2.4's own tuning story, for A4's calibration, and for E1's judgment on the
perplexity tier — it's the single highest-value thing to add.

Concretely, I'd gate planning on five items: **A1/A2** (define the voting unit and make the quorum
rule scale with the pool), **A4/A5** (define the signal→vote mapping and add abstention to the
trait), **B1** (introduce a `Document` input type with prose spans and offset mapping), **D1**
(add an eval corpus and an FPR target to §8, sequenced early), and **C2** (verify model checkpoint
licenses). On the perplexity tier I'd ship it non-voting and experimental in v1 (E3) — that
respects the owner's decision to build it while keeping an uncalibrated signal out of the verdict.
Everything else in this review can be resolved during planning.
