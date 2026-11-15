#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["lexicalrichness==0.5.1"]
# ///
"""Reproduce pinned MTLD values over explicit normalized token lists."""
import hashlib
import importlib.metadata
import inspect
import json
import math
from pathlib import Path

from lexicalrichness import LexicalRichness


def main():
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/mtld-reference.json"
    data = json.loads(fixture.read_text())
    reference = data["reference"]
    if importlib.metadata.version(reference["package"]) != reference["version"]:
        raise SystemExit("LexicalRichness version differs from the reference")
    source = inspect.getsource(LexicalRichness.mtld).encode()
    if hashlib.sha256(source).hexdigest() != reference["mtld_source_sha256"]:
        raise SystemExit("MTLD implementation differs from the pinned source")
    for case in data["cases"]:
        result = LexicalRichness(
            case["tokens"], preprocessor=None, tokenizer=None
        ).mtld(threshold=reference["threshold"])
        if not math.isclose(result, case["reference_mtld"], rel_tol=0, abs_tol=1e-12):
            raise SystemExit(f"{case['id']}: expected {case['reference_mtld']}, got {result}")
        print(f"{case['id']}: reference reproduced")


if __name__ == "__main__":
    main()
