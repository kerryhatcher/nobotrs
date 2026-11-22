#!/usr/bin/env python3
"""Regressions for hotspot validity (Plan 5, Task 6)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hotspot_validity as hv  # noqa: E402


class AurocTests(unittest.TestCase):
    def test_auroc_hand_example(self):
        # AI scores 0.9, 0.6; human scores 0.5, 0.2. Pairs won: 4 of 4 -> AUROC 1.0.
        self.assertEqual(hv.auroc([0.9, 0.6, 0.5, 0.2], [1, 1, 0, 0]), 1.0)
        # One AI score below one human score: 3 of 4 pairs won -> 0.75.
        self.assertEqual(hv.auroc([0.9, 0.4, 0.5, 0.2], [1, 1, 0, 0]), 0.75)

    def test_ties_count_half(self):
        self.assertEqual(hv.auroc([0.5, 0.5], [1, 0]), 0.5)

    def test_doc_auroc_has_ci_and_handles_missing(self):
        rows = [{"group": f"g{i}", "label": i % 2, "score": (i % 2) * 0.8 + 0.1 * (i % 3)}
                for i in range(12)]
        rows.append({"group": "gx", "label": 1, "score": None})
        result = hv.doc_auroc(rows, "score")
        self.assertEqual(result["documents"], 12)
        self.assertIsNotNone(result["ci"])
        self.assertLessEqual(result["ci"][0], result["auroc"] + 1e-9)


class EditorOverlapTests(unittest.TestCase):
    def test_editor_overlap_is_paired_within_document(self):
        docs = [
            {"group": "p1", "spans": [(0, 10)],
             "windows": [{"start": 0, "end": 10, "score": 0.9},   # top hits the edit
                         {"start": 50, "end": 60, "score": 0.1}]},
            {"group": "p2", "spans": [(40, 50)],
             "windows": [{"start": 0, "end": 10, "score": 0.9},   # top misses the edit
                         {"start": 40, "end": 50, "score": 0.1}]},
        ]
        result = hv.editor_overlap(docs)
        # top hit rate 0.5; other windows: doc1 0.0, doc2 1.0 -> mean 0.5 -> lift 1.0
        self.assertEqual(result["docs"], 2)
        self.assertAlmostEqual(result["lift"], 1.0)

    def test_single_window_documents_are_skipped(self):
        docs = [{"group": "p1", "spans": [(0, 5)],
                 "windows": [{"start": 0, "end": 5, "score": 0.9}]}]
        self.assertEqual(hv.editor_overlap(docs)["docs"], 0)


class DecisionTests(unittest.TestCase):
    def test_decide_requires_owner_confirmation(self):
        criteria = dict(hv.PROPOSED_CRITERIA, owner_confirmed=False)
        overlap = {"ci": [1.2, 1.8]}
        auroc = [{"ci": [0.7, 0.9]}]
        decision = hv.decide(auroc, overlap, criteria)
        self.assertFalse(decision["validated"])
        self.assertIn("owner has not confirmed the criteria", decision["reasons"])

    def test_proxy_evidence_cannot_promote_hotspots(self):
        criteria = dict(hv.PROPOSED_CRITERIA, owner_confirmed=True)
        decision = hv.decide([{"ci": [0.7, 0.9]}], {"ci": [1.2, 1.8]}, criteria)
        self.assertTrue(decision["diagnostic_thresholds_met"])
        self.assertFalse(decision["validated"])

    def test_cli_reports_empty_populations_as_unmeasured(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, report = Path(tmp) / "input.json", Path(tmp) / "report.json"
            source.write_text(json.dumps({"scores": {"example": {"full": []}},
                                          "editor_documents": []}))
            self.assertEqual(hv.main(["--input", str(source), "--out", str(report)]), 0)
            data = json.loads(report.read_text())
            self.assertIsNone(data["scores"]["example"]["full"]["auroc"])
            self.assertFalse(data["decision"]["validated"])


if __name__ == "__main__":
    unittest.main()
