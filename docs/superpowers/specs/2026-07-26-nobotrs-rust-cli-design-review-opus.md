# Independent review — `2026-07-26-nobotrs-rust-cli-design.md`

**Reviewer:** Claude Opus 5 (single-agent, independent)
**Date:** 2026-07-26
**Target:** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md` (317 lines, post 3 prior review rounds)
**Prior rounds this review does *not* repeat:** the 5-agent consolidated review, the Gemma 4 12B review, and the DeepSeek 4 Flash review, all already applied.

## Method

Because the spec has already survived three review passes, re-reading it for plausibility has low yield. This review instead **checks the spec's factual claims against primary sources**:

| Source consulted | Used for |
|---|---|
| `/home/kwhatcher/projects/nobots/hooks/scripts/check_ai_tells.py` (198 lines, read in full) | Every claim of the form "mirrors / carries forward `check_ai_tells.py`" |
| crates.io API (live, 2026-07-26) | `xz`, `xz2`, `lzma-rs`, `cargo-dist`, `statrs`, `whichlang`, `owo-colors` versions + licenses |
| `docs/research/03-stylometric-statistical-crates.md` | LZMA crate selection lineage |

Findings are tagged **[verified]** where a primary source is cited with a line reference, and **[judgment]** where the finding is a design argument rather than a checkable fact. Severity is my own ranking, not inherited from prior rounds.

**Overall:** the spec is in strong shape — the prior rounds visibly worked, and §2.1/§2.4's error/abstention handling is better than most shipped detectors manage. The findings below cluster into one theme: **the fixes from the last round were applied at the layer they were found in, and not propagated to the adjacent layers.** The "false green" fix reached `detect`'s output but not its exit codes; the family-vs-backend correction reached §2.4's prose but not §2.1's trait signature; the calibration discipline of §7 item 4 was applied to `MlPerplexity` but not to the three stylometric families that need it for the same reason.

---

## Blockers

### B1. The `DetectorBackend` trait cannot express what §2.2 and §2.4 require of it [verified — internal]

§2.2 states: *"A single backend can house more than one family (e.g. `stylometric` houses **four independently-abstaining families** in one implementation)."* §2.4 states: *"A family whose backend returned `ScoreOutcome::Abstained` or `Failed` **for this document** contributes no vote at all."*

But the trait (§2.1) is:

```rust
fn score(&self, doc: &Document, deadline: Deadline) -> ScoreOutcome;   // ONE outcome
// where ScoreOutcome::Scored(Score), and Score { family: SignalFamily, ... }   // ONE family
```

One `ScoreOutcome` carries at most one `Score`, which carries exactly one `SignalFamily`. So:

- The `stylometric` backend physically cannot return four votes, and cannot abstain on `Readability` while scoring `Burstiness` — the exact behavior §2.2 promises.
- `deterministic` has the same problem (`Vocabulary` + `Punctuation`).
- On the default build, this collapses the advertised six-family quorum to **two votes**, which makes `QUORUM = 2` unanimity — which is, ironically, exactly the failure mode §2.4 says it corrected ("*a naive Rust port that voted by backend would silently make the default two-backend build's `QUORUM = 2` mean unanimity*"). The spec diagnosed the bug in prose and then reintroduced it in the type signature.
- §2.4's `warnings: Vec<{ family: SignalFamily, error: Error }>` has the same shape mismatch — `Failed(Error)` is produced by a *backend*, and there is no way to attribute it to one of that backend's several families.

**Fix (pick one):**
- (a) `fn score(&self, ...) -> Vec<ScoreOutcome>` with `Score.family` distinguishing entries, plus `fn families(&self) -> &[SignalFamily]` replacing `fn family(&self)` so the aggregator knows which families were *expected* and can detect a missing one; or
- (b) drop multi-family backends entirely — one backend per family, six default backends, `prose_spans` precomputation (already specified) making the re-parse cost a non-issue.

(b) is simpler and makes `availability()`/`Failed` attribution exact; (a) preserves the single model-load seam that `score_batch` exists for. I lean (b) for the default tiers and (a)-style batching only for ML tiers, which are already single-family.

### B2. Three of the six default families were explicitly *excluded* from voting in the source implementation, and the spec promotes them without saying so [verified — `check_ai_tells.py:123–172`]

The Python builds exactly three voting families:

```python
families["vocabulary"]  = ...   # line 128/131
families["punctuation"] = ...   # line 135/137
families["burstiness"]  = ...   # line 147/149
agree = len(families)           # line 155
```

MTLD, Flesch-Kincaid, and the LZMA ratio *are computed* — and are then appended to the message under this literal wording (line 172):

> `" Additional context (informational, not independently calibrated): "`

They are deliberately non-voting because they are uncalibrated. §2.2 of the spec turns all three into first-class voting families (`LexicalDiversity`, `Readability`, `Compression`) with no acknowledgment that the implementation it ports from held them out for cause.

This matters three ways:

1. It is the sole mechanism by which "three families" becomes "six" — and therefore the sole reason §2.4 has to argue that `QUORUM = 2` is now "a much looser bar."
2. It is inconsistent with the spec's own principle. §7 item 4 holds `MlPerplexity` non-voting *because it isn't calibrated yet*, and argues that case at length. The identical argument applies verbatim to these three, and isn't made.
3. §8.1 says no threshold ships "with a real number behind it" without the corpus — but these three families need more than a threshold; they need evidence they carry independent signal at all.

**Fix:** ship `LexicalDiversity`, `Readability`, and `Compression` as **evidence-only in v1**, exactly as `MlPerplexity` is, and state that §8.1 calibration is the gate on promoting them to voting. That leaves a 3-family default build with `QUORUM = 2` — the same 2-of-3 bar the Python actually validated in production — and makes §2.4's calibration story a promotion decision rather than a demotion risk.

### B3. The six "independent" families are not statistically independent [judgment]

§2.2 already applies exactly the right reasoning to commercial vendors:

> *"all configured API vendors collapse into a single `CommercialApi` vote, not one vote per vendor, since commercial detectors are often trained/calibrated on overlapping data and are not independent signals."*

That reasoning is not applied to the spec's own families, where it also holds:

- **`Burstiness` ⟂ `Readability` is false.** Flesch-Kincaid grade = `0.39 × (words/sentences) + 11.8 × (syllables/words) − 15.59`. Mean sentence length is a *primary term* of FK and the denominator of burstiness (stdev/mean). Uniformly long sentences move both. Two votes, one underlying property.
- **`LexicalDiversity` ⟂ `Compression` is weak.** MTLD measures type-token turnover; LZMA ratio measures redundancy. Repetitive text depresses one and inflates the other by construction.

Consequence: under `QUORUM = 2`, **a single stylistic property can satisfy quorum by itself** — which is precisely the "a lone strong family is not enough on its own; agreement across channels is what carries signal" rule (`check_ai_tells.py:153–154`) being defeated while appearing to be honored. Long, even-length, formal sentences (a technical spec, a legal doc, a translated text) trip Burstiness + Readability together.

**Fix:** either collapse correlated measures into one family the way `CommercialApi` is collapsed (e.g. a single `SentenceShape` family taking the stronger of burstiness/readability), or state the correlation explicitly and make §8.1's calibration measure the pairwise correlation of family votes on the corpus before fixing `QUORUM`. Adopting B2 largely dissolves this too.

### B4. No minimum-signal floor, and no `Inconclusive` verdict — the false-green fix is half-applied [verified — `check_ai_tells.py:34–38, 143`]

The Python gates its statistics on explicit input floors:

```python
MIN_WORDS_FOR_STATS = 150        # burstiness/diversity/readability gated on this
MIN_WORDS_FOR_DIVERSITY = 50
if len(lengths) < 5: return None  # burstiness needs ≥5 sentences
```

The spec carries none of these forward. Two failure modes follow:

- **Small denominators.** On a 40-word file, most families abstain; if two that don't (e.g. `Vocabulary` on two tell words, `Punctuation` on three em dashes) both vote, quorum fires on a sample far too small to mean anything. `QUORUM` is an absolute count with no floor on how many families *could* have voted.
- **Universal abstention reads as `Clean`.** §2.4 correctly identifies that `Failed` must not masquerade as clean, and adds `warnings` for it. But a document where every family legitimately *abstained* produces `verdict: Clean, warnings: []` — byte-identical to a document that was fully analyzed and found human. That is the same false-green class the round just fixed, exiting through the door next to the one that got locked.

**Fix:** add a third verdict state (`Inconclusive` / `NotEnoughSignal`) fired when fewer than `QUORUM` families were *able* to vote, and port the Python's word/sentence floors into §2.2's per-family abstention rules explicitly (they're currently gestured at only as "text too short for burstiness" in a code comment).

### B5. Exit codes don't encode the `warnings` state — CI still goes green on a broken backend [verified — internal, §2.4 vs §3]

§2.4 establishes that `Clean` + non-empty `warnings` ≠ `Clean` + empty `warnings`, and requires both the human and JSON outputs to surface the difference. §3's exit-code contract was not updated to match:

```
0 = clean, 1 = tells/verdict found, 2 = tool failure
```

A corrupted `classifier` model on a CI runner therefore yields `verdict: Clean`, `warnings: [ModelLoadFailed]`, **exit 0** — the pipeline passes green. The revision note at the top of the spec names this exact risk ("*a stuck/corrupted `classifier` model could otherwise let `detect` report 'human-written' when it simply never got to vote*") and the fix stopped at the output layer, where a CI system never looks.

**Fix:** define the exit code for `Clean`-with-warnings. Options: exit `2` (treat a non-voting enabled backend as tool failure — safest for CI, noisiest for laptops), or a distinct code (`3`), or a `--strict` flag promoting warnings to exit `2` with exit `0` as the default. Any of these is fine; leaving it unstated is not, because whatever the implementer picks silently becomes the CI contract.

### B6. §9 item 4 blocks the release on the wrong legal question [judgment — not legal advice]

§9 item 4 and §11.4 frame this as: *does embedding CC BY-SA content in a binary obligate the binary under CC BY-SA?* — and gate the first tagged release on a legal opinion about it.

As framed, the question mostly dissolves: **a licensor is not bound by its own outbound license.** If the project holds copyright in the dictionary, it can publish `dictionary/` to the world under CC BY-SA 4.0 *and* embed the same content in an MIT binary under its own reserved rights (or by dual-licensing the data, e.g. `CC-BY-SA-4.0 OR MIT`). ShareAlike constrains downstream redistributors, not the copyright holder. Option (a) is then available immediately, and §11.4's "unsolved gap" for `cargo install` never has to be solved.

The two questions the spec *should* be asking instead, neither of which it raises:

1. **Inbound contributions break sole ownership.** §11.5 explicitly invites external dictionary contributions. The moment a third party's entries land under CC BY-SA, the project is no longer the sole holder and *cannot* unilaterally relicense the embedded copy. This needs deciding **before** contributions open — via a CLA, or an inbound `CC-BY-SA-4.0 OR MIT` dual-license stated in `dictionary/README.md` from day one. This is the real, time-sensitive blocker, and it's currently unmanaged.
2. **Is a word list copyrightable enough for ShareAlike to bite?** Individual words and short phrases are not copyrightable subject matter (37 CFR 202.1(a)); a curated compilation attracts only thin selection-and-arrangement copyright. The protection §11.1 is buying may be substantially weaker than assumed, which is worth knowing before it gates a release. (Creative Commons itself recommends against CC licenses for software and points database publishers at CC0/ODbL; ODbL is the more conventional pick for "keep the data open and attributed.")

**Also:** option (b) as written **contradicts §3.1's own definition of done**. §3.1 requires `nobotrs detect README.md` to work "fully offline" on a default build with "no model downloads," and requires `cargo install nobotrs` to work end-to-end. §11.4(b) concedes `cargo install` would need "a required one-time `nobotrs config fetch-dictionary` step." So (b) fails the stated DoD, and the two options are not actually equally weighted — the spec presents a balanced choice that its own §3.1 has already decided. Say so.

---

## Important

### I1. `Deadline` cannot deliver what §2.1 claims [judgment]

§2.1: *"`score`/`score_batch` take a `Deadline` … **so a hung model load or a slow API call can't block `detect`/`scan` indefinitely**."*

A deadline passed by value into a synchronous method is **cooperative**: it only works if the callee polls it. A backend already blocked inside `llama_cpp` FFI, inside a `candle` CUDA kernel, or inside a `reqwest::blocking` syscall polls nothing — the deadline expires and the caller is still blocked, because there is no caller running to notice. The spec is admirably honest that FFI *crashes* can't be caught; it should be equally honest that FFI *hangs* can't be preempted either. (`reqwest`'s 30s timeout is real, and is a different mechanism — a client-level timeout, not the `Deadline`.)

**Fix:** state what `Deadline` actually is — a cooperative budget backends must check at defined checkpoints (between batch items, between tokens, before model load) — and, if `detect` genuinely must not hang, specify the enforcement mechanism: run ML backends on a worker thread the caller can abandon (leaks the thread, bounded blast radius), or a subprocess the caller can kill (real preemption, more machinery). §8's "a backend that never returns must not hang `detect`/`scan`" is currently a test for behavior the design cannot produce.

### I2. `match_type: "exact"` silently drops the seed data's matching semantics [verified — `check_ai_tells.py:41–55`]

The seed list the dictionary is "seeded from" is:

```python
TELL_WORDS = re.compile(r"\b(delve|delves|delving|tapestry|…)\b", re.IGNORECASE)
```

Two semantics are load-bearing there and absent from §11.3's schema:

- **Word boundaries.** `aho-corasick` is a substring matcher. `"harness"` as an `exact` entry matches inside `harnessed`, `"era"` inside `operation`, `"beacon"` fine, `"foster"` inside `Foster` (a name). Without `\b` equivalence this is a false-positive generator on the `Vocabulary` family — the one family that fires most often.
- **Case.** No `case_sensitive` field exists, so sentence-initial `"Delve into…"` is a coin flip on the implementer's choice.

Also: §11.3's longest-match-wins rule requires `aho-corasick`'s `MatchKind::LeftmostLongest` — the default (`Standard`, leftmost-first semantics) does not implement it, and the cross-engine merge with `regex` hits needs its own defined step since the two matchers produce independent match sets.

**Fix:** add `case_sensitive: bool` (default `false`) and `whole_word: bool` (default `true`) to the entry schema; state `MatchKind::LeftmostLongest` and the cross-engine merge rule in §11.3.

### I3. §11.3's own worked example doesn't match its own seed text [verified]

```json
"pattern": "it'?s not just [a-z ]+, it'?s"
```

The Python source of this exact pattern is compiled with `re.IGNORECASE` (line 55). As written in the spec, with no flags field and no case option, this entry fails on `"It's not just a feature, it's…"` — sentence-initial, which is where the construction almost always appears. The single worked example in the schema section is a live bug. Fixed by I2's `case_sensitive` field.

### I4. `dictionary/words.json` + `phrases.json` contradicts the single-document schema [verified — internal, §11.2 vs §11.3]

§11.2 specifies two files. §11.3 shows one document containing `schema_version`, `dictionary_version`, and an `entries[]` array holding both `kind: "word"` and `kind: "phrase"` records. These cannot both be right. If two files, each needs its own version pair and the `kind` field is redundant.

Related gaps in the same schema:
- **Nothing maps an entry to a `SignalFamily`.** `category` is `"vocabulary"` / `"structural-phrase"`, and `SignalFamily` is `Vocabulary` / `Punctuation` — the correspondence is guessable but unstated, and `structural-phrase` maps to neither by name.
- **`Punctuation` has no dictionary representation at all** (em-dash density is inherently a count, not a match rule). §11.3's scope-boundary paragraph carves out the three structural patterns as code-level checks but doesn't mention punctuation, so the `deterministic` tier's second family is silently code-only. One sentence fixes it.
- **Morphology.** The seed has `delve|delves|delving` as three alternates under one concept; the schema has no `variants` field, so this becomes either three entries with three ids or a regex entry — worth deciding, since `suggested_replacements` should attach to the concept, not each inflection.

### I5. Discrete voting caps the strongest backend at the strength of the weakest [judgment]

§2.4: votes are `Abstain | Suspicious | Strong`; `ConfidenceTier` explicitly does not weight them. So a fine-tuned DeBERTa classifier returning `human_probability: 0.01` casts exactly one vote — the same weight as three em dashes. With `QUORUM = 2`, **a maximally confident ML classifier cannot flag a document alone.** A user who enabled `classifier`, downloaded the weights, and got an unambiguous verdict sees `Clean`.

The quorum rule was designed (`check_ai_tells.py:19–24`) to stop *weak heuristics* from firing alone. That rationale doesn't transfer to a calibrated model, and the spec inherits the constraint without re-deriving it for the new tier. Note this is the mirror image of §7 item 4's UX concern about `perplexity`: the spec worries loudly that users who paid 8–10GB for a non-voting tier will be confused, and doesn't notice that the voting tier has an adjacent problem.

**Fix:** either allow a single `Strong` vote from `MlClassifier` to meet quorum on its own (an override the corpus can validate), or state explicitly that even a certain classifier requires corroboration and why. Either is defensible; the current silence means the implementer decides.

### I6. The plugin hook wires up the wrong command, and changes who sees the feedback [verified — `check_ai_tells.py:14, 180`]

§6's `PostToolUse` hook invokes `bin/nobotrs lint --format json`. But §3 states `lint` deliberately applies **no quorum** and emits "every backend's raw evidence (including sub-quorum, single-family hits)." The ambient scan-on-write UX therefore fires on any file containing a single tell word — the exact false-positive behavior the quorum rule exists to prevent, routed around by the flagship integration. The Python hook it replaces runs the full quorum path and stays silent below it.

Second issue, same paragraph: `check_ai_tells.py` returns **exit 2** on findings — its own docstring (line 14) says *"exits 2 (stderr fed back to Claude)"*, and `analyze()` returns 2 at line 180. §6 maps `nobotrs`'s exit 1 to "the hook's non-blocking-feedback code, never to its blocking code," claiming this matches existing behavior. It doesn't: the Python's "fails open" property (line 194, `except: return 0`) is about *hook bugs*, not about *findings*. Per the documented hook exit-code table, exit 2 is what feeds stderr back to **Claude**, while other non-zero codes surface to the **user** and the model never sees them. The proposed remap would drop the model-feedback loop that is the entire point of the ambient UX.

**Fix:** point the hook at `detect` (or `lint --quorum`), and re-verify the exit-code mapping against the current Claude Code hooks documentation before locking it in — I'm citing the Python's own docstring as primary evidence for what the existing behavior is, and the hooks table from documentation, which is worth confirming directly.

Also unstated: **`lint`'s exit codes.** §3 defines the code table once, generically, and §3 then defines `scan`'s semantics specifically — `lint`'s are never pinned down, and the hook depends on them.

### I7. `scan` is specified as two different commands [verified — internal, §3]

Line 147: `# batch lint across a directory`. Line 155: exit `1` "if any file in the tree triggers a **`detect`-equivalent quorum verdict**." But §3's own middle paragraph says `lint` does not apply quorum. So `scan` is a batch `lint` with a `detect` exit code, and its *output* (per-file evidence, or per-file verdicts?) is undefined. Given CI is `scan`'s stated primary consumer, this is the contract that matters most.

### I8. The `xz` crate pin needs stating, and the compression preset is part of the threshold [verified — crates.io, 2026-07-26]

The spec's `xz` (pure-Rust LZMA)` label is **correct** — I checked, expecting an error, and found `xz` v0.4.x is a genuine pure-Rust fork of `xz2` (`youknowone/xz-rs`), MIT OR Apache-2.0. But:

| crate | max version | note |
|---|---|---|
| `xz` | **0.4.6-rc.0** | pure Rust; **only a pre-release exists in the 0.4 line**; `0.1.0` (2020) is the old xz2 lineage |
| `lzma-rs` | 0.3.0 (stable) | pure Rust, 33M downloads |
| `xz2` | 0.1.7 | liblzma C binding — what research 03 evaluated |

`xz = "0.4"` in `Cargo.toml` **will not resolve** — Cargo excludes pre-releases from ordinary version requirements. This needs an explicit `"0.4.6-rc.0"` pin (a knowing choice to depend on an RC) or `lzma-rs`. Worth one line in §10 either way.

Separately: `check_ai_tells.py:78` uses `lzma.compress(raw, preset=6)`. **The compression ratio is meaningless without its preset** — a threshold calibrated at preset 6 does not transfer to preset 9, and §8.1's corpus tuning silently bakes in whatever the implementer picks. Pin the preset next to the threshold. (Same class of issue: MTLD's TTR factor threshold is `0.72` in the Python, and standard MTLD averages a forward and a reverse pass — §10's hand-rolled version must match both, or the Python's numbers don't carry over. §8's "published reference test vectors" requirement is the right instinct; naming the two parameters makes it actionable.)

### I9. §8's "bounded-time" regex CI check tests the wrong thing with the wrong tool [verified — `regex` crate API]

§8 requires patterns to be "compiled in CI with a bounded-**time** limit," and cites the crate's `size_limit` option as the justification. `size_limit` (and `dfa_size_limit`) bound **compiled program size in bytes**, not compile time. A wall-clock assertion in CI is machine- and load-dependent — it will flake on a busy runner and pass on a fast one, which for a merge gate on external contributions is the worst combination.

**Fix:** assert that every entry compiles successfully under `RegexBuilder::size_limit(N)` with the same conservative `N` §11.3 already specifies for runtime. Deterministic, machine-independent, and it tests exactly the property the runtime mitigation relies on.

### I10. Keyring last in precedence means the plaintext file wins [judgment]

§4: `env var → config file → OS keychain`. The keychain — the most protected store, and the one §4 calls "opt-in hardening" — is consulted only after the plaintext TOML. A user who moves a key into the keychain but forgets to delete it from `config.toml` keeps using the plaintext copy, with no indication. Consider `env → keychain → config file`, or have `nobotrs config` warn when both are populated.

### I11. §2.4's bolded claim contradicts its own paragraph [verified — internal]

> **The default build's quorum is explicitly unanimity, stated on purpose, not by accident.** The default (`deterministic` + `stylometric`) build exposes six independent families …, so `QUORUM = 2` here is a **much looser bar** than the Python's 2-of-3 ever was.

Six families with `QUORUM = 2` is 2-of-6, which is the opposite of unanimity — as the sentence immediately following says. This reads as a leftover from the pre-correction draft (where two *backends* did mean unanimity) that survived the rewrite of the paragraph beneath it. It's a one-line edit, but it's currently a normative statement that is false, in the section that defines the product's core decision rule. (Note that under **B1** as the trait currently stands, the bolded sentence accidentally becomes true again — which is a good illustration of why B1 matters.)

---

## Minor / editorial

1. **Undefined types.** `Deadline`, `SignalFamily`, `Severity`, `ConfidenceTier`, and `ContentType` are used in the §2.1/§2.3 code blocks but never defined. `SignalFamily` in particular deserves an explicit enum — §2.4 aggregates over it, §2.2 enumerates its variants only inside a prose table, and B1/B2/B3 are all arguments about its cardinality.
2. **Orphan measure.** §2.2's `stylometric` row lists "entropy-per-token" among what it does, but no signal family covers it. Either assign it or move it to evidence-only.
3. **§3.1's DoD depends on an unset number.** "false-positive rate … below its stated target" — §8.1 leaves the target as an open product decision. Fine as a dependency, worth marking as one so nobody reads §3.1 as self-contained.
4. `prose_spans: Vec<Range<usize>>` — `Range<usize>` is not `Copy`, so iteration patterns need `.clone()` or `&`. Trivial, but the struct is presented as a contract.
5. §5's ~10MB default-build target is worth restating as a CI-asserted budget rather than an aspiration — `clap` + `serde` + `regex` + `aho-corasick` with a large embedded dictionary lands in that neighborhood only with deliberate profile settings (`lto`, `strip`, `opt-level`), which aren't mentioned.

---

## What holds up well (checked, no action needed)

- **`owo-colors` / `supports-colors`** — confirmed accurate; the crate ships no default features and `NO_COLOR` handling is genuinely opt-in. Verified against crates.io (v4.3.0, actively maintained).
- **`cargo-dist`** — alive and current (v0.32.0, published 2026-05-22). No maintenance risk to flag.
- **`f32` has no `Ord`, `total_cmp` required** — correct, and a good catch by whoever added it.
- **`catch_unwind` cannot intercept a signal** — correct, and correctly scoped as an accepted limitation rather than an overclaimed fix.
- **The Python's quorum semantics** — §2.4's description matches the source exactly: `agree = len(families)` counts a `Suspicious` (1) and a `Strong` (2) vote identically, which is what "at least `QUORUM` families agree at `Suspicious` or stronger" describes. Faithfully ported.
- **Three-family Python baseline** (`vocabulary`, `punctuation`, `burstiness`) — verified at lines 128/135/147. The spec's characterization is right; B2 is about what was *added*, not about this being wrong.
- **`whichlang`, `statrs`, `aho-corasick` selections** — all current, permissively licensed, appropriate for their stated jobs.
- **The `stylometry` crate removal** and the `rust_readability` (GPL-3.0) exclusion — both correct and correctly reasoned.
- **§4's secret-hygiene paragraph** — this is unusually good. Naming the `reqwest::Error`-contains-URL footgun and the panic-hook leak *before* four vendor modules exist is exactly the right time to write it down.

---

## Suggested edit order

Highest leverage first; the first two are where most of the rest resolves themselves.

| # | Edit | Section | Severity |
|---|---|---|---|
| 1 | Make the trait multi-family-capable (or split backends per family) | §2.1 | B1 |
| 2 | Demote `LexicalDiversity`/`Readability`/`Compression` to evidence-only pending §8.1 | §2.2, §2.4 | B2, B3 |
| 3 | Delete or rewrite the "quorum is explicitly unanimity" sentence | §2.4 | I11 |
| 4 | Add `Inconclusive` verdict + port the Python's word/sentence floors | §2.4, §2.2 | B4 |
| 5 | Define the exit code for `Clean`-with-warnings | §3 | B5 |
| 6 | Reframe §9 item 4: dual-license / CLA decision **before** §11.5 opens contributions; note (b) fails §3.1's DoD | §9, §11.4 | B6 |
| 7 | Add `case_sensitive` + `whole_word` to the entry schema; fix the worked example; state `MatchKind::LeftmostLongest` | §11.3 | I2, I3 |
| 8 | Resolve one-file-vs-two-files; map `category` → `SignalFamily`; state where `Punctuation` lives | §11.2, §11.3 | I4 |
| 9 | Restate `Deadline` as cooperative + name the preemption mechanism (or drop the "can't block indefinitely" claim) | §2.1 | I1 |
| 10 | Point the hook at `detect`; re-verify the exit-code mapping; define `lint`'s exit codes | §6, §3 | I6 |
| 11 | Resolve `scan` = batch-lint vs. batch-detect | §3 | I7 |
| 12 | Pin `xz = "0.4.6-rc.0"` (or switch to `lzma-rs`); pin the LZMA preset and MTLD factor threshold alongside their thresholds | §10, §8.1 | I8 |
| 13 | Replace the CI "bounded-time" regex check with a `size_limit` compile assertion | §8 | I9 |
| 14 | Decide whether a `Strong` `MlClassifier` vote can meet quorum alone | §2.4 | I5 |
| 15 | Reorder keyring ahead of the config file, or warn on duplicates | §4 | I10 |

Items 1, 2, and 4 are the substantive design work; the remaining twelve are mostly one-to-three-sentence edits.

---

*Nothing in B6 is legal advice — it argues that the legal question §9 currently poses is the wrong one to spend an opinion on, and names the two that are worth the money.*
