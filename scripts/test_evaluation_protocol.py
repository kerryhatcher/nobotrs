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
            "'verdict':'clean','complete':True,'families':[],'backends':[]}))\n",
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
            "'verdict':'clean','complete':True,'families':[],'backends':[]}))\n",
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
            "'verdict':'clean','complete':True,'families':[],'backends':[]}))\n",
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
