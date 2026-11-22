#!/usr/bin/env python3
"""Local-only sequential review of non-owner corpora (Plan 5, Tasks 3-4).

Texts and raw review outputs stay under ``$NOBOTRS_INTERNAL_DIR/derived/review-batch``.
The per-document rows (rule counts, rule IDs and byte spans; no text) go to
``derived/rule-lift``. Only aggregates from these rows may be committed.

Runs one command at a time, with an explicit empty config and no external flags. Beemo
needs pyarrow, so run this with an interpreter that has it (for example the local-AI venv).
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpora  # noqa: E402

DEFAULT_BINARY = ROOT / "target" / "release" / "nobotrs"
CONFIG = ROOT / "evaluation" / "baselines" / "config-empty.json"
WI_DEV = ("A.dev-", "B.dev-", "C.dev-", "N.dev-")


def hashed(corpus: str, sample_id: str) -> str:
    return hashlib.sha256(f"{corpus}:{sample_id}".encode()).hexdigest()[:12]


def review_text(binary: Path, text_path: Path, out_json: Path, worker=None) -> int:
    """Capture only complete local runs, including the entire finding list."""
    argv = [str(binary), "review", "--format", "json", "--config", str(CONFIG),
            "--language", "en", "--display-limit", "100000", str(text_path)]
    if worker is None:
        result = subprocess.run(argv, capture_output=True, check=False, env={"PATH": os.defpath})
        if result.returncode != 0:
            return result.returncode
        raw = result.stdout
    else:
        worker.stdin.write(json.dumps(str(text_path)).encode() + b"\n")
        worker.stdin.flush()
        raw = worker.stdout.readline()
        if not raw:
            raise RuntimeError("corpus review worker stopped before returning a report")
    report = json.loads(raw)
    if report.get("complete") is not True or report.get("omitted_findings") != 0:
        return 2
    out_json.write_bytes(raw)
    return 0


def findings_of(review_path: Path) -> list[dict]:
    """Unsuppressed findings with *all* their byte ranges. A finding can span several lines,
    and each range is a separate ``source_ranges`` entry; keeping only the first would
    undercount overlaps."""
    body = json.loads(review_path.read_text(encoding="utf-8"))
    out = []
    for finding in body["findings"] + body["document"]:
        if finding.get("suppressed"):
            continue
        ranges = (finding.get("location") or {}).get("source_ranges") or []
        out.append({"rule_id": finding["rule_id"],
                    "ranges": [[r["start"], r["end"]] for r in ranges]})
    return out


def items(corpus: str, internal: Path, registry: dict):
    if corpus == "gao":
        for s in corpora.iter_samples("govinfo-gao-2008", internal, registry):
            yield s
    elif corpus == "wi-dev":
        for s in corpora.iter_samples("wi-locness", internal, registry):
            if s.id.startswith(WI_DEV):
                yield s
    elif corpus == "beemo":
        for s in corpora.iter_samples("beemo", internal, registry):
            yield s
    else:
        raise SystemExit(f"unknown corpus {corpus}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", choices=("gao", "wi-dev", "beemo"))
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--worker", type=Path, help="optional corpus_review example executable")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    internal = corpora.internal_dir()
    registry = corpora.load_registry()
    corpus_id = {"gao": "govinfo-gao-2008", "wi-dev": "wi-locness", "beemo": "beemo"}[args.corpus]
    work = internal / "derived" / "review-batch" / args.corpus
    rows_dir = internal / "derived" / "rule-lift"
    work.mkdir(parents=True, exist_ok=True)
    rows_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = 0
    with ExitStack() as stack:
        worker = None
        if args.worker:
            worker = stack.enter_context(subprocess.Popen(
                [str(args.worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                env={"PATH": os.defpath}))
            stack.callback(worker.stdin.close)
        for index, sample in enumerate(items(args.corpus, internal, registry)):
            if args.limit is not None and index >= args.limit:
                break
            doc = hashed(corpus_id, sample.id)
            text_path = work / f"{doc}.txt"
            review_path = work / f"{doc}.review.json"
            text_path.write_bytes(sample.text.encode("utf-8"))
            code = review_text(args.binary, text_path, review_path, worker)
            if code != 0:
                failures += 1
                continue
            findings = findings_of(review_path)
            row_index, column = _beemo_position(sample.id) if args.corpus == "beemo" else (None, None)
            rows.append({"doc": doc, "group": sample.group, "label": sample.label,
                         "genre": sample.genre, "words": corpora.count_words(sample.text),
                         "row": row_index, "column": column,
                         "rules": _counts(findings), "findings": findings,
                         "unlocated_findings": sum(1 for f in findings if not f["ranges"])})
    out = rows_dir / f"{args.corpus}.rows.json"
    out.write_text(json.dumps(rows), encoding="utf-8")
    # Provenance: which binary produced these rows, and what it left out of alignment.
    meta = {
        "corpus": args.corpus,
        "binary": str(args.worker or args.binary),
        "binary_sha256": hashlib.sha256((args.worker or args.binary).read_bytes()).hexdigest(),
        "documents": len(rows),
        "failures": failures,
        "findings": sum(len(r["findings"]) for r in rows),
        "unlocated_findings": sum(r["unlocated_findings"] for r in rows),
        "unlocated_rule_counts": _counts([f for r in rows for f in r["findings"]
                                          if not f["ranges"]]),
        "unlocated_policy": "counted in rule lift; excluded from character overlap",
    }
    (rows_dir / f"{args.corpus}.rows.meta.json").write_text(json.dumps(meta, indent=2) + "\n",
                                                           encoding="utf-8")
    print(f"{args.corpus}: {len(rows)} documents reviewed, {failures} failures, "
          f"{meta['unlocated_findings']} unlocated findings -> {out}")
    return 1 if failures else 0


def _beemo_position(sample_id: str) -> tuple[int, str]:
    """Beemo sample ids are ``<row index>:<column>``; the row index pairs a model output with
    its expert edit exactly, without relying on prompt group."""
    index, column = sample_id.split(":", 1)
    return int(index), column


def _counts(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["rule_id"]] = counts.get(f["rule_id"], 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
