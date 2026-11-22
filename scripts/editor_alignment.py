#!/usr/bin/env python3
"""Do expert editors change what nobotrs flags? (Plan 5, Task 4)

Changed spans come from a word-level diff of whitespace tokens. Spans are byte offsets
into the *before* text, so they line up with source locations. Whitespace-only differences
are not edits. A finding counts once however many spans it overlaps. The baseline draws
random spans of the same lengths in each document (200 draws, seed 0).

Assumption: findings carry ``start`` and ``end`` byte offsets into the document. The
``review`` output schema is Plan 1 and not yet available; check this when it lands.
"""
from __future__ import annotations

import difflib
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

WORD = re.compile(r"\S+")
BASELINE_DRAWS = 200
RESAMPLES = 2000
SEED = 0


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    """(token, byte_start, byte_end) for each non-whitespace run."""
    spans = []
    for match in WORD.finditer(text):
        start = len(text[:match.start()].encode("utf-8"))
        end = start + len(match.group().encode("utf-8"))
        spans.append((match.group(), start, end))
    return spans


def changed_spans(before: str, after: str) -> list[tuple[int, int]]:
    """Byte spans in ``before`` whose words are deleted or replaced in ``after``."""
    before_tokens = _token_spans(before)
    after_tokens = [tok for tok, _, _ in _token_spans(after)]
    matcher = difflib.SequenceMatcher(a=[tok for tok, _, _ in before_tokens], b=after_tokens,
                                      autojunk=False)
    spans: list[tuple[int, int]] = []
    for tag, i1, i2, _, _ in matcher.get_opcodes():
        if tag in ("replace", "delete") and i2 > i1:
            spans.append((before_tokens[i1][1], before_tokens[i2 - 1][2]))
    return _merge(spans)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlaps(finding: dict, span: tuple[int, int]) -> bool:
    return finding["start"] < span[1] and span[0] < finding["end"]


def _ranges(finding: dict) -> list[tuple[int, int]]:
    """A finding's byte ranges. Several ranges are normal for multi-line findings."""
    if "ranges" in finding:
        return [tuple(r) for r in finding["ranges"]]
    return [(finding["start"], finding["end"])]


def _located(findings: list[dict]) -> list[dict]:
    """Findings with at least one byte range. Unlocated findings cannot be aligned."""
    return [f for f in findings if _ranges(f)]


def _range_arrays(findings: list[dict]):
    import numpy as np

    starts, ends, owner = [], [], []
    for index, finding in enumerate(findings):
        for start, end in _ranges(finding):
            starts.append(start)
            ends.append(end)
            owner.append(index)
    owner_arr = np.array(owner, dtype=int)
    boundaries = np.flatnonzero(np.r_[True, owner_arr[1:] != owner_arr[:-1]])
    return (np.array(starts, dtype=float), np.array(ends, dtype=float), owner_arr, boundaries)


def _hit_share(findings: list[dict], spans: list[tuple[int, int]]) -> float | None:
    """Share of located findings with any byte range overlapping any edit span."""
    import numpy as np

    findings = _located(findings)
    if not findings:
        return None
    if not spans:
        return 0.0
    rs, re_, owner, boundaries = _range_arrays(findings)
    sp = np.array(spans, dtype=float)
    overlap = (rs[:, None] < sp[None, :, 1]) & (sp[None, :, 0] < re_[:, None])
    per_range = overlap.any(axis=1)
    per_finding = np.logical_or.reduceat(per_range, boundaries)
    return float(per_finding.mean())


def random_spans(lengths: list[int], text_len: int, rng: random.Random) -> list[tuple[int, int]]:
    spans = []
    for length in lengths:
        if length <= 0 or length > text_len:
            continue
        start = rng.randrange(0, text_len - length + 1)
        spans.append((start, start + length))
    return spans


def alignment(findings: list[dict], spans: list[tuple[int, int]], text_len: int,
              seed: int = 0) -> dict:
    """Share of located findings overlapping an edit, against matched random spans in the same
    document (BASELINE_DRAWS draws of spans with the same lengths)."""
    import numpy as np

    located = _located(findings)
    edited = _hit_share(located, spans)
    lengths = [end - start for start, end in spans]
    baseline = None
    if located and lengths and all(0 < L <= text_len for L in lengths):
        rng = np.random.default_rng(seed)
        starts = np.stack([rng.integers(0, text_len - L + 1, size=BASELINE_DRAWS)
                           for L in lengths], axis=1)                       # (draws, spans)
        ends = starts + np.array(lengths)[None, :]
        rs, re_, owner, boundaries = _range_arrays(located)
        overlap = ((rs[None, :, None] < ends[:, None, :])
                   & (starts[:, None, :] < re_[None, :, None]))             # (draws, ranges, spans)
        per_range = overlap.any(axis=2)                                      # (draws, ranges)
        per_finding = np.logical_or.reduceat(per_range, boundaries, axis=1)  # (draws, findings)
        baseline = float(per_finding.mean(axis=1).mean())
    lift_value = edited / baseline if (edited is not None and baseline) else None
    return {"edited_rate": edited, "baseline_rate": baseline, "lift": lift_value,
            "findings": len(located), "unlocated": len(findings) - len(located),
            "changed_spans": len(spans)}


def aligned_lift(docs: list[dict], seed: int = 0) -> dict:
    """Pooled lift across documents, with a bootstrap CI that resamples prompt groups.

    Each doc: ``{"group", "findings", "spans", "text_len"}``. Per-document statistics are
    computed once; the bootstrap is a draw-by-group count matrix over group totals.
    Edited rate pools findings; the baseline averages documents equally.
    """
    import numpy as np

    per_group: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for doc in docs:
        result = alignment(doc["findings"], doc["spans"], doc["text_len"], seed)
        if result["edited_rate"] is None or result["baseline_rate"] is None:
            continue
        n = len(doc["findings"])
        per_group[doc["group"]].append((round(result["edited_rate"] * n), n,
                                        result["baseline_rate"]))
    groups = sorted(per_group)
    if not groups:
        return {"lift": None, "ci": None, "docs": 0, "groups": 0}
    G = len(groups)
    totals = np.zeros((G, 4))  # hits, findings, baseline sum, documents
    for gi, g in enumerate(groups):
        for hits, n, base in per_group[g]:
            totals[gi] += (hits, n, base, 1)

    def pooled(sums):
        hits, findings, base_sum, n_docs = sums[..., 0], sums[..., 1], sums[..., 2], sums[..., 3]
        with np.errstate(divide="ignore", invalid="ignore"):
            value = (hits / findings) / (base_sum / n_docs)
        return value

    point = pooled(totals.sum(axis=0))
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, G, size=(RESAMPLES, G))
    counts = np.zeros((RESAMPLES, G))
    np.add.at(counts, (np.arange(RESAMPLES)[:, None], draws), 1)
    sums = counts @ totals                              # (RESAMPLES, 4)
    values = pooled(sums)
    values = values[np.isfinite(values)]
    ci = None
    if values.size:
        ci = [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
    point_value = float(point) if np.isfinite(point) else None
    return {"lift": point_value, "ci": ci,
            "docs": int(totals[:, 3].sum()), "groups": G}


def introduced(rules_before: set[str], rules_after: set[str]) -> set[str]:
    """Rules present after editing but absent from the model output (introduced by editors)."""
    return rules_after - rules_before


def run_beemo(out: Path, internal: Path | None = None) -> dict:
    """Pair each Beemo row's model_output with its human_edits, diff them for changed spans,
    and aggregate findings from the local review of model_output.

    Pairing is by Beemo row index, not prompt group, because one prompt can have several rows
    (different generators). Every row is either paired or skipped with a reason, and the
    counts are reported. Reads ``derived/rule-lift/beemo.rows.json`` and
    ``derived/review-batch/beemo``. Writes aggregates only.
    """
    import json

    import corpora  # local import keeps the statistical helpers importable without data

    internal = corpora.internal_dir(internal)
    review_dir = internal / "derived" / "review-batch" / "beemo"
    rows = json.loads((internal / "derived" / "rule-lift" / "beemo.rows.json").read_text())
    if any(r.get("row") is None for r in rows):
        raise SystemExit("beemo.rows.json lacks row indices; rerun scripts/local_review_rows.py beemo")

    by_row: dict[int, dict[str, dict]] = defaultdict(dict)
    duplicates = 0
    for r in rows:
        if r["column"] in by_row[r["row"]]:
            duplicates += 1  # would silently overwrite: count and refuse below
        by_row[r["row"]][r["column"]] = r
    if duplicates:
        raise SystemExit(f"{duplicates} duplicate (row, column) entries; refusing to overwrite")

    skipped: dict[str, int] = defaultdict(int)
    without_findings = 0
    docs_by_rule: dict[str, list[dict]] = defaultdict(list)
    all_docs: list[dict] = []
    introduced: dict[str, int] = defaultdict(int)
    for row_index in sorted(by_row):
        cols = by_row[row_index]
        ai = cols.get("model_output")
        edited = cols.get("human_edits")
        if ai is None:
            skipped["no model_output text"] += 1
            continue
        if edited is None:
            skipped["no human_edits text"] += 1
            continue
        ai_text = (review_dir / f"{ai['doc']}.txt").read_text(encoding="utf-8")
        edit_text = (review_dir / f"{edited['doc']}.txt").read_text(encoding="utf-8")
        spans = changed_spans(ai_text, edit_text)
        findings = ai["findings"]
        text_len = len(ai_text.encode("utf-8"))
        group = str(ai["group"])
        if not _located(findings):
            without_findings += 1
        all_docs.append({"group": group, "findings": findings, "spans": spans, "text_len": text_len})
        for rule in {f["rule_id"] for f in _located(findings)}:
            docs_by_rule[rule].append({"group": group,
                                       "findings": [f for f in findings if f["rule_id"] == rule],
                                       "spans": spans, "text_len": text_len})
        for rule in set(edited["rules"]) - set(ai["rules"]):
            introduced[rule] += 1

    pooled = aligned_lift(all_docs)
    per_rule = {rule: aligned_lift(docs) for rule, docs in sorted(docs_by_rule.items())}
    model_rows_per_prompt = Counter(str(r["group"]) for r in rows if r["column"] == "model_output")
    payload = {
        "rows": len(rows),
        "paired": len(all_docs),
        "docs_without_located_findings": without_findings,
        "docs_used_for_edited_rate": len(all_docs) - without_findings,
        "skipped": dict(sorted(skipped.items())),
        "prompts": len(model_rows_per_prompt),
        "multi_row_prompts": sum(1 for count in model_rows_per_prompt.values() if count > 1),
        "pooled": pooled,
        "per_rule": per_rule,
        "introduced_by_editors": dict(sorted(introduced.items())),
        "caveat": "Editor changes are not ground truth for quality; lift compares findings "
                  "overlapping edited spans with random spans of matched length. Offsets are "
                  "UTF-8 bytes, matching review source ranges.",
    }
    out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# Editor alignment on Beemo (generated)", "",
             f"Rows: {payload['rows']}. Paired: {payload['paired']} (documents without located "
             f"findings: {without_findings}). Skipped: {payload['skipped']}. "
             f"Prompts: {payload['prompts']} ({payload['multi_row_prompts']} with several rows).",
             f"Pooled lift: {_fmt(pooled['lift'])} (CI {_fmt_ci(pooled['ci'])}), groups {pooled['groups']}.",
             "", "| rule | lift | CI | documents |", "|---|---|---|---|"]
    for rule, res in sorted(per_rule.items(), key=lambda kv: -(kv[1]["lift"] or 0)):
        lines.append(f"| {rule} | {_fmt(res['lift'])} | {_fmt_ci(res['ci'])} | {res['docs']} |")
    lines += ["", "Rules introduced by editors (absent from model output):", ""]
    lines += [f"- {rule}: {count} rows" for rule, count in payload["introduced_by_editors"].items()]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def _fmt(value):
    return "null" if value is None else f"{value:.2f}"


def _fmt_ci(ci):
    return "null" if ci is None else f"{ci[0]:.2f}–{ci[1]:.2f}"


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path as _Path

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=_Path, required=True,
                        help="output prefix; writes <prefix>.json and <prefix>.md")
    parser.add_argument("--internal-dir", type=_Path, default=None)
    args = parser.parse_args(argv)
    payload = run_beemo(args.out, args.internal_dir)
    print(f"alignment: {payload['prompts']} prompts; pooled lift {payload['pooled']['lift']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
