# Local model integration validation

## Desklib ONNX and Rust binding spike

Exported the pinned Desklib encoder, attention-masked mean pooling, and
linear logit with `torch.onnx.export` using PyTorch 2.15.0, ONNX 1.23.2,
ONNX Script 0.7.2, and opset 18. The graph accepts dynamic batch and
sequence axes for both input IDs and masks. The export was about 4.7 MiB
plus 1.7 GiB of external tensor data.

ONNX Runtime 1.32.0 `CPUExecutionProvider` ran `(1, 30)`, `(2, 35)`, and
`(2, 512)` against the pinned PyTorch model. The maximum logit difference
was 0.00000740. A separate Rust 1.85 probe using `ort` 2.0.0-rc.10 on
`x86_64-unknown-linux-gnu` loaded the graph and returned `0.16648975`
for the singleton case, within 0.000007 of PyTorch. The same binding
failed to build with its default features for `x86_64-unknown-linux-musl`
because prebuilt ONNX Runtime binaries are unavailable for that target.
The integration uses the optional Candle backend, which passes the CPU
parity and package checks on GNU Linux without an ONNX Runtime library.
A Rust 1.85 all-feature check also passed for `x86_64-unknown-linux-musl`.
[PyTorch ONNX exporter](https://docs.pytorch.org/docs/2.15/onnx.html) · [ort 2.0.0-rc.10 crate metadata](https://docs.rs/crate/ort/2.0.0-rc.10/source/Cargo.toml)

## Independent encoder checks

An optimized CPU float32 build scored three synthetic plaintext inputs
offline and compared against the pinned Python research runners. Python used
a padded batch and Rust scored the inputs in one scan, in path order, with
loaded sessions reused. The pass required an absolute score difference below
0.001 and the same cutoff decision for each pair.

| Case | Desklib absolute logit difference | ConPara absolute margin difference |
|---|---:|---:|
| Plain English | 0.00000633 | 0.00000262 |
| English with a ligature and typographic punctuation | 0.00000691 | 0.00000572 |
| 800 repetitions of `Test world.` | 0.00000453 | 0.00000286 |

Both encoders retained 512 tokens and about 21.24% of the long input. The
observed cutoff decisions matched in all six comparisons. A separate
Markdown analysis returned the same heuristic verdict, family decisions,
and finding counts as the previous binary. With model settings at defaults,
the SARIF report also matched byte for byte.

The default release stayed below the 8 MB size gate and passed the existing
CLI, SARIF schema, and evaluation-regression checks. A Rust 1.85 offline
installation from the packaged crate succeeded with all model features.
Corrupting a staged Desklib file without changing its size produced a
checksum failure and exit code 2 while retaining the heuristic verdict.

On the RTX 3060 workstation, the CPU-only encoder build with release
optimization level 3 and LTO disabled scored both models cold on one short
Markdown file in 9.62 seconds with 5.07 GiB peak process RSS. The scan took
26.81 seconds for three files with 5.07 GiB peak RSS. Warm scoring took
0.53–0.87 seconds per model on the short case and 6.85–9.50 seconds per
model at 512 tokens. These timings are single observations on a shared host.

## Independent DetectorScope checks

On the Unicode fixture, the local CLI worker and a direct call to the pinned
upstream DetectorScope code matched by device and precision. Both returned
ten active features and displayed six of them. Bias plus the displayed
contributions and signed remainder reproduced the raw logit within 0.000001.
Every displayed highlight round-tripped through the reported source byte
ranges to the same UTF-8 text. Both runs used the released `logreg` head and
0.85 feature filter.

| Runtime | Raw logit | CLI scoring time |
|---|---:|---:|
| CPU float32 | 0.52474409 | 29.00 s |
| RTX 3060 CUDA bfloat16 | 0.52566290 | 16.32 s |

The two variants gave the same cutoff decision on this fixture and swapped
the order of the leading two negative contributions. The direct CUDA
reference recorded 6.04 GiB peak PyTorch device allocation. These are single
cold-start observations, including artifact checks and initialization.

An offline staging run verified the model artifacts and archived the pinned
DetectorScope source before activating a new directory. The CPU build loaded
all three backends from that directory. Injecting a worker exit or a 20-second
request timeout on the first item in a scan produced exit code 2, and the
restarted worker scored the next two items in order.

The opt-in DetectorScope regression passed on both device variants. An input
of exactly 1,024 tokens stayed untruncated. A 2,401-token input retained the
same 1,024-token prefix and the same logit, reported truncation, and recorded
about 42.61% retained coverage.

With CUDA devices hidden, the CLI reported the worker's bfloat16 startup
error and returned exit code 2. The JSON kept the planned excerpt and the
completed heuristic verdict, and the failure recorded zero execution coverage.

The pinned DetectorScope source reads the residual stream entering Gemma 2
layers 8, 14, 18, and 23. Candle 0.8.4's Gemma 2 public forward path returns
final-token logits, so a native extractor would need to expose those layer
inputs before applying the four JumpReLU encoders and masked max pooling.
Native hidden-state and SAE parity remains a follow-on gate. The pinned local
worker is the supported execution path.

## Research controls

The existing research runners regenerated the GAO wrapping, Write & Improve + LOCNESS, CoAuthor, Beemo, and APT-Eval comparison reports byte for byte from their saved score caches. The [experiment log](local-detection-work-log.md) records the sample selection, score cutoffs, and complete subgroup tables. To regenerate the summaries, stage the saved JSON and NumPy inputs in this layout and run from the repository root.

```sh
export NOBOTRS_EXPERIMENT_DIR="$HOME/.cache/nobotrs-local-ai"
export HF_HUB_OFFLINE=1 OPENBLAS_NUM_THREADS=1
analysis_dir=$(mktemp -d)
mkdir "$analysis_dir/controls" "$analysis_dir/editing"
for name in results.json desklib.npz followup; do
  ln -s "$NOBOTRS_EXPERIMENT_DIR/$name" "$analysis_dir/$name"
done
for suite in controls editing; do
  for file in "$NOBOTRS_EXPERIMENT_DIR/$suite/"*.json; do
    if [ "${file##*/}" != results.json ]; then
      ln -s "$file" "$analysis_dir/$suite/"
    fi
  done
done
experiment_python="$NOBOTRS_EXPERIMENT_DIR/venv/bin/python"
"$experiment_python" scripts/local_detection_controls.py analyze \
  "$analysis_dir" "$analysis_dir/controls"
"$experiment_python" scripts/local_detection_editing_experiment.py analyze \
  "$analysis_dir/editing"
for suite in controls editing; do
  cmp "$analysis_dir/$suite/results.json" \
    "$NOBOTRS_EXPERIMENT_DIR/$suite/results.json"
done
```

The blend ranked the model-containing CoAuthor window higher in 34 of 40 pairs and flagged 13 of 40 human-only windows at the inherited cutoff. Flattening GAO text added 78 DetectorScope flags across 106 excerpts. These results support keeping local scores advisory. Qualifying a voting profile requires a fresh source-disjoint evaluation with frozen preprocessing, cutoffs, and applicability rules.
