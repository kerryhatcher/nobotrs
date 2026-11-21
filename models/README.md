# Local model manifests

These manifests pin the optional local evidence models. They contain revision,
digest, runtime, preprocessing, threshold, and license facts; they do not
redistribute weights. Artifacts are resolved under the configured models
directory (`--models-dir`, `NOBOTRS_MODELS_DIR`, or `models_dir` in config) as
`<models-dir>/<artifact path>`.

The default build has no model runtime. Build with `--features models-encoders`
for native Desklib/ConPara inference, `--features models-detectorscope` for the
optional DetectorScope worker, or `--features models` for both. Model requests
stay empty by default and never change the heuristic verdict or quorum.

The local staging helper used for validation is `scripts/prepare_local_models.py`.
It verifies upstream digests before writing derived artifacts. DetectorScope's
Hub bundle is Gemma-licensed; do not redistribute it without a separate review.
