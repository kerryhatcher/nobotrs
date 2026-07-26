# Open Plugins Integration for a Compiled Binary

Scope: how `nobotrs` (a compiled Rust CLI) ships as both a standalone binary and
an Open-Plugins-spec-conformant plugin, across harnesses. Other research docs
in this directory cover the crate/architecture choices; this one is purely
about the plugin-packaging surface.

## Freshness spot-check on the prior research

The prior research at `/mnt/storage/grimoire/research/open-plugins-spec/` (dated
2026-07-03) is broadly still accurate on structure (manifest fields, component
types, `${PLUGIN_ROOT}` expansion, conformance levels). One piece of drift worth
flagging explicitly:

- **The spec appears to have been renamed/rebranded since the prior research.**
  Fetching `https://open-plugins.com/` today still resolves and describes the
  same five component types (skills, agents, hooks, MCP servers, LSP servers),
  but fetching `https://github.com/vercel-labs/open-plugin-spec` now surfaces
  content calling itself the **"Agent Plugins Specification"**, versioned
  `1.0.0`, with a schema hosted at `agent-plugins.org`
  (`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`), and the page
  explicitly states **"Agent Plugins Specification 1.0.0 is a working draft and
  has not been published."** The prior research's repo pointer and component
  docs still line up field-for-field with what's live now, so nothing in
  `spec-structure.md` or `component-formats.md` needs correcting — but the
  project's public name and canonical schema host may be in flux. Treat
  `open-plugins.com` as the stable brand for now and don't be surprised if
  citations elsewhere say "Agent Plugins Specification" instead.
- Nothing else material changed: no new component types, no changes to
  `${PLUGIN_ROOT}` semantics, no changes to conformance levels visible on either
  fetch.

## 1. Does the spec say anything about `command` actions invoking binaries vs scripts?

**The generic Open Plugins spec doc is silent on this distinction** — it does
not say the word "binary" or "executable" anywhere in the hooks section.
`component-formats.md` documents the hook action shape as:

```json
{ "action": "command", "command": "black", "args": ["--check", "${FILE}"] }
```

`command` + `args` as separate fields is itself informative: it's exec-style
invocation (a program name/path plus an argv array), not a shell string. That
shape doesn't privilege scripts over binaries — `command` is just "the thing to
execute," and nothing in the spec restricts it to interpreted files. So the
spec permits invoking a compiled binary at `${PLUGIN_ROOT}/bin/nobotrs`; it
just never says so in plain language because the spec authors didn't consider
the script/binary distinction worth calling out.

**Claude Code's actual (more mature) implementation confirms and sharpens this.**
Per its hooks documentation (fetched live, `code.claude.com/docs/en/hooks`),
`command` hooks have two forms:

- **Exec form** (`args` present): `command` is resolved as a real executable —
  binary, `.exe`, or script with a shebang — with no shell involved. Each
  `args` element is passed through literally.
- **Shell form** (`args` absent): the `command` string is handed to `sh -c`
  (PowerShell on Windows), so shell tokenization/expansion/pipes apply.

The docs state directly: **"Both forms support compiled native binaries"**,
with the exec-form example being literally `"command":
"/usr/local/bin/my-compiled-tool"`. So yes — there is a documented,
first-class pattern for a hook whose `command` shells out to a prebuilt binary
at `${CLAUDE_PLUGIN_ROOT}/bin/<binary>`. No wrapper script is required on
Claude Code specifically; a direct binary path in `command` (exec form, with
`args`) is the clean approach there.

One nuance for portability: the *generic* Open Plugins `component-formats.md`
doc doesn't document a shell-form vs exec-form split — it only shows the
`command` + `args` shape, which maps directly onto Claude Code's exec form.
Don't rely on shell-string tricks (`&&`, pipes, `$VAR` expansion in the command
string) if the plugin needs to stay spec-portable; stick to `command` = binary
path, `args` = literal argv array.

## 2. How do real plugins ship compiled binaries today?

Searched GitHub for real Claude Code plugins wrapping Rust binaries
(`gh search code`, `gh search repos`). Two concrete examples surfaced, plus a
look at Anthropic's own official plugin registry for baseline hook conventions.

### Pattern A — PATH discovery with a wrapper script + helpful failure (`nab`)

[`MikkoParkkola/nab`](https://github.com/MikkoParkkola/nab) is a Rust CLI +
MCP server + Claude Code plugin ("a single Rust binary — not a browser"). It
does **not** bundle a prebuilt binary in the repo. Instead:

`plugin/.mcp.json`:
```json
{
  "mcpServers": {
    "nab": { "command": "${CLAUDE_PLUGIN_ROOT}/bin/nab-mcp-wrapper" }
  }
}
```

`plugin/bin/nab-mcp-wrapper` (a checked-in **shell script**, not the binary
itself):
```bash
#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${NAB_MCP_BIN:-}" ]]; then exec "${NAB_MCP_BIN}" "$@"; fi
candidates=()
if resolved="$(command -v nab-mcp 2>/dev/null)"; then candidates+=("${resolved}"); fi
candidates+=("/opt/homebrew/bin/nab-mcp" "/usr/local/bin/nab-mcp" "${HOME}/.cargo/bin/nab-mcp")
for candidate in "${candidates[@]}"; do
  if [[ -x "${candidate}" ]]; then exec "${candidate}" "$@"; fi
done
cat >&2 <<'EOF'
nab-mcp was not found.
Install nab, then reload plugins:
  brew tap MikkoParkkola/tap && brew install nab
  # or
  cargo install nab
Set NAB_MCP_BIN=/absolute/path/to/nab-mcp if you use a custom build.
EOF
exit 127
```

Its `hooks/hooks.json` similarly invokes a checked-in shell script
(`${CLAUDE_PLUGIN_ROOT}/hooks/nab-yara-edge.sh`), which is a thin stub, not the
binary directly. The actual `nab` binary is expected to already be on the
user's system (installed via Homebrew tap or `cargo install`) — the plugin
repo ships zero platform binaries and instead ships a *locator* that checks an
env var override, then `PATH`, then a few well-known install locations, and
fails loudly with install instructions if none match.

### Pattern B — separate installer script pulling from GitHub Releases (`genasis`)

[`claude-genasis/genasis`](https://github.com/claude-genasis/genasis) ships a
top-level `install.sh` (not part of any plugin manifest) whose header states
plainly:

> "downloads the matching pre-built binary from GitHub Releases. Does NOT
> compile from source... Resolve the release asset URL, download, verify
> sha256, extract. Install to `~/.local/bin/genasis`."

This is a fully separate, harness-agnostic install step the user runs once
(`curl ... | sh`), independent of any plugin marketplace mechanism. The
generated `.claude/agents/*.md` files it produces are a downstream artifact of
running the already-installed binary, not something wired through a
plugin.json hook at all.

### Anthropic's own official plugins never invoke binaries directly — they invoke scripts

Checked `anthropics/claude-plugins-official`'s `hooks/hooks.json` files
(`claude-security`, `ralph-loop`, etc.). Every one uses **shell form**, e.g.:

```json
{ "type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/hooks/banner_hook.sh\"" }
```

None of Anthropic's own official plugins ship or invoke a compiled binary —
they're all shell/Python scripts. So there's no first-party precedent to copy
verbatim for the binary case; the binary-shelling pattern above is grounded in
the platform's documented capability (§1) plus community practice (`nab`), not
in an official reference plugin.

### Critical gap: there is no `postInstall` hook in Claude Code plugins today

Searched for how plugins handle "install the dependency at plugin-install
time." Found [`anthropics/claude-code#9394`](https://github.com/anthropics/claude-code/issues/9394),
open, requesting exactly `postInstall` / `postUpdate` / `postUninstall` fields
in `plugin.json` — **this does not exist yet.** A commenter's workaround is
shelling to `npx` inside a hook at call time (works for npm-ecosystem tools,
not compiled binaries), which another commenter notes is slow. No proposed
workaround in that thread applies cleanly to a Rust binary.

**Implication for nobotrs**: there is no supported way to make "install
nobotrs" happen automatically as part of `/plugin install nobots@marketplace`.
The two real-world patterns above are the only viable options today:
(a) require the binary already on `PATH`/well-known location, installed via a
separate mechanism (Homebrew, `cargo install`, curl-to-GitHub-Releases
installer script) with the plugin's hook/skill locating it and failing with
clear instructions if absent, or (b) bundle the binary directly in the plugin
repo (see trade-off below). `nab` and `genasis` both independently converged
on "ship the binary separately, make the plugin a thin locator," which is
reasonably strong signal this is the pragmatic default until `postInstall`
ships.

### Bundling per-platform binaries directly in the repo: no examples found

Searched (`gh search code`) for plugins bundling actual per-platform binaries
under a `bin/` path (e.g. `bin/darwin-arm64/tool`, `bin/linux-x64/tool`) — zero
hits. Nobody appears to be doing this today for Claude Code plugins. Plausible
reasons: git repos bloat fast with multi-platform binaries (a Rust release
binary is commonly 5–20MB per platform × 4-6 platform/arch combos), and it
breaks the "inspectable with `ls`/`cat`/git" filesystem-first philosophy the
spec's `distribution-installation.md` research explicitly calls out as an
advantage of directory-based plugins. It's not spec-prohibited, just
apparently not done in practice — likely because `postInstall` doesn't exist
to make it convenient to fetch-on-demand instead, so people default to
"require the binary separately" rather than "bloat the repo."

## 3. Concrete component wiring for nobotrs

Given clap subcommands (`nobotrs detect`, `nobotrs lint`, `nobotrs scan`),
grounded strictly in the schemas already verified in §1–2 and in
`component-formats.md`:

### `hooks/hooks.json` — ambient PostToolUse scan

Modeled directly on nobots' own existing Python hook
(`/home/kwhatcher/projects/nobots/hooks/hooks.json`) and on the exec-form
binary pattern confirmed live against Claude Code's docs:

```json
{
  "description": "Non-blocking scan for AI writing tells in prose files after they're written or edited.",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/nobotrs",
            "args": ["scan", "--stdin-json"],
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Notes grounded in the fetched hook docs:
- Using **exec form** (`args` present) means no shell is involved and the
  binary is invoked directly — appropriate for a compiled binary, avoids
  shell-quoting concerns.
- The hook receives the full `PostToolUse` JSON payload
  (`tool_name`, `tool_input.file_path`, `tool_output`, `cwd`, etc.) on stdin —
  `nobotrs scan` would need a `--stdin-json` mode (or just always read stdin
  when invoked with no positional file arg) that extracts `tool_input.file_path`
  itself, mirroring what `check_ai_tells.py` already does per the nobots
  README's "Try the hook by hand" section
  (`echo '{"tool_input":{"file_path":"README.md"}}' | ./check_ai_tells.py`).
- PostToolUse hooks **cannot block** (confirmed live from docs: "the tool
  already ran"). Exit 0 + JSON stdout with `systemMessage` is the mechanism for
  the non-blocking nudge nobots' README describes ("nudges Claude to run a
  humanizing pass. It never blocks you") — same contract, same UX, just backed
  by the compiled binary instead of a `uv` PEP-723 script.
- If nobotrs isn't found at `${CLAUDE_PLUGIN_ROOT}/bin/nobotrs` (see §5 on
  whether it's bundled or located), exit non-zero-but-not-2 so Claude Code
  shows a debug-log error without disrupting the session — same non-blocking
  contract nobots already guarantees.

### `skills/detect-ai-writing/SKILL.md` — on-demand invocation

A skill's job under Open Plugins is to be *instructions for the host/agent*,
not a binary wrapper itself — the SKILL.md body just tells the agent to shell
out:

```markdown
---
name: detect-ai-writing
description: Scores text against vocabulary, structural, and stylometric AI-writing tells and returns a confidence tier with evidence. Use when the user asks "is this AI-generated?" or wants a file checked for AI writing tells.
---

# Detect AI Writing

Run the compiled `nobotrs` binary against the target file and report its
verdict verbatim; do not re-derive a score yourself.

```bash
${PLUGIN_ROOT}/bin/nobotrs detect <path/to/file>
```

If the binary is not found at that path (unbundled/PATH-based distribution,
see plugin README), fall back to:

```bash
nobotrs detect <path/to/file>
```

and if that also fails, tell the user to install nobotrs (see plugin
README) rather than attempting the analysis yourself.
```

This mirrors the existing nobots `detect-ai-writing` skill's contract
(confidence tier + reasons, never a bare yes/no per the nobots README) but
delegates the actual scoring to the compiled binary instead of instructing the
agent to reason about the text itself. Per `spec-structure.md`'s field
reference, `${PLUGIN_ROOT}` expansion is documented to work inside skill
bodies as well as manifest/hook fields, so this is spec-legal.

### `commands/scan.md` (optional, Extended Profile only)

If a slash-command surface is wanted in addition to the ambient hook and the
on-demand skill, `commands/*.md` per `component-formats.md` is unrestricted
markdown — same "shell out to `${PLUGIN_ROOT}/bin/nobotrs`" instruction as the
skill, just invoked via `/nobotrs:scan` instead of natural-language triggering.
Not required for Core Profile conformance; skip if the two above cover the
UX.

## 4. Cross-harness reality check

Per `harness-compatibility.md`'s Component Support Matrix, and confirmed
against the live open-plugins.com fetch (matrix unchanged):

| Component | Claude Code | OpenCode | Pi |
|---|:---:|:---:|:---:|
| Skills (SKILL.md) | ✓ | ✓ (via tools, not native SKILL.md) | ✓ (TypeScript, not SKILL.md) |
| Hooks (hooks.json) | ✓ | ✓ (own JS event system, not hooks.json) | ✓ (own TS hook system, not hooks.json) |

**The ambient `PostToolUse` scan is Claude-Code-only in practice**, exactly as
nobots' own README already states in its "Host caveat" callout. This isn't
because the *Open Plugins spec* fails to define `PostToolUse` — it does define
`PostToolUse`/`PreToolUse` as core events in `component-formats.md` — but
because OpenCode and Pi don't consume `hooks/hooks.json` at all; per
`harness-compatibility.md` they use their own native JS/TS plugin-module event
systems (`tool.execute.after` for OpenCode, in-process TS hooks for Pi) that
are architecturally incompatible with a filesystem `hooks.json` + spawned
subprocess model. A conformant-but-minimal host is explicitly allowed under
the spec's "Minimal Conformant Host" tier to ignore `hooks` entirely and only
implement skills — so this isn't a bug in either the spec or those harnesses,
it's the spec's own tiered-conformance design working as intended.

**Practical consequence for nobotrs**: on OpenCode/Pi, only `detect-ai-writing`
(and any slash command) work, invoked explicitly by the user or agent — same
caveat nobots' Python version already carries forward unchanged. The compiled
binary doesn't change this cross-harness story at all; it only changes how the
*plugin* invokes its own logic (subprocess to a binary vs. inline `uv` script),
not which harnesses can wire up automatic triggering. Since MCP servers *are*
listed as Claude-Code-only too (not OpenCode/Pi per the matrix), even routing
nobotrs through an MCP server instead of a hook wouldn't buy back
cross-harness ambient scanning — skills remain the only component type with
real cross-harness reach.

## 5. Proposed `plugin.json` + directory layout

This is a proposal to inform the design doc, not a final structure — the CLI
architecture and packaging docs in this same research batch (`06-cli-packaging-distribution.md`)
should be reconciled with it, particularly on the binary-distribution question
raised in §2.

```
nobotrs/
├── .claude-plugin/
│   └── plugin.json                 # Claude Code vendor-specific manifest location
├── .plugin/
│   └── plugin.json                 # generic Open Plugins location (identical content)
├── ai-writing-guide.md             # field guide, ported from nobots
├── ai-detection-tools.md           # detector/API catalog, ported from nobots
├── skills/
│   ├── humanize-writing/SKILL.md
│   └── detect-ai-writing/SKILL.md  # shells to ${PLUGIN_ROOT}/bin/nobotrs detect
├── agents/
│   ├── ai-tell-reviewer.md
│   └── ai-tell-quickcheck.md
├── hooks/
│   └── hooks.json                  # PostToolUse -> ${CLAUDE_PLUGIN_ROOT}/bin/nobotrs scan
├── bin/
│   └── nobotrs -> (see distribution note below)
├── LICENSE
└── README.md
```

`plugin.json` (identical content at both manifest locations, per
`spec-structure.md`'s vendor-preference rule — Claude Code prefers
`.claude-plugin/` when both exist):

```json
{
  "name": "nobotrs",
  "version": "0.1.0",
  "description": "Detects AI-generated text and lints prose for AI writing tells — Rust rewrite of nobots.",
  "author": { "name": "Kerry Hatcher", "email": "kerry@kerryhatcher.com" },
  "homepage": "https://github.com/kerryhatcher/nobotrs",
  "repository": "https://github.com/kerryhatcher/nobotrs",
  "license": "MIT",
  "keywords": ["writing", "ai-detection", "editing", "style", "prose", "rust"],
  "skills": "./skills/",
  "agents": "./agents/",
  "hooks": "./hooks/hooks.json"
}
```

### The `bin/` question is unresolved and needs a decision in the design doc

Per §2's findings, there are two grounded options and no clear winner from
precedent alone:

- **Option A (nab-style, locate-don't-bundle)**: `bin/nobotrs` in the repo is
  actually a small shell/wrapper script (or the hook's `command` just points
  straight at a well-known install path with a `NOBOTRS_BIN` env override),
  and the real binary is installed separately (Homebrew tap, `cargo install
  nobotrs`, or a curl-to-GitHub-Releases install script à la genasis). Keeps
  the plugin repo tiny and platform-agnostic; costs the user a separate
  install step and risks silent staleness if the plugin updates but the
  separately-installed binary doesn't.
- **Option B (bundle prebuilt binaries per-platform)**: `bin/<target-triple>/nobotrs`
  checked into the repo for each supported platform, with `hooks.json`
  resolving the right one (Claude Code doesn't document a
  `${PLATFORM}`/`${ARCH}` token, so this would need a tiny shell-form
  dispatcher script rather than a direct exec-form binary path — reintroducing
  a wrapper anyway). No real-world precedent found for this pattern; likely to
  bloat the git repo across releases (binary diffs don't delta well).

Given no ecosystem precedent for Option B and that both real examples found
converged on Option A, **Option A is the safer default to design around**,
with the `bin/nobotrs` wrapper doing exactly what `nab-mcp-wrapper` does: check
an env override, check `PATH`, check well-known install dirs, and fail with
install instructions — until Claude Code ships `postInstall` (tracked
upstream, anthropics/claude-code#9394, open/unresolved as of this research),
at which point Option A's wrapper script becomes the natural place to trigger
an automatic download instead of just failing loudly.

## Sources

- `/mnt/storage/grimoire/research/open-plugins-spec/README.md` (local file, prior research)
- `/mnt/storage/grimoire/research/open-plugins-spec/spec-structure.md` (local file, prior research)
- `/mnt/storage/grimoire/research/open-plugins-spec/component-formats.md` (local file, prior research)
- `/mnt/storage/grimoire/research/open-plugins-spec/harness-compatibility.md` (local file, prior research)
- `/mnt/storage/grimoire/research/open-plugins-spec/distribution-installation.md` (local file, prior research)
- `/home/kwhatcher/projects/nobots/README.md` (local file, existing Python plugin for context)
- `/home/kwhatcher/projects/nobots/hooks/hooks.json` (local file, existing Python plugin hook config)
- `/home/kwhatcher/projects/nobots/.claude-plugin/plugin.json` (local file, existing Python plugin manifest)
- [https://open-plugins.com/](https://open-plugins.com/) (fetched live, 2026-07-26)
- [https://github.com/vercel-labs/open-plugin-spec](https://github.com/vercel-labs/open-plugin-spec) (fetched live, 2026-07-26 — now surfaces "Agent Plugins Specification" branding, see freshness note above)
- [https://code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks) (fetched live, 2026-07-26 — stdin schema, exec/shell form, exit-code semantics)
- [https://github.com/MikkoParkkola/nab](https://github.com/MikkoParkkola/nab) — real Claude Code plugin wrapping a Rust binary (`plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json`, `plugin/bin/nab-mcp-wrapper`, `plugin/hooks/nab-yara-edge.sh`, `plugin/.mcp.json` fetched via `gh api`)
- [https://github.com/claude-genasis/genasis](https://github.com/claude-genasis/genasis) — real project using a separate GitHub-Releases installer script (`install.sh` fetched via `gh api`)
- [https://github.com/anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — official plugin registry, `plugins/claude-security/hooks/hooks.json` and `plugins/ralph-loop/hooks/hooks.json` fetched via `gh api` for baseline hook conventions
- [https://github.com/anthropics/claude-code/issues/9394](https://github.com/anthropics/claude-code/issues/9394) — open feature request for `postInstall`/`postUpdate`/`postUninstall` plugin.json fields, confirms no native install-time dependency mechanism exists
- `gh search code`, `gh search repos` (GitHub code/repo search via `gh` CLI, 2026-07-26) — used to locate real-world examples and confirm absence of bundled-per-platform-binary examples
