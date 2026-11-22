#!/usr/bin/env python3
"""Regressions for per-rule lift (Plan 5, Task 3)."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rule_lift as rl  # noqa: E402


def doc(group, label, words, rules, genre="civic"):
    return {"group": group, "label": label, "genre": genre, "words": words, "rules": rules}


class RuleLiftTests(unittest.TestCase):
    def test_bootstrap_keeps_groups_together(self):
        by_group = {"a": [doc("a", "ai", 100, {"r": 1}), doc("a", "ai", 100, {"r": 0})],
                    "b": [doc("b", "ai", 100, {"r": 2})]}
        rows = rl._resampled_rows(by_group, ["a", "a", "b"])
        groups = [r["group"] for r in rows]
        self.assertEqual(groups.count("a"), 4)  # two draws of group a, two rows each
        self.assertEqual(groups.count("b"), 1)
        rng = random.Random(0)
        for _ in range(50):
            drawn = rl._resample_groups(["a", "b"], rng)
            resampled = rl._resampled_rows(by_group, drawn)
            for group in ("a", "b"):
                self.assertEqual(sum(1 for r in resampled if r["group"] == group),
                                 drawn.count(group) * len(by_group[group]))

    def test_small_denominator_is_null(self):
        rows = [doc(f"d{i}", "human", 1200, {"r": 1}) for i in range(9)]  # 9 docs
        entry = rl.rates(rows, "human")["r"]
        self.assertIsNone(entry["per_10k"])
        self.assertIsNone(entry["ci"])
        self.assertIn("need 10", entry["null_reason"])
        few_words = [doc(f"d{i}", "human", 500, {"r": 1}) for i in range(10)]  # 5,000 words
        self.assertIsNone(rl.rates(few_words, "human")["r"]["per_10k"])

    def test_lift_math_on_hand_example(self):
        ai_rows = [doc(f"a{i}", "ai", 1000, {"r": 6 if i == 0 else 0}) for i in range(10)]
        human_rows = [doc(f"h{i}", "human", 1000, {"r": 2 if i == 0 else 0}) for i in range(10)]
        table = rl.compare(ai_rows + human_rows, "ai", "human")
        self.assertAlmostEqual(table["r"]["ai_per_10k"], 6.0)
        self.assertAlmostEqual(table["r"]["human_per_10k"], 2.0)
        self.assertAlmostEqual(table["r"]["lift"], 3.0)

    def test_lift_is_null_under_small_denominator(self):
        ai = rl.rates([doc("a", "ai", 500, {"r": 3})], "ai")["r"]
        human = {"per_10k": 2.0, "ci": None}
        self.assertIsNone(rl.lift(ai, human)["lift"])

    def test_weak_and_human_common_flags(self):
        entry = {"lift": 1.1, "ci": [0.8, 1.4], "ai_per_10k": 3.0, "human_per_10k": 3.4}
        self.assertEqual(rl.flags(entry), ["weak", "human-common"])

    def test_bootstrap_is_seeded(self):
        rows = [doc(f"d{i}", "ai", 1000, {"r": i % 3}) for i in range(12)]
        self.assertEqual(rl.rates(rows, "ai")["r"]["ci"], rl.rates(rows, "ai")["r"]["ci"])



class ZeroRateTests(unittest.TestCase):
    def test_zero_hits_in_adequate_group_is_zero_not_null(self):
        ai_rows = [doc(f"a{i}", "ai", 1000, {"r": 2}) for i in range(10)]
        human_rows = [doc(f"h{i}", "human", 1000, {}) for i in range(10)]  # never fires
        table = rl.compare(ai_rows + human_rows, "ai", "human")
        self.assertEqual(table["r"]["human_per_10k"], 0.0)
        self.assertIsNotNone(table["r"]["ai_per_10k"])
        self.assertIsNone(table["r"]["lift"])
        self.assertIn("zero", table["r"]["reason"])

    def test_small_denominator_gives_reason_not_silent_null(self):
        ai_rows = [doc(f"a{i}", "ai", 500, {"r": 1}) for i in range(3)]
        human_rows = [doc(f"h{i}", "human", 1000, {}) for i in range(10)]
        table = rl.compare(ai_rows + human_rows, "ai", "human")
        self.assertIsNone(table["r"]["ai_per_10k"])
        self.assertIsNone(table["r"]["lift"])
        self.assertIn("small denominator", table["r"]["reason"])

    def test_rule_absent_from_all_rows_is_not_reported(self):
        rows = [doc(f"a{i}", "ai", 1000, {}) for i in range(10)]
        self.assertEqual(rl.compare(rows, "ai", "human"), {})

if __name__ == "__main__":
    unittest.main()
