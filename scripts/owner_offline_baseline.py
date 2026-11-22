#!/usr/bin/env python3
"""Offline owner-corpus baseline (Plan 5, Task 2 for owner posts; owner-invoked).

Runs `review` and `detect` with an explicit empty config and no external flags, for each
committed owner post. Writes <out>/<post-stem>/review.json and report.json, plus
<out>/run.json recording the binary and config hashes, argv, exit codes and git revision.
External services are refused: this script never passes --gptzero or --openrouter-judge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "evaluation" / "corpora" / "owner-posts-v1" / "samples"
DEFAULT_BINARY = ROOT / "target" / "release" / "nobotrs"
DEFAULT_CONFIG = ROOT / "evaluation" / "baselines" / "config-empty.json"
EXTERNAL_FLAGS = ("--gptzero", "--openrouter-judge")
DISPLAY_LIMIT = "100000"  # binary maximum; review also reports omitted_findings


class BaselineRefusal(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_argv(binary: Path, config: Path, command: str, post: Path) -> list[str]:
    argv = [str(binary), command, "--format", "json", "--config", str(config),
            "--language", "en", "--display-limit", DISPLAY_LIMIT, str(post)]
    for flag in EXTERNAL_FLAGS:
        if flag in argv:
            raise BaselineRefusal(f"external flag {flag} refused for owner offline baseline")
    return argv


def run_baseline(binary: Path, config: Path, out: Path, posts: list[Path],
                 repo: Path = ROOT) -> dict:
    if not binary.is_file():
        raise BaselineRefusal(f"binary not found: {binary}")
    if not config.is_file():
        raise BaselineRefusal(f"config not found: {config}")
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(config.read_text())
    if any(cfg.get(key) for key in ("gptzero", "openrouter_judge", "models")):
        raise BaselineRefusal("expected an offline config with no models or external clients")
    per_post = {}
    commands = []
    for post in posts:
        stem = post.stem
        post_dir = out / stem
        post_dir.mkdir(exist_ok=True)
        exits = {}
        for command, name in (("review", "review.json"), ("detect", "report.json")):
            argv = build_argv(binary, config, command, post)
            commands.append(argv)
            result = subprocess.run(argv, capture_output=True, check=False, env={"PATH": os.defpath})
            exits[command] = result.returncode
            # detect exits 3 for an inconclusive verdict (e.g. too little prose); the JSON is
            # still the report, so keep any stdout and record the exit code beside it.
            if result.stdout:
                (post_dir / name).write_bytes(result.stdout)
        per_post[stem] = exits
    git_rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=False).stdout.strip()
    run = {
        "binary": str(binary), "binary_sha256": sha256_file(binary),
        "config": str(config.relative_to(repo)) if config.is_relative_to(repo) else str(config),
        "config_sha256": sha256_file(config), "external": "none",
        "git_revision": git_rev, "display_limit": int(DISPLAY_LIMIT),
        "posts": per_post, "commands": commands,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "evaluation" / "baselines" / "owner-posts-v1-offline")
    parser.add_argument("--limit", type=int, default=None, help="first N posts (testing)")
    args = parser.parse_args(argv)
    posts = sorted(POSTS.glob("*.md"))[: args.limit]
    try:
        run = run_baseline(args.binary, args.config, args.out, posts)
    except BaselineRefusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    failed = {k: v for k, v in run["posts"].items() if v.get("review") != 0 or v.get("detect") not in (0, 1, 3)}
    # Expected non-zero detect exits (verified): 3 = inconclusive verdict.
    print(f"owner offline baseline: {len(run['posts'])} posts; review failures: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
