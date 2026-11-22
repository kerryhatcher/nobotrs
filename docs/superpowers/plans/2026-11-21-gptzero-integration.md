# GPTZero Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in GPTZero detection backend to the `nobotrs` Rust CLI, so `nobotrs detect --gptzero` returns GPTZero's document verdict as informational evidence alongside the offline heuristics.

**Architecture:** A feature-gated HTTP client (`ureq`, blocking, rustls) posts text to `POST /v2/predict/text` with an `x-api-key` header. A new `DetectorBackend` adapter maps the response into a `ScoreOutcome` under a new `SignalFamily::External` that never votes in the heuristic quorum, mirroring how `SignalFamily::Model` is handled. Everything is off by default: the default build has no network code and no keys.

**Tech Stack:** Rust 1.85+, `ureq` 2.x (blocking, `tls` feature), `serde`/`serde_json` (existing), `clap` (existing). No async runtime: the crate is synchronous.

**Spec:** No separate spec document exists. Decisions and their sources are in the Decisions section below; the GPTZero facts they rest on are listed under Verified API Facts.

## Decisions

- **Opt-in only.** `README.md` states the default build "makes no network requests and requires no keys." GPTZero is a keyed network service that receives the user's document. Integration is behind a Cargo feature `gptzero` (off by default) and a runtime switch (`--gptzero` / `NOBOTRS_GPTZERO=1` / config `gptzero: true`). Both gates must be on.
- **Key from environment only.** The key is read from `GPTZERO_API_KEY`. It is never read from or written to the config file, never printed, never logged, and never included in error text.
- **No crate.** A search of crates.io for "gptzero" found no GPTZero client (the only hit is an unrelated package). Write a thin client over `ureq` + `serde`.
- **Oversize input is refused, not chunked.** Text over the documented 150,000-character API limit produces `Error::ResourceLimit` and an abstention. The adapter does not split and merge results, because the merge semantics are not defined by the API.
- **Informational, never a vote.** `SignalFamily::External` is excluded from quorum, as `Model` is (`src/aggregate.rs:60`).
- **Recommended execution order is linear.** Tasks 1–5 share interfaces, so run them in order.

## Verified API Facts

Source: GPTZero support and developer pages, read 2026-11-21. Treat anything not listed here as unverified until Task 0 captures a live response.

- Base URL `https://api.gptzero.me`; endpoint `POST /v2/predict/text`; header `x-api-key`; body includes `document` (string) and `version` (string) per the developers page.
- Response names mentioned: `document_classification` (`HUMAN_ONLY` | `MIXED` | `AI_ONLY`), `class_probabilities` (keys `human`, `ai`, `mixed`), `predicted_class`, `confidence_category` (`high` | `medium` | `low`), `highlight_sentence_for_ai`.
- Text limit on API plans: 150,000 characters; over-limit requests get `400`. Missing/expired key → `401`; unrecognized key → `403`.
- Rate limit: 30,000 requests/hour for all plans; higher by request to api@gptzero.me.
- Monthly word quotas with overage; once the overage cap is reached, requests are declined.
- A limited free trial exists without a key (limit not stated).
- **Unverified:** exact request/response field names and types for document- and sentence-level probabilities, perplexity, and whether `version` is required. The full OpenAPI schema is on the Stoplight site, which returned a shell when fetched. Task 0 settles this.

## Global Constraints

- Default build (`cargo build` with no features) must contain no HTTP client and make no network calls. Verified in Task 6.
- `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked` must pass.
- The API key must never appear in stdout, stderr, JSON/SARIF output, `config` output, or error messages.
- Any new `Settings` field must keep `#[serde(default, deny_unknown_fields)]` behavior and must not break existing config files.
- Output stays deterministic and offline-equivalent when the feature is off.

## Review Focus

1. **Empty or whitespace-only input** → abstain with no network call. Expected: no request is made and no quota is consumed. Pinned in Task 4.
2. **Input over 150,000 characters** → `ResourceLimit` abstention with a clear reason; never a raw `400` surfaced as a crash. Pinned in Task 3.
3. **Missing or invalid key** → one clear config message naming the env var, not the key value; `401`/`403` map to `ConfigError`. Pinned in Tasks 2 and 3.
4. **Network down, timeout, or hostile slow server** → the backend returns `Failed`/`Incomplete` with a warning, and the heuristic verdict and exit code are unchanged. Pinned in Tasks 3 and 5.
5. **Quota exhausted or rate limited (`429`, overage cap)** → a distinct warning, not a panic and not a silent empty result. Pinned in Task 3.

## File Structure

- Create: `src/external/mod.rs` — module root; re-exports the GPTZero backend and a `NAME`/`FAMILY` constant pair.
- Create: `src/external/gptzero/mod.rs` — `GptZeroBackend` (`DetectorBackend` impl) and status reporting.
- Create: `src/external/gptzero/client.rs` — HTTP client, request/response types, error mapping.
- Create: `tests/fixtures/gptzero/predict_text_<scenario>.json` — captured or hand-verified response fixtures (Task 0 decides which).
- Create: `tests/gptzero_backend.rs` — integration tests against a local `TcpListener` mock server.
- Modify: `Cargo.toml` — `gptzero` feature, optional `ureq` dependency, `include` entries for new paths.
- Modify: `src/config.rs` — `gptzero: bool`, `gptzero_base_url: String` on `Settings`; env/CLI resolution.
- Modify: `src/backend.rs` — add `SignalFamily::External`.
- Modify: `src/aggregate.rs:60` — exclude `External` from quorum.
- Modify: `src/pipeline.rs:167,183,212` — treat `External` like `Model` where it is currently checked.
- Modify: `src/cli/mod.rs` — `--gptzero` global flag.
- Modify: `src/output.rs` — additive `gptzero` field in JSON output, with the warning in human output.
- Modify: `README.md`, `docs/configuration.md`, `HANDOFF.md` — qualify the "no network" claim and document the opt-in.

---

### Task 0: Live response spike (decision gate)

**Files:**
- Create: `tests/fixtures/gptzero/predict_text_sample.json`
- Create: `docs/superpowers/plans/gptzero-spike-notes.md`

**Interfaces:**
- Consumes: nothing.
- Produces: confirmed request body (`document`, `version` required or not), confirmed response field names, types, and sentence-level field shape. Tasks 2–3 use these exact names.

- [ ] **Step 1: Obtain a key or use the free trial.** The user supplies a key via `GPTZERO_API_KEY` in their own shell. Do not paste it into chat, files, or commits. If none is available, try the no-key trial at the Stoplight docs; it may have a low usage cap.
- [ ] **Step 2: Capture one request.** Send a fixed ~500-word human-written sample and a fixed AI-generated sample with `curl --form-string` against `POST https://api.gptzero.me/v2/predict/text` using `x-api-key: $GPTZERO_API_KEY`. Save the raw JSON response to the fixture path, with the key redacted if it is echoed anywhere.
- [ ] **Step 3: Record the exact schema** in `docs/superpowers/plans/gptzero-spike-notes.md`: request fields, every response field with its JSON type, sentence-level structure, and the `400` error body.
- [ ] **Step 4: Verify.** Run `jq 'keys' tests/fixtures/gptzero/predict_text_sample.json` and confirm it matches the notes. Expected: the keys listed in the notes, no secret values.
- [ ] **Step 5: Gate.** If `version` is required, add it to the request in Task 2. If the schema differs from Verified API Facts, update those facts in this plan before Task 2.

---

### Task 1: Feature flag, settings, and enum variant

**Files:**
- Modify: `Cargo.toml`
- Modify: `src/config.rs`, `src/backend.rs`, `src/cli/mod.rs`
- Test: `src/config.rs` (existing `#[cfg(test)]` module)

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings { gptzero: bool, gptzero_base_url: String }` (defaults `false`, `"https://api.gptzero.me"`); `SignalFamily::External`; Cargo feature `gptzero`; `Overrides.gptzero: Option<bool>`.

- [ ] **Step 1: Write failing tests** asserting: default `Settings::default().gptzero == false`; `NOBOTRS_GPTZERO=1` sets it true with origin `environment:NOBOTRS_GPTZERO`; an unknown key `gptzero_api_key` in the config file is rejected (`deny_unknown_fields`), proving the key cannot be stored in config.
- [ ] **Step 2: Run** `cargo test --locked config::` and confirm the new tests fail.
- [ ] **Step 3: Implement** the two `Settings` fields and env/CLI resolution using the existing `setting!` pattern. Add `External` to `SignalFamily`. Add `gptzero` feature: `gptzero = ["dep:ureq"]`, with `ureq = { version = "2", default-features = false, features = ["tls", "json"], optional = true }`.
- [ ] **Step 4: Run** `cargo test --locked` and `cargo build` (default features). Expected: pass; default build does not compile `ureq`. Confirm with `cargo tree -e normal | grep -c ureq` → `0`.
- [ ] **Step 5: Commit** `feat(gptzero): add opt-in settings and external signal family`.

---

### Task 2: HTTP client and wire types

**Files:**
- Create: `src/external/mod.rs`, `src/external/gptzero/mod.rs`, `src/external/gptzero/client.rs`
- Modify: `src/lib.rs` (add `#[cfg(feature = "gptzero")] pub mod external;`)
- Test: `tests/gptzero_backend.rs`

**Interfaces:**
- Consumes: `Settings.gptzero_base_url`; response shape from `docs/superpowers/plans/gptzero-spike-notes.md`.
- Produces:
  - `pub const GPTZERO_MAX_CHARS: usize = 150_000;`
  - `pub struct GptZeroClient` with `pub fn new(api_key: String, base_url: String, timeout: std::time::Duration) -> Self`
  - `pub fn detect_text(&self, text: &str) -> Result<DetectResponse, crate::error::Error>`
  - `pub struct DetectResponse { pub document_classification: String, pub class_probabilities: ClassProbabilities, pub predicted_class: String, pub confidence_category: String }` (field types confirmed in Task 0)
  - `pub struct ClassProbabilities { pub human: f64, pub ai: f64, pub mixed: f64 }`

- [ ] **Step 1: Write failing tests** against a local `std::net::TcpListener` mock: (a) a fixture response parses into `DetectResponse`; (b) a request carries header `x-api-key: test-key` and JSON body with `document`; (c) a `401` response maps to `Error::ConfigError` whose message does not contain `test-key`.
- [ ] **Step 2: Run** `cargo test --locked --features gptzero gptzero_backend` and confirm failure.
- [ ] **Step 3: Implement** `GptZeroClient::detect_text`: check `text.chars().count() <= GPTZERO_MAX_CHARS` before sending (else `Error::ResourceLimit`); build a `ureq::AgentBuilder` with the given timeout; POST JSON; map status codes: `400` → `ConfigError`/`InternalError` with body text (no key), `401`/`403` → `ConfigError("GPTZero rejected the API key; check GPTZERO_API_KEY")`, `429` → `NetworkError("rate limited")`, transport error/timeout → `NetworkError`/`Timeout`.
- [ ] **Step 4: Run** the same tests; expected PASS.
- [ ] **Step 5: Commit** `feat(gptzero): add HTTP client and response types`.

---

### Task 3: Error and quota handling

**Files:**
- Modify: `src/external/gptzero/client.rs`
- Test: `tests/gptzero_backend.rs`

**Interfaces:**
- Consumes: `GptZeroClient::detect_text` from Task 2.
- Produces: no new public names; behavior pins for Review Focus items 2, 3, 4, 5.

- [ ] **Step 1: Write failing tests:** (a) 150,001-character input → `ResourceLimit`, and the mock server receives zero requests; (b) `429` → `NetworkError` containing "rate limited"; (c) a mock that accepts the connection and never responds, with timeout 200 ms → `Timeout` or `NetworkError` returned within 2 s; (d) overage-declined response (use the status and body captured in Task 0 or the documented decline) → a distinct `ConfigError`/`NetworkError` message mentioning quota, not a panic.
- [ ] **Step 2: Run** and confirm failure.
- [ ] **Step 3: Implement** the remaining mappings and the timeout as the `ureq` agent timeout (a cooperative `Deadline` cannot interrupt a blocking socket read, per `src/deadline.rs`).
- [ ] **Step 4: Run** `cargo test --locked --features gptzero`; expected PASS.
- [ ] **Step 5: Commit** `feat(gptzero): map API errors, quota and timeout`.

---

### Task 4: Backend adapter

**Files:**
- Create/Modify: `src/external/gptzero/mod.rs`
- Modify: `src/pipeline.rs:167,183,212`, `src/aggregate.rs:60`
- Test: `tests/gptzero_backend.rs`, plus a unit test in `src/aggregate.rs`

**Interfaces:**
- Consumes: `GptZeroClient` (Tasks 2–3); `SignalFamily::External` (Task 1); `ScoreOutcome` (`src/backend.rs`); `Score` (`src/score.rs`).
- Produces: `pub struct GptZeroBackend { client: GptZeroClient }` implementing `DetectorBackend` with `name() == "gptzero"` and `family() == SignalFamily::External`.

- [ ] **Step 1: Write failing tests:** (a) empty and whitespace-only documents return `Abstained` and make zero HTTP requests; (b) a fixture AI-leaning response yields `Scored` with a `Score` whose severity/direction follows `predicted_class` and `confidence_category`; (c) a `NetworkError` yields `Failed`, not `Scored`; (d) in `aggregate.rs`, an `External` scored outcome does not change the quorum count.
- [ ] **Step 2: Run** and confirm failure.
- [ ] **Step 3: Implement** `DetectorBackend for GptZeroBackend`. Map `document_classification`/`predicted_class` to a `Score` using the existing `Score` constructors in `src/score.rs`. Add `External` to the exclusions at `aggregate.rs:60` and to the three `Model`-specific checks in `pipeline.rs` (empty docs must abstain without calling the client). Confirm the exact `Score` fields by reading `src/score.rs` before writing the mapping.
- [ ] **Step 4: Run** `cargo test --locked --features gptzero`; expected PASS.
- [ ] **Step 5: Commit** `feat(gptzero): add detector backend adapter`.

---

### Task 5: CLI wiring, key resolution, and output

**Files:**
- Modify: `src/cli/mod.rs`, `src/output.rs`, `src/config.rs` (key read)
- Test: `tests/gptzero_backend.rs` (CLI smoke tests using `assert_cmd` if already a dev-dependency; otherwise invoke the binary via `std::process::Command`)

**Interfaces:**
- Consumes: `Settings.gptzero`, `Settings.gptzero_base_url`, `GptZeroBackend` (Task 4).
- Produces: `--gptzero` global flag; `GPTZERO_API_KEY` read by `fn gptzero_api_key() -> Option<String>` in `src/config.rs`; additive `"gptzero"` object in JSON output.

- [ ] **Step 1: Write failing tests:** (a) `--gptzero` without `GPTZERO_API_KEY` exits with a message naming the variable and does not print any key; (b) with the key set and a mock base URL, `detect --format json` includes a `gptzero` object and the heuristic `verdict`/exit code is unchanged compared with a run without `--gptzero`; (c) human output contains a line stating that the text was sent to GPTZero; (d) `config` output shows `gptzero: enabled/disabled` and key presence as a boolean only.
- [ ] **Step 2: Run** and confirm failure.
- [ ] **Step 3: Implement** the flag, key read from env, backend registration only when both gates are on, and the output additions. Keep the JSON addition additive; check `src/output.rs` for the current `schema_version` and follow its convention for additive changes.
- [ ] **Step 4: Run** `cargo test --locked --features gptzero`; expected PASS.
- [ ] **Step 5: Commit** `feat(gptzero): wire --gptzero flag and output`.

---

### Task 6: Live test, packaging, and docs

**Files:**
- Create: `tests/gptzero_live.rs` (`#[ignore]`, requires `GPTZERO_API_KEY`)
- Modify: `Cargo.toml` (`include` entries for any new docs/fixtures), `README.md`, `docs/configuration.md`, `HANDOFF.md`

**Interfaces:**
- Consumes: everything above.
- Produces: user-facing documentation; no new code interfaces.

- [ ] **Step 1: Write** the `#[ignore]` live test: one call with a short sample; asserts a parseable response. Run it manually with `GPTZERO_API_KEY` set: `cargo test --locked --features gptzero -- --ignored gptzero_live`.
- [ ] **Step 2: Verify default build has no network code:** `cargo build --locked && cargo tree --locked -e normal | grep -c -E 'ureq|rustls'` → `0`.
- [ ] **Step 3: Update docs.** README: replace the unconditional "makes no network requests" sentence with "the default build makes no network requests; the optional `gptzero` feature sends text to GPTZero when explicitly enabled." `docs/configuration.md`: document `gptzero`, `gptzero_base_url`, `GPTZERO_API_KEY`, and that the key is never stored in config.
- [ ] **Step 4: Full gate:** `cargo fmt --check && cargo clippy --locked --all-targets --features gptzero -- -D warnings && cargo test --locked --features gptzero && cargo test --locked`. Expected: all pass.
- [ ] **Step 5: Commit** `docs(gptzero): document opt-in integration and add live test`.

---

## Review Focus coverage map

| Review Focus item | Owning task | Test |
|---|---|---|
| 1. Empty input, no call | Task 4 | `empty_document_abstains_without_request` |
| 2. Oversize input | Task 3 | `oversize_input_is_resource_limit_no_request` |
| 3. Bad key, key not leaked | Tasks 2, 5 | `unauthorized_maps_to_config_error_without_key`, `config_shows_key_presence_only` |
| 4. Network failure, heuristics unchanged | Tasks 3, 5 | `timeout_returns_within_budget`, `heuristic_result_unchanged_with_gptzero_failure` |
| 5. Quota / rate limit | Task 3 | `rate_limit_and_quota_are_distinct_warnings` |

## Open items for the user

- A GPTZero API key (or permission to use the no-key trial) for Task 0. Plans and pricing are unclear (monthly word quotas, overage caps); confirm with api@gptzero.me before any production use.
- Confirm that sending user text to a third-party service is acceptable for this CLI's users, since it reverses the project's offline promise. The design keeps it opt-in, but the decision is yours.

---

## Execution deviations (recorded during native execution)

- **Feature and HTTP client follow the design spec.** The feature is `api-clients` and the client is `reqwest` (blocking, rustls), as in `docs/superpowers/specs/2026-07-26-nobotrs-rust-cli-design.md` §2.2. Earlier drafts of this plan said `gptzero` and `ureq`.
- **No `DetectorBackend` and no new `SignalFamily`.** GPTZero output is attached to `Report` as an optional `external` side channel, set only by `detect` and `analyze`. The pipeline, coverage logic, and aggregator are untouched, so the verdict cannot change by construction. Tasks 1, 4 and the family edits in Task 4 were replaced by this.
- **Spec conflict, not resolved here.** The design spec makes commercial APIs a *voting* `CommercialApi` family (one vote per tier). The approved plan makes GPTZero non-voting, for comparison use. The implementation follows the approved plan. Moving to the spec's voting model would be a separate decision.
- **Timeout** is a fixed 30 s per request, not the heuristic `timeout_ms`. A cooperative `Deadline` cannot interrupt a blocking socket read.
- **Output schema**: `Report.external` is skipped in JSON when absent, so existing output is unchanged.
- **Scope**: `--gptzero` is rejected for `lint` and `scan` with an error (exit 2).
- **Live responses differ from the public reference.** See `gptzero-spike-notes.md`. The client parses only the fields it needs and ignores unknown ones.
