#!/usr/bin/env python3
"""Regressions for editor alignment (Plan 5, Task 4)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import editor_alignment as ea  # noqa: E402


class ChangedSpanTests(unittest.TestCase):
    def test_whitespace_only_is_not_an_edit(self):
        before = "The  budget\tpassed.\n\nNext  item."
        after = "The budget passed. Next item."
        self.assertEqual(ea.changed_spans(before, after), [])

    def test_replaced_word_gives_its_byte_span(self):
        before = "Alpha beta gamma."
        after = "Alpha delta gamma."
        spans = ea.changed_spans(before, after)
        self.assertEqual([before.encode()[s:e].decode() for s, e in spans], ["beta"])

    def test_byte_offsets_survive_multibyte_text(self):
        before = "Smart quotes “work” and beta here."
        after = "Smart quotes “work” and delta here."
        (start, end), = ea.changed_spans(before, after)
        self.assertEqual(before.encode()[start:end].decode(), "beta")


class AlignmentTests(unittest.TestCase):
    def test_overlap_counts_once(self):
        findings = [{"start": 0, "end": 10}, {"start": 50, "end": 60}]
        spans = [(0, 4), (6, 9)]  # both spans overlap the first finding
        result = ea.alignment(findings, spans, text_len=100)
        self.assertEqual(result["edited_rate"], 0.5)

    def test_baseline_uses_matched_lengths(self):
        findings = [{"start": 0, "end": 5}]
        spans = [(20, 30)]  # one 10-byte edit
        import random
        drawn = ea.random_spans([10, 3], 100, random.Random(0))
        self.assertEqual([end - start for start, end in drawn], [10, 3])
        self.assertTrue(all(0 <= start and end <= 100 for start, end in drawn))
        result = ea.alignment(findings, spans, text_len=100, seed=0)
        self.assertEqual(result["changed_spans"], 1)
        self.assertGreaterEqual(result["baseline_rate"], 0.0)

    def test_aligned_lift_groups_variants(self):
        docs = [
            {"group": "p1", "findings": [{"start": 0, "end": 5}], "spans": [(0, 5)], "text_len": 50},
            {"group": "p1", "findings": [{"start": 40, "end": 45}], "spans": [(0, 5)], "text_len": 50},
            {"group": "p2", "findings": [{"start": 10, "end": 15}], "spans": [(10, 15)], "text_len": 50},
        ]
        result = ea.aligned_lift(docs)
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["docs"], 3)
        self.assertIsNotNone(result["lift"])



class RunBeemoTests(unittest.TestCase):
    def test_run_beemo_pairs_by_prompt_and_writes_aggregates_only(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            internal = Path(tmp)
            review = internal / "derived" / "review-batch" / "beemo"
            rules = internal / "derived" / "rule-lift"
            review.mkdir(parents=True)
            rules.mkdir(parents=True)
            ai_text = "The budget may rise. Gerund list, freezing pay, packing rooms."
            edit_text = "The budget may rise. Freezing pay, packing rooms."
            (review / "ai1.txt").write_text(ai_text, encoding="utf-8")
            (review / "ed1.txt").write_text(edit_text, encoding="utf-8")
            rows = [
                {"doc": "ai1", "group": "p1", "label": "ai", "genre": "u", "words": 9,
                 "row": 0, "column": "model_output", "rules": {"structure.gerund": 1},
                 "findings": [{"rule_id": "structure.gerund", "ranges": [[22, 40]]}]},
                {"doc": "ed1", "group": "p1", "label": "ai_edited_by_human", "genre": "u",
                 "words": 7, "row": 0, "column": "human_edits", "rules": {}, "findings": []},
            ]
            (rules / "beemo.rows.json").write_text(json.dumps(rows), encoding="utf-8")
            payload = ea.run_beemo(Path(tmp) / "out", internal)
            self.assertEqual(payload["paired"], 1)
            self.assertEqual(payload["skipped"], {})
            self.assertEqual(payload["rows"], 2)
            self.assertTrue((Path(tmp) / "out.json").exists())
            self.assertTrue((Path(tmp) / "out.md").exists())
            self.assertNotIn("budget", (Path(tmp) / "out.json").read_text())  # aggregates only



class RangeAndPairingTests(unittest.TestCase):
    def test_multi_range_finding_counts_when_any_range_overlaps(self):
        # One finding split over two lines; only its second range overlaps the edit.
        findings = [{"rule_id": "r", "ranges": [[0, 4], [50, 60]]}]
        self.assertEqual(ea._hit_share(findings, [(55, 58)]), 1.0)
        self.assertEqual(ea._hit_share(findings, [(10, 20)]), 0.0)

    def test_unlocated_findings_are_excluded_and_counted(self):
        findings = [{"rule_id": "r", "ranges": []}, {"rule_id": "r", "ranges": [[0, 3]]}]
        result = ea.alignment(findings, [(0, 3)], text_len=20)
        self.assertEqual(result["findings"], 1)
        self.assertEqual(result["unlocated"], 1)

    def test_byte_offsets_for_multibyte_before_span(self):
        text = "\u201cAlpha\u201d beta gamma"  # curly quotes are 3 bytes each
        after = "\u201cAlpha\u201d delta gamma"
        (start, end), = ea.changed_spans(text, after)
        self.assertEqual(text.encode()[start:end].decode(), "beta")
        self.assertEqual(start, len("\u201cAlpha\u201d ".encode()))

    def test_duplicate_row_column_refuses_to_overwrite(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            internal = Path(tmp)
            (internal / "derived" / "rule-lift").mkdir(parents=True)
            (internal / "derived" / "review-batch" / "beemo").mkdir(parents=True)
            rows = [{"doc": "a", "group": "p", "label": "ai", "row": 0, "column": "model_output",
                     "rules": {}, "findings": []},
                    {"doc": "b", "group": "p", "label": "ai", "row": 0, "column": "model_output",
                     "rules": {}, "findings": []}]
            (internal / "derived" / "rule-lift" / "beemo.rows.json").write_text(json.dumps(rows))
            with self.assertRaises(SystemExit):
                ea.run_beemo(internal / "out", internal)


if __name__ == "__main__":
    unittest.main()
