#!/usr/bin/env python3
"""Persist a cached dev/validation quorum sweep from an existing result file.

No detector rerun, no sample text, and no independent-test acceptance.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    ProtocolError,
    load_json,
    metrics,
    sha256_file,
    sweep_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--selection-id", required=True)
    parser.add_argument("--corpus-label", required=True)
    args = parser.parse_args()
    try:
        result = load_json(args.result, "evaluation result")
        split = result.get("split")
        if split not in ("development", "validation"):
            raise ProtocolError("cached sweep is allowed only for development/validation")
        rows = result.get("raw_feature_cache")
        if not isinstance(rows, list) or not rows:
            raise ProtocolError("result has no cached rows")
        if "effective_configuration" not in result:
            raise ProtocolError("result lacks effective settings identity")
        sweeps = {
            str(quorum): metrics(sweep_rows(rows, quorum))
            for quorum in (1, 2, 3)
        }
        recorded = result.get("metrics", {})
        for key in ("confusion_matrix", "covered_count", "abstentions",
                    "operational_failures"):
            if sweeps["2"][key] != recorded.get(key):
                raise ProtocolError(f"cached quorum-2 {key} does not match the result")
        artifact = {
            "schema_version": "1.0.0",
            "selection_id": args.selection_id,
            "status": "selection-observation-not-release-evidence",
            "corpus_label": args.corpus_label,
            "split": split,
            "detector_rerun": False,
            "independent_test_accessed": False,
            "source_result": {
                "path": str(args.result),
                "sha256": sha256_file(args.result),
                "manifest_sha256": result["corpus_identity"]["manifest_sha256"],
                "corpus_content_sha256": result["corpus_identity"]["corpus_content_sha256"],
                "configuration_sha256": result["corpus_identity"]["configuration_sha256"],
                "configuration_source": result["corpus_identity"].get("configuration_source"),
                "effective_settings_sha256": result["effective_configuration"]["settings_sha256"],
                "binary_sha256": result["corpus_identity"]["binary_sha256"],
                "sample_count": result.get("metrics", {}).get("sample_count"),
            },
            "sweeps": {
                quorum: {"quorum": int(quorum), "metrics": value,
                         "use": "cached selection observation only"}
                for quorum, value in sweeps.items()
            },
            "selection": {
                "default_quorum": 2,
                "decision": (
                    "Retain quorum 2 and existing default thresholds unchanged. "
                    "Do not tune candidate thresholds/rules from these outcomes."
                ),
                "thresholds_changed": False,
                "defaults_changed": False,
                "independent_test_performance": False,
            },
            "limitations": [
                "Cached sweep over a biased, partial pilot split; not independent-test performance.",
                "No detector was rerun for this sweep and no sample text is included.",
                "No threshold/rule/default was changed.",
                "Independent-test data was not read or used.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    except (ProtocolError, OSError, ValueError) as error:
        print(f"cached-sweep: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "selection_id": artifact["selection_id"],
        "split": artifact["split"],
        "source_result_sha256": artifact["source_result"]["sha256"],
        "sweeps": {
            quorum: {
                "confusion_matrix": artifact["sweeps"][quorum]["metrics"]["confusion_matrix"],
                "coverage": artifact["sweeps"][quorum]["metrics"]["coverage"],
                "abstentions": artifact["sweeps"][quorum]["metrics"]["abstentions"],
                "precision": artifact["sweeps"][quorum]["metrics"]["precision"],
                "recall": artifact["sweeps"][quorum]["metrics"]["recall"],
                "f1": artifact["sweeps"][quorum]["metrics"]["f1"],
                "fpr": artifact["sweeps"][quorum]["metrics"]["false_positive_rate"],
            }
            for quorum in ("1", "2", "3")
        },
        "detector_rerun": False,
        "independent_test_accessed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
