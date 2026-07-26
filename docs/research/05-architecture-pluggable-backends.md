# Pluggable Backend Architecture & External API Clients

Research for `nobotrs`, a Rust port of the `nobots` slop-detection plugin. Scope: (A) idiomatic Rust patterns
for a multi-backend detector architecture with feature-flag-gated optional heavy dependencies, and (B) HTTP
client, secrets/config, and public-API-documentation research for optional external commercial detector
backends (Sapling, GPTZero, Copyleaks, Pangram). Researched 2026-07-26.

---

## Part A — Backend/plugin architecture pattern in Rust

### The trait + feature-flag pattern is standard and well-supported

The intended design — a `trait DetectorBackend { fn score(&self, text: &str) -> Result<Score>; }` with
multiple implementations, some compiled in only when a Cargo feature is enabled — is a well-established,
idiomatic Rust pattern. It rests on two independent, both-confirmed-current Cargo mechanisms:

1. **Optional dependencies as features.** Marking a dependency `optional = true` lets it be toggled by a
   Cargo feature. As of Cargo 1.60+, the recommended style is the explicit `dep:` syntax rather than relying
   on the older implicit same-named feature:

   ```toml
   [dependencies]
   candle-core = { version = "...", optional = true }
   ort = { version = "...", optional = true }

   [features]
   default = []
   classifier = ["dep:ort"]
   perplexity = ["dep:candle-core"]
   ml = ["classifier", "perplexity"]
   ```

   `dep:` explicitly includes a dependency in a feature and suppresses the older implicit feature of the
   same name — useful for hiding the concrete crate name behind a user-facing feature like `ml` rather than
   exposing `candle-core` directly. Cargo is moving toward *requiring* `dep:` for this in a future edition
   (implicit features for optional deps are slated for removal), so using `dep:` now is future-proof, not
   just stylistic. [Cargo Book: Features](https://doc.rust-lang.org/cargo/reference/features.html)

2. **Feature-gated code via `#[cfg(feature = "...")]`**, compiling the backend implementation (and its
   `impl DetectorBackend for ...`) only when the corresponding feature is active, so a build with
   `--no-default-features` never touches `candle`/`ort`/`tch-rs` or triggers a model-weight download.

**Recommended shape for nobotrs**, synthesizing the above with the newtype-for-trait-objects idiom (see
below):

```toml
[features]
default = ["deterministic", "stylometric"]
deterministic = []
stylometric = []
classifier = ["dep:ort"]          # or candle-core/candle-transformers
perplexity = ["dep:candle-core", "dep:candle-transformers"]
api-clients = ["dep:reqwest"]     # gates ALL external commercial backends
full = ["classifier", "perplexity", "api-clients"]
```

- Keep `default` limited to the deterministic + stylometric backends (per the scoping constraint that a
  user who wants only those shouldn't pull in `candle`/`ort`/`tch-rs` or model weights).
- Gate all four external API backends (Sapling/GPTZero/Copyleaks/Pangram) behind one `api-clients` feature
  that pulls in `reqwest`, since they share the same HTTP-client dependency — no reason to give each vendor
  its own feature unless a future need arises to exclude specific vendors from the binary for size/audit
  reasons (sccache does this per-backend; see prior art below — worth doing the same if binary size or
  vendor-specific compliance ever becomes a concern, but not necessary at MVP scope).

### Feature-unification gotchas (verified against the current Cargo Book)

- **Union across the dependency graph.** If the same dependency is reachable through multiple paths with
  different features enabled, Cargo builds it once with the *union* of all requested features. This mostly
  matters in workspaces with multiple crates depending on the same optional dep with different feature
  sets — for a single-binary CLI like nobotrs this is low-risk, but worth remembering if the project later
  splits into a `nobotrs-core` lib crate plus a `nobotrs` CLI crate in a workspace.
- **Resolver v2 (now default).** `resolver = "2"` — the default for edition 2021+, which nobotrs will use —
  prevents feature unification across build-dependencies/dev-dependencies/target-specific deps that don't
  apply to the normal dependency graph. No action needed beyond using a current edition; just don't
  override it back to v1.
- **`cargo tree -e features` / `cargo tree --duplicates`** are the practical tools to verify actual compiled
  feature sets and catch accidental duplication once the ML-feature dependency tree gets nontrivial.
- **Downstream default-features leakage**: if nobotrs is ever consumed as a library dependency by another
  crate, that crate must remember `default-features = false` if it wants to avoid pulling in whatever ends
  up in nobotrs's `default` set. Not a concern for a pure CLI binary, but worth a comment in `Cargo.toml` if
  a `nobotrs-core` lib crate is split out later.

[Source: Cargo Book, Features](https://doc.rust-lang.org/cargo/reference/features.html)

### Trait object visibility: the newtype idiom

A secondary but relevant pattern for the `DetectorBackend` trait: if the trait itself doesn't need to be
public API (only a `Vec<Box<dyn DetectorBackend>>` selected at runtime does), keep the trait crate-private
and expose only a newtype wrapper, avoiding Rust's requirement that "any type referenced in a public
function signature must be at least as visible as the function itself." This keeps the internal backend
abstraction free to evolve without becoming a public API commitment. Static dispatch (generics/enum
dispatch) was flagged by the source as lower-overhead than `Box<dyn Trait>`, but for a CLI selecting one or
a handful of backends per run (not a hot loop), the dynamic-dispatch overhead is immaterial — an `enum
Backend { Deterministic(...), Stylometric(...), ... }` or `Vec<Box<dyn DetectorBackend>>` are both fine;
prefer whichever composes more easily with the ensemble-scoring design other agents are researching.
[Source: jmmv.dev, "Rust traits and dependency injection"](https://jmmv.dev/2022/04/rust-traits-and-dependency-injection.html)

### Real-world prior art

- **sccache** (Mozilla/wasmerio) is the strongest real-world precedent for "many pluggable backends behind
  Cargo features, default build excludes the heavy ones." Its storage backends — `s3`, `redis`, `gcs`,
  `memcached`, `azure`, `gha`, `webdav`, `oss`, `cos` — are each an optional dependency gated by its own
  same-named feature; `cargo build --features=s3,gcs` (or `--no-default-features --features=...`) picks
  exactly the backends wanted, and the project publishes builds with all backends by default but documents
  trimming them down. This is directly analogous to nobotrs gating classifier/perplexity/API backends.
  [GitHub: mozilla/sccache](https://github.com/mozilla/sccache),
  [crates.io: sccache](https://crates.io/crates/sccache)
- **ort** (ONNX Runtime bindings) and **candle** both use Cargo features to select compute backends (e.g.
  CUDA, CoreML) and alternate execution providers (`ort-candle` lets `ort`'s API run on a `candle` backend),
  confirming the same feature-gated-backend pattern is standard practice in the Rust ML-tooling ecosystem
  nobotrs's classifier/perplexity backends will sit in.
  [GitHub: pykeio/ort examples](https://github.com/pykeio/ort/tree/main/examples),
  [GitHub: huggingface/candle](https://github.com/huggingface/candle)

### Recommendation

Adopt: `trait DetectorBackend` (kept crate-private or newtype-wrapped) with one `impl` per backend; each
non-default backend's crate dependency marked `optional = true` with `dep:` feature syntax; one feature per
heavy backend family (`classifier`, `perplexity`) plus one shared `api-clients` feature for all four
external vendors; `default = ["deterministic", "stylometric"]`; a `full` feature for convenience. This
matches both current Cargo best practice and sccache's proven real-world precedent.

---

## Part B — External API backend clients

### 1. HTTP client: reqwest + tokio, blocking-wrapper option

- **reqwest**: current max version **0.13.4**, license **MIT OR Apache-2.0**. Confirmed as the standard
  high-level HTTP client for Rust. [crates.io API: reqwest](https://crates.io/api/v1/crates/reqwest)
- **tokio**: current max version **1.53.1**, license **MIT**. Standard async runtime; reqwest's default
  (non-blocking) API requires it. [crates.io API: tokio](https://crates.io/api/v1/crates/tokio)
- **`reqwest::blocking`** is real and current: it's gated behind reqwest's `blocking` Cargo feature
  (`reqwest = { version = "0.13", features = ["blocking"] }`) and internally spins up its own tokio runtime
  per-call so the rest of the binary never needs to be async. Hard constraint, explicitly documented:
  **`reqwest::blocking` must never be called from inside an existing async/tokio runtime** — doing so
  panics. If nobotrs's core is synchronous (likely, given the deterministic/stylometric backends have no
  reason to be async), `reqwest::blocking` is the pragmatic choice: no `#[tokio::main]`, no `.await`
  propagation through the CLI's call graph, no async-taint of the trait signature (`DetectorBackend::score`
  can stay a plain synchronous `fn`). The tradeoff is that concurrent multi-backend or multi-vendor calls
  (e.g. querying Sapling and GPTZero at once) would need manual thread spawning (`std::thread` /
  `rayon`/`std::thread::scope`) rather than `tokio::join!`, and reqwest's blocking client still transitively
  depends on tokio internally regardless of which API surface is used — it doesn't remove the dependency,
  just the requirement to structure the whole program around `async fn`. Recommendation: use
  `reqwest::blocking` behind the `api-clients` feature unless/until the tool's design elsewhere already
  needs an async runtime (e.g. concurrent local-model inference), in which case switching to the async
  client and running backends concurrently via `tokio::spawn` would be more natural.
  [docs.rs: reqwest::blocking](https://docs.rs/reqwest/latest/reqwest/blocking/index.html),
  [GitHub issue: reqwest #1233, blocking + tokio interaction](https://github.com/seanmonstar/reqwest/issues/1233)

### 2. Public API documentation availability per vendor

All four vendors publish enough public documentation to build a client against without a private
agreement, though quality/format varies:

| Vendor | Docs | Format | Notes |
|---|---|---|---|
| **Sapling** | [sapling.ai/docs/api/detector/](https://sapling.ai/docs/api/detector/) | Hand-written REST reference | Simple POST with `key` + `text` params (200,000-char limit per request), optional `sent_scores`/`score_string` flags. Free dev key: 50,000 chars/24h (matches existing `ai-detection-tools.md` reference). |
| **GPTZero** | [gptzero.stoplight.io](https://gptzero.stoplight.io/docs/gptzero-api/) | **Stoplight-hosted (OpenAPI-based)**, with generated code samples in 17 languages | Best-documented of the four for client-generation purposes since Stoplight is backed by a machine-readable spec. Returns `document_classification` (HUMAN_ONLY/MIXED/AI_ONLY) plus `class_probabilities` and `confidence_category`. API key from `app.gptzero.me/app/api`. |
| **Copyleaks** | [docs.copyleaks.com](https://docs.copyleaks.com/using-the-apis/overview/), AI-detector-specific: [docs.copyleaks.com/reference/actions/writer-detector/check/](https://docs.copyleaks.com/reference/actions/writer-detector/check/) | Structured reference site (looks Redoc/OpenAPI-derived given the `/reference/actions/...` URL shape) | Includes a `sandbox: true` request flag for testing without consuming credits — useful for nobotrs's own integration tests against a real endpoint shape without burning the free 25,000 chars/month quota. |
| **Pangram** | [docs.pangram.com](https://docs.pangram.com/) and [pangram.readthedocs.io/en/latest/api/rest.html](https://pangram.readthedocs.io/en/latest/api/rest.html) | REST reference + official Python SDK ([github.com/pangramlabs/pangram-sdk](https://github.com/pangramlabs/pangram-sdk)) | Response includes `fraction_ai`, `fraction_ai_assisted`, `fraction_human` (0.0–1.0 floats) — a finer-grained scoring shape than the binary/tri-state classifications from the other three; worth designing the common `Score` type to accommodate a continuous fraction rather than only a label. Confirmed **not free** (~$0.05/1,000 words), consistent with the existing `ai-detection-tools.md` note. |

No vendor was found to publish a downloadable OpenAPI/Swagger JSON file directly (only GPTZero's
Stoplight and, likely, Copyleaks's Redoc-style docs are spec-derived under the hood) — full
request/response schema capture for each is out of scope here per the assignment and left to
implementation time against each vendor's live reference page.

### 3. Secrets/config handling for user-supplied API keys

Three realistic options, compared for a 2026-era Rust CLI:

- **`keyring` crate** — current max version **4.1.5**, license **MIT OR Apache-2.0**. Cross-platform access
  to the OS-native secret store (macOS Keychain, Windows Credential Manager, Linux Secret
  Service/D-Bus or `keyutils`). As of the current major version, the library has been split: the
  core API/trait now lives in `keyring-core`, with each credential-store backend (macOS, Windows, Secret
  Service, etc.) in its own crate, and `keyring` acting as the glue/facade crate most consumers should
  depend on directly. This is the most secure option — API keys never touch plaintext disk — but adds a
  real dependency (D-Bus on Linux desktop environments without a running Secret Service daemon can fail,
  e.g. headless servers/containers/CI, which matters for a CLI tool that may run in non-desktop
  environments). [crates.io API: keyring](https://crates.io/api/v1/crates/keyring),
  [GitHub: open-source-cooperative/keyring-rs](https://github.com/open-source-cooperative/keyring-rs)
- **Config file** — `directories` crate (current max version **6.0.0**, license **MIT OR Apache-2.0**) to
  locate the platform-correct config dir (XDG on Linux, Known Folder API on Windows, Standard Directory
  guidelines on macOS) for something like `~/.config/nobotrs/config.toml`, combined with `serde` + `toml`
  for parsing (see §4). Simple, portable, works headless/in-CI, but stores the key in plaintext unless the
  user is told to `chmod 600` it themselves — nobotrs would need to do this explicitly on Unix
  (`std::fs::Permissions` / `set_permissions` at 0600) when writing the file, and there's no equivalent
  protection available on Windows via std alone.
  [crates.io API: directories](https://crates.io/api/v1/crates/directories)
- **Environment variables** (`SAPLING_API_KEY`, etc.) — zero extra dependency, standard for CI/scripting
  use, but leaks into process listings/shell history/crash dumps more readily than either alternative, and
  isn't persistent across sessions on its own (users would still need a config file or shell profile entry
  to avoid retyping it).

**Recommendation**: layer all three, in the order a typical Rust CLI does — env var overrides config file
overrides keyring, or some similar explicit precedence — with the config file as the baseline persistence
mechanism (since it's the one guaranteed to work headless/in-CI) and `keyring` as an **opt-in** upgrade
for users on a desktop OS who want the key off disk entirely (e.g. `nobotrs config set-key sapling
--keyring`). Since these are external-service API keys (not, e.g., an SSH private key or a database
password), and this is an opt-in feature for a CLI tool rather than a security product, plaintext config
file with tightened file permissions is a reasonable *default*, with `keyring` documented as the
recommended hardening step — this matches common practice in comparable Rust CLIs (e.g. `gh` and `aws-cli`
both default to a config file, offering OS-keychain integration as an option rather than a requirement).
Flag for the spec: plaintext config file is a real security tradeoff or the user should decide is
acceptable up front, since it's the default in this recommendation.

### 4. Config format: serde + toml

- **serde** — current max version **1.0.229**, license **MIT OR Apache-2.0**. The standard
  serialization/deserialization framework; effectively unavoidable, and every other candidate crate above
  already depends on it transitively. [crates.io API: serde](https://crates.io/api/v1/crates/serde)
- **toml** — current max version **1.1.3+spec-1.1.0**, license **MIT OR Apache-2.0**. Native Rust
  TOML encoder/decoder with `Serialize`/`Deserialize` support via serde derive macros. Confirmed standard
  choice for CLI config files in the Rust ecosystem (TOML is what Cargo itself uses, which makes it a
  natural fit for Rust-tool config idioms). [crates.io API: toml](https://crates.io/api/v1/crates/toml)

No license issues in this entire Part B dependency set — reqwest, tokio, keyring, directories, serde, and
toml are all dual MIT/Apache-2.0 except tokio, which is MIT-only. All compatible with nobotrs's MIT
license.

---

## Sources

- [Cargo Book: Features](https://doc.rust-lang.org/cargo/reference/features.html)
- [RFC 2957: cargo-features2](https://rust-lang.github.io/rfcs/2957-cargo-features2.html)
- [RFC 3491: remove-implicit-features](https://rust-lang.github.io/rfcs/3491-remove-implicit-features.html)
- [jmmv.dev: Rust traits and dependency injection](https://jmmv.dev/2022/04/rust-traits-and-dependency-injection.html)
- [GitHub: mozilla/sccache](https://github.com/mozilla/sccache)
- [crates.io: sccache](https://crates.io/crates/sccache)
- [GitHub: pykeio/ort — examples](https://github.com/pykeio/ort/tree/main/examples)
- [GitHub: huggingface/candle](https://github.com/huggingface/candle)
- [lib.rs: ort-candle](https://lib.rs/crates/ort-candle)
- [docs.rs: reqwest::blocking](https://docs.rs/reqwest/latest/reqwest/blocking/index.html)
- [GitHub issue: seanmonstar/reqwest #1233](https://github.com/seanmonstar/reqwest/issues/1233)
- [crates.io API: reqwest](https://crates.io/api/v1/crates/reqwest)
- [crates.io API: tokio](https://crates.io/api/v1/crates/tokio)
- [crates.io API: keyring](https://crates.io/api/v1/crates/keyring)
- [crates.io API: directories](https://crates.io/api/v1/crates/directories)
- [crates.io API: serde](https://crates.io/api/v1/crates/serde)
- [crates.io API: toml](https://crates.io/api/v1/crates/toml)
- [GitHub: open-source-cooperative/keyring-rs](https://github.com/open-source-cooperative/keyring-rs)
- [Sapling AI Detector API docs](https://sapling.ai/docs/api/detector/)
- [GPTZero API docs (Stoplight)](https://gptzero.stoplight.io/docs/gptzero-api/5bf295g49gwxp-gpt-zero-api)
- [Copyleaks API overview](https://docs.copyleaks.com/using-the-apis/overview/)
- [Copyleaks AI Text Detection — Check reference](https://docs.copyleaks.com/reference/actions/writer-detector/check/)
- [Pangram Labs Documentation](https://docs.pangram.com/)
- [Pangram REST API reference](https://pangram.readthedocs.io/en/latest/api/rest.html)
- [GitHub: pangramlabs/pangram-sdk](https://github.com/pangramlabs/pangram-sdk)
- Existing reference: `/home/kwhatcher/projects/nobots/ai-detection-tools.md` (free-tier API figures cross-checked against vendor docs above)
