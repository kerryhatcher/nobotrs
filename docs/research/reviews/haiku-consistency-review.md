# Internal Consistency Review: nobotrs Rust CLI Design Spec

**Reviewer:** Haiku 4.5  
**Date:** 2026-07-26  
**Scope:** Mechanical consistency only (placeholders, contradictions, reference accuracy)

---

## 1. Leftover Placeholders and Vague Language

**Result:** None found.

The spec contains no "TBD," "TODO," or incomplete sentences. Language throughout is precise and intentional. Conditional statements (e.g., deferred features, future options) are clearly marked as such rather than vague open-endedness.

Examples of clear conditional language:
- Line 108: "A future option, **not committed to**: an optional Python sidecar shelling out to the existing `deep_stylometry.py`, degrading gracefully when absent."
- Line 110: "Deferred; revisit once the `classifier` tier's ML dependency choice is settled empirically."
- Line 102: "an automatic-download wrapper is a plausible v2 addition once the binary is actually published via `cargo-dist`."

Requirements that are explicitly stated as open items (§9, lines 120–127) are framed as "key open items carried into implementation planning," not as vague design requirements.

---

## 2. Internal Contradictions

### 2a. CLI commands (§3) vs. commands implied elsewhere

**Section 3 lists four commands:**
- `nobotrs detect <path|--stdin>`
- `nobotrs lint <path>`
- `nobotrs scan <dir>`
- `nobotrs config`

**Verification:**

- **`detect`:** §2.4, line 70: "A top-level `detect` command runs every enabled backend and combines their `Score`s…" ✓ Consistent.
- **`lint`:** §3, line 76: Listed in command synopsis. No contradictory mentions elsewhere. ✓
- **`scan`:** §3, line 77: Listed in command synopsis. §6, line 101: References "ambient scan-on-write UX" from a `PostToolUse` hook, implying `scan` is triggered by the plugin. ✓ Consistent.
- **`config`:** §3, line 79: Listed in command synopsis. §4, lines 86–90: Describes configuration file location, API key precedence, and keyring integration—all management operations consistent with a `config` command. ✓ Consistent.

**Result:** No contradictions. All four commands are referenced consistently across §2, §3, §4, and §6.

### 2b. Feature flags (§2.2) vs. feature-flag references elsewhere

**Section 2.2 feature-flag table lists:**
- `deterministic` (always on)
- `stylometric` (always on)
- `classifier` (off by default)
- `perplexity` (off by default)
- `api-clients` (off by default)
- `full` (meta-feature enabling all five tiers)

**Verification:**

- **§2.1, line 39:** "Heavy backends are gated behind Cargo feature flags" ✓ Matches §2.2 structure.
- **§2.2, lines 51–52:** "`classifier` and `perplexity` are separate flags…; `api-clients` is one shared flag gating all four vendor clients…" ✓ Matches table.
- **§2.2, line 53:** "A `full` meta-feature enables all five tiers for users who want maximum coverage in one build." ✓ Matches table.
- **§5, line 95:** "default build (deterministic + stylometric only) targets roughly 10MB; `classifier`/`perplexity` features add candle (~50-80MB) or ONNX Runtime (~100-150MB)…" — Mentions `classifier` and `perplexity` but not `api-clients`. This is not a contradiction (api-clients size impact is not discussed, likely because `reqwest` is small and commonly used), but the sizing information is incomplete. ✓ Not a contradiction, but an incomplete picture.
- **§8, line 118:** "`classifier` and `perplexity` backends need a smaller, separate integration-test tier gated behind their own feature flags…" ✓ Matches §2.2.
- **§9, line 124:** "Prototype candle + `desklib/ai-text-detector-v1.01` as the first concrete step of the `classifier` tier…" ✓ Mentions `classifier`, consistent.

**Result:** No contradictions. Feature-flag names are used consistently. Minor gap: §5 does not discuss the size or distribution impact of `api-clients`, but this is an omission, not a contradiction.

### 2c. Packaging story coherence (§5 vs. §6)

**Section 5 (Packaging and distribution):**
- `cargo-dist` builds per-platform binaries (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64) to GitHub Releases.
- Auto-generates Homebrew tap formula.
- Publishes to crates.io on tag push.
- Default build targets ~10MB; optional features documented as separate install paths.

**Section 6 (Plugin packaging):**
- `bin/nobotrs` is a **thin wrapper script, not a bundled binary** (lines 102).
- Wrapper searches: env var override, `PATH`, well-known install directories.
- On failure: prints actionable install message (`cargo install` / `brew install` / direct download link).
- "locate or fail with clear instructions" is v1 behavior (line 102).
- Automatic-download wrapper is a "plausible v2 addition" (line 102).

**Coherence check:** Does §5 (cargo-dist + GitHub Releases + Homebrew) logically support §6 (plugin wrapper locates binary)?

- §5 provides the distribution mechanism: GitHub Releases ✓, Homebrew formula ✓, crates.io (for `cargo install`) ✓.
- §6 wrapper searches for the binary in locations where a user would have installed it via those mechanisms (PATH, well-known directories, env var override) ✓.
- §6 failure message directs users to those same installation paths ✓.

**Gap identified:** §6 does not explicitly clarify whether the plugin manager (Claude Code's plugin installation system) would trigger any automatic installation of the binary. §6 says Claude Code has no `postInstall` hook (line 101), implying v1 requires manual binary installation after plugin installation. This is a completeness gap (how does a user's install flow work?), not a logical contradiction between §5 and §6. The two sections compose logically, but the user-facing install UX between "install plugin" and "run plugin command" is not fully specified.

**Result:** No contradictions. §5 and §6 compose logically. Acknowledged gap: plugin installation UX is incomplete (not specified whether plugin install prompts binary install, or user must install binary separately).

---

## 3. Non-goals (§1) vs. Explicit v1 scope-outs (§7)

### Non-goals (§1, lines 21–24):

1. **Text generation or auto-rewriting.** "Text generation or auto-rewriting of any kind. `lint` only flags and suggests; it never edits files." (line 22)
2. **Full feature parity with `nobots` deep_stylometry.py on dependency-parse-dependent features.** "Full feature parity with `nobots`' `deep_stylometry.py` on dependency-parse-dependent features (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence)…" (line 23)
3. **Bundling prebuilt binaries in plugin repo.** "Bundling prebuilt binaries inside the plugin repository itself." (line 24)

### Explicit v1 scope-outs (§7, lines 105–127):

1. **Dependency-parse-dependent stylometric features** (lines 107–108): "Dependency-parse-dependent stylometric features (dependency distance, whiz-deletion, sentence-relative Biber features, textdescriptives-style coherence). No pure-Rust dependency parser exists anywhere in the ecosystem…"
2. **POS-tag-dependent features** (lines 109–110): "POS-tag-dependent features (POS proportions, function/content-word ratio, hedges, amplifiers, nominalizations)…"
3. **`stylometry` crate license verification** (lines 110–111): "flagged as a direct dependency candidate for classic authorship-analysis statistics, but its license was not independently confirmed in research…"
4. **Any text generation or auto-rewrite capability** (line 112): "Any text generation or auto-rewrite capability. Confirmed out of scope per product decision — lint-only."

### Mapping:

| Non-goal | Scope-out | Match |
|----------|-----------|-------|
| Text generation/auto-rewriting (NL 1) | Any text generation or auto-rewrite (SO 4) | ✓ Exact match |
| Full feature parity / dependency parsing (NL 2) | Dependency-parse-dependent features (SO 1) | ✓ Exact match |
| No bundled binaries in plugin repo (NL 3) | *Not present* | — |
| *Not present* | POS-tag-dependent features (SO 2) | — |
| *Not present* | `stylometry` license verification (SO 3) | — |

**Analysis:**

- **NL 1 ↔ SO 4:** Exact agreement on text generation / auto-rewriting. ✓

- **NL 2 ↔ SO 1:** NL 2 states non-goal as "full feature parity… on dependency-parse-dependent features"; SO 1 elaborates on the reason (no pure-Rust parser) and deferrability (Python sidecar option for v2). ✓ Consistent; not a contradiction.

- **NL 3 (no bundled binaries) not in SO:** NL 3 is a plugin-packaging design constraint, not a feature cut. Explicit v1 scope-outs are framed around features being deferred (dependency parsing, POS tagging) or requiring verification (license). Packaging decisions are not framed as scope-outs. This is intentional framing, not a contradiction.

- **SO 2 (POS-tag-dependent features) not in NL:** SO 2 is a specific feature-level deferral not mentioned in the high-level Non-goals. NL 2 covers the broader non-goal of "full feature parity," and SO 2 is a specific instantiation. Not a contradiction; SO 2 is granular detail omitted from the high-level Non-goals for brevity.

- **SO 3 (`stylometry` license verification) not in NL:** SO 3 is a due-diligence / open item (verify before depending), not a feature cut. Correctly placed in Explicit v1 scope-outs under "open items," not in Non-goals.

**Result:** No contradictions. Non-goals and Explicit v1 scope-outs are logically consistent. Different scoping and levels of granularity are intentional, not contradictory.

---

## 4. Cross-reference Accuracy

**Internal section references found in spec:**

1. **Line 23:** "See §7" — in context of "hard ecosystem gap" for dependency parsing.
   - Target: §7 (Explicit v1 scope-outs), line 107–108: "No pure-Rust dependency parser exists anywhere in the ecosystem…"
   - **Match:** ✓ Section 7 explains the gap.

2. **Line 24:** "See §6" — in context of "Bundling prebuilt binaries inside the plugin repository itself."
   - Target: §6 (Plugin packaging), lines 102–103: "No plugin repo in the ecosystem was found bundling actual per-platform binaries in-repo — the two real examples found (`nab`, `genasis`) both locate-or-download instead."
   - **Match:** ✓ Section 6 explains the no-bundling design.

**External references (not section-internal):**
- Line 5: References research files at `/mnt/storage/grimoire/research/…` and `docs/research/00-consolidated-summary.md` — external, not spec-internal.
- Line 40: References "research report 05" — external.
- Line 130: References "docs/research/00-consolidated-summary.md § 'Recommended stack'" — external.

**Result:** No broken cross-references. Both internal section references (lines 23, 24) correctly point to sections that contain the referenced content.

---

## Summary

| Check | Result |
|-------|--------|
| 1. Placeholders / vague language | ✓ None found |
| 2a. CLI commands consistency | ✓ Consistent |
| 2b. Feature flags consistency | ✓ Consistent (minor gap: `api-clients` sizing not discussed) |
| 2c. Packaging story coherence | ✓ Logical composition (gap: plugin install UX not fully specified) |
| 3. Non-goals vs. scope-outs | ✓ No contradictions |
| 4. Cross-reference accuracy | ✓ All references valid |

**Acknowledged incompleteness (not contradictions):**
- §5 does not discuss the size/distribution impact of the `api-clients` feature flag (only covers `classifier` and `perplexity`).
- §5 and §6 do not jointly specify the user-facing install flow between "install plugin" and "first use of plugin" (i.e., whether binary installation is automatic, prompted, or entirely manual).

These are gaps in completeness, not internal contradictions within the spec's mechanical structure.
