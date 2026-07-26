# Handoff: nobotrs core-default-build implementation

**Written:** 2026-07-26, mid-session, for a fresh agent/session to pick up cleanly.

## What this is

`nobotrs` (repo: `/home/kwhatcher/projects/nobotrs`) is a Rust CLI that detects
AI-generated text and lints prose for AI-writing "tells." We are implementing
its **default build** (deterministic + stylometric tiers, no ML/API features)
per an approved design spec, using a written implementation plan executed via
the `superpowers:subagent-driven-development` skill (fresh implementer
subagent per task, task review after each, fix loop on findings).

- **Spec (approved):** `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md`
- **Plan being executed (21 tasks, full detail):** `docs/superpowers/plans/2026-07-26-nobotrs-core-default-build.md`
- **Four stub plans, not started, not detailed yet:** `docs/superpowers/plans/2026-07-26-nobotrs-{classifier-tier,perplexity-tier,api-clients-tier,plugin-packaging}.md` — do not touch these until the core plan is fully done and merged; they depend on it.
- **Execution mode:** directly on the `main` branch. The user was asked and explicitly declined an isolated worktree ("No, work directly on main"). Do not create a worktree unless the user asks.
- **SDD workspace:** `.superpowers/sdd/2026-07-26-nobotrs-core-default-build/` (relative to repo root) — contains the ledger (`progress.md`), every task's brief/report/review-diff files. This is git-ignored scratch; the real record is git history plus this ledger. This handoff doc lives at the repo root (`HANDOFF.md`), not inside that workspace directory.

## How to resume — read this first

1. Read the skill: `superpowers:subagent-driven-development` (invoke it via the Skill tool, or read `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/SKILL.md`). It defines the per-task loop (dispatch implementer → review → fix loop → next task) that everything below assumes.
2. Read `.superpowers/sdd/2026-07-26-nobotrs-core-default-build/progress.md` — it's the ledger, authoritative over this handoff doc if they ever disagree (this doc is a snapshot; the ledger is live).
3. **Do not re-dispatch any task marked `complete` in the ledger.** Tasks 1-13 are complete and reviewed clean (each has a `Task N: complete (commits ..., review clean)` line). Resume at Task 14, which is mid-fix-loop (see below).
4. Harness task-tracking IDs #23-#43 correspond to plan Task 1-21 (offset by 22) — #23 = plan Task 1, #36 = plan Task 14, #43 = plan Task 21. If your TaskList doesn't show these (fresh session), that's fine — the ledger is the real source of truth, not the harness todo list; recreate todos if useful but don't treat their absence as meaning work wasn't done.
5. **Agent IDs referenced anywhere in this doc or in scrollback are NOT resumable across sessions.** If you're a fresh session, you cannot `SendMessage` to `a8bb6b4749d890d2a` (Task 14's implementer) — that agent handle only exists within the session that spawned it. Dispatch a **new** implementer instead, giving it the same context a resumed one would have had (see "Immediate next action" below).

## Done: Tasks 1-13 (all complete, reviewed clean)

Every task below has full detail in the ledger (`progress.md`) including its
commit range and a one-line summary of what the review verified. Skim the
ledger rather than re-deriving this from git log.

1. Project scaffolding + CLI skeleton (clap, 4 stub subcommands)
2. `Error`/`Availability`/`Deadline` foundational types
3. `Document` type + markdown-aware prose-span segmentation
4. `Score`/`Evidence`/`VoteStrength` types (NaN-safe probability clamping)
5. `SignalFamily`/`ScoreOutcome`/`DetectorBackend` trait
6. Tell dictionary artifact (`dictionary/entries.json`, 46 entries, CC BY-SA 4.0 `LICENSE`/`README`, root `NOTICE`)
7. Dictionary loader (serde structs, compile-time `include_str!` embed, size-limited regex compilation)
8. `Vocabulary` backend (aho-corasick + regex, word-boundary matching, longest-match-wins merge)
9. `Punctuation` backend (em-dash density thresholds)
10. `Burstiness` backend (sentence-length stdev/mean, gated on both word AND sentence floors — see note below)
11. `LexicalDiversity` backend (hand-rolled MTLD, evidence-only, reference vector validated against real `lexicalrichness` via `uv run`)
12. `Readability` backend (hand-rolled Flesch-Kincaid, evidence-only, reference vector validated against real `textstat` via `uv run`)
13. `Compression` backend (LZMA ratio via `lzma_rs::lzma_compress` + Shannon entropy-per-token, evidence-only)

**Current `HEAD`:** `e39fc70` (this is Task 14's implementation commit — see below, it is NOT yet fully closed out).

**Two notable corrections applied during implementation** (both intentional, documented in the plan and ledger, not bugs to "fix"):
- Task 10 (`Burstiness`) gates on **both** `word_count >= 150` **and** `>= 5 sentences`, contradicting the design spec's prose (which only mentions the sentence floor) but matching the verified actual behavior of the Python reference `check_ai_tells.py`. This was a deliberate plan-writing correction, not a task deviation.
- `Score` carries a `vote: VoteStrength` field not literally listed in the spec's struct sketch — necessary for aggregation (Task 14) to be implementable; documented in the plan's Task 4.

**Pattern established across all backend tasks, worth continuing:** where a task claims to have run an external reference tool (`uv run --with lexicalrichness ...`, `uv run --with textstat ...`, or research against `lzma-rs`'s real docs.rs API), the controller (you) should verify the claim is genuine before trusting it — check for real download-log evidence in the implementer's report, and where feasible have the *reviewer* independently re-run the same command. This caught nothing wrong in Tasks 11-13, but the practice is why we're confident nothing wrong slipped through.

## In progress: Task 14 (ensemble aggregation) — mid-fix-loop, NOT complete

This is the single most safety-critical component in the project: the
quorum-aggregation logic (`src/aggregate.rs`) that turns per-backend
`ScoreOutcome`s into a `Verdict` (`Flagged`/`Clean`/`Inconclusive`) plus a
`warnings` list.

**State:**
- Implemented and committed: `e39fc70` — "feat: add quorum aggregation with Inconclusive verdict and warnings surface". `cargo test` reports 61/61 passing.
- Reviewed: **Approved overall**, but with **one open Important finding** that has NOT yet been fixed. This means Task 14 is NOT complete — do not mark it so, and do not proceed to Task 15 until this closes out (fix → scoped re-review → ledger entry).

**The open finding (verbatim from the reviewer, fix round 1 not yet dispatched):**

> **Important:** Scenario 4 (Failed + quorum-met Flagged verdict with non-empty warnings) has no direct test assertion. `failed_backend_populates_warnings` uses two `Scored(None)` votes + 1 `Failed`, which produces `agreeing=0` → `Clean`, and the test doesn't assert on `verdict` at all — only `warnings`. `clean_with_warnings_is_still_clean_verdict_but_nonempty_warnings` explicitly targets the `Clean`+warnings combination. No test combines a `Failed` outcome with a `Flagged` verdict (i.e., `Scored(Strong)`×2 + `Failed`×1 at quorum=2) to prove warnings don't suppress or alter a `Flagged` result. The implementation is correct by hand-trace (verdict computation never reads `warnings`), but this specific interaction is unverified by the test suite. This gap originates in the brief's own Step-1 test block (the implementer copied it verbatim, no deviation), not implementer negligence, but it's a real coverage hole worth closing before this logic is trusted further downstream.

The reviewer independently hand-traced all 5 required correctness scenarios
(the code itself is correct) and ran `cargo test aggregate::` directly,
confirming 6/6 passing. This is a **test-coverage gap, not a logic bug** —
the fix is "add one more test," not "change the aggregation logic."

**Files involved in this fix:**
- Reviewer's full report (verdict, all findings, strengths): task output was not saved to a file — it exists only in this handoff's excerpt above and in prior conversation scrollback, which a fresh session won't have. If you need the full original review text and it's not visible to you, it's fine to proceed from the excerpt above; it's complete enough to act on.
- `src/aggregate.rs` — where the test needs to be added, alongside the existing `failed_backend_populates_warnings` and `clean_with_warnings_is_still_clean_verdict_but_nonempty_warnings` tests (bottom of the file, `#[cfg(test)] mod tests`).
- Task brief: `.superpowers/sdd/2026-07-26-nobotrs-core-default-build/task-14-brief.md`
- Task report (implementer's original): `.superpowers/sdd/2026-07-26-nobotrs-core-default-build/task-14-report.md`
- Review diff already generated: `.superpowers/sdd/2026-07-26-nobotrs-core-default-build/review-91bff74..e39fc70.diff`

## Immediate next action

Per the subagent-driven-development skill's fix-loop process (round 1 of up
to 5, resume-or-fresh-implementer):

1. Dispatch an implementer (fresh, since the original agent handle isn't
   resumable across sessions) with: the task-14 brief path, the task-14
   report path, and the finding verbatim (copy the blockquote above). Ask
   it to add a test proving a `Failed` outcome does not suppress or alter a
   `Flagged` verdict — concretely: 2× `Scored(VoteStrength::Strong)` (or
   `Suspicious`) + 1× `Failed(...)`, quorum=2, asserting
   `verdict == Verdict::Flagged` **and** `warnings.len() == 1` in the same
   test. Have it re-run the full test suite and append a fix report to
   `task-14-report.md`, then commit as a new commit (not amending `e39fc70`).
2. Generate a scoped review package: `scripts/review-package docs/superpowers/plans/2026-07-26-nobotrs-core-default-build.md e39fc70 <new-head>` (the `scripts/` here is `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/scripts/`).
3. Dispatch a scoped re-reviewer with that diff, the finding, and the brief — verdict ADDRESSED/NOT ADDRESSED, check for new breakage.
4. If ADDRESSED with no new Critical/Important breakage: append to the ledger:
   - `Task 14: fix round 1/5 (1 addressed, 0 open — missing test for Failed+Flagged-verdict interaction (scenario 4); added; commits e39fc70..<new-head>)`
   - `Task 14: complete (commits 91bff74..<new-head>, review clean)`
5. Mark harness task #36 completed, #37 in_progress.
6. Proceed to Task 15 exactly as Tasks 1-14 were run: `scripts/task-brief PLAN 15` → dispatch implementer → review → (fix loop if needed) → ledger entry → next task.

## Remaining work after Task 14 closes: Tasks 15-21

Still to do, in order, each following the identical dispatch→review→(fix
loop)→ledger pattern used for every task so far. Full detail (file lists,
TDD steps, exact code) is in the plan file itself — read each task's section
there, or use `scripts/task-brief` to extract just that task.

15. **Output rendering** — human + `--format json`, spec-exact exit code mapping (0=Clean/no-warnings, 1=Flagged, 2=tool-failure-or-any-warnings, 3=Inconclusive). `src/output.rs`.
16. **`detect` CLI command** — wires all 6 backends + Task 14's `aggregate()` + Task 15's output into `nobotrs detect <path|->`. First point the whole pipeline runs end-to-end. `src/cli/detect.rs`.
17. **`lint` CLI command** — unfiltered per-backend evidence, no quorum. `src/cli/lint.rs`.
18. **`scan <dir>` CLI command** — batch `detect` (not batch `lint`), default ignore patterns, summary line. `src/cli/scan.rs`.
19. **`config` CLI command (basic)** — resolved platform config path via `directories` crate, backend availability printout. API-key/model management is explicitly out of scope here (deferred to the `api-clients-tier` stub plan). `src/cli/config.rs`.
20. **Packaging basics** — release profile, binary-size CI budget, `cargo-deny` config. `.github/workflows/binary-size.yml`, `deny.toml`.
21. **End-to-end definition-of-done test** — `nobotrs detect README.md` on the default build, sub-second, offline, per the spec's own v1 "must work" scenario. `tests/definition_of_done.rs`.

## After Task 21: final review and finish

Per the subagent-driven-development skill: once all 21 tasks are complete,
dispatch a **final whole-branch code review** (most capable model available,
using `superpowers:requesting-code-review`'s reviewer template) against the
full diff from `git merge-base main HEAD` (which, since we're on `main`
directly with no branch point, means reviewing the entire diff introduced
this session — check with the user how they want the baseline defined,
since there's no separate feature branch to diff against here). Fix any
findings in one batched fix wave, one scoped re-review, then use
`superpowers:finishing-a-development-branch` to decide how to
integrate/ship. Delete this SDD workspace directory only after that final
review is clean — the ledger's job is done once the ledger's job is done, not before.

## Things a fresh agent should NOT do

- Do not re-run or "double check" Tasks 1-13 — they're reviewed clean, re-litigating them wastes effort the ledger exists to prevent.
- Do not create a git worktree — the user declined one for this work.
- Do not start on the classifier/perplexity/api-clients/plugin-packaging stub plans — they're explicitly out of scope until this core plan finishes.
- Do not skip the scoped re-review after Task 14's fix — an unreviewed fix is exactly the kind of thing this process exists to catch.
- Do not treat this handoff doc as more authoritative than `progress.md` (the ledger) or actual `git log` — if they disagree, trust the ledger and git history; update/regenerate this handoff doc rather than trusting a stale copy.
