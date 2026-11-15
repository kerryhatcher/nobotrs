#!/usr/bin/env python3
"""Recompute pinned burstiness/population-stdev vectors without rewriting them."""
import json
import math
import statistics
from pathlib import Path


def sentence_text(lengths):
    return " ".join(
        " ".join(["word"] * length) + "." for length in lengths
    )


def main():
    fixture_path = (
        Path(__file__).resolve().parents[1] / "tests/fixtures/burstiness-reference.json"
    )
    fixture = json.loads(fixture_path.read_text())
    tolerance = fixture["reference"]["comparison_tolerance"]
    for case in fixture["cases"]:
        cid = case["id"]
        lengths = case["sentence_lengths"]
        text = sentence_text(lengths)
        if len(text.split()) != case["expected_words"]:
            raise SystemExit(f"{cid}: generated word count differs")
        if len(lengths) != case["expected_sentences"]:
            raise SystemExit(f"{cid}: sentence count differs")
        mean = statistics.mean(lengths)
        deviation = statistics.pstdev(lengths)
        ratio = deviation / mean
        for name, actual, expected in (
            ("mean", mean, case["expected_mean"]),
            ("population_stdev", deviation, case["expected_population_stdev"]),
            ("cv", ratio, case["expected_cv"]),
        ):
            if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
                raise SystemExit(f"{cid} {name}: expected {expected}, got {actual}")
        print(f"{cid}: population-stdev/CV reference reproduced")


if __name__ == "__main__":
    main()
