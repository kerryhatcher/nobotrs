# nobotrs `api-clients` Tier Implementation Plan (STUB)

> **STUB — not yet detailed.** This is a task outline, not a ready-to-execute plan: no file/interface contracts, no TDD steps, no code. Expand it into full task detail (per `superpowers:writing-plans`) before dispatching it for execution. Depends on `2026-07-26-nobotrs-core-default-build.md` being implemented first (specifically the `config` command skeleton from that plan's Task 19, which this tier extends with key management).

**Goal:** Add the `api-clients` Cargo feature — four optional commercial-vendor detector clients (Sapling, GPTZero, Copyleaks, Pangram) collapsing to a single `CommercialApi` voting family, per spec §2.2/§2.4, plus the full secrets-handling contract from spec §4.

**Source spec sections:** §2.2 (`api` tier row, `CommercialApi` one-vote-per-tier-not-per-vendor rule), §2.3 (Pangram's continuous fractions vs. other vendors' coarser bands), §2.4 (majority/max-confidence composition across active vendors), §4 (full secrets contract), §8 (mocked-HTTP testing, no live calls in `cargo test`).

## Anticipated task outline (to expand later)

1. Shared vendor-client trait/shape (spec §2.2: "one client module per vendor... share the same `reqwest` dependency and trait shape").
2. Per-vendor client modules: Sapling, GPTZero, Copyleaks, Pangram — each mapping its native response format onto `human_probability` bands or Pangram's native continuous fraction (spec §2.3).
3. `CommercialApi` backend: collapses all configured vendors into one vote via majority (or configured max-confidence) rule (spec §2.4) — never one vote per vendor.
4. **Secrets precedence** (spec §4): env var → optional OS keychain (`keyring` crate) → config file, in that order — corrected from an earlier draft that put keychain last. `keyring` stays opt-in, not required, since its Linux backend depends on Secret Service D-Bus (commonly absent on headless CI).
5. **Secret redaction contract** (spec §4) — this needs its own dedicated task, not an afterthought: sanitize `reqwest::Error` URLs before logging (query-param keys), audit all `unwrap()`/panic paths in vendor client request-building for accidental key exposure via the default panic hook, redact secrets in any future `--verbose`/`--debug` output by design, and never echo a misconfigured secret's *value* back to the user (echoing the *variable name* is fine).
6. No commercial API is ever called without an explicit key configured for that specific vendor (spec §4) — enabling the feature flag at build time must not itself send data anywhere; test this explicitly (build with the flag, no keys configured, assert zero network calls attempted).
7. Mocked-HTTP test suite per vendor (spec §8) — no live network calls, no real API keys required for `cargo test`. Document the periodic manual re-verification note spec §8 calls for (mocks can't catch upstream vendor schema drift).
8. `config` command extensions: key management (set/clear per vendor, show which precedence tier is active for a configured key) — extends the basic `config` command from the core plan.
9. File-permission enforcement for the config file (spec §4: `0600` on Unix, equivalent ACL on Windows) if not already covered generically by the core plan's config path resolution.
