#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["textstat==0.7.10", "pyphen==0.18.1", "nltk==3.10.4"]
# ///
"""Recheck external comparison values; never rewrite native expectations."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import nltk
import textstat


def main():
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/readability-reference.json"
    data = json.loads(fixture.read_text())
    reference = data["reference"]
    for package in ("textstat", "pyphen", "nltk"):
        actual = importlib.metadata.version(package)
        if actual != reference[package]:
            raise SystemExit(f"{package}: expected {reference[package]}, got {actual}")
    try:
        corpus = nltk.data.find("corpora/cmudict/cmudict")
    except LookupError:
        raise SystemExit("Install the reference corpus explicitly: "
                         "uv run --with nltk==3.10.4 python -m nltk.downloader cmudict") from None
    with corpus.open() as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != reference["cmudict_sha256"]:
        raise SystemExit("CMU dictionary differs from the pinned reference corpus")
    textstat.set_lang(reference["language"])
    for case in data["cases"]:
        text = case["sentence_group"] * case["repetitions"]
        actual = {
            "reference_words": textstat.lexicon_count(text, removepunct=True),
            "reference_sentences": textstat.sentence_count(text),
            "reference_syllables": textstat.syllable_count(text),
            "reference_grade": textstat.flesch_kincaid_grade(text),
        }
        for name, value in actual.items():
            if not math.isclose(value, case[name], rel_tol=0, abs_tol=1e-9):
                raise SystemExit(f"{case['id']} {name}: expected {case[name]}, got {value}")
        print(f"{case['id']}: reference reproduced")


if __name__ == "__main__":
    main()
