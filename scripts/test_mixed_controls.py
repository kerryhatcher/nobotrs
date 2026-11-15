#!/usr/bin/env python3
"""Synthetic regressions for development-only HC3 mixed controls."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import build_mixed_controls as builder  # noqa: E402
from evaluation_protocol import corpus_content_sha256, sha256_bytes, sha256_file  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
HC3_REV = "4d0ff18143b5a7e1b1e79beb540c04549d1e59d3"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_assessment(root):
    corpus = root / "assessment"
    (corpus / "samples").mkdir(parents=True)
    human_text = "human prefix answer with enough words for a development control."
    generated_text = "generated suffix answer with enough words for a development control."
    (corpus / "samples" / "h0.txt").write_text(human_text, encoding="utf-8")
    (corpus / "samples" / "g0.txt").write_text(generated_text, encoding="utf-8")
    samples = []
    for sample_id, role, text, label in (
        ("h0", "human", human_text, "human"),
        ("g0", "generated", generated_text, "generated"),
    ):
        samples.append({
            "id": sample_id,
            "file": f"samples/{sample_id}.txt",
            "split": "development",
            "slice": "corpus:hc3",
            "source_group": "hc3@rev:finance:q0",
            "near_duplicate_group": "nd-" + sample_id,
            "label": label,
            "license": "CC-BY-SA-4.0",
            "provenance": {"source": "https://example.org/hc3", "retrieved": "2026-11-14"},
            "content_sha256": sha256_bytes(text.encode("utf-8")),
            "corpus_source": "hc3",
            "base_group": "hc3@rev:finance:q0",
            "domain": "finance",
            "question_id": 0,
            "answer_index": 0,
            "dimension_values": {"language_hint": "unknown"},
        })
    # Metadata-only independent sample; its file is intentionally absent so any
    # attempt to read held-out content fails loudly.
    samples.append({
        "id": "heldout",
        "file": "samples/heldout.txt",
        "split": "independent-test",
        "slice": "corpus:hc3",
        "source_group": "hc3@rev:finance:q1",
        "near_duplicate_group": "nd-heldout",
        "label": "human",
        "license": "CC-BY-SA-4.0",
        "provenance": {"source": "https://example.org/hc3", "retrieved": "2026-11-14"},
        "content_sha256": "a" * 64,
        "corpus_source": "hc3",
        "base_group": "hc3@rev:finance:q1",
        "domain": "finance",
        "question_id": 1,
        "answer_index": 0,
        "dimension_values": {"language_hint": "unknown"},
    })
    (corpus / "source" / "hc3").mkdir(parents=True)
    (corpus / "source" / "hc3" / "acquisition.json").write_text("{\"portable_snapshot\":true}\n", encoding="utf-8")
    (corpus / "source" / "hc3" / "dataset-card.md").write_text(
        "---\nlicense: cc-by-sa-4.0\n---\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "1.0.0",
        "corpus_version": "synthetic-assessment",
        "corpus_revision": "synthetic-assessment",
        "purpose": "Synthetic assessment fixture for mixed controls.",
        "near_duplicate_threshold": 0.8,
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "source_snapshots": {"hc3": {
            "path": "source/hc3",
            "acquisition_sha256": sha256_file(corpus / "source/hc3/acquisition.json"),
            "dataset_card_sha256": sha256_file(corpus / "source/hc3/dataset-card.md"),
        }},
        "corpus_content_sha256": corpus_content_sha256(samples),
        "samples": samples,
    }
    write_json(corpus / "manifest.json", manifest)
    return corpus, human_text, generated_text


class MixedControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.assessment, self.human, self.generated = build_assessment(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_controls_are_development_only_null_label_and_exact(self):
        out = self.root / "controls"
        summary = builder.build(out, self.assessment)
        self.assertEqual(summary["samples"], 1)
        self.assertEqual(summary["splits"], {"development": 1})
        manifest = json.loads((out / "manifest.json").read_text())
        sample = manifest["samples"][0]
        self.assertIsNone(sample["label"])
        self.assertEqual(sample["split"], "development")
        self.assertEqual(sample["license"], "CC-BY-SA-4.0")
        text = (out / sample["file"]).read_bytes()
        self.assertEqual(text, self.human.encode() + b"\n\n" + self.generated.encode())
        provenance = sample["provenance"]["transformation"]
        self.assertEqual(provenance["human_sample_id"], "h0")
        self.assertEqual(provenance["generated_sample_id"], "g0")
        self.assertEqual(provenance["separator_hex"], "0a0a")
        self.assertFalse(provenance["held_out_used"])
        audit = json.loads((out / "curation.json").read_text())
        self.assertEqual(audit["selection"]["source_samples_read"], ["g0", "h0"])
        self.assertEqual(audit["selection"]["source_samples_outside_development_read"], [])
        self.assertFalse(audit["claims"]["detector_run"])
        self.assertIn("nonnative-speaker", json.dumps(audit["limitations"]))

    def test_controls_are_deterministic(self):
        first = self.root / "first"
        second = self.root / "second"
        builder.build(first, self.assessment)
        builder.build(second, self.assessment)
        for name in ("manifest.json", "curation.json", "summary.json"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_occupied_output_refused_before_source_reads(self):
        out = self.root / "occupied"
        out.mkdir()
        marker = out / "unrelated.txt"
        marker.write_text("preserve\n", encoding="utf-8")
        missing = self.root / "missing-assessment"
        with self.assertRaises(Exception) as raised:
            builder.build(out, missing)
        self.assertIn("fresh or empty", str(raised.exception))
        self.assertEqual(marker.read_text(), "preserve\n")

    def test_retired_assessment_is_refused(self):
        write_json(self.assessment / "retirement.json", {
            "schema_version": "1.0.0",
            "retirement_id": "synthetic-retired",
            "status": "retired-exposed-selection-data",
            "manifest_sha256": sha256_file(self.assessment / "manifest.json"),
            "corpus_content_sha256": json.loads((self.assessment / "manifest.json").read_text())["corpus_content_sha256"],
            "retired_split": "independent-test",
            "retired_sample_count": 1,
            "retired_id_set_sha256": sha256_bytes(b"heldout\n"),
            "retired_sample_ids": ["heldout"],
            "disposition": {"not_independent_test": True, "preserve_original_manifest_splits_results": True},
        })
        with self.assertRaises(Exception):
            builder.build(self.root / "controls-retired", self.assessment)


if __name__ == "__main__":
    unittest.main()
