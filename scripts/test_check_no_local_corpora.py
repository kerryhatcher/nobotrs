#!/usr/bin/env python3
"""Regressions for the local corpus guard (Plan 5, Task 1)."""
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_no_local_corpora as guard  # noqa: E402
import corpora  # noqa: E402
from test_corpora import make_internal, stub_entry  # noqa: E402

EXCERPT = ("After consolidating schools, freezing pay, packing classes, and contracting out "
           "custodial work, the district still faces a shortfall of about eight million")
BEEMO_ROWS = [{"prompt_id": "p", "model_output": "", "human_output": "Lead in. " + EXCERPT
               + " dollars next year.", "human_edits": ""}]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    return repo


def run_guard(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = guard.main(args)
    return code, out.getvalue(), err.getvalue()


class GuardCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = make_repo(base)
        self.internal = make_internal(base / "internal", {
            "beemo/data/train-00000-of-00001.parquet": b"PAR1stub"})
        self.registry_path = base / "registry.json"
        self.registry_path.write_text(json.dumps({"schema_version": 1, "corpora": [
            stub_entry("beemo", "beemo")]}), encoding="utf-8")
        self.patch = mock.patch.object(corpora, "_parquet_rows", return_value=BEEMO_ROWS)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self._tmp.cleanup()

    def _args(self):
        return ["--repo", str(self.repo), "--internal-dir", str(self.internal),
                "--registry", str(self.registry_path)]

    def test_guard_flags_beemo_excerpt(self):
        leak = self.repo / "draft.md"
        leak.write_text("Draft. " + EXCERPT + " dollars.\n", encoding="utf-8")
        git(self.repo, "add", "draft.md")
        code, out, err = run_guard(self._args())
        self.assertEqual(code, 1)
        self.assertIn("draft.md", out)
        self.assertIn("beemo", out)
        self.assertNotIn("shortfall", out + err)  # never prints corpus or file text

    def test_counts_and_hashed_id_pass(self):
        clean = self.repo / "summary.md"
        clean.write_text("Beemo: 1 prompt, 3 texts; rate 0.25; id 3f2a9c1b8d4e\n", encoding="utf-8")
        git(self.repo, "add", "summary.md")
        code, out, _ = run_guard(self._args())
        self.assertEqual(code, 0)
        self.assertIn("clean", out)

    def test_unstaged_untracked_files_are_not_scanned(self):
        (self.repo / "scratch.md").write_text(EXCERPT, encoding="utf-8")
        code, _, _ = run_guard(self._args())
        self.assertEqual(code, 0)

    def test_tracked_file_is_scanned(self):
        leak = self.repo / "notes.md"
        leak.write_text(EXCERPT, encoding="utf-8")
        git(self.repo, "add", "notes.md")
        git(self.repo, "commit", "-q", "-m", "notes")
        code, out, _ = run_guard(self._args())
        self.assertEqual(code, 1)
        self.assertIn("notes.md", out)

    def test_staged_bytes_are_checked_not_the_worktree(self):
        leak = self.repo / "draft.md"
        leak.write_text("Draft. " + EXCERPT + " dollars.\n", encoding="utf-8")
        git(self.repo, "add", "draft.md")
        leak.write_text("counts only, cleaned in the worktree\n", encoding="utf-8")
        code, out, _ = run_guard(self._args())
        self.assertEqual(code, 1)
        self.assertIn("draft.md", out)

    def test_exception_is_bound_to_staged_path_bytes_and_sample(self):
        leak = self.repo / "fixture.md"
        leak.write_text(EXCERPT, encoding="utf-8")
        git(self.repo, "add", "fixture.md")
        _, out, _ = run_guard(self._args())
        sample = out.strip().rsplit(" ", 1)[1]
        allowlist = self.repo / guard.ALLOWLIST_PATH
        allowlist.parent.mkdir()
        entry = {
            "path": "fixture.md",
            "sha256": hashlib.sha256(leak.read_bytes()).hexdigest(),
            "corpus": "beemo",
            "sample": sample,
        }
        allowlist.write_text(json.dumps({"schema_version": 1, "exceptions": [entry]}))
        self.assertEqual(run_guard(self._args())[0], 1)
        git(self.repo, "add", str(guard.ALLOWLIST_PATH))
        code, out, _ = run_guard(self._args())
        self.assertEqual(code, 0)
        self.assertIn("1 audited historical overlap", out)
        leak.write_text(EXCERPT + "\n", encoding="utf-8")
        self.assertEqual(run_guard(self._args())[0], 0)
        self.assertEqual(run_guard(self._args() + ["--source", "worktree"])[0], 1)
        git(self.repo, "add", "fixture.md")
        self.assertEqual(run_guard(self._args())[0], 1)
        leak.write_text(EXCERPT, encoding="utf-8")
        (self.repo / "copy.md").write_bytes(leak.read_bytes())
        git(self.repo, "add", "fixture.md", "copy.md")
        code, out, _ = run_guard(self._args())
        self.assertEqual(code, 1)
        self.assertIn("LEAK copy.md", out)
        self.assertNotIn("LEAK fixture.md", out)

    def test_unstaged_worktree_leak_ignored_by_default_but_seen_with_source_worktree(self):
        clean = self.repo / "notes.md"
        clean.write_text("counts only\n", encoding="utf-8")
        git(self.repo, "add", "notes.md")
        clean.write_text(EXCERPT, encoding="utf-8")  # leaked but not staged
        code, _, _ = run_guard(self._args())
        self.assertEqual(code, 0)
        code_wt, out_wt, _ = run_guard(self._args() + ["--source", "worktree"])
        self.assertEqual(code_wt, 1)
        self.assertIn("notes.md", out_wt)

    def test_exit_two_when_local_corpora_absent(self):
        missing = self.internal.parent / "absent"
        code, _, err = run_guard(["--repo", str(self.repo), "--internal-dir", str(missing),
                                  "--registry", str(self.registry_path)])
        self.assertEqual(code, 2)
        self.assertIn("could not run", err)

    def test_checksum_failure_is_reported_not_passed(self):
        (self.internal / "test-artifacts/beemo/data/train-00000-of-00001.parquet").write_bytes(b"x")
        clean = self.repo / "summary.md"
        clean.write_text("counts only\n", encoding="utf-8")
        git(self.repo, "add", "summary.md")
        code, _, err = run_guard(self._args())
        self.assertEqual(code, 2)
        self.assertIn("checksum mismatch", err)


class OwnerExemptionTests(unittest.TestCase):
    def test_owner_post_text_is_not_a_guard_source(self):
        self.assertNotIn("owner-posts-v1", corpora.non_owner_corpora(corpora.load_registry()))

    def test_real_guard_reports_no_leak_in_committed_owner_posts(self):
        """Runs the guard against the real local corpora and the committed owner posts only.
        Exit 1 would be a leak. Exit 2 means at least one corpus was not checked (for
        example Beemo without pyarrow); that is reported, never treated as a pass."""
        if not corpora.DEFAULT_INTERNAL_DIR.is_dir():
            self.skipTest("internal corpus directory not present")
        posts = sorted((corpora.ROOT / "evaluation/corpora/owner-posts-v1/samples").glob("*.md"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = guard.main(["--repo", str(corpora.ROOT), "--paths", *map(str, posts)])
        self.assertNotEqual(code, 1, out.getvalue())
        if code == 2:
            self.assertIn("NOT CHECKED", err.getvalue())

if __name__ == "__main__":
    unittest.main()
