#!/usr/bin/env python3
"""Versioned local DetectorScope worker for nobotrs.

Protocol ``nobotrs-detectorscope-v1`` is newline-delimited JSON on stdin/stdout.
The first stdout line is a handshake. Diagnostics go to stderr. No network,
server port, or automatic download is used: the pinned checkout and Hub snapshot
must already exist under NOBOTRS_DETECTORSCOPE_SOURCE and NOBOTRS_MODELS_DIR.

Request:  {"id": 1, "text": "...", "head": "logreg", "tau": 0.85}
Response: {"id": 1, "ok": true, ...detection evidence...}
"""
import contextlib
import itertools
import json
import math
import os
from pathlib import Path
import sys

PROTOCOL = "nobotrs-detectorscope-v1"
MODEL_REVISION = "9baaff9e2d1cdb79cafa90cdb27811b847e69dae"
CODE_REVISION = "52ecc87775154b35d4550911de22faad4fc68f40"
MODEL = "liamdugan/detector-scope"
TAU = 0.85


def emit(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    sys.stdout.flush()


def main():
    source = Path(os.environ["NOBOTRS_DETECTORSCOPE_SOURCE"]).resolve()
    models = Path(os.environ["NOBOTRS_MODELS_DIR"]).resolve()
    sys.path.insert(0, os.fspath(source))
    import torch
    import transformers
    from detectorscope import AuditableDetector

    device = os.environ.get("NOBOTRS_DETECTORSCOPE_DEVICE", "cpu")
    dtype = os.environ.get("NOBOTRS_DETECTORSCOPE_DTYPE", "float32")
    if dtype == "bfloat16" and device == "cuda" and not torch.cuda.is_bf16_supported():
        raise ValueError("CUDA device does not support bfloat16")
    root = models / "detectorscope"
    # The Hub snapshot layout is fixed by the manifest; no network fallback.
    # Library/model-loading chatter must never contaminate the framed protocol.
    with contextlib.redirect_stdout(sys.stderr):
        detector = AuditableDetector.from_pretrained(os.fspath(root), torch_dtype=dtype).eval()
        head_obj = detector.load_head("logreg", TAU)
    if device == "cuda":
        detector = detector.to("cuda")
        torch.set_float32_matmul_precision("highest")
    else:
        torch.set_num_threads(int(os.environ.get("NOBOTRS_MODEL_THREADS", max(1, min(8, os.cpu_count() or 1)))))
    threshold = float(head_obj.threshold)
    emit({
        "type": "ready",
        "protocol": PROTOCOL,
        "model": MODEL,
        "model_revision": MODEL_REVISION,
        "code_revision": CODE_REVISION,
        "head": "logreg",
        "tau": TAU,
        "device": device,
        "dtype": dtype,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "threshold": threshold,
        "feature_filter": TAU,
    })
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = {}
        try:
            request = json.loads(line)
            request_id = int(request["id"])
            text = str(request["text"])
            if len(text) > 4_000_000:
                raise ValueError("request text exceeds 4 MB")
            with torch.inference_mode():
                result = detector(text, head="logreg", tau=TAU, return_highlights=True)
            if not math.isfinite(result.logit) or not math.isfinite(result.bias):
                raise ValueError("non-finite detector output")
            tokens = result.tokens or []
            # Recover exact offsets from the pinned extractor tokenizer.
            encoding = detector.extractor.tokenizer(
                text, max_length=1024, truncation=True, return_offsets_mapping=True,
            )
            # HF fast tokenizers report character offsets; Rust maps byte ranges.
            offsets = []
            for a, b in encoding["offset_mapping"]:
                a, b = int(a), int(b)
                offsets.append([
                    len(text[:a].encode("utf-8")),
                    len(text[:b].encode("utf-8")),
                ])
            if len(offsets) != len(tokens):
                raise ValueError("tokenizer offset/string mismatch")
            features = []
            selected = itertools.chain(
                itertools.islice((f for f in result.features if f.importance > 0), 5),
                itertools.islice((f for f in result.features if f.importance < 0), 5),
            )
            for feature in selected:
                strongest = sorted(feature.highlights or [], key=lambda pair: -pair[1])[:5]
                features.append({
                    "id": int(feature.id),
                    "description": feature.description or "",
                    "contribution": float(feature.importance),
                    "active_tokens": len(feature.highlights or []),
                    "highlight_limit": 5,
                    "highlights": [
                        {
                            "token_index": int(index),
                            "text": tokens[index],
                            "activation": float(value),
                            "start": offsets[index][0],
                            "end": offsets[index][1],
                        }
                        for index, value in strongest
                    ],
                })
            total = len(result.features)
            all_sum = sum(float(f.importance) for f in result.features)
            displayed_sum = sum(feature["contribution"] for feature in features)
            emit({
                "id": request_id,
                "ok": True,
                "logit": float(result.logit),
                "bias": float(result.bias),
                "threshold": threshold,
                "label": result.label,
                "reconstruction_residual": float(result.residual),
                "active_features": total,
                "omitted_features": max(0, total - len(features)),
                "all_contribution_sum": all_sum,
                "displayed_contribution_sum": displayed_sum,
                "remainder": float(result.logit) - float(result.bias) - displayed_sum,
                "tokens": len(tokens),
                "features": features,
            })
        except Exception as error:  # keep protocol alive for a typed request failure
            print(f"detectorscope worker request error: {error}", file=sys.stderr, flush=True)
            try:
                emit({"id": int(request.get("id", 0)), "ok": False, "error": str(error)})
            except Exception:
                pass
            # A model/protocol failure is not recoverable in-process.
            return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        print(f"detectorscope worker startup error: {error}", file=sys.stderr, flush=True)
        try:
            emit({"type": "error", "protocol": PROTOCOL, "error": str(error)})
        except Exception:
            pass
        raise SystemExit(1)
