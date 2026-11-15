#!/usr/bin/env python3
"""Validate pinned compression/entropy vectors without rewriting expectations.

Entropy is recomputed independently from prepared prose with the Python standard
library. Pinned LZMA-Alone streams are decompressed with ``lzma.FORMAT_ALONE``
to prove the container and exact raw bytes. Native lzma-rs encoding bytes are
rechecked by the Rust reference test; this script does not claim compression
quality parity with Python's ``lzma.compress(..., preset=6)``.
"""
import hashlib
import json
import lzma
import math
import re
from collections import Counter
from pathlib import Path


def cargo_lock_package(lock: str, name: str):
    for block in lock.split("[[package]]")[1:]:
        if re.search(rf'^name = "{re.escape(name)}"$', block, re.MULTILINE):
            version = re.search(r'^version = "([^"]+)"$', block, re.MULTILINE)
            checksum = re.search(r'^checksum = "([^"]+)"$', block, re.MULTILINE)
            return (version.group(1) if version else None,
                    checksum.group(1) if checksum else None)
    raise SystemExit(f"crate {name} is absent from Cargo.lock")


def entropy(tokens):
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    return -math.fsum((count / total) * math.log2(count / total)
                      for count in counts.values())


def main():
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "tests/fixtures/compression-reference.json").read_text())
    reference = fixture["reference"]
    version, checksum = cargo_lock_package(
        (root / "Cargo.lock").read_text(), reference["crate"])
    if version != reference["version"]:
        raise SystemExit(f"lzma-rs version {version} != pinned {reference['version']}")
    if checksum != reference["crates_io_checksum"]:
        raise SystemExit("lzma-rs Cargo.lock checksum differs from the pinned reference")
    tolerance = reference["comparison_tolerance"]
    for case in fixture["cases"]:
        cid = case["id"]
        prose = (case["text"] + "\n").encode() if case["text"] else b""
        if len(prose) != case["expected_prose_bytes"]:
            raise SystemExit(f"{cid}: prose bytes differ")
        tokens = prose.decode().split()
        if len(tokens) != case["expected_tokens"]:
            raise SystemExit(f"{cid}: token count differs")
        actual_entropy = entropy(tokens)
        if not math.isclose(actual_entropy, case["expected_entropy"],
                            rel_tol=0, abs_tol=tolerance):
            raise SystemExit(
                f"{cid}: entropy {actual_entropy} != {case['expected_entropy']}")
        encoded_hex = case["lzma_alone_hex"]
        if encoded_hex is None:
            if prose or case["expected_compressed_bytes"] != 0:
                raise SystemExit(f"{cid}: only empty prose may omit the stream")
            if case["expected_lzma_sha256"] is not None:
                raise SystemExit(f"{cid}: empty prose must not pin a stream hash")
            if case["expected_lzma_ratio"] != 1.0:
                raise SystemExit(f"{cid}: empty helper ratio must remain the 1.0 sentinel")
            print(f"{cid}: empty sentinel and entropy reproduced")
            continue
        stream = bytes.fromhex(encoded_hex)
        if len(stream) != case["expected_compressed_bytes"]:
            raise SystemExit(f"{cid}: compressed length differs")
        if hashlib.sha256(stream).hexdigest() != case["expected_lzma_sha256"]:
            raise SystemExit(f"{cid}: compressed stream hash differs")
        if stream[:5] != b"\x5d\x00\x00\x80\x00" or stream[5:13] != b"\xff" * 8:
            raise SystemExit(f"{cid}: unexpected LZMA-Alone properties/header")
        try:
            decoded = lzma.decompress(stream, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError as error:
            raise SystemExit(f"{cid}: pinned stream does not decompress: {error}") from None
        if decoded != prose:
            raise SystemExit(f"{cid}: decompressed bytes differ from prepared prose")
        actual_ratio = len(stream) / len(prose)
        if not math.isclose(actual_ratio, case["expected_lzma_ratio"],
                            rel_tol=0, abs_tol=tolerance):
            raise SystemExit(
                f"{cid}: compressed/raw ratio {actual_ratio} != "
                f"{case['expected_lzma_ratio']}")
        print(f"{cid}: LZMA-Alone stream, ratio, and entropy reproduced")


if __name__ == "__main__":
    main()
