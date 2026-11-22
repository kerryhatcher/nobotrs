#!/usr/bin/env python3
"""Reproducible baseline recorder (Plan 5, Task 2).

Runs the nobotrs binary on one input and writes ``run.json`` plus the raw ``report.json``,
``review.json`` and exit codes beside it. Vendor output policy (roadmap decision 3):

- GPTZero: the raw response goes only to ``$NOBOTRS_INTERNAL_DIR/derived/baselines/``.
  The committed ``run.json`` keeps status, date, local path and response hash.
- OpenRouter: the committed record keeps verdict, confidence, the reply text, model,
  serving provider, tokens and cost, plus ``"ai_generated": true``. The prompt and the
  input text are never stored.

Only Bibb and the owner corpus are recorded in the repository. Beemo and other local
corpora are never passed here (their texts must not be committed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import tempfile
import urllib.error
import urllib.request
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpora  # noqa: E402

BIBB_SHA = "5c45d6d3edb1f09cf567915a1ea14699316fdeefe7576d9ac805aa7d69aa23d4"
DEFAULT_MODELS = ("desklib", "conpara", "detectorscope")


class BaselineError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def judge_stability(reports: list[dict]) -> tuple[float | None, int]:
    """Agreement of the modal OpenRouter label among non-failed repeats, and failed count.

    A repeat is failed when it has no verdict label. Returns ``(None, failed)`` when every
    repeat failed.
    """
    labels = []
    failed = 0
    for report in reports:
        verdict = (report or {}).get("verdict") or {}
        label = verdict.get("label")
        if label is None:
            failed += 1
        else:
            labels.append(label)
    if not labels:
        return None, failed
    modal = Counter(labels).most_common(1)[0][1]
    return modal / len(labels), failed


def sanitize_openrouter(judge: dict) -> dict:
    """Keep only the fields allowed in committed output. Prompt and input text are dropped.

    ``ai_generated`` describes the **provenance of this record** — it is always ``True``
    because the record was produced by an AI judge (OpenRouter). It does NOT describe the
    text under judgment. The vendor's own verdict label (AI / HUMAN / MIXED) is in the
    ``verdict`` field. The aggregate local detector outcome is recorded separately in the
    ``run.json`` ``verdict`` / ``detect`` fields.
    """
    verdict = judge.get("verdict") or {}
    return {
        "status": judge.get("status"),
        "verdict": verdict.get("label"),
        "confidence": verdict.get("confidence"),
        "reply_text": judge.get("reply_text") or judge.get("unparsed_reply"),
        "model": judge.get("model"),
        "provider": judge.get("provider"),
        "prompt_tokens": judge.get("prompt_tokens"),
        "completion_tokens": judge.get("completion_tokens"),
        "cost": judge.get("cost"),
        "ai_generated": True,
    }


def gptzero_summary(section: dict, raw: bytes, local_path: str) -> dict:
    return {
        "status": section.get("status"),
        "date": dt.date.today().isoformat(),
        "local_path": local_path,
        "response_sha256": sha256_bytes(raw),
    }


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


class Recorder:
    def __init__(self, binary: Path, internal: Path, models_dir: Path | None,
                 repo: Path = ROOT, env: dict | None = None):
        self.binary = binary
        self.internal = internal
        self.models_dir = models_dir
        self.repo = repo
        self.env = env if env is not None else dict(os.environ)
        self.commands: list[list[str]] = []

    def run(self, args: list[str]) -> tuple[int, bytes]:
        argv = [str(self.binary), *args]
        self.commands.append(["nobotrs", *args])
        # A recorder run must never inherit globally enabled external clients or models.
        env = {k:v for k,v in self.env.items() if not k.startswith("NOBOTRS_") or k=="NOBOTRS_MODEL_PYTHON"}
        with tempfile.NamedTemporaryFile("w",suffix=".json") as config:
            json.dump({},config)
            config.flush()
            env["NOBOTRS_CONFIG"] = config.name
            result = subprocess.run(argv, capture_output=True, env=env, check=False)
        return result.returncode, result.stdout

    def supports(self, flag: str) -> bool:
        _, out = self.run(["detect", "--help"])
        return flag.encode() in out

    def record(self, input_path: Path, out_dir: Path, *, models: tuple[str, ...],
               model_coverage: str, external: bool, judge_repeats: int, vendor: str="both") -> dict:
        data = input_path.read_bytes()
        out_dir.mkdir(parents=True, exist_ok=True)
        input_sha = sha256_bytes(data)
        if external and input_sha != BIBB_SHA:
            raise BaselineError("external baseline is authorized only for the pinned Bibb fixture")
        if out_dir.resolve().is_relative_to(self.repo.resolve()):
            public = {BIBB_SHA}
            manifest=self.repo/"evaluation/corpora/owner-posts-v1/manifest.json"
            if manifest.exists():
                public.update(p["sha256"] for p in json.loads(manifest.read_text())["posts"])
            if input_sha not in public:
                raise BaselineError("only approved fixture and owner sample hashes may be recorded in the repository")
        text = data.decode("utf-8", errors="replace")

        detect_args = ["detect", "--format", "json", "--language", "en"]
        if models:
            detect_args += ["--timeout-ms","180000","--models", ",".join(models), "--models-dir", str(self.models_dir)]
            if model_coverage == "full":
                if not self.supports("--model-coverage"):
                    raise BaselineError("model-coverage full needs the Plan 4 binary (no "
                                        "--model-coverage flag in this build)")
                detect_args += ["--model-coverage", "full"]
        detect_args.append(str(input_path))
        detect_exit, detect_out = self.run(detect_args)
        if detect_exit not in (0, 1, 2, 3) or not detect_out.strip():
            raise BaselineError(f"detect exited {detect_exit}")
        (out_dir / "report.json").write_bytes(detect_out)

        review_exit, review_out = self.run(["review", "--language","en","--format", "json", str(input_path)])
        if review_exit in (0, 1):
            (out_dir / "review.json").write_bytes(review_out)
            review_status = "recorded"
        else:
            # The Plan 1 `review` subcommand is absent from this build. Say so, never fake it.
            review_status = f"unavailable (exit {review_exit}: subcommand missing or failed)"
        lint_exit, _ = self.run(["lint", "--language","en","--format", "json", str(input_path)])

        gptzero: dict = {"status": "not_run"}
        openrouter: dict = {"repeats": [], "agreement": None, "failed": 0}
        if external and vendor in ("both", "gptzero"):
            try:
                gptzero = self._external_gptzero(input_path, input_sha)
            except urllib.error.HTTPError as error:
                gptzero = {"status": "failed", "http_status": error.code, "date": dt.date.today().isoformat()}
            except (OSError, ValueError) as error:
                gptzero = {"status": "failed", "error_type": type(error).__name__, "date": dt.date.today().isoformat()}
        if external and vendor in ("both", "openrouter"):
            openrouter = self._external_judge(input_path, judge_repeats)

        run = {
            "git_revision": _git(self.repo, "rev-parse", "HEAD"),
            "git_dirty": bool(_git(self.repo, "status", "--porcelain")),
            "input_sha256": input_sha,
            "bytes": len(data),
            "chars": len(text),
            "binary_sha256": sha256_bytes(self.binary.read_bytes()),
            "guide_sha256": sha256_bytes((self.repo/"docs/ai-writing-guide.md").read_bytes()),
            "pipeline_contract": json.loads(detect_out).get("metric_contract"),
            "model_preprocessing": {b["backend"]: b["outcome"]["details"]["model_evidence"]["preprocessing_revision"]
                                    for b in json.loads(detect_out).get("backends",[]) if
                                    isinstance(b.get("outcome",{}).get("details"),dict) and
                                    b["outcome"]["details"].get("model_evidence")},
            "settings": {"models": list(models), "model_coverage": model_coverage,
                         "external": external, "judge_repeats": judge_repeats,
                         "language": "en"},
            "manifest_hashes": self._manifest_hashes(),
            "devices": {"cpu": _cpu_name(), "python": platform.python_version()},
            "backend_completion": _backend_completion(out_dir / "report.json"),
            "exit_codes": {"detect": detect_exit, "review": review_exit, "lint": lint_exit},
            "review_status": review_status,
            "external": {
                "gptzero": gptzero,
                "openrouter_repeats": openrouter["repeats"],
                "openrouter_label_agreement": openrouter["agreement"],
                "openrouter_failed_repeats": openrouter["failed"],
            },
            "commands": self.commands,
        }
        (out_dir / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
        return run

    def _manifest_hashes(self) -> dict[str, str]:
        hashes = {}
        for path in sorted((self.repo / "models").glob("*.json")):
            hashes[f"models/{path.name}"] = sha256_bytes(path.read_bytes())
        return hashes

    def _external_gptzero(self, input_path: Path, input_sha: str) -> dict:
        if self.internal.resolve().is_relative_to(self.repo.resolve()):
            raise BaselineError("vendor captures require a private directory outside the worktree")
        data = input_path.read_bytes()
        if sha256_bytes(data) != BIBB_SHA:
            raise BaselineError("Bibb input changed before capture")
        req=urllib.request.Request("https://api.gptzero.me/v2/predict/text",
            data=json.dumps({"document":data.decode("utf-8")}).encode(),
            headers={"Content-Type":"application/json","Accept":"application/json",
                     "x-api-key":self.env["GPTZERO_API_KEY"]}, method="POST")
        # One request. Hash the actual wire bytes before parsing, and retain them only locally.
        with urllib.request.urlopen(req,timeout=60) as response:
            raw=response.read()
        if not json.loads(raw).get("documents"):
            raise BaselineError("GPTZero returned no documents")
        section={"status":"ok"}
        local_dir = self.internal / "derived" / "baselines" / input_sha
        local_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        local_file = local_dir / "gptzero.json"
        with tempfile.NamedTemporaryFile(dir=local_dir,delete=False) as capture:
            capture.write(raw)
        os.replace(capture.name,local_file)
        return gptzero_summary(section, raw, str(local_file.relative_to(self.internal)))

    def _external_judge(self, input_path: Path, repeats: int) -> dict:
        reports = []
        for _ in range(repeats):
            _, out = self.run(["analyze", "--openrouter-judge","--language","en", "--format", "json",
                               str(input_path)])
            reports.append(json.loads(out or b"{}").get("openrouter") or {})
        agreement, failed = judge_stability(reports)
        return {"repeats": [sanitize_openrouter(r) for r in reports],
                "agreement": agreement, "failed": failed}


def _backend_completion(report_path: Path) -> dict:
    try:
        body = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    completion = {}
    for backend in body.get("backends", []) or []:
        if isinstance(backend, dict) and "backend" in backend:
            outcome = backend.get("outcome") or {}
            completion[backend["backend"]] = outcome.get("status", "unknown")
    return completion


def require_external_keys(env: dict, vendor="both") -> None:
    keys = {"gptzero":"GPTZERO_API_KEY", "openrouter":"OPENROUTER_API_KEY"}
    missing = [k for v,k in keys.items() if vendor in ("both",v) and not env.get(k)]
    if missing:
        raise BaselineError("refusing --external: missing " + ", ".join(missing))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="one local text or Markdown file")
    source.add_argument("--corpus", help="owner-posts-v1 (the only corpus committed)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "target/release/nobotrs")
    parser.add_argument("--models", default="", help="comma-separated local models, or none")
    parser.add_argument("--models-dir", type=Path, default=None)
    parser.add_argument("--model-coverage", choices=("opening", "full"), default="opening")
    parser.add_argument("--external", action="store_true")
    parser.add_argument("--vendor", choices=("both","gptzero","openrouter"), default="both")
    parser.add_argument("--judge-repeats", type=int, default=1)
    parser.add_argument("--internal-dir", default=None)
    args = parser.parse_args(argv)

    try:
        if args.judge_repeats < 1:
            raise BaselineError("--judge-repeats must be positive")
        if args.external:
            require_external_keys(os.environ,args.vendor)
            if args.input is None:
                raise BaselineError("--external is supported only with the pinned Bibb fixture")
        internal = corpora.internal_dir(args.internal_dir)
        models = tuple(m for m in args.models.split(",") if m)
        models_dir = args.models_dir or Path(os.environ.get(
            "NOBOTRS_MODELS_DIR", str(Path.home() / ".cache/nobotrs-local-ai/models-v1")))
        recorder = Recorder(args.binary, internal, models_dir if models else None)
        if args.input:
            inputs = [(args.input, args.out)]
        else:
            if args.corpus != corpora.OWNER_CORPUS:
                raise BaselineError("only owner-posts-v1 may be recorded in the repository")
            posts = sorted((ROOT / "evaluation/corpora/owner-posts-v1/samples").glob("*.md"))
            inputs = [(p, args.out / p.stem) for p in posts]
        for path, out_dir in inputs:
            recorder.commands = []
            recorder.record(path, out_dir, models=models, model_coverage=args.model_coverage,
                            external=args.external, judge_repeats=args.judge_repeats, vendor=args.vendor)
            print(f"recorded {out_dir}")
    except (BaselineError, corpora.CorpusError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
