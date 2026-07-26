# CLI Framework & Packaging/Distribution Research for nobotrs

## Introduction

This document surveys Rust crates and tools for building CLI applications with colored terminal output, JSON formatting, and cross-platform distribution. The research focuses on tools that support shipping `nobotrs` as a single compiled binary (macOS/Linux/Windows) via crates.io, GitHub Releases, Homebrew, and potentially cargo-binstall. Version numbers, licenses, and maintenance status are verified as of July 2026.

---

## 1. CLI Argument Parsing: `clap`

**Link:** https://crates.io/crates/clap  
**Docs:** https://docs.rs/clap/latest/clap/

### Current Status
- **Latest Version:** 4.6.4 (released July 21, 2026)
- **License:** MIT OR Apache-2.0 (dual)
- **Minimum Rust Version:** 1.85.0 (uses Rust 2024 edition)
- **Maintenance:** Extremely active — 63.8M downloads/month, 64,701 reverse dependencies

### Fit for nobotrs
**Excellent.** `clap` is the standard-library-tier CLI parser in the Rust ecosystem. It provides:
- Derive macro API (`#[derive(Parser, Subcommand)]`) for declarative subcommand definition, perfect for `detect`, `lint`, `scan` subcommands
- Automatic help generation and colored output
- Shell completion generation
- Suggested error messages for typos
- No friction; used in the vast majority of Rust CLI tools

### Recommendation
Use `clap` with the derive API for subcommand parsing. No alternatives needed.

---

## 2. Colored Terminal Output

Research compared four main libraries: `owo-colors`, `termcolor`, `colored`, and `anstyle`.

### Summary: Recommended Approach
**Use `owo-colors` directly for immediate terminal coloring.** For interoperability with library consumers (if nobotrs exposes diagnostics as a library), optionally layer `anstyle` on top, but for a CLI-only tool, `owo-colors` alone is sufficient and more direct.

### 2a. `owo-colors`

**Link:** https://crates.io/crates/owo-colors  
**Docs:** https://docs.rs/owo-colors/latest/owo_colors/

- **Latest Version:** 4.3.0 (released June 24, 2026)
- **License:** MIT
- **Zero allocations, no_std compatible**
- **Environment Variables:** Supports `NO_COLOR` and `FORCE_COLOR` (automatic; enabled by default)
- **Additional Checks:** TTY detection, CI environment detection, terminal type recognition (requires `supports-colors` feature)

**Fit:** **Excellent.** Lowest-overhead colored output. Respects standard environment variables. No dependencies beyond optional `supports-colors` feature.

### 2b. `anstyle`

**Link:** https://crates.io/crates/anstyle  
**Docs:** https://docs.rs/anstyle/latest/anstyle/

- **License:** MIT OR Apache-2.0 (dual)
- **Purpose:** Core types for ANSI escape codes; **interoperability layer** between color libraries
- **Ecosystem:** `anstyle-owo-colors` and `anstyle-termcolor` adapters allow different parts of a library to output colors using different backends

**Fit:** **Optional.** If `nobotrs` exposes a library crate for other tools to use (e.g., a `nobotrs_core` library), `anstyle` + adapters provide flexibility. For CLI-only, skip this.

### 2c. `termcolor` and `colored`

- **`termcolor`:** Targets deprecated Console APIs on Windows; not recommended (Rust CLI recommendations as of 2026 flag this explicitly).
- **`colored`:** Actively maintained (MSRV 1.80, CI-enforced), but requires allocations and is not no_std. Overshadowed by `owo-colors` in 2026 recommendations.

---

## 3. JSON Output: `serde_json`

**Link:** https://crates.io/crates/serde_json  
**Docs:** https://docs.rs/serde_json/latest/serde_json/

### Current Status
- **Latest Version:** 1.0.151
- **License:** MIT OR Apache-2.0 (dual)
- **Downloads:** 614.1M total, 89.3M recent
- **Maintenance:** Extremely stable; de facto standard

### Fit for nobotrs
**Trivial.** Use `serde` + `serde_json` for `--format json` output. Serialize detection scores and metadata to JSON.

**Typical usage:**
```rust
#[derive(serde::Serialize)]
struct DetectionResult {
    file: String,
    score: f32,
    lines: Vec<LineMatch>,
}

println!("{}", serde_json::to_string_pretty(&result)?);
```

No alternatives needed; `serde` + `serde_json` is the ecosystem standard.

---

## 4. Cross-Compilation: `cross` & `cargo-dist`

The problem: shipping precompiled binaries for x86_64, aarch64, and armv7 (Linux/macOS/Windows) without manual toolchain setup or bloated Docker images.

### 4a. `cross`

**Link:** https://github.com/cross-rs/cross  
**Crates.io:** https://crates.io/crates/cross

- **Latest Version:** 0.2.5
- **License:** MIT OR Apache-2.0 (dual)
- **Maintenance:** Active (last commit March 25, 2026)
- **What it does:** Docker/Podman wrapper that provides complete cross-compilation environments (toolchain + cross-compiled libraries) without installing on your system
- **CLI:** Drop-in replacement for `cargo build --target=...` but uses Docker by default
- **Container Engine:** Tries Docker first, falls back to Podman; configurable via `CROSS_CONTAINER_ENGINE` env var

### Fit for nobotrs
**Good for local development & CI builds.** Use `cross build --target aarch64-unknown-linux-gnu` etc. to build binaries locally without setting up ARM toolchains. Less critical if using `cargo-dist` (which handles this automatically).

### 4b. `cargo-dist`

**Link:** https://github.com/axodotdev/cargo-dist  
**Docs:** https://axodotdev.github.io/cargo-dist/  
**Crates.io:** https://crates.io/crates/cargo-dist

- **Latest Version:** 0.32.0 (released May 21, 2026)
- **License:** MIT OR Apache-2.0 (dual)
- **Maintenance:** Active; maintained by Axiom (axodotdev)
- **What it does:**
  - Unified release orchestration: plan builds, build binaries for multiple targets, create installers, publish to GitHub Releases, publish to Homebrew/crates.io, announce
  - Generates GitHub Actions workflow (release.yml) for fully automated CI/CD
  - Supports "build and host" separation: build on CI (GitHub Actions), host artifacts on GitHub Releases

### Key Features for nobotrs
1. **Multi-target Builds:** Automatically cross-compiles to Linux (x86_64, aarch64, armv7), macOS (x86_64, aarch64), Windows (x86_64, aarch64) with Docker-based toolchains (using cargo-zigbuild for Linux, cargo-xwin for Windows)
2. **Homebrew Tap Publishing:** Generates Homebrew formula automatically and publishes to a tap repository on push-to-tag. Translates Cargo.toml `license` field (SPDX) to Homebrew's Ruby syntax.
3. **GitHub Releases:** Uploads tarballs and Windows MSI installers to GitHub Releases automatically
4. **Install Script:** Provides shell (`curl | sh`) and PowerShell installers for one-liner install
5. **Installer Formats:** Tarballs, .msi (Windows), Homebrew formula, crates.io (for `cargo install`)
6. **Auditable Binaries:** Supports `cargo-auditable` for recording dependencies in binaries (can now combine with cross-compilation via cargo-zigbuild)

### Setup
```bash
cargo dist init  # Generates Cargo.toml config + .github/workflows/release.yml
git tag v0.1.0
git push --tags  # Triggers automatic release.yml workflow
```

### Recommendation for nobotrs
**Use `cargo-dist` for production releases.** It automates the entire pipeline:
- On tag push → GitHub Actions runs release.yml
- Builds binaries (via `cross` internally for cross-compilation)
- Publishes to GitHub Releases, Homebrew tap, crates.io
- Generates install scripts

For local testing/iteration, use `cross` directly or native `cargo build`.

---

## 5. Homebrew Distribution

**Approach with cargo-dist:** Automatic.

**Setup (one-time):**
1. Create a tap repository `kwhatcher/homebrew-nobotrs` on GitHub
2. Configure in `nobotrs/Cargo.toml`:
   ```toml
   [package.metadata.dist]
   homebrew-tap = "kwhatcher/homebrew-nobotrs"
   ```
3. On first tag, `cargo-dist` auto-generates a formula and opens a PR to the tap repo (or you configure GitHub Actions to auto-push)

**Result:** Users install with `brew install kwhatcher/nobotrs/nobotrs` or tap first: `brew tap kwhatcher/homebrew-nobotrs && brew install nobotrs`.

**Note:** Pre-releases don't publish to Homebrew by default; configure `publish-prereleases = true` in `dist` config if needed.

For details, see: [Homebrew tap automation guide](https://builtfast.dev/blog/automating-homebrew-tap-updates-with-github-actions/)

---

## 6. crates.io Publishing

**For Binary Crates:**

- `nobotrs` should have a `src/main.rs` (binary crate) and optionally `src/lib.rs` if a library API is useful
- Publishing is identical to libraries: `cargo publish` after `cargo login`
- Users install the binary via `cargo install nobotrs` (requires Rust + ~seconds to minutes compile time, unless they use `cargo-binstall`)
- Document in README whether the crate is binary-only or provides a library API

**Why this matters:**
- Binary crate on crates.io means developers can `cargo install nobotrs` easily
- Paired with pre-built binaries on GitHub Releases (via `cargo-dist`), non-Rust users can `curl | sh` or `brew install`
- Homebrew formula also offers an install path for end users

**Special Note:** crates.io does **not** host binaries directly; it only hosts source. That's why `cargo-dist` publishes binaries to GitHub Releases separately and generates a Homebrew tap (which downloads from GitHub Releases or builds from crates.io source).

---

## 7. Binary Size Optimization

### Problem
Heavy ML dependencies (ONNX Runtime, Candle, tch-rs) can significantly increase binary size. Even with `strip = true` and `opt-level = "z"`, unpruned ML libraries can add 50–200 MB.

### Standard Mitigations

**In `Cargo.toml` release profile:**
```toml
[profile.release]
strip = true              # Remove symbols (saves 3–8%)
opt-level = "z"           # Optimize for size (over "3")
lto = true                # Link-Time Optimization (better codegen)
codegen-units = 1         # Single codegen unit (slower build, better optimization)
```

**Alternative for smaller binaries (trade speed for size):**
```toml
[profile.release]
opt-level = "s"           # Moderate size optimization (faster than "z", still smaller than default)
```

### ML Framework Approach: Feature Flags

**Recommended:** Make heavy ML features optional via Cargo features:
```toml
[dependencies]
ort = { version = "...", optional = true, features = ["load-dynamic"] }
candle-core = { version = "...", optional = true }

[features]
default = []
ml-detection = ["ort", "candle-core"]
```

Then users or packagers can:
- `cargo install nobotrs` → lightweight CLI binary (regex/pattern-matching only, ~10–20 MB)
- `cargo install --features ml-detection nobotrs` → full ML binary (~100–150 MB, depending on runtime choice)
- Or use `cross` + `strip` for binary releases (always include ML by default in GitHub Releases; offer a "light" variant if needed)

### ONNX Runtime: `load-dynamic` Feature

The `ort` crate (ONNX Runtime Rust bindings) supports `load-dynamic`:
- **Static linking (default):** Binary includes ONNX Runtime libraries (~40–60 MB). Large, but fully portable.
- **Dynamic linking (`load-dynamic`):** Binary is small (~5–10 MB); loads shared library (.so, .dll, .dylib) at runtime. Requires distributing runtime alongside or user having it installed. **Not recommended for single-binary distribution.**

For a single-binary CLI shipped via Homebrew/GitHub Releases, static linking is standard practice.

### Candle Alternative
Candle (by Hugging Face) is lighter-weight than ONNX Runtime and specifically designed for smaller binaries and WebAssembly. If ML feature is small-to-medium model inference (not complex pipelines), Candle may be a better fit.

### Binary Size Reality (2026)
- Lightweight CLI (no ML, minimal deps): ~5–10 MB (stripped, release mode)
- With ONNX Runtime (static): ~100–150 MB
- With Candle (medium model): ~50–80 MB
- Strip + LTO + `opt-level = "z"`: Shaves 10–20% off the above

**Practical recommendation:** Ship both:
1. **`nobotrs-core`** (Homebrew, GitHub Releases, crates.io): lightweight, pattern/regex based, ~10 MB
2. **`nobotrs-ml`** (GitHub Releases "ML" variant or separate crate): full ML, ~120 MB, for users who need it

Or single binary with ML optional at compile time, and document:
```bash
# Lightweight (pattern-only)
cargo install nobotrs

# Full ML (larger download, compiled locally or pre-built)
cargo install --features ml-detection nobotrs
# or
brew install kwhatcher/nobotrs/nobotrs --with-ml  # if Homebrew supports it
```

---

## Recommended Stack for nobotrs

| Component | Tool | Rationale |
|-----------|------|-----------|
| **CLI Parsing** | `clap` 4.6.4 | Standard, excellent subcommand support, derive macros. |
| **Colored Output** | `owo-colors` 4.3.0 | Zero-alloc, no_std-compatible, respects NO_COLOR. |
| **JSON Output** | `serde_json` 1.0.151 | Ecosystem standard for serialization. |
| **Cross-Compilation (CI)** | `cargo-dist` 0.32.0 | Fully automated multi-target builds, Homebrew, GitHub Releases. |
| **Cross-Compilation (Local)** | `cross` 0.2.5 | Docker-based, zero-setup toolchains (optional, cargo-dist handles CI). |
| **Binary Optimization** | Cargo `[profile.release]` + feature flags | `strip`, `opt-level = "z"`, LTO, feature-gated ML deps. |
| **Distribution Channels** | GitHub Releases, Homebrew (auto via cargo-dist), crates.io | Progressive: cargo install → pre-built → system packages. |

---

## Implementation Notes

1. **Initialization:**
   ```bash
   cargo init --name nobotrs
   cargo add clap --features derive
   cargo add owo-colors
   cargo add serde serde_json
   cargo dist init  # Generates release.yml, dist config
   ```

2. **Subcommand Structure (clap):**
   ```rust
   #[derive(Parser)]
   #[command(name = "nobotrs")]
   struct Args {
       #[command(subcommand)]
       command: Command,
   }
   
   #[derive(Subcommand)]
   enum Command {
       Detect { file: String },
       Lint { file: String },
       Scan { dir: String },
   }
   ```

3. **Colored Output (owo-colors):**
   ```rust
   use owo_colors::OwoColorize;
   
   println!("{} (score: {})", "AI-generated".red().bold(), score);
   ```

4. **JSON Output (serde_json):**
   ```rust
   if args.format == "json" {
       println!("{}", serde_json::to_string_pretty(&result)?);
   } else {
       println!("{}", result.format_human_readable());
   }
   ```

5. **Feature-Gated ML:**
   ```rust
   #[cfg(feature = "ml-detection")]
   mod ml_classifier {
       // ONNX/Candle code here
   }
   ```

6. **Release Workflow:**
   - Tag: `git tag v0.1.0 && git push --tags`
   - GitHub Actions (release.yml) triggers, builds, publishes to GitHub Releases + Homebrew tap + crates.io

---

## Sources

- [clap on crates.io](https://crates.io/crates/clap)
- [clap documentation on docs.rs](https://docs.rs/clap/latest/clap/)
- [owo-colors on crates.io](https://crates.io/crates/owo-colors)
- [owo-colors documentation on docs.rs](https://docs.rs/owo-colors/latest/owo_colors/)
- [anstyle on crates.io](https://crates.io/crates/anstyle)
- [anstyle documentation on docs.rs](https://docs.rs/anstyle/latest/anstyle/)
- [Rust CLI recommendations: Managing colors](https://rust-cli-recommendations.sunshowers.io/managing-colors-in-rust.html)
- [serde_json on crates.io](https://crates.io/crates/serde_json)
- [serde_json documentation on docs.rs](https://docs.rs/serde_json/latest/serde_json/)
- [cross-rs/cross on GitHub](https://github.com/cross-rs/cross)
- [cross crate on crates.io](https://crates.io/crates/cross)
- [cargo-dist on GitHub](https://github.com/axodotdev/cargo-dist)
- [cargo-dist documentation](https://axodotdev.github.io/cargo-dist/)
- [cargo-dist on crates.io](https://crates.io/crates/cargo-dist)
- [Automating Homebrew Tap Updates with GitHub Actions](https://builtfast.dev/blog/automating-homebrew-tap-updates-with-github-actions/)
- [How to Distribute Rust CLI Tools](https://www.rustfaq.org/en/how-to-distribute-rust-cli-tools-cargo-install-homebrew-etc/)
- [Publishing on crates.io (Cargo Book)](https://doc.rust-lang.org/cargo/reference/publishing.html)
- [Packaging and Distributing a Rust Tool (Rust CLI Book)](https://rust-cli.github.io/book/tutorial/packaging.html)
- [Shrinking Rust Binary Output](https://shane-o.dev/articles/rust-binary-size)
- [How to Reduce Binary Size in Rust (Rust FAQ)](https://www.rustfaq.org/en/how-to-reduce-binary-size-in-rust/)
- [Binary Size Optimization (Rust Project Primer)](https://rustprojectprimer.com/building/size.html)
- [Rust for Data Engineers Part 7: ML Inference](https://blog.amsayed.dev/blog/rust-for-data-engineers-part-7)
- [Real-time ML Model Deployment with Rust and ONNX Runtime](https://calmops.com/programming/rust/real-time-ml-model-development-with-rust-and-onnx-runtime/)
- [Building Sentence Transformers in Rust (Dev Community)](https://dev.to/mayu2008/building-sentence-transformers-in-rust-a-practical-guide-with-burn-onnx-runtime-and-candle-281k)
- [colored crate on crates.io](https://crates.io/crates/colored)
- [cargo-binstall on crates.io](https://crates.io/crates/cargo-binstall)
- [cargo-binstall GitHub releases](https://github.com/cargo-bins/cargo-binstall/releases)
