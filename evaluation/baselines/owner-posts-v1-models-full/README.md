# Owner model measurements: partial and deferred

The implementation and scoped engineering checks are complete. These corpus measurements are incomplete. The cold scheduler exhausted its bounded wait without allocating a model: the final sample recorded 1,496 MiB available, zero free swap, full-memory PSI averages of 95.83% (10 seconds), 96.45% (60 seconds), and 85.5% (300 seconds), and one-minute load about 1,003. The 1,800-second timer was observed at 2,005 seconds because the shared host stalled. No further model retry is active.

## Recorded coverage

The corpus has 43 owner-labelled documents. At least one model was attempted on 28; 15 remain untouched. Nine documents have all three model applicability outcomes resolved, including one short document skipped by every model. These are coverage counts, not editorial or authorship qualification.

| Model | Full scores | Skipped | Incomplete | Failed | Missing |
|---|---:|---:|---:|---:|---:|
| Desklib | 26 | 1 | 1 | 0 | 15 |
| ConPara | 9 | 1 | 0 | 0 | 33 |
| DetectorScope | 8 | 1 | 0 | 1 | 33 |

The Desklib incomplete result for `2025-04-01-gear-review-system76-pangolin-12-2.md` retains its valid opening output but has zero full-window token coverage: one timed-out window and five not run. The original DetectorScope failure on the CDN post returned a deadline error; kernel OOM records were not accessible, so no OOM cause is asserted. Interrupted documents without a completed result remain missing.

## Immutable sources and derived records

- The root `run.json` and ten document directories preserve the original three-session attempt, including its failure.
- `recovery/desklib/` retains each backend/report/review attempt, interrupted-run snapshots, input identities and measured memory records. Later attempts reused successful scores and the short-text skip.
- `deferred-scheduler-attempt-1.json` records the bounded cold wait and unmet resource conditions. It allocated no model while waiting.
- `consolidated/run.json` catalogues all source identities, original versus recovered origins, missing statuses and source hashes. Its `finished` field is false. Per-document reports are derived joins, explicitly identified as sequential attempts. They do not invent joint hotspot rankings.
- `consolidated/coverage-summary.json` distinguishes attempted, untouched and fully resolved documents. Missing-source placeholders are counted as missing, never as measured failures.

The owner AUROC command correctly rejected the unfinished population. AUROC and the feature survey were not computed on this selected partial population. The explicit status is in `evaluation/reports/owner-model-diagnostics-status.json`. Editorial utility remains unvalidated, and no DetectorScope feature association has been claimed as human reviewed.

## Resume when the shared host is quiet

All inference uses local pinned artifacts, CPU float32, full coverage, a 20-minute per-document cooperative deadline, and two runtime threads in recovery. Initial scores retain their original provenance. One model process runs at a time; a registry is reused within that sweep. No remote service is called.

```sh
CARGO_BUILD_JOBS=1 cargo build --locked --release --features models --example owner_model_sweep
python3 scripts/deferred_owner_model_measurements.py \
  --binary target/release/examples/owner_model_sweep \
  --models-dir "$NOBOTRS_MODELS_DIR" \
  --python "$NOBOTRS_MODEL_PYTHON" \
  --root evaluation/baselines/owner-posts-v1-models-full \
  --max-wait-seconds 1800 --quiet-seconds 300 --max-pressure-recoveries 3
```

The cold scheduler waits with no model allocated for five continuous minutes of low PSI/load and sufficient RAM. Recovery reuses completed results, processes untouched documents before retrying earlier incomplete attempts, and stops safely on renewed pressure. On completion it consolidates the records and runs the owner AUROC and feature survey commands. Read the resulting summaries before committing them; diagnostic accuracy does not satisfy the blinded editorial-utility gate.
