#!/usr/bin/env python3
"""Metadata-only summary of an existing evaluation result file.

Adds fixed-seed source-component cluster bootstrap uncertainty to precision,
recall, F1, false-positive rate, and coverage. It does not run the detector and
does not read corpus text or sample payloads.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    LABELS,
    ProtocolError,
    VERDICTS,
    load_json,
    metrics as protocol_metrics,
    sha256_file,
)

SEED = "evaluation-cluster-bootstrap-v1-2026-11-14"
REPLICATES = 2000
METRICS = ("precision", "recall", "f1", "false_positive_rate", "coverage")
DENOMINATORS = {
    "precision": "tp+fp",
    "recall": "tp+fn",
    "f1": "2*tp+fp+fn",
    "false_positive_rate": "fp+tn",
    "coverage": "labeled",
}
LIMITATIONS = [
    "Cluster bootstrap resamples source components from this result; it is not a fresh corpus or independent sample.",
    "Pilot source selection is biased and partial; missing domains, generators, cells, and attacks are disclosed in the corpus documentation.",
    "No independently labeled nonnative-speaker or human-edited material is available; native-speaker status is not inferred.",
    "Per-generator slices necessarily separate correlated human/generated answers; overall and source/domain slices retain source-component clustering.",
    "No AUC is reported because the detector has no continuous calibrated ensemble score.",
    "Clustered bootstrap cannot establish small false-positive-rate certification from tiny or biased samples.",
    "All-identical replicate distributions return null bounds; they are not evidence of zero risk.",
    "No pseudo-independent binomial intervals are applied to clustered human/generated rows.",
    "This tool does not run the detector and does not read sample text; it summarizes an existing result file.",
]


def validate_rows(rows):
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ProtocolError(f"row {index} is not an object")
        label = row.get("label")
        if label is not None and label not in LABELS:
            raise ProtocolError(f"row {index} has invalid label {label!r}")
        verdict = row.get("verdict")
        if verdict not in VERDICTS:
            raise ProtocolError(f"row {index} has invalid verdict {verdict!r}")
        if not isinstance(row.get("complete"), bool):
            raise ProtocolError(f"row {index} complete must be boolean")
        if not isinstance(row.get("source_group"), str) or not row["source_group"]:
            raise ProtocolError(f"row {index} lacks a source_group")
        runtime = row.get("runtime_seconds")
        if runtime is not None:
            if isinstance(runtime, bool) or not isinstance(runtime, (int, float)):
                raise ProtocolError(f"row {index} runtime_seconds must be numeric")
            if not math.isfinite(runtime) or runtime < 0:
                raise ProtocolError(f"row {index} runtime_seconds must be finite and nonnegative")


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def row_metrics(rows):
    labeled = [row for row in rows if row.get("label") in LABELS]
    unknown = [row for row in rows if row.get("label") not in LABELS]
    covered = [row for row in labeled
               if row.get("complete") and row.get("verdict") != "inconclusive"]
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for row in covered:
        if row["label"] == "generated":
            counts["tp" if row["verdict"] == "flagged" else "fn"] += 1
        else:
            counts["fp" if row["verdict"] == "flagged" else "tn"] += 1
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    return {
        "sample_count": len(rows),
        "labeled_count": len(labeled),
        "unknown_label_count": len(unknown),
        "covered_count": len(covered),
        "coverage": ratio(len(covered), len(labeled)),
        "abstentions": sum(row.get("complete") and row.get("verdict") == "inconclusive"
                           for row in labeled),
        "unknown_label_abstentions": sum(
            row.get("complete") and row.get("verdict") == "inconclusive"
            for row in unknown
        ),
        "operational_failures": sum(not row.get("complete") for row in rows),
        "confusion_matrix": counts,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "auc": None,
        "auc_reason": "No continuous calibrated ensemble score; discrete verdicts do not support AUC.",
    }


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def metric_values(rows):
    metrics = row_metrics(rows)
    return {name: metrics[name] for name in METRICS}


def bootstrap_metric(values, point, denominator, replicates):
    if not values:
        return {
            "estimate": point,
            "lower": None,
            "upper": None,
            "valid_replicates": 0,
            "total_replicates": replicates,
            "denominator": denominator,
            "degenerate": True,
            "reason": "No valid replicates: zero denominator.",
        }
    if len(set(values)) == 1:
        return {
            "estimate": point,
            "lower": None,
            "upper": None,
            "valid_replicates": len(values),
            "total_replicates": replicates,
            "denominator": denominator,
            "degenerate": True,
            "reason": "All valid replicate values identical; no observed variation, so unseen-error uncertainty is not estimable.",
        }
    return {
        "estimate": point,
        "lower": percentile(values, 0.025),
        "upper": percentile(values, 0.975),
        "valid_replicates": len(values),
        "total_replicates": replicates,
        "denominator": denominator,
        "degenerate": False,
        "reason": None,
    }


def cluster_bootstrap(rows, *, seed=SEED, replicates=REPLICATES):
    if not isinstance(replicates, int) or replicates < 1:
        raise ProtocolError("replicates must be a positive integer")
    clusters = {}
    for row in rows:
        group = row.get("source_group")
        if not isinstance(group, str) or not group:
            raise ProtocolError("result rows lack source_group; regenerate with the current evaluator")
        clusters.setdefault(group, []).append(row)
    cluster_ids = sorted(clusters)
    point = protocol_metrics(rows)
    values = {name: [] for name in METRICS}
    rng = random.Random(seed)
    for _ in range(replicates):
        sampled = [clusters[cluster_ids[rng.randrange(len(cluster_ids))]]
                   for _ in cluster_ids]
        replicate_rows = [row for cluster in sampled for row in cluster]
        replicate = metric_values(replicate_rows)
        for name in METRICS:
            if replicate[name] is not None:
                values[name].append(replicate[name])
    return {
        "cluster_key": "source_group",
        "cluster_count": len(cluster_ids),
        "seed": seed,
        "replicates": replicates,
        "confidence": 0.95,
        "metrics": {
            name: bootstrap_metric(values[name], point[name], DENOMINATORS[name], replicates)
            for name in METRICS
        },
    }


def slice_report(rows, dimension, *, seed=SEED, replicates=REPLICATES):
    values = sorted({str(row.get("dimension_values", {}).get(dimension))
                     for row in rows
                     if row.get("dimension_values", {}).get(dimension) is not None})
    output = {}
    for value in values:
        selected = [
            row for row in rows
            if str(row.get("dimension_values", {}).get(dimension)) == value
        ]
        metrics = protocol_metrics(selected)
        output[value] = {
            "sample_count": len(selected),
            "metrics": metrics,
            "bootstrap": cluster_bootstrap(selected, seed=seed, replicates=replicates),
        }
    return output


def runtime_summary(rows):
    values = [row["runtime_seconds"] for row in rows
              if isinstance(row.get("runtime_seconds"), (int, float))
              and not isinstance(row.get("runtime_seconds"), bool)]
    if not values:
        return {"sample_count": 0, "total_seconds": None, "mean_seconds": None,
                "p95_seconds": None}
    values.sort()
    return {
        "sample_count": len(values),
        "total_seconds": sum(values),
        "mean_seconds": sum(values) / len(values),
        "p95_seconds": percentile(values, 0.95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--replicates", type=int, default=REPLICATES)
    parser.add_argument("--seed", default=SEED)
    args = parser.parse_args()
    try:
        result = load_json(args.result, "evaluation result")
        rows = result.get("raw_feature_cache")
        if not isinstance(rows, list) or not rows:
            raise ProtocolError("result has no raw_feature_cache rows")
        split = result.get("split")
        if split not in ("regression", "development", "validation", "independent-test"):
            raise ProtocolError("result split is invalid")
        validate_rows(rows)
        overall_metrics = protocol_metrics(rows)
        bootstrap = cluster_bootstrap(rows, seed=args.seed, replicates=args.replicates)
        slices = {
            "source": slice_report(rows, "corpus_source", seed=args.seed,
                                   replicates=args.replicates),
            "domain": slice_report(rows, "domain", seed=args.seed,
                                   replicates=args.replicates),
            "generator": slice_report(rows, "generator", seed=args.seed,
                                      replicates=args.replicates),
        }
        for optional in ("attack", "language_hint", "length_bucket"):
            values = {str(row.get("dimension_values", {}).get(optional))
                      for row in rows
                      if row.get("dimension_values", {}).get(optional) is not None}
            if len(values) > 1:
                slices[optional] = slice_report(rows, optional, seed=args.seed,
                                                replicates=args.replicates)
        identity = result.get("corpus_identity", {})
        output = {
            "schema_version": "1.0.0",
            "summary_id": "evaluation-cluster-bootstrap-v1",
            "source_result": {
                "path": str(args.result),
                "sha256": sha256_file(args.result),
                "split": split,
                "corpus_version": result.get("corpus_version"),
                "manifest_sha256": identity.get("manifest_sha256"),
                "corpus_content_sha256": identity.get("corpus_content_sha256"),
                "configuration_sha256": identity.get("configuration_sha256"),
                "configuration_source": identity.get("configuration_source"),
                "effective_settings_sha256": result.get("effective_configuration", {}).get("settings_sha256"),
                "binary_sha256": identity.get("binary_sha256"),
                "retirement": result.get("retirement"),
                "content_verification": result.get("content_verification"),
            },
            "method": {
                "cluster_bootstrap": True,
                "cluster_key": "source_group",
                "seed": args.seed,
                "replicates": args.replicates,
                "confidence_interval": "percentile 2.5/97.5; null bounds when all valid replicate values are identical",
                "no_auc": True,
            },
            "overall": {
                "metrics": overall_metrics,
                "bootstrap": bootstrap,
            },
            "slices": slices,
            "runtime": runtime_summary(rows),
            "abstentions": {
                "labeled": overall_metrics["abstentions"],
                "unknown_label": overall_metrics["unknown_label_abstentions"],
                "operational_failures": overall_metrics["operational_failures"],
            },
            "auc": None,
            "auc_reason": overall_metrics["auc_reason"],
            "limitations": LIMITATIONS,
            "detector_run": False,
            "sample_text_included": False,
        }
        args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    except (ProtocolError, OSError, ValueError) as error:
        print(f"summarize-evaluation: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "split": output["source_result"]["split"],
        "samples": output["overall"]["metrics"]["sample_count"],
        "clusters": output["overall"]["bootstrap"]["cluster_count"],
        "replicates": output["overall"]["bootstrap"]["replicates"],
        "metrics": {
            name: {
                "estimate": output["overall"]["bootstrap"]["metrics"][name]["estimate"],
                "lower": output["overall"]["bootstrap"]["metrics"][name]["lower"],
                "upper": output["overall"]["bootstrap"]["metrics"][name]["upper"],
                "valid_replicates": output["overall"]["bootstrap"]["metrics"][name]["valid_replicates"],
            }
            for name in METRICS
        },
        "auc": None,
        "detector_run": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
