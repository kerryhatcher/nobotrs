# nobotrs Plugin Packaging (Agent Plugins Specification) Implementation Plan (STUB)

> **STUB — not yet detailed.** This is a task outline, not a ready-to-execute plan: no file/interface contracts, no TDD steps, no code. Expand it into full task detail (per `superpowers:writing-plans`) before dispatching it for execution. Depends on `2026-07-26-nobotrs-core-default-build.md` being implemented and packaged/published (spec §5) first — the wrapper this plan builds has nothing to locate until a real `cargo install`/Homebrew/GitHub Release artifact exists.

**Goal:** Ship `nobotrs` as an Agent Plugins Specification–conformant plugin wrapping the standalone binary, per spec §6 — manifest, skill, ambient `PostToolUse` hook, and the cross-platform locate-or-fail wrapper.

**Source spec sections:** §6 (the whole section), §3 (exit codes the hook wrapper must map), §5 (packaging this wrapper depends on existing).

## Anticipated task outline (to expand later)

1. `.plugin/plugin.json` manifest (generic) + `.claude-plugin/plugin.json` vendor copy for Claude Code's discovery path, per the Agent Plugins Spec's vendor-precedence rule.
2. `skills/detect-ai-writing/SKILL.md` — portable across any conformant harness.
3. **`bin/nobotrs` wrapper** — an `sh`/`bash` script for Linux/macOS plus a `.ps1` companion for Windows (or a tiny statically-linked Rust locator binary, if that proves simpler to maintain than duplicating search logic across two shells). Search order: env var override → `PATH` → well-known per-platform install dirs (`~/.cargo/bin`, `/opt/homebrew/bin`, `/usr/local/bin` on Unix; `%USERPROFILE%\.cargo\bin` on Windows). First match wins if multiple installs are found — stated as the resolution rule, not left environment-dependent. On failure: print the exact `cargo install` command, the `brew install` command, and a direct GitHub Release URL, as plain text.
4. `hooks/hooks.json` — wire the `PostToolUse` hook to **`bin/nobotrs detect --format json`**, explicitly not `lint` (spec §6: wiring to `lint` would bypass quorum and fire on a single tell-word hit, defeating the whole quorum system at the one point users experience it passively).
5. **Re-verify the current Claude Code hooks exit-code protocol before locking in a mapping** (spec §6 flags this explicitly as unresolved) — an earlier draft's assumed mapping (exit 1 → non-blocking feedback, exit 2 → block) doesn't match `check_ai_tells.py`'s own documented behavior and conflates two different concerns (findings vs. hook bugs). Map `nobotrs`'s actual four exit codes (0/1/2/3, spec §3) into whatever the hooks protocol's current codes mean — the hard requirement regardless of the exact mapping: the ambient scan must never *block* a write.
6. State the Claude-Code-only caveat explicitly in docs (spec §6): OpenCode and Pi use native JS/TS event systems, not `hooks.json` — same caveat nobots' own README already carries forward.
7. Manual install-flow test: fresh machine (or container), `/plugin install`, confirm the wrapper's failure message actually appears and is accurate when the binary isn't yet installed (spec §6: plugin install and binary install are deliberately separate manual steps in v1).
