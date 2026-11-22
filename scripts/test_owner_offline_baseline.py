#!/usr/bin/env python3
"""Regressions for the owner offline baseline driver (Plan 5 owner invocation)."""
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import owner_offline_baseline as ob  # noqa: E402

STUB = """#!/usr/bin/env python3
import json, sys
argv = sys.argv[1:]
with open(sys.argv[0] + '.log', 'a') as log:
    log.write(' '.join(argv) + '\\n')
print(json.dumps({'findings': [], 'argv': argv}))
"""


class OwnerBaselineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.binary = base / "stub-nobotrs"
        self.binary.write_text(STUB)
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IEXEC)
        self.config = base / "config.json"
        self.config.write_text("{}\n")
        self.post = base / "2025-01-01-post.md"
        self.post.write_text("text\n")
        self.out = base / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def test_argv_is_offline_with_explicit_config(self):
        argv = ob.build_argv(self.binary, self.config, "review", self.post)
        self.assertIn("--config", argv)
        self.assertEqual(argv[argv.index("--config") + 1], str(self.config))
        self.assertNotIn("--gptzero", argv)
        self.assertNotIn("--openrouter-judge", argv)

    def test_external_flags_are_refused(self):
        original = ob.EXTERNAL_FLAGS
        try:
            ob.EXTERNAL_FLAGS = ("--language",)  # simulate a flag leaking into argv
            with self.assertRaises(ob.BaselineRefusal):
                ob.build_argv(self.binary, self.config, "review", self.post)
        finally:
            ob.EXTERNAL_FLAGS = original

    def test_run_writes_outputs_and_run_record(self):
        run = ob.run_baseline(self.binary, self.config, self.out, [self.post], repo=Path(self._tmp.name))
        stem = self.post.stem
        self.assertTrue((self.out / stem / "review.json").exists())
        self.assertTrue((self.out / stem / "report.json").exists())
        body = json.loads((self.out / "run.json").read_text())
        self.assertEqual(body["external"], "none")
        self.assertEqual(body["config_sha256"], ob.sha256_file(self.config))
        self.assertEqual(run["posts"][stem], {"review": 0, "detect": 0})

    def test_missing_binary_refused(self):
        with self.assertRaises(ob.BaselineRefusal):
            ob.run_baseline(Path(self._tmp.name) / "absent", self.config, self.out, [self.post])


if __name__ == "__main__":
    unittest.main()
