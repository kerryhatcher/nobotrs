#!/usr/bin/env python3
"""Synthetic regressions for the joint assessment-pilot curator."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import curate_assessment_pilot as curator  # noqa: E402
from evaluation_protocol import (  # noqa: E402
    ProtocolError,
    corpus_content_sha256,
    sha256_bytes,
    sha256_file,
    validate_grouping,
    validate_manifest,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
HC3_SOURCES = list(curator.HC3_SOURCES)
BASE = " ".join(f"word{i}" for i in range(60))
NEAR = " ".join(
    ("changed" if i == 30 else f"word{i}") for i in range(60)
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_hc3(root):
    cache = root / "hc3-cache"
    cache.mkdir()
    responses = []
    for source in HC3_SOURCES:
        records = []
        for question_id in range(6):
            human = BASE if source == "finance" and question_id == 3 else f"{source} human q{question_id} unique sentence."
            chatgpt = f"{source} generated q{question_id} sibling answer."
            records.append({
                "question": f"{source} question {question_id}",
                "human_answers": [human],
                "chatgpt_answers": [chatgpt],
            })
        payload = ("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n").encode("utf-8")
        file_name = f"{source}.jsonl"
        (cache / file_name).write_bytes(payload)
        responses.append({
            "source": source,
            "file": file_name,
            "sha256": sha256_bytes(payload),
            "rows": len(records),
            "url": f"https://example.org/{source}.jsonl",
            "selection": "synthetic",
        })
    card = b"---\nlicense: cc-by-sa-4.0\n---\nSynthetic HC3 card.\n"
    (cache / "dataset-card.md").write_bytes(card)
    acquisition = {
        "dataset": "Hello-SimpleAI/HC3",
        "revision": curator.HC3_REVISION,
        "declared_license": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "dataset_card_sha256": sha256_bytes(card),
        "responses": responses,
        "errors": [],
        "viewed_question_ids_force_development": [str(i) for i in range(15)],
    }
    write_json(cache / "acquisition.json", acquisition)
    return cache


def build_raid(root, overlap_source):
    cache = root / "raid-cache"
    cache.mkdir()
    rows_human = [
        {
            "id": "10000000-0000-4000-8000-000000000001",
            "source_id": overlap_source,
            "model": "human",
            "domain": "abstracts",
            "attack": "none",
            "generation": NEAR,
        },
        {
            "id": "10000000-0000-4000-8000-000000000002",
            "source_id": overlap_source,
            "model": "human",
            "domain": "abstracts",
            "attack": "none",
            "generation": "sibling human text that shares the excluded source group.",
        },
        {
            "id": "10000000-0000-4000-8000-000000000003",
            "source_id": "20000000-0000-4000-8000-000000000001",
            "model": "human",
            "domain": "abstracts",
            "attack": "none",
            "generation": "accepted human text in a fresh source group.",
        },
    ]
    rows_generated = [{
        "id": "10000000-0000-4000-8000-000000000004",
        "source_id": "30000000-0000-4000-8000-000000000001",
        "model": "gpt4",
        "domain": "books",
        "attack": "none",
        "generation": "accepted generated text in another fresh source group.",
    }]
    queries = []
    for name, domain, model, rows in (
        ("human.json", "abstracts", "human", rows_human),
        ("gpt4.json", "books", "gpt4", rows_generated),
    ):
        payload = {
            "rows": [
                {"row_idx": index, "row": row, "truncated_cells": []}
                for index, row in enumerate(rows)
            ]
        }
        data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (cache / name).write_bytes(data)
        queries.append({
            "domain": domain,
            "model": model,
            "attack": "none",
            "upstream_split": "train",
            "revision": curator.RAID_REVISION,
            "url": f"https://example.org/{name}",
            "file": name,
            "sha256": sha256_bytes(data),
            "rows": len(rows),
            "available": len(rows),
            "partial_view": True,
            "offset": 0,
            "length": len(rows),
        })
    card = b"---\nlicense: mit\n---\nSynthetic RAID card.\n"
    license_bytes = b"MIT License\n\nCopyright (c) 2024- Liam Dugan\n"
    (cache / "dataset-card.md").write_bytes(card)
    (cache / "LICENSE").write_bytes(license_bytes)
    acquisition = {
        "dataset": "liamdugan/raid",
        "revision": curator.RAID_REVISION,
        "upstream_license": "MIT (dataset card declaration)",
        "license_url": "https://example.org/raid",
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "queries": queries,
        "errors": [],
        "purpose": "synthetic fresh RAID fixture",
    }
    write_json(cache / "acquisition.json", acquisition)
    return cache


def build_old(root, overlap_source):
    old = root / "old-corpus"
    (old / "samples").mkdir(parents=True)
    text = "old retired sample text with enough words for hashing and grouping."
    (old / "samples" / "old-0.txt").write_text(text, encoding="utf-8")
    sample = {
        "id": "old-0",
        "file": "samples/old-0.txt",
        "split": "independent-test",
        "source_group": "old-source",
        "near_duplicate_group": "old-near",
        "label": "human",
        "slice": "synthetic",
        "license": "MIT",
        "provenance": {"source": "https://example.org/old", "retrieved": "2026-11-14"},
        "content_sha256": sha256_bytes(text.encode("utf-8")),
        "source_id": overlap_source,
        "dimension_values": {"language_hint": "unknown"},
    }
    manifest = {
        "schema_version": "1.0.0",
        "corpus_version": "synthetic-old-v1",
        "corpus_revision": "synthetic-old-v1",
        "purpose": "Synthetic retired old corpus for exclusion tests.",
        "near_duplicate_threshold": 0.8,
        "corpus_content_sha256": corpus_content_sha256([sample]),
        "samples": [sample],
    }
    write_json(old / "manifest.json", manifest)
    ids = ["old-0"]
    ledger = {
        "schema_version": "1.0.0",
        "retirement_id": "synthetic-old-retirement",
        "status": "retired-exposed-selection-data",
        "manifest_sha256": sha256_file(old / "manifest.json"),
        "corpus_content_sha256": manifest["corpus_content_sha256"],
        "retired_split": "independent-test",
        "retired_sample_count": 1,
        "retired_id_set_sha256": sha256_bytes(("\n".join(ids) + "\n").encode("utf-8")),
        "retired_sample_ids": ids,
        "disposition": {
            "not_independent_test": True,
            "preserve_original_manifest_splits_results": True,
        },
    }
    write_json(old / "retirement.json", ledger)
    return old


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.overlap_source = "40000000-0000-4000-8000-000000000001"
        self.hc3 = build_hc3(self.root)
        self.raid = build_raid(self.root, self.overlap_source)
        self.old = build_old(self.root, self.overlap_source)

    def tearDown(self):
        self.temp.cleanup()

    def curate(self, name="out"):
        out = self.root / name
        summary = curator.write_corpus(out, self.hc3, self.raid, self.old, "2026-11-14")
        return out, summary

    def load(self, path):
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

    def test_exclusion_propagates_siblings_and_cross_corpus_transitive_links(self):
        out, summary = self.curate()
        manifest = self.load(out / "manifest.json")
        audit = self.load(out / "curation.json")
        ids = {sample["id"] for sample in manifest["samples"]}
        self.assertNotIn("hc3-finance-q3-h0", ids)
        self.assertNotIn("hc3-finance-q3-g0", ids)
        self.assertNotIn("raid-10000000-0000-4000-8000-000000000001", ids)
        self.assertNotIn("raid-10000000-0000-4000-8000-000000000002", ids)
        self.assertIn("raid-10000000-0000-4000-8000-000000000003", ids)
        counts = audit["old_corpus_exclusions"]["excluded_counts"]
        self.assertEqual(counts.get("old_raid_v1_source_id_overlap"), 2)
        self.assertEqual(counts.get("transitive_old_overlap"), 2)
        self.assertGreaterEqual(
            audit["old_corpus_exclusions"]["excluded_component_count"], 1
        )
        self.assertTrue(any(
            component.get("cross_corpus")
            for component in audit["old_corpus_exclusions"]["excluded_components"]
        ))
        # All answers in a question group share one split.
        groups = {}
        for sample in manifest["samples"]:
            if sample.get("corpus_source") == "hc3":
                groups.setdefault(sample["base_group"], set()).add(sample["split"])
        for splits in groups.values():
            self.assertEqual(len(splits), 1)
        # Viewed question IDs are development.
        for sample in manifest["samples"]:
            if sample.get("corpus_source") == "hc3" and sample["question_id"] <= 14:
                self.assertEqual(sample["split"], "development")

    def test_old_corpus_binding_and_content_hashes_are_verified(self):
        stale = self.root / "old-stale"
        shutil.copytree(self.old, stale)
        ledger = self.load(stale / "retirement.json")
        ledger["status"] = "open"
        write_json(stale / "retirement.json", ledger)
        with self.assertRaises((ProtocolError, curator.CurationError)):
            curator.load_old_exclusions(stale)

        stale2 = self.root / "old-stale-2"
        shutil.copytree(self.old, stale2)
        (stale2 / "samples" / "old-0.txt").write_text("tampered bytes", encoding="utf-8")
        with self.assertRaises((ProtocolError, curator.CurationError)):
            curator.load_old_exclusions(stale2)

    def test_integrity_and_replay(self):
        first, first_summary = self.curate("first")
        second, second_summary = self.curate("second")
        self.assertEqual((first / "manifest.json").read_bytes(),
                         (second / "manifest.json").read_bytes())
        self.assertEqual((first / "curation.json").read_bytes(),
                         (second / "curation.json").read_bytes())
        self.assertEqual(first_summary["corpus_content_sha256"],
                         second_summary["corpus_content_sha256"])
        manifest = self.load(first / "manifest.json")
        info = validate_manifest(manifest, first / "manifest.json",
                                 split="development", require_content_hashes=True,
                                 require_near_duplicate_groups=True)
        validate_grouping(info.samples, None)
        for sample in info.samples:
            data = (first / sample["file"]).read_bytes()
            self.assertEqual(sha256_bytes(data), sample["content_sha256"])
        for kind, snapshot in manifest["source_snapshots"].items():
            self.assertEqual(sha256_file(first / snapshot["path"] / "acquisition.json"),
                             snapshot["acquisition_sha256"])

    def test_occupied_output_is_refused_before_source_reads(self):
        out = self.root / "occupied"
        out.mkdir()
        marker = out / "unrelated.txt"
        marker.write_text("preserve me\n", encoding="utf-8")
        missing_hc3 = self.root / "missing-hc3"
        missing_raid = self.root / "missing-raid"
        with self.assertRaises(curator.CurationError) as raised:
            curator.write_corpus(out, missing_hc3, missing_raid, self.old, "2026-11-14")
        self.assertIn("fresh or empty", str(raised.exception))
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")

    def test_preflight_does_not_read_heldout_and_nested_gitattributes(self):
        out, _ = self.curate()
        config = self.root / "config.json"
        write_json(config, {"quorum": 2})
        criteria = self.root / "criteria.json"
        write_json(criteria, {"criteria_id": "synthetic", "criteria_version": "1"})
        binary = self.root / "fake-binary"
        binary.write_text("preflight only hashes bytes\n", encoding="utf-8")
        manifest = self.load(out / "manifest.json")
        independent = [sample for sample in manifest["samples"]
                       if sample["split"] == "independent-test"]
        self.assertTrue(independent)
        for sample in independent:
            (out / sample["file"]).unlink()
        preflight = self.root / "preflight.json"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/assessment_preflight.py"),
            "--corpus", str(out), "--config", str(config),
            "--release-criteria", str(criteria), "--binary", str(binary),
            "--output", str(preflight),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.load(preflight)
        self.assertEqual(report["status"], "assessment-preflight-passed")
        self.assertFalse(report["content_verification"]["independent_held_out_verified"])
        self.assertGreater(len(report["content_verification"]["held_out_not_read"]), 0)

        attrs = subprocess.run([
            "git", "check-attr", "text", "diff", "--",
            "evaluation/corpora/assessment-pilot-v1/source/hc3/responses/finance.jsonl",
            "evaluation/corpora/assessment-pilot-v1/source/raid-fresh/responses/books-gpt4-offset500.json",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(attrs.returncode, 0, attrs.stderr)
        self.assertIn("text: unset", attrs.stdout)
        self.assertIn("diff: unset", attrs.stdout)

        criteria_text = (ROOT / "evaluation/release-criteria/assessment-pilot-v1.json").read_text()
        self.assertIn("proposed", criteria_text)
        self.assertNotIn("frozen-unopened", criteria_text)


if __name__ == "__main__":
    unittest.main()
