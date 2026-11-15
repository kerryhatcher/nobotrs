#!/usr/bin/env python3
"""Regressions for metadata-only cluster-bootstrap evaluation summaries."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parents[1]

from evaluation_protocol import metrics  # noqa: E402


def row(sample_id, group, label, verdict, *, source="hc3", domain="finance",
        generator="human", complete=True, runtime=1.0):
    return {
        "id": sample_id,
        "source_group": group,
        "label": label,
        "verdict": verdict,
        "complete": complete,
        "status": 0,
        "runtime_seconds": runtime,
        "dimension_values": {
            "corpus_source": source,
            "domain": domain,
            "generator": generator,
        },
        "note": "ZZZSECRET",
    }


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.result = self.root / "result.json"
        rows = [
            row("a-h", "cluster-a", "human", "clean", generator="human", runtime=1.0),
            row("a-g", "cluster-a", "generated", "flagged", generator="chatgpt", runtime=1.2),
            row("b-h", "cluster-b", "human", "flagged", generator="human", runtime=0.8),
            row("b-g", "cluster-b", "generated", "clean", generator="chatgpt", runtime=0.9),
            row("c-h1", "cluster-c", "human", "clean", source="human-only", runtime=1.1),
            row("c-h2", "cluster-c", "human", "clean", source="human-only", runtime=1.1),
            row("u", "cluster-u", None, "inconclusive", generator="mixed", runtime=0.5),
        ]
        value = {
            "split": "development",
            "corpus_version": "synthetic-summary",
            "raw_feature_cache": rows,
            "corpus_identity": {
                "manifest_sha256": "a" * 64,
                "corpus_content_sha256": "b" * 64,
                "configuration_sha256": "c" * 64,
                "configuration_source": "explicit --config",
                "binary_sha256": "d" * 64,
            },
            "effective_configuration": {"settings_sha256": "e" * 64},
            "content_verification": {"held_out_not_read": ["heldout"]},
            "retirement": {"status": "not-retired"},
        }
        self.result.write_text(json.dumps(value), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_summary(self, name="summary.json", replicates=200):
        output = self.root / name
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/summarize_evaluation.py"),
            "--result", str(self.result), "--output", str(output),
            "--replicates", str(replicates),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output, json.loads(output.read_text())

    def test_cluster_bootstrap_slices_null_denominators_and_no_text(self):
        output, summary = self.run_summary()
        self.assertEqual(summary["overall"]["bootstrap"]["cluster_count"], 4)
        self.assertEqual(summary["overall"]["bootstrap"]["replicates"], 200)
        for name in ("precision", "recall", "f1", "false_positive_rate", "coverage"):
            value = summary["overall"]["bootstrap"]["metrics"][name]
            self.assertLessEqual(value["valid_replicates"], 200)
            self.assertIn("denominator", value)
        self.assertIsNone(summary["auc"])
        self.assertFalse(summary["detector_run"])
        self.assertFalse(summary["sample_text_included"])
        self.assertIn("source", summary["slices"])
        self.assertIn("domain", summary["slices"])
        self.assertIn("generator", summary["slices"])
        human_only = summary["slices"]["source"]["human-only"]["bootstrap"]["metrics"]
        self.assertIsNone(human_only["recall"]["estimate"])
        self.assertEqual(human_only["recall"]["valid_replicates"], 0)
        self.assertTrue(human_only["recall"]["degenerate"])
        self.assertIsNone(human_only["recall"]["lower"])
        self.assertIsNone(human_only["recall"]["upper"])
        self.assertIsNone(human_only["precision"]["estimate"])
        self.assertTrue(human_only["false_positive_rate"]["degenerate"])
        self.assertIsNone(human_only["false_positive_rate"]["lower"])
        self.assertIsNone(human_only["false_positive_rate"]["upper"])
        self.assertIn("no observed variation",
                      human_only["false_positive_rate"]["reason"].lower())
        self.assertNotIn("ZZZSECRET", output.read_text())
        self.assertIn("nonnative-speaker", json.dumps(summary["limitations"]))

    def test_nondefault_replicates_propagate_and_metrics_match_framework(self):
        output, summary = self.run_summary("nondefault.json", replicates=37)
        self.assertEqual(summary["method"]["replicates"], 37)
        self.assertEqual(summary["overall"]["bootstrap"]["replicates"], 37)
        for slice_name in ("source", "domain", "generator"):
            for value in summary["slices"][slice_name].values():
                self.assertEqual(value["bootstrap"]["replicates"], 37)
        cached = json.loads(self.result.read_text())["raw_feature_cache"]
        framework = metrics(cached)
        for key in ("confusion_matrix", "precision", "recall", "f1",
                    "false_positive_rate", "coverage", "abstentions",
                    "operational_failures"):
            self.assertEqual(summary["overall"]["metrics"][key], framework[key])

    def test_invalid_row_fields_are_rejected(self):
        for field, value in (
            ("verdict", "mystery"),
            ("label", "maybe"),
            ("complete", "yes"),
            ("runtime_seconds", -1),
            ("runtime_seconds", float("inf")),
        ):
            result = json.loads(self.result.read_text())
            result["raw_feature_cache"][0][field] = value
            self.result.write_text(json.dumps(result), encoding="utf-8")
            run = subprocess.run([
                sys.executable, str(ROOT / "scripts/summarize_evaluation.py"),
                "--result", str(self.result), "--output", str(self.root / "bad.json"),
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(run.returncode, 0, field)
            self.assertIn("row 0", run.stderr)

    def test_summary_is_deterministic(self):
        first, _ = self.run_summary("first.json")
        second, _ = self.run_summary("second.json")
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_source_group_is_rejected(self):
        value = json.loads(self.result.read_text())
        del value["raw_feature_cache"][0]["source_group"]
        self.result.write_text(json.dumps(value), encoding="utf-8")
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/summarize_evaluation.py"),
            "--result", str(self.result), "--output", str(self.root / "bad.json"),
        ], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_group", result.stderr)


if __name__ == "__main__":
    unittest.main()
