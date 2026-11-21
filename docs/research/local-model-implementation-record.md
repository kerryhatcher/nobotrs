# Local model integration implementation record

Date: 2026-11-20. Worktree: `local_ai`. Plan:
[local model integration](../superpowers/plans/2026-11-20-local-model-integration.md).
This record separates implementation evidence from the independent executable
validation record in [local-model-integration-validation.md](local-model-integration-validation.md).

## Contract and defaults

- Added stable IDs `desklib`, `conpara`, `detectorscope` and a dedicated
  `SignalFamily::Model`. The reducer now excludes that family explicitly, and a
  unit test forces a model score's `voting_eligible` flag true to prove it still
  contributes no vote.
- `Settings.models` defaults to empty; `models_dir` defaults to `None`. The
  established settings precedence is extended with `--models`, `NOBOTRS_MODELS`,
  `--models-dir`, and `NOBOTRS_MODELS_DIR`. An explicit empty `--models ""`
  clears a configured list.
- Default `enabled_backends`, quorum, verdict policy, findings, and exit codes
  are unchanged. Model backends are appended after the heuristic registry and
  never enter `families`.
- `nobotrs config` reports all three models with known/compiled/artifact/enabled
  status and `ready`, `not_compiled`, `artifacts_unavailable`,
  `runtime_unavailable`, or `unknown` availability. It runs before model
  resolution and never initializes a tokenizer, model, or Python worker.
- Missing feature support, missing models directory, or missing artifacts becomes
  a per-backend `Failed` outcome. Completed heuristic siblings stay in the report
  and the ordinary incomplete-run status 2 applies. Unknown IDs and duplicate
  requests fail settings validation.
- Empty input reaches model backends instead of the generic heuristic empty-prose
  abstention, producing typed `language_unknown`, `language_unsupported`, or
  `text_too_short` model abstentions.

## Manifests and artifacts

`models/*.json` pin upstream revisions, code revisions, tokenizer digests,
architecture/runtime, preprocessing revision, token limit, thresholds, and
separate weight/base/tokenizer/code license facts. DetectorScope records the
Gemma-licensed Hub bundle and Apache-2.0 source separately. DetectorScope's
manifest lists every consumed Hub file, including the head, top-level config,
extractor config/generation config/tokenizer files, index, three shards, and
feature table.

Artifacts remain external. `scripts/prepare_local_models.py`:

- resolves exact revisions from an explicitly supplied offline HF cache;
- verifies source and generated digests;
- derives the ConPara tensor-only safetensors file and fast tokenizer;
- stages the DetectorScope Hub layout and a `git archive` of the pinned source;
- verifies all manifest digests before activation; and
- activates a complete sibling directory with one atomic rename. Existing
  versions are immutable; staging uses `mkdtemp`, so no PID-named directory is
  deleted or reused.

Runtime loading verifies the bytes once and consumes those owned bytes. Native
encoders use `VarBuilder::from_buffered_safetensors`, not an unsafe mmap of a
file that could change after verification. The DetectorScope worker verifies
its declared artifacts once per backend instance, then starts the worker.

The Cargo package allowlists `models/*.json`, `models/README.md`, source/test
files, and integration source file types. A repo-local weights directory cannot
be packaged accidentally. Cargo `include`/`exclude` are not combined.

## Native encoders

Desklib and ConPara share Candle 0.8.4 DeBERTa-v3 inference on CPU float32:

- Desklib: masked-mean pooling followed by the checkpoint's single linear logit.
- ConPara: the pinned ordered Unicode v2 normalization and whitespace collapse,
  CLS pooling, `Linear(1024,512) -> GELU(erf) -> Linear(512,2)`, and the
  AI-minus-human logit margin. Only the ConPara input is normalized.

`tests/fixtures/models/encoder-reference.json` was generated from the pinned
Python revisions with token IDs, all-one masks, scores, clipping, Unicode,
whitespace, and short-input cases. A tokenizer-only unit test checks exact
retained IDs and masks without loading weights. The opt-in full parity test
checks scores at a predeclared `1e-3` tolerance and cutoff decisions.

Implementation-run parity on the same longer plain fixture:

| Model | Rust | Pinned Python | Absolute delta |
|---|---:|---:|---:|
| Desklib | 2.6289637089 | 2.6289741993 | 1.05e-5 |
| ConPara | 6.5882313251 | 6.5882310867 | 2.38e-7 |

Fixture bounds: case 3 is `"Test world. " * 800`, 2,402 full tokens, retained
512 IDs including `[CLS]`/`[SEP]`, all-one mask, and 21.24% retained character
coverage. Short input (5 words) abstains. The 26-word whitespace case scores and
preserves exact tokenization.

Independent optimized validation extended this to Unicode and more cases and
reported worst absolute score delta `6.92e-6`, identical cutoff decisions, and
512 tokens with about 21.24% retained coverage on the clipped input.

Runtime observations are named-host only. An optimized cold run of both encoders
took about 9.62 s with peak RSS about 5.32 GiB; warm short texts were about
0.53–0.87 s per model, and warm 512-token inputs about 6.85–9.50 s under shared
workstation load. Loading is lazy and reused across a scan. The cooperative
timeout does not preempt an in-flight Candle call; the documented setup uses an
explicit larger `--timeout-ms` for model runs.

## DetectorScope worker

The adapter uses the pinned Hub bundle, head `logreg`, `tau=0.85`, released
threshold `0.5008`, and a stable flat-whitespace formatting profile. The protocol
is newline-delimited JSON with a ready handshake, request IDs, bounded frames, a
bounded writer queue, and bounded response/handshake waits. Source revision,
model revision, code revision, head, tau, threshold, device, and dtype are
verified. Failures kill and reap the worker and clear the state so a later item
can restart.

Evidence includes raw logit, bias, full signed contribution sum validation,
residual, active/omitted feature counts, signed remainder, top positive and
negative features, and activation highlights. Python character offsets are
converted to UTF-8 byte offsets, mapped through the flat-whitespace map, then
through `Document::source_ranges`; unsafe mappings are omitted.

Implementation-run CPU float32 on the 50-word fixture:

- logit `0.5603123903`, bias `0.6096460819`;
- reconstruction residual `-5.916e-9`;
- 8 active features, top IDs `[13188, 33517, 1797, 42523, 30146, 20533, 39975, 39573]`;
- ordering and reconstruction passed, with highlights mapping to source bytes.

Independent CPU float32 and CUDA bfloat16 references matched the CLI logit and
ordered signed top feature IDs; the CUDA probe used the RTX 3060 and about 6.04
GiB peak allocation. The CUDA result is an independent validation result, not a
default policy change.

The tokenizer JSON carries its own truncation defaults, so the adapter measures
length on an explicitly unbounded clone. An implementation recheck on
`"Test world. " * 800` retained 1,024 tokens with `truncated=true` and 42.61%
character coverage, and the worker's reported token count was validated against
the bounded excerpt. The real CPU worker returned logit `3.4726026058`, bias
`0.6096460819`, residual `-1.74e-7`, 11 active features, and 2 omitted display
features. A model failure after preparation now retains a planned-excerpt object
in `Error::ModelFailure` with executed coverage reported as zero.

## ONNX/ort gate

An independent spike exported Desklib to ONNX (PyTorch 2.15.0, opset 18, onnx
1.23.2, onnxscript 0.7.2). ONNX Runtime 1.32 CPU dynamic shapes `[1,30]`,
`[2,35]`, and `[2,512]` matched PyTorch within `7.40e-6`. `ort` 2.0.0-rc.10
built on Rust 1.85 GNU/Linux and returned `0.16648975` against Python
`0.16649668`.

The packaging gate failed on `x86_64-unknown-linux-musl` because prebuilt ONNX
Runtime binaries are unavailable. Candle remains the supported path. This is a
packaging blocker, not a numerical failure.

## Remaining blockers

- No model installer, authenticity/signature service, or automatic download.
  Artifacts and the worker Python environment are external pending a packaging
  and redistribution review.
- DetectorScope remains a worker adapter. A native Rust Gemma/SAE extractor is a
  follow-on; none is claimed here.
- The release still uses one opening excerpt per model. Multi-window document
  aggregation was not added.
- No new opt-in voting profile. The model family cannot vote; correlated models
  remain one informational family.
- No fresh source-disjoint evaluation was collected for this change. GAO,
  learner-English, CoAuthor, Beemo, and APT-Eval remain explored controls from
  the research cache. The independent validation reproduced their report
  regeneration byte-for-byte from cached scores, but that is not fresh data.
- Default compatibility, feature-off behavior, report compatibility, scan order,
  and packaging are covered by tests; CUDA and full numerical parity remain
  opt-in, hardware-dependent checks.
