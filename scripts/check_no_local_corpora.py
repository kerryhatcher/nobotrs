#!/usr/bin/env python3
"""Fail if a tracked or staged file shares a 12-word run with a local non-owner corpus.

Exit codes: 0 clean, 1 leak found, 2 the guard could not run. Output names files and
hashed sample IDs only; it never prints corpus or file text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpora  # noqa: E402

ALLOWLIST_PATH = Path("scripts/local-corpus-guard-allowlist.json")


def load_allowlist(base: Path) -> set[tuple[str, str, str, str]]:
    path = base / ALLOWLIST_PATH
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("invalid corpus guard allowlist schema")
    entries = data.get("exceptions")
    fields = ("path", "sha256", "corpus", "sample")
    if not isinstance(entries, list):
        raise ValueError("invalid corpus guard allowlist exceptions")
    exceptions = set()
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(field), str) and entry[field] for field in fields
        ):
            raise ValueError("invalid corpus guard allowlist entry")
        exceptions.add(tuple(entry[field] for field in fields))
    return exceptions


def candidate_files(repo: Path) -> list[Path]:
    """Tracked files plus staged additions/changes, deduplicated, existing only."""
    def git_list(*args: str) -> list[str]:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
        return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]

    names = set(git_list("ls-files", "-z"))
    names |= set(git_list("diff", "--cached", "--name-only", "--diff-filter=AM", "-z"))
    return sorted(repo / name for name in names if (repo / name).is_file())


def export_index(repo: Path, dest: Path) -> list[Path]:
    """Write the index (the staged bytes of every tracked or staged file) under ``dest``."""
    subprocess.run(["git", "-C", str(repo), "checkout-index", "-a", "--prefix", f"{dest}/"],
                   capture_output=True, check=True)
    return sorted(p for p in dest.rglob("*") if p.is_file())


def _repo_relative(path: Path, base: Path, repo: Path) -> Path:
    """Map an exported copy back to its repository path for reporting."""
    if base == repo:
        return path
    return repo / path.relative_to(base)


def _display(path: Path, repo: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(corpora.ROOT))
    parser.add_argument("--internal-dir", default=None)
    parser.add_argument("--registry", default=str(corpora.REGISTRY_PATH))
    parser.add_argument("--shingle", type=int, default=12)
    parser.add_argument("--corpora", nargs="*", default=None,
                        help="corpus IDs to guard (default: every non-owner corpus)")
    parser.add_argument("--paths", nargs="*", default=None,
                        help="check these files instead of the repository")
    parser.add_argument("--source", choices=("index", "worktree"), default="index",
                        help="index: staged bytes of tracked and staged files (default); "
                             "worktree: current working-tree files")
    args = parser.parse_args(argv)
    repo = Path(args.repo).absolute()

    internal = corpora.internal_dir(args.internal_dir)
    if not internal.is_dir():
        print(f"could not run: no local corpora at {internal}", file=sys.stderr)
        return 2
    try:
        registry = corpora.load_registry(Path(args.registry))
        targets = args.corpora or corpora.non_owner_corpora(registry)
        files = ([Path(p).absolute() for p in args.paths] if args.paths is not None
                 else candidate_files(repo))
    except (corpora.CorpusError, subprocess.CalledProcessError, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="nobotrs-guard-") as tmp:
        if args.paths is None and args.source == "index":
            try:
                files = export_index(repo, Path(tmp))
            except subprocess.CalledProcessError as exc:
                print(f"could not run: cannot export the index: {exc}", file=sys.stderr)
                return 2
            base = Path(tmp)
        else:
            base = repo
        # Check each corpus separately so one unreadable corpus cannot hide the others.
        hits: list[tuple[Path, str, str]] = []
        unchecked: list[tuple[str, str]] = []
        for corpus in targets:
            try:
                hits += corpora.leaked(files, [corpus], args.shingle, internal=internal,
                                       registry=registry)
            except (corpora.CorpusError, OSError) as exc:
                unchecked.append((corpus, str(exc)))
        try:
            exceptions = load_allowlist(base) if args.shingle == 12 else set()
            approved_paths = {entry[0] for entry in exceptions}
            digests = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in {path for path, _, _ in hits}
                if _display(path, base) in approved_paths
            }
            unapproved = [
                (_repo_relative(path, base, repo), corpus, sample)
                for path, corpus, sample in hits
                if (_display(path, base), digests.get(path), corpus, sample) not in exceptions
            ]
        except (OSError, ValueError) as exc:
            print(f"could not run: corpus guard allowlist: {exc}", file=sys.stderr)
            return 2
        approved_count = len(hits) - len(unapproved)
        hits = unapproved

    if approved_count:
        print(f"local corpus guard: {approved_count} audited historical overlap(s) allowed")
    for path, corpus, sample in hits:
        print(f"LEAK {_display(path, repo)}: shares a {args.shingle}-word run "
              f"with {corpus} sample {sample}")
    for corpus, reason in unchecked:
        print(f"NOT CHECKED {corpus}: {reason}", file=sys.stderr)
    if hits:
        print(f"local corpus guard: {len(hits)} leak(s); remove the text or keep it local",
              file=sys.stderr)
        return 1
    if unchecked:
        print(f"local corpus guard: incomplete ({len(unchecked)} of {len(targets)} corpora "
              "not checked); report this explicitly", file=sys.stderr)
        return 2
    print(f"local corpus guard: clean ({len(files)} files, {len(targets)} corpora)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
