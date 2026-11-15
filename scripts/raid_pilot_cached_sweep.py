#!/usr/bin/env python3
"""Persist a cached RAID-pilot validation sweep without rerunning the detector.

The input is an existing development/validation result file. The script reuses
its cached family votes, recomputes quorum verdicts with the same protocol code,
and writes a versioned selection artifact. It never opens sample text and never
touches independent-test data.
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

SELECTION_ID = "raid-pilot-v1-validation-cached-sweep-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result", type=pathlib.Path,
        default=pathlib.Path(
            "evaluation/corpora/raid-pilot-v1/results/validation.json"),
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        default=pathlib.Path(
            "evaluation/corpora/raid-pilot-v1/selection/"
            "validation-cached-sweep-v1.json"),
    )
    parser.add_argument("--selection-id", default=SELECTION_ID)
    args = parser.parse_args()
    try:
        result = load_json(args.result, "validation result")
        if result.get("split") != "validation":
            raise ProtocolError("cached sweep requires a validation result")
        rows = result.get("raw_feature_cache")
        if not isinstance(rows, list) or not rows:
            raise ProtocolError("validation result has no cached rows")
        if result.get("content_verification", {}).get("held_out_not_read") is None:
            raise ProtocolError("validation result does not record held-out isolation")
        if result["content_verification"].get("independent_held_out_verified") is not False:
            raise ProtocolError("validation result claims held-out verification")
        if "effective_configuration" not in result:
            raise ProtocolError("validation result lacks effective settings identity")

        sweeps = {}
        for quorum in (1, 2, 3):
            sweeps[str(quorum)] = metrics(sweep_rows(rows, quorum))
        # Quorum 2 is the cached run's actual policy. Verify the cached family
        # sweep agrees with the recorded result before treating it as evidence.
        recorded = result.get("metrics", {})
        recomputed = sweeps["2"]
        for key in ("confusion_matrix", "covered_count", "abstentions",
                    "operational_failures"):
            if recomputed[key] != recorded.get(key):
                raise ProtocolError(
                    f"cached quorum-2 {key} does not match the recorded result"
                )

        artifact = {
            "schema_version": "1.0.0",
            "selection_id": args.selection_id,
            "status": "selection-observation-not-release-evidence",
            "split": "validation",
            "method": (
                "Reused cached family votes from the existing validation result "
                "and recomputed quorum verdicts with evaluation_protocol."
            ),
            "detector_rerun": False,
            "held_out_accessed": False,
            "held_out_sample_count": len(
                result["content_verification"]["held_out_not_read"]
            ),
            "source_result": {
                "path": str(args.result),
                "sha256": sha256_file(args.result),
                "manifest_sha256": result["corpus_identity"]["manifest_sha256"],
                "corpus_content_sha256":
                    result["corpus_identity"]["corpus_content_sha256"],
                "configuration_sha256":
                    result["corpus_identity"]["configuration_sha256"],
                "configuration_source":
                    result["corpus_identity"].get("configuration_source"),
                "effective_settings_sha256":
                    result["effective_configuration"]["settings_sha256"],
                "effective_settings": result["effective_configuration"]["settings"],
                "release_criteria_sha256":
                    result["corpus_identity"].get("release_criteria_sha256"),
                "release_criteria_id":
                    result["corpus_identity"].get("release_criteria_id"),
                "binary_sha256": result["corpus_identity"]["binary_sha256"],
                "engine_identity": result.get("engine_identity"),
                "sample_count": result.get("metrics", {}).get("sample_count"),
            },
            "sweeps": {
                quorum: {
                    "quorum": int(quorum),
                    "metrics": value,
                    "use": "cached selection observation only",
                }
                for quorum, value in sweeps.items()
            },
            "selection": {
                "default_quorum": 2,
                "decision": (
                    "Retain quorum 2 and existing default thresholds unchanged. "
                    "Treat the detector as a conservative lint policy, not a "
                    "useful general authorship detector."
                ),
                "rationale": [
                    "Quorum 1 raises recall on this pilot but produces an "
                    "unacceptable observed false-positive rate.",
                    "Quorum 3 loses coverage and abstains on 54 validation samples.",
                    "Quorum 2 keeps the existing conservative default behavior.",
                ],
                "thresholds_changed": False,
                "defaults_changed": False,
                "selected_from_cached_validation_only": True,
                "independent_test_performance": False,
            },
            "non_claims": [
                "These are selection observations on a biased, partial RAID pilot.",
                "They are not independent-test performance or general accuracy claims.",
                "The pilot omits domains, generators, and human cells; labels are imbalanced.",
                "No threshold or default was changed from this sweep.",
                "No held-out data was opened, run, or tuned against.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (ProtocolError, OSError, ValueError) as error:
        print(f"cached-sweep: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "selection_id": artifact["selection_id"],
        "source_result_sha256": artifact["source_result"]["sha256"],
        "quorums": sorted(artifact["sweeps"]),
        "quorum1": artifact["sweeps"]["1"]["metrics"]["confusion_matrix"],
        "quorum2": artifact["sweeps"]["2"]["metrics"]["confusion_matrix"],
        "quorum3": artifact["sweeps"]["3"]["metrics"]["confusion_matrix"],
        "quorum3_abstentions": artifact["sweeps"]["3"]["metrics"]["abstentions"],
        "thresholds_changed": False,
        "held_out_accessed": False,
        "detector_rerun": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
