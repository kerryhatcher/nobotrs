#!/usr/bin/env python3
"""Standard-library regressions for the evaluation protocol."""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    ProtocolError,
    claim_independent_access,
    corpus_content_sha256,
    decode_sample_bytes,
    metrics,
    read_sample_bytes,
    read_sample_texts,
    sha256_bytes,
    sweep_rows,
    validate_grouping,
    validate_manifest,
    load_retirement,
    validate_retirement,
    RETIREMENT_STATUS,
)

ROOT = Path(__file__).resolve().parents[1]


def sample(sample_id, text, *, split="development", label="human",
           source_group=None, near_group=None, license_name="MIT",
           provenance=None, content_hash=None):
    return {
        "id": sample_id,
        "file": f"{sample_id}.txt",
        "split": split,
        "source_group": source_group or sample_id,
        "label": label,
        "slice": "test",
        "provenance": provenance or {
            "source": "https://example.org/source",
            "retrieved": "2026-11-14",
        },
        "license": license_name,
        "content_sha256": content_hash or sha256_bytes(text.encode("utf-8")),
        "near_duplicate_group": near_group or sample_id,
    }


def manifest(samples, *, corpus_revision="corpus-v1", declared_content=None,
             threshold=0.8):
    value = {
        "schema_version": "1.0.0",
        "corpus_version": "test-corpus-v1",
        "corpus_revision": corpus_revision,
        "purpose": "Protocol regression fixture; not authorship evidence.",
        "near_duplicate_threshold": threshold,
        "samples": samples,
    }
    if declared_content is not None:
        value["corpus_content_sha256"] = declared_content
    return value


FORCED_SOURCE_IDS = [
    "e5e058ce-be2b-459d-af36-32532aaba5ff",
    "f95b107b-d176-4af5-90f7-4d0bb20caf93",
    "856d8972-9e3d-4544-babc-0fe16f21e04d",
    "fbc8a5ea-90fa-47b8-8fa7-73dd954f1524",
    "72c41b8d-0069-4886-b734-a4000ffca286",
]


def build_retired_corpus(root: Path) -> Path:
    """Build a minimal preflight-valid corpus with a retirement ledger."""
    corpus = root / "retired-corpus"
    samples_dir = corpus / "samples"
    samples_dir.mkdir(parents=True)
    samples = []
    for index, source_id in enumerate(FORCED_SOURCE_IDS):
        text = f"development sample {index} with enough words for validation."
        file_name = f"samples/dev-{index}.txt"
        (corpus / file_name).write_bytes(text.encode("utf-8"))
        samples.append({
            "id": f"dev-{index}",
            "file": file_name,
            "split": "development",
            "source_group": f"src-dev-{index}",
            "near_duplicate_group": f"nd-dev-{index}",
            "label": "human",
            "slice": "synthetic",
            "license": "MIT",
            "provenance": {
                "source": "https://example.org/source",
                "retrieved": "2026-11-14",
            },
            "content_sha256": sha256_bytes(text.encode("utf-8")),
            "source_id": source_id,
            "dimension_values": {"language_hint": "unknown"},
        })
    for split, sample_id, text in (
        ("validation", "val-0", "validation sample with enough words for checks."),
        ("independent-test", "ind-0", "independent sample with enough words for checks."),
    ):
        file_name = f"samples/{sample_id}.txt"
        (corpus / file_name).write_bytes(text.encode("utf-8"))
        samples.append({
            "id": sample_id,
            "file": file_name,
            "split": split,
            "source_group": f"src-{sample_id}",
            "near_duplicate_group": f"nd-{sample_id}",
            "label": "generated",
            "slice": "synthetic",
            "license": "MIT",
            "provenance": {
                "source": "https://example.org/source",
                "retrieved": "2026-11-14",
            },
            "content_sha256": sha256_bytes(text.encode("utf-8")),
            "source_id": f"00000000-0000-4000-8000-{0 if split == 'validation' else 1:012d}",
            "dimension_values": {"language_hint": "unknown"},
        })

    source = corpus / "source"
    responses = source / "responses"
    responses.mkdir(parents=True)
    response_bytes = b'{"rows":[]}\n'
    (responses / "response.json").write_bytes(response_bytes)
    acquisition = {
        "dataset": "liamdugan/raid",
        "revision": "865cac74188466cb0c3b7574a10204007b57a459",
        "upstream_license": "MIT (dataset card declaration)",
        "license_url": "https://example.org/license",
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "queries": [{
            "domain": "abstracts",
            "model": "human",
            "attack": "none",
            "upstream_split": "train",
            "revision": "865cac74188466cb0c3b7574a10204007b57a459",
            "url": "https://example.org/query",
            "file": "responses/response.json",
            "sha256": sha256_bytes(response_bytes),
            "rows": 0,
            "available": 0,
            "partial_view": True,
        }],
        "errors": [],
        "notes": "synthetic retirement fixture",
        "portable_snapshot": True,
        "original_acquisition_sha256": "a" * 64,
    }
    (source / "acquisition.json").write_text(
        json.dumps(acquisition, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (source / "dataset-card.md").write_text(
        "---\nlicense: mit\n---\nSynthetic card.\n", encoding="utf-8"
    )
    (source / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2024- Liam Dugan\n", encoding="utf-8"
    )
    provenance = {
        "dataset": "liamdugan/raid",
        "revision": "865cac74188466cb0c3b7574a10204007b57a459",
        "upstream_license": "MIT (dataset card declaration)",
        "license_url": "https://example.org/license",
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "upstream_retrieved": "2026-11-14",
        "upstream_retrieved_timezone": "America/New_York",
        "retrieved_override": False,
        "acquisition_sha256": sha256_bytes((source / "acquisition.json").read_bytes()),
        "upstream_acquisition_sha256": "a" * 64,
        "dataset_card_sha256": sha256_bytes((source / "dataset-card.md").read_bytes()),
        "license_sha256": sha256_bytes((source / "LICENSE").read_bytes()),
        "queries": acquisition["queries"],
        "errors": [],
        "notes": "synthetic retirement fixture",
        "reproduction": "synthetic",
    }
    (source / "PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    content_hash = corpus_content_sha256(samples)
    manifest_value = {
        "schema_version": "1.0.0",
        "corpus_version": "synthetic-retired-v1",
        "corpus_revision": "synthetic-retired-v1",
        "purpose": "Synthetic retirement guard regression; not authorship evidence.",
        "near_duplicate_threshold": 0.8,
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "retrieved_override": False,
        "language_policy": {
            "runtime_default": "unknown",
            "per_sample_overrides": False,
            "overrides_recorded": [],
        },
        "split_policy": {"forced_to_development": FORCED_SOURCE_IDS},
        "source_snapshot": {
            "path": "source",
            "acquisition_sha256": provenance["acquisition_sha256"],
            "upstream_acquisition_sha256": provenance["upstream_acquisition_sha256"],
            "dataset_card_sha256": provenance["dataset_card_sha256"],
            "license_sha256": provenance["license_sha256"],
            "provenance_sha256": sha256_bytes((source / "PROVENANCE.json").read_bytes()),
            "response_count": 1,
        },
        "curation_audit": "curation.json",
        "corpus_content_sha256": content_hash,
        "samples": samples,
    }
    manifest_path = corpus / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    audit = {
        "schema_version": "1.0.0",
        "corpus_version": "synthetic-retired-v1",
        "revision": "865cac74188466cb0c3b7574a10204007b57a459",
        "retrieved": "2026-11-14",
        "retrieved_timezone": "America/New_York",
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "corpus_content_sha256": content_hash,
        "claims": {
            "complete_raid_benchmark": False,
            "general_accuracy_certification": False,
            "independent_test_opened": False,
            "thresholds_or_defaults_changed": False,
        },
        "row_accounting": {"rejected": 0},
    }
    (corpus / "curation.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    independent_ids = sorted(
        sample["id"] for sample in samples if sample["split"] == "independent-test"
    )
    ledger = {
        "schema_version": "1.0.0",
        "retirement_id": "synthetic-retirement-v1",
        "status": RETIREMENT_STATUS,
        "corpus_version": "synthetic-retired-v1",
        "corpus_revision": "synthetic-retired-v1",
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "corpus_content_sha256": content_hash,
        "retired_split": "independent-test",
        "retired_sample_count": len(independent_ids),
        "retired_id_set_sha256": sha256_bytes(
            ("\n".join(independent_ids) + "\n").encode("utf-8")
        ),
        "retired_sample_ids": independent_ids,
        "disposition": {
            "not_independent_test": True,
            "preserve_original_manifest_splits_results": True,
        },
        "exposure": {"event": "synthetic git diff exposure"},
    }
    (corpus / "retirement.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value, name="manifest.json"):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def write_text(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def write_bytes(self, name, data):
        (self.root / name).write_bytes(data)

    def test_regression_manifest_remains_compatible(self):
        path = ROOT / "tests/fixtures/evaluation/manifest.json"
        value = json.loads(path.read_text())
        info = validate_manifest(value, path, split="regression")
        self.assertEqual(info.corpus_revision, "regression-2026-10-10-v1")
        texts = read_sample_texts(info.samples, path.parent)
        grouping = validate_grouping(info.samples, texts)
        self.assertEqual(grouping["source_groups"], 7)

    def test_placeholder_license_and_provenance_are_rejected(self):
        text = "A sufficiently long sample for protocol validation."
        bad_license = sample("a", text, license_name="unknown")
        with self.assertRaises(ProtocolError):
            validate_manifest(manifest([bad_license]), self.write(manifest([bad_license])),
                              split="development")
        bad_provenance = sample("a", text, provenance="unknown")
        with self.assertRaises(ProtocolError):
            validate_manifest(manifest([bad_provenance]),
                              self.write(manifest([bad_provenance])), split="development")
        bad_source = sample("a", text, provenance={
            "source": "unknown", "retrieved": "2026-11-14"})
        with self.assertRaises(ProtocolError):
            validate_manifest(manifest([bad_source]), self.write(manifest([bad_source])),
                              split="development")

    def test_split_label_and_file_types_are_validated(self):
        text = "A sufficiently long sample for protocol validation."
        for bad in (
            sample("a", text, split="test"),
            sample("a", text, label="maybe"),
        ):
            with self.assertRaises(ProtocolError):
                validate_manifest(manifest([bad]), self.write(manifest([bad])),
                                  split="development")
        bad_file = sample("a", text)
        bad_file["file"] = "../escape.txt"
        with self.assertRaises(ProtocolError):
            validate_manifest(manifest([bad_file]), self.write(manifest([bad_file])),
                              split="development")
        duplicate = [sample("a", text), sample("a", text)]
        with self.assertRaises(ProtocolError):
            validate_manifest(manifest(duplicate), self.write(manifest(duplicate)),
                              split="development")
        unknown = sample("a", text, label=None)
        path = self.write(manifest([unknown]))
        info = validate_manifest(json.loads(path.read_text()), path, split="development")
        self.assertIsNone(info.samples[0]["label"])

    def test_content_hash_and_corpus_identity_are_verified(self):
        text = "A sufficiently long sample for protocol validation."
        good = sample("a", text)
        self.write_text("a.txt", text)
        declared = corpus_content_sha256([good])
        path = self.write(manifest([good], declared_content=declared))
        info = validate_manifest(json.loads(path.read_text()), path, split="development")
        self.assertEqual(info.corpus_content_sha256, declared)
        read_sample_texts(info.samples, self.root)
        wrong = sample("a", text, content_hash="0" * 64)
        with self.assertRaises(ProtocolError):
            read_sample_texts([wrong], self.root)
        bad_declared = manifest([good], declared_content="1" * 64)
        with self.assertRaises(ProtocolError):
            validate_manifest(bad_declared, self.write(bad_declared), split="development")

    def test_content_hash_covers_exact_bytes_not_normalized_text(self):
        data = b"line one\r\nline two\r\n"
        self.write_bytes("a.txt", data)
        item = sample("a", data.decode("utf-8"), content_hash=sha256_bytes(data))
        contents = read_sample_bytes([item], self.root)
        self.assertEqual(contents["a"], data)
        texts = decode_sample_bytes(contents)
        self.assertIn("\r\n", texts["a"])
        self.write_bytes("a.txt", data.replace(b"\r\n", b"\n"))
        with self.assertRaises(ProtocolError):
            read_sample_bytes([item], self.root)

    def test_source_and_near_duplicate_groups_cannot_cross_splits(self):
        text = "A sufficiently long sample for protocol validation."
        left = sample("a", text, split="development", source_group="shared")
        right = sample("b", text, split="validation", source_group="shared")
        value = manifest([left, right])
        path = self.write(value)
        info = validate_manifest(value, path, split="development")
        with self.assertRaises(ProtocolError):
            validate_grouping(info.samples, None)
        left = sample("a", text, split="development", near_group="near")
        right = sample("b", text, split="validation", near_group="near")
        value = manifest([left, right])
        info = validate_manifest(value, self.write(value), split="development")
        with self.assertRaises(ProtocolError):
            validate_grouping(info.samples, None)

    def test_near_duplicate_text_cannot_cross_splits(self):
        left_text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        right_text = "alpha beta gamma delta epsilon zeta eta theta iota lambda"
        left = sample("a", left_text, split="development")
        right = sample("b", right_text, split="validation")
        value = manifest([left, right])
        info = validate_manifest(value, self.write(value), split="development")
        texts = {"a": left_text, "b": right_text}
        with self.assertRaises(ProtocolError):
            validate_grouping(info.samples, texts, threshold=0.5)

    def test_independent_manifest_requires_hashes_and_groups(self):
        text = "A sufficiently long sample for protocol validation."
        good = sample("a", text, split="independent-test")
        value = manifest([good], declared_content=corpus_content_sha256([good]))
        path = self.write(value)
        validate_manifest(value, path, split="independent-test",
                          require_content_hashes=True,
                          require_near_duplicate_groups=True)
        missing_hash = sample("a", text, split="independent-test")
        missing_hash.pop("content_sha256")
        value = manifest([missing_hash])
        with self.assertRaises(ProtocolError):
            validate_manifest(value, self.write(value), split="independent-test",
                              require_content_hashes=True)
        missing_group = sample("a", text, split="independent-test")
        missing_group.pop("near_duplicate_group")
        value = manifest([missing_group], declared_content=corpus_content_sha256([missing_group]))
        with self.assertRaises(ProtocolError):
            validate_manifest(value, self.write(value), split="independent-test",
                              require_near_duplicate_groups=True)

    def test_independent_access_is_one_shot_and_atomic(self):
        text = "A sufficiently long sample for protocol validation."
        item = sample("a", text, split="independent-test")
        value = manifest([item], declared_content=corpus_content_sha256([item]))
        manifest_path = self.write(value)
        info = validate_manifest(value, manifest_path, split="independent-test",
                                 require_content_hashes=True,
                                 require_near_duplicate_groups=True)
        config = self.write({"quorum": 2}, "config.json")
        criteria = self.write({"criteria_id": "release-v1",
                               "criteria_version": "1"}, "criteria.json")
        identity = {
            "schema_version": "1.0.0",
            "split": "independent-test",
            "corpus_revision": info.corpus_revision,
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "configuration_sha256": sha256_bytes(config.read_bytes()),
            "release_criteria_sha256": sha256_bytes(criteria.read_bytes()),
            "release_criteria_id": "release-v1",
        }
        record = self.write({"status": "frozen-unopened", **identity}, "access.json")
        updated = claim_independent_access(record, identity)
        self.assertEqual(updated["status"], "accessed")
        self.assertTrue(updated["access_id"])
        self.assertFalse((record.parent / (record.name + ".lock")).exists())
        self.assertFalse(list(record.parent.glob("access.json.*.tmp")))
        with self.assertRaises(ProtocolError):
            claim_independent_access(record, identity)

    def test_stale_and_locked_access_records_are_rejected(self):
        text = "A sufficiently long sample for protocol validation."
        item = sample("a", text, split="independent-test")
        value = manifest([item], declared_content=corpus_content_sha256([item]))
        info = validate_manifest(value, self.write(value), split="independent-test",
                                 require_content_hashes=True,
                                 require_near_duplicate_groups=True)
        identity = {
            "schema_version": "1.0.0",
            "split": "independent-test",
            "corpus_revision": info.corpus_revision,
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "configuration_sha256": "a" * 64,
            "release_criteria_sha256": "b" * 64,
            "release_criteria_id": "release-v1",
            "binary_sha256": "d" * 64,
        }
        stale = dict(identity)
        stale["manifest_sha256"] = "c" * 64
        record = self.write({"status": "frozen-unopened", **stale}, "stale.json")
        with self.assertRaises(ProtocolError):
            claim_independent_access(record, identity)
        stale_binary = dict(identity)
        stale_binary["binary_sha256"] = "e" * 64
        record = self.write(
            {"status": "frozen-unopened", **stale_binary}, "stale-binary.json"
        )
        with self.assertRaises(ProtocolError):
            claim_independent_access(record, identity)
        record = self.write({"status": "frozen-unopened", **identity}, "locked.json")
        (record.parent / (record.name + ".lock")).write_text("held")
        with self.assertRaises(ProtocolError):
            claim_independent_access(record, identity)

    def test_access_is_claimed_before_independent_text_is_read(self):
        text = "A sufficiently long sample for protocol validation."
        item = sample("a", text, split="independent-test")
        value = manifest([item], declared_content=corpus_content_sha256([item]))
        info = validate_manifest(value, self.write(value), split="independent-test",
                                 require_content_hashes=True,
                                 require_near_duplicate_groups=True)
        identity = {
            "schema_version": "1.0.0",
            "split": "independent-test",
            "corpus_revision": info.corpus_revision,
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "configuration_sha256": "a" * 64,
            "release_criteria_sha256": "b" * 64,
            "release_criteria_id": "release-v1",
            "binary_sha256": "d" * 64,
        }
        record = self.write({"status": "frozen-unopened", **identity}, "access.json")
        updated = claim_independent_access(record, identity)
        self.assertEqual(updated["status"], "accessed")
        with self.assertRaises(ProtocolError):
            read_sample_texts(info.samples, self.root)

    def test_metrics_confusion_abstention_and_failures(self):
        rows = [
            {"label": "generated", "complete": True, "verdict": "flagged"},
            {"label": "generated", "complete": True, "verdict": "clean"},
            {"label": "human", "complete": True, "verdict": "flagged"},
            {"label": "human", "complete": True, "verdict": "clean"},
            {"label": "human", "complete": True, "verdict": "inconclusive"},
            {"label": "generated", "complete": False, "verdict": "inconclusive"},
            {"label": None, "complete": True, "verdict": "flagged"},
        ]
        result = metrics(rows)
        self.assertEqual(result["labeled_count"], 6)
        self.assertEqual(result["covered_count"], 4)
        self.assertEqual(result["coverage"], 4 / 6)
        self.assertEqual(result["abstentions"], 1)
        self.assertEqual(result["operational_failures"], 1)
        self.assertEqual(result["confusion_matrix"], {"tp": 1, "fp": 1, "fn": 1, "tn": 1})
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["f1"], 0.5)
        self.assertEqual(result["false_positive_rate"], 0.5)
        low, high = result["false_positive_rate_wilson_95"]
        self.assertTrue(0.0 <= low < 0.5 < high <= 1.0)
        self.assertIn("independent rows",
                      result["false_positive_rate_wilson_95_assumption"])
        self.assertIn("clustered", result["false_positive_rate_wilson_95_assumption"])
        empty = metrics([])
        self.assertIsNone(empty["coverage"])
        self.assertIsNone(empty["precision"])
        self.assertEqual(empty["confusion_matrix"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0})

    def test_unknown_labels_are_reported_separately(self):
        rows = [
            {"label": "generated", "complete": True, "verdict": "flagged"},
            {"label": "human", "complete": True, "verdict": "clean"},
            {"label": None, "complete": True, "verdict": "flagged"},
            {"label": None, "complete": True, "verdict": "inconclusive"},
            {"label": None, "complete": False, "verdict": "inconclusive"},
        ]
        result = metrics(rows)
        self.assertEqual(result["sample_count"], 5)
        self.assertEqual(result["labeled_count"], 2)
        self.assertEqual(result["unknown_label_count"], 3)
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["unknown_label_coverage"], 1 / 3)
        self.assertEqual(result["unknown_label_abstentions"], 1)
        self.assertEqual(result["unknown_label_operational_failures"], 1)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)

    def test_evaluate_uses_verified_bytes_via_stdin(self):
        data = b"# sample\r\n\r\nexperts\r\nagree\r\n"
        self.write_bytes("sample.md", data)
        item = sample(
            "sample", data.decode("utf-8"), split="regression",
            label=None, content_hash=sha256_bytes(data),
        )
        item["file"] = "sample.md"
        value = manifest([item])
        manifest_path = self.write(value)
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['FAKE_CAPTURE']).write_bytes(sys.stdin.buffer.read())\n"
            "pathlib.Path(os.environ['FAKE_ARGS']).write_text('\\n'.join(sys.argv[1:]))\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake-0.1',"
            "'dictionary_version':'fake-dict','metric_contract':'fake-v1',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        capture = self.root / "capture.bin"
        args_file = self.root / "args.txt"
        output = self.root / "result.json"
        env = os.environ.copy()
        env["FAKE_CAPTURE"] = str(capture)
        env["FAKE_ARGS"] = str(args_file)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/evaluate.py"),
             "--binary", str(fake), "--manifest", str(manifest_path),
             "--output", str(output)],
            capture_output=True, text=True, env=env, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(capture.read_bytes(), data)
        args = args_file.read_text().splitlines()
        self.assertIn("detect", args)
        self.assertIn("-", args)
        self.assertIn("--markdown", args)
        self.assertNotIn("sample.md", " ".join(args))
        self.assertNotIn(str(self.root), " ".join(args))
        report = json.loads(output.read_text())
        self.assertEqual(report["engine_identity"]["binary_sha256"], sha256_bytes(fake.read_bytes()))

    def test_detector_runs_sanitize_nobotrs_environment_and_isolate_config(self):
        data = b"A sufficiently long sample for protocol validation.\n"
        self.write_bytes("env-sample.txt", data)
        item = sample(
            "env-sample", data.decode("utf-8"), split="regression",
            label=None, content_hash=sha256_bytes(data),
        )
        item["file"] = "env-sample.txt"
        manifest_path = self.write(manifest([item]), "env-manifest.json")
        config3 = self.write({"quorum": 3}, "config3.json")
        hostile_config = self.write({"quorum": 1}, "hostile-config.json")
        env_capture = self.root / "captured-env.json"
        config_capture = self.root / "captured-config.json"
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "config_path = pathlib.Path(args[args.index('--config') + 1])\n"
            "raw = config_path.read_bytes()\n"
            "config = json.loads(raw)\n"
            "pathlib.Path(os.environ['FAKE_ENV']).write_text(json.dumps({\n"
            "    key: value for key, value in os.environ.items()\n"
            "    if key.upper().startswith('NOBOTRS_')}, sort_keys=True))\n"
            "pathlib.Path(os.environ['FAKE_CONFIG']).write_bytes(raw)\n"
            "sys.stdin.buffer.read()\n"
            "quorum = int(os.environ.get('NOBOTRS_QUORUM', config.get('quorum', 2)))\n"
            "verdict = 'flagged' if quorum <= 2 else 'clean'\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake-0.1',\n"
            "    'dictionary_version':'fake-dict','metric_contract':'fake-v1',\n"
            "    'verdict':verdict,'complete':True,'families':[],'backends':[],\n"
            "    'settings':{'quorum':quorum}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        base_env = os.environ.copy()
        base_env["FAKE_ENV"] = str(env_capture)
        base_env["FAKE_CONFIG"] = str(config_capture)
        command = [
            sys.executable, str(ROOT / "scripts/evaluate.py"),
            "--binary", str(fake), "--manifest", str(manifest_path),
        ]

        baseline_path = self.root / "baseline.json"
        first = subprocess.run(
            command + ["--output", str(baseline_path), "--config", str(config3)],
            capture_output=True, text=True, env=base_env, check=False,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        baseline = json.loads(baseline_path.read_text())
        self.assertEqual(baseline["regression_results"][0]["verdict"], "clean")
        self.assertEqual(baseline["corpus_identity"]["configuration_sha256"],
                         sha256_bytes(config3.read_bytes()))
        self.assertEqual(baseline["effective_configuration"]["supplied_keys"],
                         ["quorum"])
        self.assertEqual(baseline["effective_configuration"]["settings"]["quorum"], 3)
        check_path = self.write(
            {"regression_results": baseline["regression_results"]}, "check.json"
        )

        hostile_env = base_env.copy()
        hostile_env["NOBOTRS_QUORUM"] = "1"
        hostile_env["NOBOTRS_CONFIG"] = str(hostile_config)
        hostile_output = self.root / "hostile.json"
        second = subprocess.run(
            command + [
                "--output", str(hostile_output), "--config", str(config3),
                "--check", str(check_path),
            ],
            capture_output=True, text=True, env=hostile_env, check=False,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(env_capture.read_text()), {})
        self.assertEqual(json.loads(config_capture.read_text())["quorum"], 3)
        hostile = json.loads(hostile_output.read_text())
        self.assertEqual(hostile["effective_configuration"]["settings"]["quorum"], 3)
        self.assertEqual(hostile["corpus_identity"]["configuration_sha256"],
                         sha256_bytes(config3.read_bytes()))
        self.assertIn("NOBOTRS_QUORUM",
                      hostile["effective_configuration"]["sanitized_nobotrs_variables"])
        self.assertIn("NOBOTRS_CONFIG",
                      hostile["effective_configuration"]["sanitized_nobotrs_variables"])

        default_output = self.root / "defaults.json"
        third = subprocess.run(
            command + ["--output", str(default_output)],
            capture_output=True, text=True, env=hostile_env, check=False,
        )
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual(json.loads(env_capture.read_text()), {})
        self.assertEqual(json.loads(config_capture.read_text()), {})
        defaults = json.loads(default_output.read_text())
        self.assertTrue(defaults["corpus_identity"]["configuration_source"].startswith(
            "synthesized empty config"
        ))
        self.assertEqual(defaults["corpus_identity"]["configuration_sha256"],
                         sha256_bytes(b"{}\n"))
        self.assertEqual(defaults["effective_configuration"]["supplied_keys"], [])
        self.assertEqual(defaults["effective_configuration"]["settings"]["quorum"], 2)

    def test_retirement_ledger_binds_manifest_and_ids(self):
        corpus = build_retired_corpus(self.root)
        manifest_path = corpus / "manifest.json"
        value = json.loads(manifest_path.read_text())
        info = validate_manifest(
            value, manifest_path, split="development",
            require_content_hashes=True, require_near_duplicate_groups=True,
        )
        ledger = load_retirement(corpus)
        retirement = validate_retirement(ledger, info)
        self.assertEqual(retirement["status"], RETIREMENT_STATUS)
        self.assertEqual(retirement["retired_split"], "independent-test")
        self.assertEqual(retirement["retired_sample_count"], 1)
        self.assertFalse(retirement["independent_test_allowed"])
        self.assertFalse(retirement["freeze_allowed"])

        stale_manifest = dict(ledger)
        stale_manifest["manifest_sha256"] = "0" * 64
        with self.assertRaises(ProtocolError):
            validate_retirement(stale_manifest, info)
        stale_ids = dict(ledger)
        stale_ids["retired_sample_ids"] = []
        with self.assertRaises(ProtocolError):
            validate_retirement(stale_ids, info)
        stale_status = dict(ledger)
        stale_status["status"] = "open"
        with self.assertRaises(ProtocolError):
            validate_retirement(stale_status, info)

    def test_retired_corpus_refuses_independent_before_sample_or_access_reads(self):
        corpus = build_retired_corpus(self.root)
        marker = self.root / "detector-ran"
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
            "sys.stdin.buffer.read()\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake',"
            "'dictionary_version':'fake','metric_contract':'fake',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],"
            "'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        config = self.write({"quorum": 2}, "ret-config.json")
        criteria = self.write(
            {"criteria_id": "retired-v1", "criteria_version": "1"},
            "ret-criteria.json",
        )
        record = self.root / "retired-access.json"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/evaluate.py"),
            "--binary", str(fake), "--manifest", str(corpus / "manifest.json"),
            "--output", str(self.root / "retired-independent.json"),
            "--split", "independent-test", "--config", str(config),
            "--release-criteria", str(criteria),
            "--release-access-record", str(record),
        ], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retired", result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(record.exists())
        self.assertFalse(record.with_name(record.name + ".lock").exists())

    def test_retired_corpus_allows_development_and_validation(self):
        corpus = build_retired_corpus(self.root)
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "sys.stdin.buffer.read()\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake',"
            "'dictionary_version':'fake','metric_contract':'fake',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],"
            "'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        config = self.write({"quorum": 2}, "ret-config.json")
        criteria = self.write(
            {"criteria_id": "retired-v1", "criteria_version": "1"},
            "ret-criteria.json",
        )
        for split in ("development", "validation"):
            output = self.root / f"retired-{split}.json"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/evaluate.py"),
                "--binary", str(fake),
                "--manifest", str(corpus / "manifest.json"),
                "--output", str(output), "--split", split,
                "--config", str(config), "--release-criteria", str(criteria),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report["split"], split)
            self.assertEqual(report["retirement"]["status"], RETIREMENT_STATUS)

    def test_retired_corpus_freeze_refused_without_record(self):
        corpus = build_retired_corpus(self.root)
        fake = self.root / "fake-nobotrs"
        fake.write_text("preflight only reads binary bytes\n", encoding="utf-8")
        config = self.write({"quorum": 2}, "ret-config.json")
        criteria = self.write(
            {"criteria_id": "retired-v1", "criteria_version": "1"},
            "ret-criteria.json",
        )
        record = self.root / "retired-freeze-access.json"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/raid_pilot_preflight.py"),
            "--corpus", str(corpus), "--config", str(config),
            "--release-criteria", str(criteria), "--binary", str(fake),
            "--output", str(self.root / "retired-freeze-preflight.json"),
            "--access-record-out", str(record), "--freeze",
        ], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retired", result.stderr)
        self.assertFalse(record.exists())
        self.assertFalse(record.with_name(record.name + ".lock").exists())

        preflight = self.root / "retired-preflight.json"
        allowed = subprocess.run([
            sys.executable, str(ROOT / "scripts/raid_pilot_preflight.py"),
            "--corpus", str(corpus), "--config", str(config),
            "--release-criteria", str(criteria), "--binary", str(fake),
            "--output", str(preflight),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        report = json.loads(preflight.read_text())
        self.assertEqual(report["status"], "preflight-passed-retired")
        self.assertEqual(report["retirement"]["status"], RETIREMENT_STATUS)
        self.assertEqual(report["independent_access"]["status"], "refused-retired")
        self.assertFalse(report["independent_access"]["access_record_written"])

    def test_development_run_does_not_open_held_out_text(self):
        dev_data = b"# development\n\nexperts\nagree\n"
        held_out_data = b"# held out\n\nthis file is intentionally absent\n"
        self.write_bytes("development.md", dev_data)
        dev = sample(
            "dev", dev_data.decode("utf-8"), split="development",
            label="human", content_hash=sha256_bytes(dev_data),
        )
        dev["file"] = "development.md"
        held_out = sample(
            "heldout", held_out_data.decode("utf-8"), split="independent-test",
            label=None, content_hash=sha256_bytes(held_out_data),
        )
        held_out["file"] = "heldout-missing.md"
        value = manifest(
            [dev, held_out], corpus_revision="mixed-v1",
            declared_content=corpus_content_sha256([dev, held_out]),
        )
        manifest_path = self.write(value, "mixed.json")
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['FAKE_CAPTURE']).write_bytes(sys.stdin.buffer.read())\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake-0.1',"
            "'dictionary_version':'fake-dict','metric_contract':'fake-v1',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        capture = self.root / "capture.bin"
        output = self.root / "result.json"
        env = os.environ.copy()
        env["FAKE_CAPTURE"] = str(capture)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/evaluate.py"),
             "--binary", str(fake), "--manifest", str(manifest_path),
             "--output", str(output), "--split", "development"],
            capture_output=True, text=True, env=env, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(capture.read_bytes(), dev_data)
        report = json.loads(output.read_text())
        verification = report["content_verification"]
        self.assertEqual(verification["verified_sample_ids"], ["dev"])
        self.assertEqual(verification["held_out_not_read"], ["heldout"])
        self.assertFalse(verification["independent_held_out_verified"])
        self.assertEqual(report["corpus_identity"]["corpus_content_sha256"],
                         value["corpus_content_sha256"])

    def test_evaluate_independent_claim_precedes_binary_and_is_one_shot(self):
        data = b"# independent\n\nexperts\nagree\n"
        self.write_bytes("independent.md", data)
        item = sample(
            "independent", data.decode("utf-8"), split="independent-test",
            label=None, content_hash=sha256_bytes(data),
        )
        item["file"] = "independent.md"
        value = manifest(
            [item], corpus_revision="independent-v1",
            declared_content=corpus_content_sha256([item]),
        )
        manifest_path = self.write(value, "independent.json")
        info = validate_manifest(
            value, manifest_path, split="independent-test",
            require_content_hashes=True, require_near_duplicate_groups=True,
        )
        config = self.write({"quorum": 2}, "config.json")
        criteria = self.write(
            {"criteria_id": "release-v1", "criteria_version": "1"}, "criteria.json"
        )
        fake = self.root / "fake-nobotrs"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['FAKE_CAPTURE']).write_bytes(sys.stdin.buffer.read())\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake-0.1',"
            "'dictionary_version':'fake-dict','metric_contract':'fake-v1',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        identity = {
            "schema_version": "1.0.0",
            "split": "independent-test",
            "corpus_revision": info.corpus_revision,
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "configuration_sha256": sha256_bytes(config.read_bytes()),
            "release_criteria_sha256": sha256_bytes(criteria.read_bytes()),
            "release_criteria_id": "release-v1",
            "binary_sha256": sha256_bytes(fake.read_bytes()),
        }
        record = self.write({"status": "frozen-unopened", **identity}, "access.json")
        capture = self.root / "capture.bin"
        output = self.root / "result.json"
        env = os.environ.copy()
        env["FAKE_CAPTURE"] = str(capture)
        command = [
            sys.executable, str(ROOT / "scripts/evaluate.py"),
            "--binary", str(fake), "--manifest", str(manifest_path),
            "--output", str(output), "--split", "independent-test",
            "--config", str(config), "--release-criteria", str(criteria),
            "--release-access-record", str(record),
        ]
        first = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(capture.read_bytes(), data)
        self.assertEqual(json.loads(record.read_text())["status"], "accessed")
        report = json.loads(output.read_text())
        self.assertTrue(report["corpus_identity"]["access_id"])
        second = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("not unopened", second.stderr)

    def test_sweep_quorum_recomputes_verdicts(self):
        rows = [
            {"families": [{"vote": "suspicious"}, {"vote": "strong"}]},
            {"families": [{"vote": "suspicious"}]},
            {"families": [{"vote": "suspicious"}, {"vote": "none"}]},
        ]
        self.assertEqual([row["verdict"] for row in sweep_rows(rows, 2)],
                         ["flagged", "inconclusive", "clean"])
        self.assertEqual([row["verdict"] for row in sweep_rows(rows, 1)],
                         ["flagged", "flagged", "flagged"])
        with self.assertRaises(ProtocolError):
            sweep_rows(rows, 0)
        with self.assertRaises(ProtocolError):
            sweep_rows(rows, 4)

    def test_corpus_content_hash_is_order_independent(self):
        text = "A sufficiently long sample for protocol validation."
        left = sample("a", text)
        right = sample("b", text + " More.")
        self.assertEqual(corpus_content_sha256([left, right]),
                         corpus_content_sha256([right, left]))


if __name__ == "__main__":
    unittest.main()
