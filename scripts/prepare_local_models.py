#!/usr/bin/env python3
"""Stage pinned local model artifacts and regenerate native parity fixtures.

This helper never downloads weights. It resolves the exact revisions from the
embedded manifests against an existing Hugging Face cache, verifies source
digests, derives the ConPara tensor-only safetensors artifact and fast
tokenizer, and stages the DetectorScope Hub layout. Model weights stay external
and are not redistributed by the repository.

Examples:
  python scripts/prepare_local_models.py stage --models-dir ~/.cache/nobotrs/models
  python scripts/prepare_local_models.py reference --models-dir ~/.cache/nobotrs/models \
      --output tests/fixtures/models/encoder-reference.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DESKLIB = ("desklib/ai-text-detector-v1.01", "5fdea974cd4287c61674951ec78803aa274e2fb7")
CONPARA = ("SES-Lab-OTH/deberta-conpara", "a5f896f20f14259cf8a966fa4ae2012bd8d80164")
BACKBONE = ("microsoft/deberta-v3-large", "64a8c8eab3e352a784c658aef62be1662607476f")
SCOPE = ("liamdugan/detector-scope", "9baaff9e2d1cdb79cafa90cdb27811b847e69dae")
CONPARA_RAW = "a0a4eaf8914471b76102703e9de25ab5e7d49a49e3d5b529036ef4f61e72ab7c"


def digest(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def check(path, expected):
    actual = digest(path)
    if actual != expected:
        raise SystemExit(f"digest mismatch: {path}: expected {expected}, got {actual}")


def snapshot(spec, cache, local_files_only):
    from huggingface_hub import snapshot_download
    return Path(snapshot_download(
        repo_id=spec[0], revision=spec[1], cache_dir=cache,
        local_files_only=local_files_only,
    ))


def source_revision(path):
    head = (path / ".git/HEAD").read_text().strip()
    if head.startswith("ref: "):
        ref = head.removeprefix("ref: ")
        candidate = path / ".git" / ref
        if candidate.exists():
            return candidate.read_text().strip()
        for line in (path / ".git/packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
        raise SystemExit(f"source reference not found: {path}: {ref}")
    return head


def manifest_artifacts():
    result = {}
    for path in sorted((ROOT / "models").glob("*.json")):
        if path.name == "conpara-unicode-v2.json":
            continue
        data = json.loads(path.read_text())
        entries = [(item["path"], item["sha256"]) for item in data.get("artifacts", [])]
        if data.get("tokenizer"):
            entries.append((data["tokenizer"]["file"], data["tokenizer"]["sha256"]))
        result[data["id"]] = entries
    return result


def _populate(staging, cache, link, scope_source, local_files_only):
    desktop = snapshot(DESKLIB, cache, local_files_only)
    conpara = snapshot(CONPARA, cache, local_files_only)
    backbone = snapshot(BACKBONE, cache, local_files_only)
    scope = snapshot(SCOPE, cache, local_files_only)

    def put(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        if link:
            target.symlink_to(source)
        else:
            shutil.copyfile(source, target)

    for name in ("model.safetensors", "tokenizer.json", "tokenizer_config.json",
                 "special_tokens_map.json", "spm.model", "config.json"):
        put(desktop / name, staging / "desklib" / name)
    check(staging / "desklib/model.safetensors",
          "c024a1704c65f5a4bffeda58745c58fc0ed67d6ca07b158b068a257238815265")
    check(staging / "desklib/config.json",
          "a9512ad54a256ca2e26bb16336cfcaa7c93d071a8667c659044003ef3973a9e2")

    check(conpara / "rawguard.pt", CONPARA_RAW)
    import numpy as np
    import torch
    from numpy._core.multiarray import _reconstruct
    from safetensors.torch import save_file
    from transformers import AutoTokenizer

    types = [np.ndarray, np.dtype,
             (_reconstruct, "numpy.core.multiarray._reconstruct")]
    types.extend(type(np.dtype(kind)) for kind in ("float64", "float32", "int64", "int32"))
    with torch.serialization.safe_globals(types):
        checkpoint = torch.load(conpara / "rawguard.pt", map_location="cpu", weights_only=True)
    state = {key: value.contiguous().to(torch.float32)
             for key, value in checkpoint["model_state_dict"].items()}
    target = staging / "conpara/model.safetensors"
    target.parent.mkdir(parents=True, exist_ok=True)
    save_file(state, target, metadata={"format": "pt"})
    check(target, "be997091698ff9ac5f204fe005554a17b87c7f51d3e291a1eed6471fc975d92f")
    tokenizer = AutoTokenizer.from_pretrained(str(backbone), local_files_only=True)
    tokenizer.save_pretrained(staging / "conpara")
    shutil.copyfile(backbone / "config.json", staging / "conpara/config.json")
    (staging / "conpara/checkpoint-meta.json").write_text(json.dumps({
        "threshold_margin": float(checkpoint["threshold_margin"]),
        "version": str(checkpoint.get("version")),
        "val_bal_acc": float(checkpoint.get("val_bal_acc")),
        "tpr1": float(checkpoint.get("tpr1")),
    }, indent=2) + "\n")

    for name in ("model.safetensors", "features.jsonl", "config.json"):
        put(scope / name, staging / "detectorscope" / name)
    for name in ("config.json", "generation_config.json", "tokenizer_config.json",
                 "special_tokens_map.json", "tokenizer.model", "tokenizer.json",
                 "model.safetensors.index.json", "model-00001-of-00003.safetensors",
                 "model-00002-of-00003.safetensors", "model-00003-of-00003.safetensors"):
        put(scope / "extractor" / name, staging / "detectorscope/extractor" / name)
    put(scope / "heads/logreg_tau0.85.safetensors",
        staging / "detectorscope/heads/logreg_tau0.85.safetensors")

    if scope_source is not None:
        revision = source_revision(scope_source)
        if revision != "52ecc87775154b35d4550911de22faad4fc68f40":
            raise SystemExit("DetectorScope source revision mismatch")
        target = staging / "detectorscope/source"
        target.mkdir(parents=True)
        # Archive the committed tree rather than copying a possibly dirty checkout.
        import io
        import subprocess
        import tarfile
        archive = subprocess.check_output(
            ["git", "-C", str(scope_source), "archive", "--format=tar", revision])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(target, filter="data")
        (target / ".git").mkdir(exist_ok=True)
        (target / ".git/HEAD").write_text(revision + "\n")

    for _, entries in manifest_artifacts().items():
        for path, expected in entries:
            check(staging / path, expected)


def stage(models, cache, link=True, scope_source=None, local_files_only=True):
    """Build a complete sibling version and activate it with one atomic rename."""
    import tempfile
    destination = models
    if destination.exists():
        raise SystemExit(
            f"{destination} already exists; choose a new --models-dir (immutable versions only)")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-",
                                    dir=destination.parent))
    try:
        _populate(staging, cache, link, scope_source, local_files_only)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"activated {destination}")


def reference(models, output, conpara_source):
    import numpy as np
    import torch
    from torch import nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

    texts = [
        "The cat sat on the mat. It was a quiet afternoon, and the garden needed "
        "watering before dinner. The neighbors were away for the weekend, so the "
        "street stayed still and the only sound came from the birds in the old oak tree.",
        ("Café — “quoted” ﬁ 中 zero\u200bwidth text. " * 12).strip(),
        "Test world. " * 800,
        "Too short.",
        "One two three four five six seven eight nine ten. " * 6,
        "One\n two\tthree   four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one.",
    ]
    cases = [{"id": f"case-{i}", "text": text} for i, text in enumerate(texts, start=1)]

    if source_revision(conpara_source) != "b6388ca8b95b75c057f5e6dfa3ee5b7c3f92eced":
        raise SystemExit("ConPara source revision mismatch")
    sys.path.insert(0, str(conpara_source / "src"))
    from conpara import NoFeat, normalise

    class Desklib(PreTrainedModel):
        def __init__(self, config):
            super().__init__(config)
            self.model = AutoModel.from_config(config)
            self.classifier = nn.Linear(config.hidden_size, 1)
            self.post_init()

    d_tok = AutoTokenizer.from_pretrained(str(models / "desklib"), local_files_only=True)
    config = AutoConfig.from_pretrained(str(models / "desklib"), local_files_only=True)
    d_model, loading = Desklib.from_pretrained(
        str(models / "desklib"), config=config, output_loading_info=True, local_files_only=True)
    if any(loading.values()):
        raise SystemExit(f"unexpected Desklib keys: {loading}")
    d_model.eval()
    c_tok = AutoTokenizer.from_pretrained(str(models / "conpara"), local_files_only=True)
    c_model = NoFeat(backbone=str(models / "conpara"), config_only=True)
    from safetensors.torch import load_file
    c_model.load_state_dict(load_file(models / "conpara/model.safetensors"), strict=True)
    c_model.eval()
    with torch.inference_mode():
        for case in cases:
            batch = d_tok([case["text"]], padding=True, truncation=True,
                          max_length=512, return_tensors="pt")
            hidden = d_model.model(**{k: v for k, v in batch.items()
                                      if k in ("input_ids", "attention_mask", "token_type_ids")
                                      }).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1)
            score = float(d_model.classifier((hidden * mask).sum(1) / mask.sum(1))[0, 0])
            case["desklib"] = {
                "score": score,
                "ids": batch["input_ids"][0].tolist(),
                "attention_mask": batch["attention_mask"][0].tolist(),
                "truncated": len(d_tok(case["text"], truncation=False)["input_ids"]) > 512,
            }
            normalized = normalise(case["text"])
            c_batch = c_tok([normalized], padding=True, truncation=True,
                            max_length=512, return_tensors="pt")
            c_batch.pop("token_type_ids", None)
            logits = c_model(c_batch["input_ids"], c_batch["attention_mask"]).float()
            case["conpara"] = {
                "score": float(logits[0, 1] - logits[0, 0]),
                "normalized": normalized,
                "ids": c_batch["input_ids"][0].tolist(),
                "attention_mask": c_batch["attention_mask"][0].tolist(),
                "truncated": len(c_tok(normalized, truncation=False)["input_ids"]) > 512,
            }
    payload = {
        "schema_version": "1.0.0",
        "purpose": "Native Candle/Python parity reference from the pinned revisions; synthetic text only.",
        "models": {"desklib": DESKLIB[1], "conpara": CONPARA[1],
                   "backbone": BACKBONE[1]},
        "tolerance": {"absolute_score": 1e-3, "exact_tokens": True},
        "cases": cases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("stage", "reference"))
    parser.add_argument("--models-dir", type=Path,
                        default=Path.home() / ".cache/nobotrs-local-ai/models")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "tests/fixtures/models/encoder-reference.json")
    parser.add_argument("--copy", action="store_true",
                        help="copy artifacts instead of symlinking them")
    parser.add_argument("--hf-cache", type=Path, default=None,
                        help="offline Hugging Face cache directory")
    parser.add_argument("--detectorscope-source", type=Path,
                        default=Path.home() / ".cache/nobotrs-local-ai/detectorscope/source",
                        help="pinned DetectorScope checkout to stage for the worker")
    parser.add_argument("--conpara-source", type=Path,
                        default=Path.home() / ".cache/nobotrs-local-ai/followup/conpara-src",
                        help="pinned ConPara source checkout used only for reference generation")
    args = parser.parse_args()
    if args.stage == "stage":
        stage(args.models_dir, args.hf_cache, link=not args.copy,
              scope_source=args.detectorscope_source)
    else:
        reference(args.models_dir, args.output, args.conpara_source)


if __name__ == "__main__":
    main()
