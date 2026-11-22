#!/usr/bin/env python3
"""Hotspot validity against owner labels and Beemo editor changes (Plan 5, Task 6).

Two checks, both predeclared:
- Document AUROC of each model's score (opening and full-coverage) for AI vs human, on the
  owner corpus (overall and by genre) and on Beemo (model_output vs human_output).
- Editor overlap: on Beemo, does the top-ranked window overlap an editor's changed spans
  more than the other windows of the same document? Paired within document, bootstrapped
  over prompt groups.

Criteria are written into the report before the run and must be confirmed by the owner.
Promotion requires separate blinded editorial utility evidence. This script reports diagnostics.

Input JSON groups numeric document rows by model and coverage, with editor windows and edit spans in matching coordinates. Only aggregate diagnostics are written.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESAMPLES = 2000
SEED = 0

PROPOSED_CRITERIA = {
    "status": "proposed; owner confirmation required before the run",
    "owner_confirmed": False,
    "editor_overlap_lift_ci_lower_above": 1.0,  # on Beemo
    "auroc_ci_lower_above": 0.6,                # at least one model, full coverage, owner corpus
}


class ValidityError(RuntimeError):
    pass


def auroc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney AUROC with average ranks for ties. labels: 1 = positive (AI)."""
    positives = [s for s, y in zip(scores, labels) if y == 1]
    negatives = [s for s, y in zip(scores, labels) if y == 0]
    if not positives or not negatives:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    rank_sum = sum(ranks[i] for i, y in enumerate(labels) if y == 1)
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def _percentile_ci(values: list[float]) -> list[float] | None:
    if not values:
        return None
    values = sorted(values)
    return [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]


def doc_auroc(rows: list[dict], score_key: str) -> dict:
    """AUROC with a bootstrap CI resampling documents grouped by ``group``.

    Each row: ``{"group", "label": 1 (AI) | 0 (human), score_key: float}``.
    """
    usable = [r for r in rows if r.get(score_key) is not None]
    scores = [float(r[score_key]) for r in usable]
    labels = [int(r["label"]) for r in usable]
    point = auroc(scores, labels)
    by_group: dict[str, list[dict]] = {}
    for r in usable:
        by_group.setdefault(r["group"], []).append(r)
    groups = sorted(by_group)
    rng = random.Random(SEED)
    draws = []
    for _ in range(RESAMPLES):
        picked = [row for _ in groups for row in by_group[groups[rng.randrange(len(groups))]]]
        value = auroc([float(r[score_key]) for r in picked], [int(r["label"]) for r in picked])
        if value is not None:
            draws.append(value)
    return {"auroc": point, "ci": _percentile_ci(draws), "documents": len(usable),
            "groups": len(groups), "score_key": score_key}


def _overlaps(window: dict, spans: list[tuple[int, int]]) -> bool:
    return any(window["start"] < end and start < window["end"] for start, end in spans)


def editor_overlap(documents: list[dict]) -> dict:
    """Paired within document. Each doc: ``{"group", "windows": [{start, end, score}],
    "spans": [(start, end)]}``. Lift = top-window overlap rate / other-window overlap rate,
    pooled over documents, with a bootstrap over prompt groups."""
    per_doc = []
    for doc in documents:
        windows = doc["windows"]
        if len(windows) < 2:
            continue
        top = max(windows, key=lambda w: w["score"])
        others = [w for w in windows if w is not top]
        top_hit = 1.0 if _overlaps(top, doc["spans"]) else 0.0
        other_rate = sum(1.0 for w in others if _overlaps(w, doc["spans"])) / len(others)
        per_doc.append((doc["group"], top_hit, other_rate))
    if not per_doc:
        return {"lift": None, "ci": None, "docs": 0, "groups": 0}

    def lift_of(rows) -> float | None:
        top_mean = sum(t for _, t, _ in rows) / len(rows)
        other_mean = sum(o for _, _, o in rows) / len(rows)
        return top_mean / other_mean if other_mean > 0 else None

    by_group: dict[str, list] = {}
    for row in per_doc:
        by_group.setdefault(row[0], []).append(row)
    groups = sorted(by_group)
    rng = random.Random(SEED)
    draws = []
    for _ in range(RESAMPLES):
        picked = [row for _ in groups for row in by_group[groups[rng.randrange(len(groups))]]]
        value = lift_of(picked)
        if value is not None:
            draws.append(value)
    return {"lift": lift_of(per_doc), "ci": _percentile_ci(draws), "docs": len(per_doc),
            "groups": len(groups)}


def decide(auroc_results: list[dict], overlap: dict, criteria: dict) -> dict:
    """Return pass/fail with the reason for each criterion."""
    reasons = []
    overlap_ci = overlap.get("ci")
    overlap_ok = bool(overlap_ci) and overlap_ci[0] > criteria["editor_overlap_lift_ci_lower_above"]
    reasons.append(f"editor overlap CI lower bound "
                   f"{'> ' if overlap_ok else 'not > '}{criteria['editor_overlap_lift_ci_lower_above']}")
    auroc_ok = any(r.get("ci") and r["ci"][0] > criteria["auroc_ci_lower_above"]
                   for r in auroc_results)
    reasons.append(f"at least one full-coverage AUROC CI lower bound "
                   f"{'> ' if auroc_ok else 'not > '}{criteria['auroc_ci_lower_above']}")
    if criteria.get("owner_confirmed") is not True:
        reasons.append("owner has not confirmed the criteria")
    reasons.append("blinded editorial utility at comparable effort has not been measured")
    return {"validated": False, "diagnostic_thresholds_met": bool(overlap_ok and auroc_ok),
            "reasons": reasons}


def owner_scores(baseline: Path, manifest: Path) -> dict:
    """Join finished model runs to provenance labels and preserve missing evidence."""
    run = json.loads((baseline / "run.json").read_text())
    posts = json.loads(manifest.read_text())["posts"]
    by_file = {row["file"]: row for row in run["documents"]}
    if not run["finished"] or set(by_file) != {post["file"] for post in posts}:
        raise ValidityError("owner baseline is incomplete")
    scores = {}
    models = ("desklib", "conpara", "detectorscope")
    for post in posts:
        entry = by_file[post["file"]]
        if entry["input_sha256"] != post["sha256"] or entry["label"] != post["label"]:
            raise ValidityError("baseline and manifest identities disagree")
        if post["confidence"] != "high":
            continue
        report_path = baseline / Path(post["file"]).stem / "report.json"
        report = json.loads(report_path.read_text()) if report_path.is_file() else {}
        outcomes = {b["backend"]: b["outcome"] for b in report.get("backends", [])}
        for model in models:
            outcome = outcomes.get(model, {})
            details = outcome.get("details", {})
            score = details.get("score", details) if isinstance(details, dict) else {}
            evidence = score.get("model_evidence") or {}
            full = entry.get("backends", {}).get(model) == "scored_full"
            for coverage, value in (("opening", evidence.get("raw_output")),
                                    ("full", evidence.get("full_coverage_output") if full else None)):
                scores.setdefault(model, {}).setdefault(coverage, []).append({
                    "group": post["sha256"], "genre": post["genre"],
                    "label": int(post["label"] == "ai_drafted"), "score": value,
                })
    return scores


def score_summary(rows):
    result = doc_auroc(rows, "score")
    result["missing_documents"] = len(rows) - result["documents"]
    result["by_genre"] = {
        genre: doc_auroc([r for r in rows if r.get("genre") == genre], "score")
        for genre in sorted({r["genre"] for r in rows if "genre" in r})
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--owner-baseline", type=Path, help="finished checkpoint directory")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation/corpora/owner-posts-v1/manifest.json")
    source.add_argument("--input", type=Path,
                        help="JSON with scores keyed by model, each with opening/full rows "
                             "(group, label, score), and editor_documents with group, windows and spans")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data = ({"scores": owner_scores(args.owner_baseline, args.manifest), "editor_documents": []}
            if args.owner_baseline else json.loads(args.input.read_text(encoding="utf-8")))
    scores = {model: {coverage: score_summary(rows) for coverage, rows in modes.items()}
              for model, modes in data["scores"].items()}
    overlap = editor_overlap(data["editor_documents"])
    full = [m["full"] for m in scores.values() if "full" in m]
    output = {"population": "high-confidence owner development posts" if args.owner_baseline else "supplied numeric observations",
              "scores": scores, "editor_overlap": overlap, "criteria": PROPOSED_CRITERIA,
              "decision": decide(full, overlap, PROPOSED_CRITERIA)}
    args.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
