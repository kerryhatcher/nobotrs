#!/usr/bin/env python3
"""Per-rule lift of nobotrs findings against human controls (Plan 5, Task 3).

Inputs are per-document rows: ``{"group", "label", "genre", "words", "rules": {id: hits}}``.
Rates are hits per 10,000 words. Rates with fewer than 10 documents or 10,000 words are
``null`` (roadmap Task 1 rule). Confidence intervals come from a document-level bootstrap
(2,000 resamples, seed 0) that resamples whole groups.

Counts include unsuppressed located and document-wide findings from editorial review.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpora  # noqa: E402

MIN_DOCS = 10
MIN_WORDS = 10_000
RESAMPLES = 2_000
SEED = 0


def _resample_groups(groups: list[str], rng: random.Random) -> list[str]:
    """Draw len(groups) groups with replacement; returns the drawn group keys."""
    return [groups[rng.randrange(len(groups))] for _ in groups]


def _resampled_rows(by_group: dict[str, list[dict]], drawn: list[str]) -> list[dict]:
    """Every row of a drawn group enters together, so related documents stay together."""
    return [row for group in drawn for row in by_group[group]]


def _per_10k(hits: int, words: int) -> float | None:
    if words < MIN_WORDS:
        return None
    return hits * 10_000 / words


def _summarise(rows: list[dict], rule: str) -> tuple[int, int, int, int]:
    docs_with = sum(1 for r in rows if r["rules"].get(rule, 0) > 0)
    hits = sum(r["rules"].get(rule, 0) for r in rows)
    words = sum(r["words"] for r in rows)
    return docs_with, len(rows), hits, words


def rates(rows: list[dict], label: str, genre: str | None = None,
          rules: list[str] | None = None) -> dict[str, dict]:
    """Per-rule rates for one label (and optionally one genre), with a grouped bootstrap.

    The bootstrap resamples whole groups with replacement (seed 0, 2,000 draws). It is
    vectorised: a draw-by-group count matrix multiplies the per-group totals, which gives
    the same result as rebuilding the resampled rows for every draw, far faster.
    """
    import numpy as np

    selected = [r for r in rows if r["label"] == label and (genre is None or r["genre"] == genre)]
    if rules is None:
        rules = sorted({rule for r in selected for rule in r["rules"]})
    else:
        rules = list(rules)
    groups = sorted({r["group"] for r in selected})
    if not selected:
        return {rule: {"docs_with": 0, "docs": 0, "hits": 0, "words": 0, "per_10k": None,
                       "ci": None, "null_reason": "no documents for this label"}
                for rule in rules}
    gi = {g: i for i, g in enumerate(groups)}
    ri = {rule: j for j, rule in enumerate(rules)}
    G, R = len(groups), len(rules)
    hits_g = np.zeros((G, R))
    docs_with_g = np.zeros((G, R))
    words_g = np.zeros(G)
    docs_g = np.zeros(G)
    for r in selected:
        g = gi[r["group"]]
        words_g[g] += r["words"]
        docs_g[g] += 1
        for rule, count in r["rules"].items():
            hits_g[g, ri[rule]] += count
            if count > 0:
                docs_with_g[g, ri[rule]] += 1

    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, G, size=(RESAMPLES, G))
    counts = np.zeros((RESAMPLES, G))
    np.add.at(counts, (np.arange(RESAMPLES)[:, None], draws), 1)
    hits_b = counts @ hits_g            # (RESAMPLES, R)
    words_b = counts @ words_g          # (RESAMPLES,)
    valid = words_b >= MIN_WORDS

    out: dict[str, dict] = {}
    total_docs = int(docs_g.sum())
    total_words = int(words_g.sum())
    for j, rule in enumerate(rules):
        hits = int(hits_g[:, j].sum())
        docs_with = int(docs_with_g[:, j].sum())
        small = total_docs < MIN_DOCS or total_words < MIN_WORDS
        ci = None
        if not small and valid.any():
            values = hits_b[valid, j] * 10_000 / words_b[valid]
            ci = [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
        out[rule] = {"docs_with": docs_with, "docs": total_docs, "hits": hits,
                     "words": total_words,
                     "per_10k": None if small else _per_10k(hits, total_words), "ci": ci,
                     "null_reason": None if not small else
                     f"{total_docs} docs and {total_words} words; need {MIN_DOCS} and {MIN_WORDS}"}
    return out


def lift(ai: dict, human: dict) -> dict:
    """Ratio of AI to human rates. Each undefined case carries a reason.

    A zero human rate with an adequate denominator is a real 0.0, and the lift is undefined
    (reason ``human rate is zero``). A null rate means the denominator is too small.
    """
    a, h = ai.get("per_10k"), human.get("per_10k")
    if a is None or h is None:
        return {"lift": None, "ci": None, "ai_per_10k": a, "human_per_10k": h,
                "reason": "small denominator (see null_reason)"}
    if h == 0:
        return {"lift": None, "ci": None, "ai_per_10k": a, "human_per_10k": h,
                "reason": "human rate is zero, so lift is undefined"}
    ci = None
    if ai.get("ci") and human.get("ci") and human["ci"][0] > 0:
        ci = [ai["ci"][0] / human["ci"][1], ai["ci"][1] / human["ci"][0]]
    return {"lift": a / h, "ci": ci, "ai_per_10k": a, "human_per_10k": h, "reason": None}


def flags(entry: dict) -> list[str]:
    result = []
    if entry["ci"] is not None and entry["ci"][0] <= 1 <= entry["ci"][1]:
        result.append("weak")
    if entry["human_per_10k"] is not None and entry["ai_per_10k"] is not None \
            and entry["human_per_10k"] >= entry["ai_per_10k"]:
        result.append("human-common")
    return result


def collect_owner_rows(review_dir: Path) -> list[dict]:
    """Owner rows from ``<review_dir>/<stem>/review.json`` and the owner manifest.
    Documents without review output are skipped and named in the result."""
    manifest = corpora.load_owner_manifest()
    rows = []
    missing = []
    for post in manifest["posts"]:
        stem = Path(post["file"]).stem
        path = review_dir / stem / "review.json"
        if not path.is_file():
            missing.append(stem)
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        counts: dict[str, int] = defaultdict(int)
        for finding in body["findings"] + body["document"]:
            if not finding.get("suppressed"):
                counts[finding["rule_id"]] += 1
        rows.append({"group": stem, "label": post["label"], "genre": post["genre"],
                     "words": post["words"], "rules": dict(counts),
                     "confidence": post["confidence"]})
    if missing:
        print(f"skipped without review output: {len(missing)}", file=sys.stderr)
    return rows


def render_markdown(comparisons: dict[str, dict]) -> str:
    lines = ["# Rule lift against human controls (generated)", ""]
    for name, table in comparisons.items():
        lines += [f"## {name}", "", "| rule | lift | CI | AI /10k | human /10k | flags |",
                  "|---|---|---|---|---|---|"]
        for rule, entry in sorted(table.items(), key=lambda kv: -(kv[1]["lift"] or 0)):
            ci = "null" if entry["ci"] is None else f"{entry['ci'][0]:.2f}–{entry['ci'][1]:.2f}"
            lines.append(f"| {rule} | {_fmt(entry['lift'])} | {ci} | {_fmt(entry['ai_per_10k'])} | "
                         f"{_fmt(entry['human_per_10k'])} | {', '.join(flags(entry))} |")
        lines.append("")
    return "\n".join(lines)


def _fmt(value):
    return "null" if value is None else f"{value:.2f}"


def compare(rows: Iterable[dict], ai_label: str, human_label: str, genre: str | None = None) -> dict:
    rows = list(rows)
    universe = sorted({rule for r in rows if genre is None or r["genre"] == genre
                       for rule in r["rules"]})
    ai = rates(rows, ai_label, genre, rules=universe)
    human = rates(rows, human_label, genre, rules=universe)
    table = {}
    for rule in universe:
        table[rule] = lift(ai[rule], human[rule])
    return table


def load_rows(path: Path) -> list[dict]:
    """Rows written by scripts/local_review_rows.py (local derived files; no text)."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_comparisons(owner: list[dict], gao: list[dict], beemo: list[dict],
                      wi: list[dict]) -> dict:
    """Comparison sets from the plan. Owner primary rows exclude medium-confidence posts."""
    primary_owner = [r for r in owner if r.get("confidence", "high") != "medium"]
    genres = sorted({r["genre"] for r in primary_owner})
    out: dict = {}
    out["(a) owner ai_drafted vs owner human (primary)"] = compare(primary_owner, "ai_drafted", "human")
    out["(a-sensitivity) owner incl. medium-confidence post"] = compare(owner, "ai_drafted", "human")
    for genre in genres:
        out[f"(a) owner by genre: {genre}"] = compare(primary_owner, "ai_drafted", "human", genre)
    out["(b) Beemo model_output vs human_output"] = compare(beemo, "ai", "human")
    relabelled_owner = [dict(r, label="ai") for r in primary_owner if r["label"] == "ai_drafted"]
    out["(c) owner ai_drafted vs GAO 2008 (civic human control)"] = compare(
        relabelled_owner + gao, "ai", "human")
    ai_sets = relabelled_owner + [r for r in beemo if r["label"] == "ai"]
    for genre in ("native", "learner"):
        out[f"(d) AI sets vs W&I {genre} (non-native check)"] = compare(
            ai_sets + [r for r in wi], "ai", "human", genre)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--review-dir", type=Path, required=True,
                        help="owner review outputs: <post-stem>/review.json")
    parser.add_argument("--rows-dir", type=Path, required=True,
                        help="local rows from scripts/local_review_rows.py (gao, wi-dev, beemo)")
    parser.add_argument("--out", type=Path, required=True, help="output prefix (committed)")
    args = parser.parse_args(argv)
    owner = collect_owner_rows(args.review_dir)
    comparisons = build_comparisons(
        owner, load_rows(args.rows_dir / "gao.rows.json"),
        load_rows(args.rows_dir / "beemo.rows.json"), load_rows(args.rows_dir / "wi-dev.rows.json"))
    payload = {"comparisons": comparisons,
               "caveats": ["Owner corpus confounds authorship with genre and era (human posts are "
                           "technical tutorials, AI drafts mostly civic).",
                           "W&I uses the dev split only.",
                           "Beemo and GAO texts are local; this file holds aggregates only.",
                           "Owner word counts come from scripts/corpora.py (front matter included)."]}
    args.out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(render_markdown(comparisons), encoding="utf-8")
    print(f"wrote {args.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
