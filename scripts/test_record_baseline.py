#!/usr/bin/env python3
"""Regressions for the baseline recorder (Plan 5, Task 2). Uses a stub binary, so no
network call and no model run happens here."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parent))

import record_baseline as rb  # noqa: E402

STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
argv = sys.argv[1:]
state = Path(os.environ["STUB_STATE"])
state.mkdir(parents=True, exist_ok=True)
with (state / "calls.log").open("a") as log:
    log.write(" ".join(argv) + "\n")
if argv[:1] == ["detect"] and "--help" in argv:
    print("  --models <MODELS>")
    if os.environ.get("STUB_COVERAGE") == "1":
        print("  --model-coverage <MODEL_COVERAGE>")
    sys.exit(0)
if argv[:1] == ["detect"]:
    print(json.dumps({"verdict": "Clean", "backends": [
        {"backend": "vocabulary", "family": "Vocabulary", "outcome": {"status": "scored"}},
        {"backend": "desklib", "family": "Model", "outcome": {"status": "skipped"}}]}))
    sys.exit(0)
if argv[:1] == ["review"]:
    if os.environ.get("STUB_REVIEW") == "1":
        print(json.dumps({"findings": []}))
        sys.exit(0)
    print("error: unrecognized subcommand 'review'", file=sys.stderr)
    sys.exit(2)
if argv[:1] == ["lint"]:
    print(json.dumps({"findings": []}))
    sys.exit(0)
if argv[:1] == ["analyze"] and "--gptzero" in argv:
    print(json.dumps({"gptzero": {"status": "ok", "verdict": {
        "predicted_class": "ai", "class_probabilities": {"human": 0.1, "ai": 0.8, "mixed": 0.1}},
        "inputText": "SECRET INPUT", "sentences": [{"text": "SECRET"}], "scanId": "scan-123"}}))
    sys.exit(0)
if argv[:1] == ["analyze"] and "--openrouter-judge" in argv:
    counter = state / "judge.count"
    n = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(n + 1))
    labels = os.environ.get("STUB_LABELS", "AI").split(",")
    label = labels[n % len(labels)]
    if label == "fail":
        print(json.dumps({"openrouter": {"status": "failed", "verdict": None,
                                         "prompt": "SECRET PROMPT TEXT", "model": "m"}}))
    else:
        print(json.dumps({"openrouter": {
            "status": "ok", "model": "stub/model", "verdict": {"label": label, "confidence": 80},
            "unparsed_reply": None, "prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001,
            "prompt": "SECRET PROMPT TEXT"}}))
    sys.exit(0)
print("unexpected", argv, file=sys.stderr)
sys.exit(3)
'''


class StubBinary:
    def __init__(self, base: Path):
        self.path = base / "nobotrs-stub"
        self.path.write_text(STUB, encoding="utf-8")
        self.path.chmod(self.path.stat().st_mode | stat.S_IEXEC)
        self.state = base / "state"


def make_env(stub: StubBinary, **extra) -> dict:
    env = {"STUB_STATE": str(stub.state)}
    env.update(extra)
    return env


class JudgeStabilityTests(unittest.TestCase):
    def test_judge_stability(self):
        reports = [{"verdict": {"label": "AI"}}, {"verdict": {"label": "AI"}},
                   {"verdict": {"label": "MIXED"}}, {"verdict": None, "status": "failed"},
                   {"verdict": {"label": "AI"}}]
        self.assertEqual(rb.judge_stability(reports), (0.75, 1))

    def test_all_failed_is_none(self):
        self.assertEqual(rb.judge_stability([{"verdict": None}] * 5), (None, 5))


class RecordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.stub = StubBinary(self.base)
        self.input = self.base / "sample.md"
        self.input.write_text("A short draft about the budget.\n", encoding="utf-8")
        self.internal = self.base / "internal"
        self.out = self.base / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, args, env_extra=None, *, extra_env=None):
        env = make_env(self.stub, **(env_extra or {}))
        argv = ["--input", str(self.input), "--out", str(self.out),
                "--binary", str(self.stub.path), "--internal-dir", str(self.internal), *args]
        def offline_response(req,timeout):
            self.assertEqual(req.full_url,"https://api.gptzero.me/v2/predict/text")
            return BytesIO(b'{"documents":[{}],"scanId":"scan-123"}')
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(rb,"BIBB_SHA",rb.sha256_bytes(self.input.read_bytes())), mock.patch.object(rb.urllib.request,"urlopen",side_effect=offline_response):
            return rb.main(argv)

    def test_run_json_fields_offline(self):
        self.assertEqual(self._run([]), 0)
        run = json.loads((self.out / "run.json").read_text())
        for key in ("git_revision", "git_dirty", "input_sha256", "bytes", "chars",
                    "binary_sha256", "settings", "manifest_hashes", "devices",
                    "backend_completion", "exit_codes", "external", "commands"):
            self.assertIn(key, run)
        self.assertEqual(run["input_sha256"], rb.sha256_bytes(self.input.read_bytes()))
        self.assertEqual(run["backend_completion"], {"vocabulary": "scored", "desklib": "skipped"})
        self.assertEqual(run["external"]["gptzero"], {"status": "not_run"})
        self.assertTrue(run["commands"][0][0] == "nobotrs")
        self.assertTrue(run["review_status"].startswith("unavailable"))
        self.assertFalse((self.out / "review.json").exists())
        self.assertTrue((self.out / "report.json").exists())

    def test_review_json_recorded_when_subcommand_exists(self):
        self.assertEqual(self._run([], {"STUB_REVIEW": "1"}), 0)
        self.assertTrue((self.out / "review.json").exists())
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(run["review_status"], "recorded")

    def test_refuses_external_without_keys(self):
        marker = self.stub.state / "calls.log"
        with mock.patch.dict(os.environ, make_env(self.stub), clear=True):
            code = rb.main(["--input", str(self.input), "--out", str(self.out),
                            "--binary", str(self.stub.path), "--external"])
        self.assertEqual(code, 2)
        self.assertFalse(marker.exists(), "no binary call may happen without keys")

    def test_gptzero_body_never_committed(self):
        keys = {"GPTZERO_API_KEY": "k1", "OPENROUTER_API_KEY": "k2"}
        self.assertEqual(self._run(["--external", "--judge-repeats", "2"], keys), 0)
        committed = (self.out / "run.json").read_text()
        for secret in ("inputText", "sentences", "class_probabilities", "scanId", "SECRET"):
            self.assertNotIn(secret, committed)
        gz = json.loads(committed)["external"]["gptzero"]
        self.assertEqual(set(gz), {"status", "date", "local_path", "response_sha256"})
        raw = (self.internal / gz["local_path"]).read_text()
        self.assertIn("scanId", raw, "raw response is kept locally, not discarded")

    def test_openrouter_record_is_sanitized(self):
        keys = {"GPTZERO_API_KEY": "k1", "OPENROUTER_API_KEY": "k2"}
        self.assertEqual(self._run(["--external", "--judge-repeats", "2"], keys), 0)
        committed = (self.out / "run.json").read_text()
        self.assertNotIn("SECRET PROMPT TEXT", committed)
        self.assertNotIn('"prompt"', committed)
        external = json.loads(committed)["external"]
        self.assertEqual(external["openrouter_repeats"][0]["ai_generated"], True)
        self.assertEqual(external["openrouter_repeats"][0]["verdict"], "AI")
        self.assertEqual(external["openrouter_repeats"][0]["model"], "stub/model")
        self.assertEqual(external["openrouter_label_agreement"], 1.0)

    def test_full_coverage_requires_plan4_binary(self):
        code = self._run(["--models", "desklib", "--models-dir", str(self.base),
                          "--model-coverage", "full"], {"STUB_COVERAGE": "0"})
        self.assertEqual(code, 2)

    def test_full_coverage_accepted_when_flag_present(self):
        code = self._run(["--models", "desklib", "--models-dir", str(self.base),
                          "--model-coverage", "full"], {"STUB_COVERAGE": "1"})
        self.assertEqual(code, 0)

    def test_only_owner_corpus_may_be_recorded(self):
        with mock.patch.dict(os.environ, make_env(self.stub), clear=True):
            code = rb.main(["--corpus", "beemo", "--out", str(self.out),
                            "--binary", str(self.stub.path)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
