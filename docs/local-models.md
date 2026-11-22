# Optional local model evidence

`desklib`, `conpara`, and `detectorscope` are opt-in local evidence backends.
They are informational only: they contribute **zero** quorum votes and zero
eligible families. The heuristic verdict, quorum, findings, and defaults are
unchanged. The default model list is empty and the default Cargo build contains
no model runtime.

## Build

```sh
# Default small build: model requests fail closed with an actionable message.
cargo build --locked

# Native Desklib + ConPara DeBERTa-v3 inference (Candle, CPU float32).
cargo build --locked --features models-encoders

# Optional DetectorScope worker adapter only.
cargo build --locked --features models-detectorscope

# Both runtimes.
cargo build --locked --features models
```

The native encoder path uses Candle 0.8.4 and the Rust MSRV is 1.85.0. An
independent ONNX Runtime 2.0.0-rc.10 spike also produced the same Desklib logit
within `7.4e-6` on GNU/Linux, but its prebuilt runtime packaging is unavailable
for `x86_64-unknown-linux-musl`; Candle is therefore the supported path.

## Stage artifacts

Weights are not redistributed. Resolve the pinned revisions in `models/*.json`
from an existing offline Hugging Face cache and stage a complete version:

```sh
export NOBOTRS_MODELS_DIR="$HOME/.cache/nobotrs-local-ai/models-v1"
python scripts/prepare_local_models.py stage \
  --models-dir "$NOBOTRS_MODELS_DIR" \
  --hf-cache "$HOME/.cache/huggingface/hub" \
  --detectorscope-source "$HOME/.cache/nobotrs-local-ai/detectorscope/source"
```

The helper verifies source and generated digests, derives ConPara's
tensor-only safetensors artifact, packages its fast tokenizer, archives the
pinned DetectorScope checkout, and activates a complete directory with one
atomic rename. Existing versions are immutable; choose a new directory instead
of replacing one in place. Staged symlinks depend on their Hugging Face cache
entries. Use `--copy` for a version that survives cache eviction.

The staged layout is:

```text
<models-dir>/desklib/{model.safetensors,tokenizer.json,config.json,...}
<models-dir>/conpara/{model.safetensors,tokenizer.json,config.json,...}
<models-dir>/detectorscope/{model.safetensors,features.jsonl,config.json,extractor/,heads/,source/}
```

## Run

```sh
nobotrs analyze notes.md --models desklib,conpara --language en \
  --models-dir "$NOBOTRS_MODELS_DIR" --timeout-ms 120000 --format json
nobotrs analyze notes.md --models detectorscope --language en \
  --models-dir "$NOBOTRS_MODELS_DIR" --timeout-ms 120000 --format json
nobotrs scan docs/ --models desklib --language en \
  --models-dir "$NOBOTRS_MODELS_DIR" --timeout-ms 120000
```

`--models` also accepts `NOBOTRS_MODELS`, and `--models-dir` accepts
`NOBOTRS_MODELS_DIR` or `models_dir` in the JSON config. CLI values replace
environment and file values. An explicit empty `--models ""` clears a
configured model list. The setting precedence matches the other settings.

Model requests require an English assertion for the initial profiles
(`--language en`). Unknown or unsupported language applicability abstains with a
typed reason. The same applies below the profile's 25-word floor. A requested
model that is not compiled, has no models directory, or has missing artifacts
becomes a failed backend outcome; completed heuristic siblings stay in the
report and the run exits 2 under the existing incomplete-run contract. A bad
checksum or inference failure also fails closed. Model scores alone never
change findings, the verdict, or an otherwise-clean exit status.

The cooperative `--timeout-ms` budget still applies. Cold model loading is not
preemptible; the validated optimized cold run for both encoders was about 9.6
seconds and warm short-text scoring is sub-second to a few seconds per model.
Use a larger explicit timeout for model runs (for example `--timeout-ms 120000`)
rather than changing heuristic defaults. The DetectorScope worker is isolated
in a killable local subprocess, so its transactions can be bounded and recovered.

## Evidence and privacy

Each model result carries additive `model_evidence`: model and tokenizer
revisions, optional code revision, runtime/device/precision, raw output and
units, cutoff provenance, prepared and retained excerpt coverage, token limit,
truncation, planned vs executed coverage, elapsed time, and DetectorScope's
bias, signed contributions, residual, omitted count, and activation highlights.
Highlights are mapped byte-exactly back through the prepared prose and Markdown
source map; unsafe mappings are omitted. DetectorScope descriptions are model
interpretations, not factual topic labels. Model evidence is deliberately kept
out of SARIF rule findings for this release.

DetectorScope runs offline through a versioned newline-delimited JSON worker
(`integrations/model_workers/detectorscope_worker.py`, protocol
`nobotrs-detectorscope-v1`). It needs:

- `NOBOTRS_MODEL_PYTHON` (optional; defaults to `python3`) with the pinned
  research environment;
- `NOBOTRS_DETECTORSCOPE_SOURCE` (optional; defaults to
  `<models-dir>/detectorscope/source`) at the pinned commit;
- `NOBOTRS_DETECTORSCOPE_DEVICE` (`cpu` or `cuda`) and
  `NOBOTRS_DETECTORSCOPE_DTYPE` (`float32`, `bfloat16`, or `float16`).

No server port, cloud call, or automatic download occurs during scoring.
Handshake identity, source revision, request IDs, bounded frames, timeouts, and
crash recovery are checked. `config` reports runtime unavailable without
loading Python when a required source or explicit interpreter is missing.

## Config reporting

`nobotrs config` always succeeds for an unavailable enabled model and reports
known/compiled/artifact/enabled/availability status for all three IDs without
initializing tokenizers or inference. Availability strings are `ready`,
`not_compiled`, `artifacts_unavailable`, `runtime_unavailable`, or `unknown`.
Artifact presence is a cheap size/existence check; hashes are verified before a
model is loaded.

## Licensing and packaging blockers

- Desklib weights and tokenizer: upstream model card declares MIT; the base
  `microsoft/deberta-v3-large` terms apply separately.
- ConPara weights: upstream model card and pinned source LICENSE declare MIT;
  the base model and tokenizer terms apply separately.
- DetectorScope Hub bundle: marked Gemma-licensed; the pinned source checkout is
  Apache-2.0. Both are recorded separately in the manifest.
- Artifacts and the optional worker environment remain external pending a
  packaging and redistribution review. The Cargo package allowlists only
  `models/*.json`, `models/README.md`, and source/test files; it cannot
  accidentally package a repo-local weights directory.
- There is no model installer, signature/authenticity service, or automatic
  download. Installation is an explicit local staging step.

## Verification

`tests/fixtures/models/encoder-reference.json` pins token IDs, all-one masks,
raw scores, clipping, Unicode, whitespace, and short-input cases from the exact
Python revisions. The opt-in native check is:

```sh
NOBOTRS_MODEL_PARITY=1 NOBOTRS_MODELS_DIR="$NOBOTRS_MODELS_DIR" \
  cargo test --locked --features models-encoders --test model_parity
```

A tokenizer-only unit test checks exact retained IDs and masks without loading
model weights. With `NOBOTRS_MODELS_DIR` and `NOBOTRS_MODEL_PYTHON` set to the
staged artifacts and worker environment, run the DetectorScope parity check:

```sh
cargo test --locked --release --features models-detectorscope \
  --test detectorscope_parity -- --ignored
```

The test has reference values for CPU float32 and RTX 3060 CUDA bfloat16.
It checks signed contributions, Unicode source ranges, and the exact and
over-limit 1,024-token cases.

### Editorial diagnostics parity checkpoint (2026-11-21)

The public Bibb fixture now has an independently generated Python tokenizer reference (`scripts/dump_reference_tokens.py`, local Transformers loader). `detector_scope_tokens_and_offsets_match_reference` passes against the pinned Rust tokenizer: every ID and UTF-8 byte offset agrees. The loader still emits its generic Mistral-regex warning for this Gemma tokenizer; this checkpoint preserves the pinned tokenizer and does not enable a regex override. Agreement is runtime parity, not validation of the model or of suggested edits. Re-run the gate when tokenizer bytes, loader or normalization change.

### Opt-in section diagnostics

`--model-coverage full` (or `model_coverage: "full"`, `NOBOTRS_MODEL_COVERAGE=full`) retains the opening score and adds section-packed windows. Opening remains the default for detect/analyze. Review with selected models defaults to full; an explicit opening flag keeps excerpt-only analysis. Models never vote, and no new default runtime dependencies are introduced.

The packing policy is `section-packed-v1`, aggregation is `token-weighted-mean-v1`, and ranking is `within-doc-z-v1`. Units and paragraphs are packed without crossing a heading change; oversized units split at token boundaries. Every body token is planned once, special tokens count toward each window's model limit, and failed/timed-out/not-run windows leave explicit prose gaps. The aggregate exists only when every window succeeds. Per-window token counts describe body tokens; the worker also verifies the full input ID count including specials. Deadlines are cooperative: native inference cannot be preempted, but a call that finishes after the deadline receives no successful coverage credit.

Normalized model text and its navigation ranges are separate. ConPara maps table expansion, Unicode normalization and whitespace collapse to original prose. DetectorScope carries flat-whitespace offsets through to original UTF-8 source ranges and verifies window retokenization. Legacy statistical segmentation is unchanged.

Review labels diagnostics: “Where local classifiers react most. Not a Google signal and not evidence of authorship.” It excludes incomplete model runs and windows below 128 body tokens from ranking. Models need at least two nonconstant eligible window scores. The first contributing model supplies reference windows; other models align by maximum unit overlap with byte-overlap ties. Per-model ranks expose disagreement. Overlap alignment is an approximation when tokenizers split the same unit differently; it does not imply identical contexts.

`validated` remains false. Promotion requires a recorded blinded editor comparison against section heuristics at comparable review effort; authorship accuracy or edit overlap alone is insufficient. Feature associations require documented human review after tokenizer parity. The mapping currently has no reviewed entries; feature IDs and signed directions remain diagnostics with null guidance. Per-window contributions are never summed into editorial advice.

Survey feature presence locally with `scripts/survey_detectorscope_features.py --binary target/release/nobotrs --corpus owner-posts-v1 --models-dir "$NOBOTRS_MODELS_DIR" --out evaluation/reports/detectorscope-feature-survey.csv`. The script records counts, rates, undefined lift as empty, and hashed IDs only; it never writes excerpts or mappings. Unknown labels, medium-confidence samples, insufficient context and incomplete runs are visible exclusions. A limited run is a smoke check, not validation. Local-only corpora remain under `$NOBOTRS_INTERNAL_DIR`.

### Memory-bounded corpus measurements

The historical all-model owner attempt kept three sessions resident and was stopped during host memory pressure. Its first ten checkpoints and the DetectorScope deadline failure remain immutable. Use `--example owner_model_sweep` for recovery: one model per process, one registry reused within that sweep, verified owner input hashes, and only missing/incomplete scores re-executed. Existing successful or profile-skipped results are reused with source hashes. Every new backend/report/review attempt is retained separately.

`scripts/run_owner_model_sweeps.py` runs native sweeps sequentially, then DetectorScope. The recorded baseline keeps CPU float32 and full coverage, bounds runtime threads to two and retains the 20-minute per-document deadline. After a second pressure episode, initial memory gates require 8 GiB for a native model (observed group peak about 2.63 GiB plus at least 4 GiB available headroom), and a provisional 15 GiB for DetectorScope (previous worker RSS sample about 10.6 GiB plus the same headroom). The monitor records process VmHWM and group RSS so the DetectorScope gate can be refined from an actual single-model peak. The local PyTorch runtime reports no CUDA devices; these measurements retain CPU float32. It defers before launch when memory is unavailable. With nearly exhausted swap, each document needs at least 4 GiB available memory. The launcher also waits with no model resident until memory PSI full averages over 10 and 60 seconds are at most 2%, and one-minute load is at most twice the logical CPU count. Three consecutive readings below the active memory floor or above 10% full memory PSI terminate only the sweep's own process group; unrelated applications are never signalled. Incomplete attempts run after all untouched documents, and a pressure abort does not trigger an inference retry loop.

The legacy three-session driver now requires an explicit `--allow-multiple-models` flag for historical reproduction. Do not use it for ordinary corpus measurement on a busy workstation. The resource monitor, runtime thread settings and checkpoint provenance accompany the scores; no default CLI inference setting changes.

`scripts/consolidate_owner_model_sweeps.py` joins attempts into the existing owner baseline document layout, verifies source identities and retains original/recovered origins. Consolidated reports explicitly state that the three model scores came from sequential attempts. Joint hotspot ranks are not invented; per-model ranks remain in each immutable review attempt. Feature survey reuse reads DetectorScope's own windows from the consolidated report, excluding incomplete and insufficient-context observations.
