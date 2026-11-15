#!/usr/bin/env python3
"""Regressions for the pinned Python reference archive identity."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_python_reference import (  # noqa: E402
    COMMIT,
    EXPECTED_REFERENCE_SHA256,
    REFERENCE_FILES,
    reference_metadata,
)

REFERENCE = Path(f"/tmp/nobotrs-python-reference/{COMMIT}")


@unittest.skipUnless(REFERENCE.is_dir(), "verified Python reference archive is absent")
class ReferenceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / COMMIT
        for name in REFERENCE_FILES:
            source = REFERENCE / name
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def tearDown(self):
        self.temp.cleanup()

    def test_verified_archive_hashes_are_pinned(self):
        metadata = reference_metadata(self.root)
        self.assertEqual(metadata["commit"], COMMIT)
        self.assertEqual(metadata["file_sha256"], EXPECTED_REFERENCE_SHA256)
        self.assertIn("git archive", metadata["provenance"])

    def test_modified_archive_is_rejected(self):
        target = self.root / "src/nobots/core/detect.py"
        target.write_bytes(target.read_bytes() + b"\n# tampered\n")
        with self.assertRaisesRegex(SystemExit, "hashes differ"):
            reference_metadata(self.root)

    def test_mislabeled_archive_is_rejected(self):
        wrong = self.root.parent / "not-the-pinned-commit"
        self.root.rename(wrong)
        with self.assertRaisesRegex(SystemExit, "must end in the pinned commit"):
            reference_metadata(wrong)


if __name__ == "__main__":
    unittest.main()
