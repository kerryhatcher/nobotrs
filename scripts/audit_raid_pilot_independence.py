#!/usr/bin/env python3
"""Audit split stability and evaluated-sample independence for the RAID pilot.

The audit reads only manifest metadata and development/validation result files.
It does not open independent-test sample text and does not run the detector.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import curate_raid_pilot as curator  # noqa: E402
from evaluation_protocol import (  # noqa: E402
    corpus_content_sha256,
    load_json,
    load_retirement,
    sha256_bytes,
    sha256_file,
    validate_manifest,
    validate_retirement,
)

# Recorded from the three corpus generations produced before the final report.
# Only provenance/metadata changed; the corpus content identity is invariant.
RECORDED_GENERATIONS = [
    {
        "generation": 1,
        "manifest_sha256": "9af3b6527eaab1a3b8969ed6dade098a95931d07a31f8993f2b9da441693e346",
        "corpus_content_sha256": "349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d",
        "splits": {"development": 662, "validation": 220, "independent-test": 218},
        "components": {"development": 146, "validation": 62, "independent-test": 42},
        "change": "initial corpus; original absolute-path acquisition record copied",
        "predictions": "first development/validation predictions were produced after this generation",
    },
    {
        "generation": 2,
        "manifest_sha256": "24fea2955289c1ec7946763f694556fe43dfc7b7d2cf94a4ae36dc021410ab63",
        "corpus_content_sha256": "349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d",
        "splits": {"development": 662, "validation": 220, "independent-test": 218},
        "components": {"development": 146, "validation": 62, "independent-test": 42},
        "change": "metadata-only: portable relative acquisition paths and fixed retrieved metadata",
    },
    {
        "generation": 3,
        "manifest_sha256": "dcc538e2fe6dcbb7ad5ff99dc0886d235f105297be161ee77f40745d8ed3ddfa",
        "corpus_content_sha256": "349a0c64684e30b31f2f893547cceaf30609354d33aa5a266332bc84e2d5858d",
        "splits": {"development": 662, "validation": 220, "independent-test": 218},
        "components": {"development": 146, "validation": 62, "independent-test": 42},
        "change": "metadata-only: upstream retrieval provenance fields added",
    },
]

ADDITIONAL_POETRY_SOURCE = "527dc536-7b69-4c2f-94af-afeb85894a07"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def id_set_sha256(ids) -> str:
    return sha256_bytes(("\n".join(sorted(ids)) + "\n").encode("utf-8"))


def display_path(path: pathlib.Path, corpus: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(corpus.resolve()))
    except ValueError:
        return path.name


def result_ids(result: dict) -> list[str]:
    rows = result.get("raw_feature_cache")
    require(isinstance(rows, list) and rows, "result has no raw_feature_cache")
    ids = [row.get("id") for row in rows]
    require(all(isinstance(value, str) and value for value in ids),
            "result contains an invalid sample ID")
    require(len(ids) == len(set(ids)), "result contains duplicate sample IDs")
    return ids


def reassign_from_manifest(manifest: dict) -> dict[str, str]:
    """Reproduce the deterministic split from manifest metadata only."""
    samples = manifest["samples"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        groups[sample["near_duplicate_group"]].append(sample)
    forced = set(manifest.get("split_policy", {}).get("forced_to_development", []))
    components = []
    for members in groups.values():
        ids = sorted(sample["id"] for sample in members)
        source_groups = {sample["source_group"] for sample in members}
        require(len(source_groups) == 1,
                "a near-duplicate component spans multiple source groups")
        sources = sorted({sample["source_id"] for sample in members})
        components.append({
            "id": "component:" + sha256_bytes(
                "\n".join(ids).encode("utf-8")
            )[:32],
            "members": members,
            "sources": sources,
            "forced": bool(set(sources) & forced),
        })
    assignment = curator.assign_splits(components)
    for component in components:
        for member in component["members"]:
            require(assignment[component["id"]] == member["split"],
                    f"deterministic reassignment differs for {member['id']}")
    return assignment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/raid-pilot-v1"))
    parser.add_argument("--development-result", type=pathlib.Path,
                        default=pathlib.Path(
                            "evaluation/corpora/raid-pilot-v1/results/development.json"))
    parser.add_argument("--validation-result", type=pathlib.Path,
                        default=pathlib.Path(
                            "evaluation/corpora/raid-pilot-v1/results/validation.json"))
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path(
                            "evaluation/corpora/raid-pilot-v1/independence-audit.json"))
    args = parser.parse_args()
    try:
        manifest_path = args.corpus / "manifest.json"
        manifest = load_json(manifest_path, "manifest")
        info = validate_manifest(
            manifest, manifest_path, split="development",
            require_content_hashes=True, require_near_duplicate_groups=True,
        )
        retirement = load_retirement(args.corpus)
        retirement_info = (
            validate_retirement(retirement, info) if retirement else None
        )
        manifest_hash = sha256_file(manifest_path)
        computed_content = corpus_content_sha256(info.samples)
        require(computed_content == manifest.get("corpus_content_sha256"),
                "manifest content hash does not match its samples")
        recorded_content = {
            generation["corpus_content_sha256"] for generation in RECORDED_GENERATIONS
        }
        require(recorded_content == {computed_content},
                "recorded generations did not share the current corpus content hash")
        recorded_splits = {
            json.dumps(generation["splits"], sort_keys=True)
            for generation in RECORDED_GENERATIONS
        }
        current_splits = manifest["counts"]["splits"]
        require(recorded_splits == {json.dumps(current_splits, sort_keys=True)},
                "recorded generations did not share the current split counts")

        dev_result = load_json(args.development_result, "development result")
        val_result = load_json(args.validation_result, "validation result")
        for result, split, path in (
            (dev_result, "development", args.development_result),
            (val_result, "validation", args.validation_result),
        ):
            require(result.get("split") == split, f"{path} has the wrong split")
            require(result["corpus_identity"]["manifest_sha256"] == manifest_hash,
                    f"{path} does not bind the current manifest")
            require(result["corpus_identity"]["corpus_content_sha256"] == computed_content,
                    f"{path} does not bind the current corpus content hash")
            require(result["content_verification"]["independent_held_out_verified"] is False,
                    f"{path} opened held-out text")
            require(not (args.corpus / "results" / "independent-test.json").exists(),
                    "an independent-test result file exists")

        dev_ids = result_ids(dev_result)
        val_ids = result_ids(val_result)
        manifest_dev_ids = sorted(sample["id"] for sample in info.samples
                                  if sample["split"] == "development")
        manifest_val_ids = sorted(sample["id"] for sample in info.samples
                                  if sample["split"] == "validation")
        independent_ids = {sample["id"] for sample in info.samples
                           if sample["split"] == "independent-test"}
        require(sorted(dev_ids) == manifest_dev_ids,
                "development result IDs do not match the manifest development set")
        require(sorted(val_ids) == manifest_val_ids,
                "validation result IDs do not match the manifest validation set")
        require(not (set(dev_ids) & set(val_ids)),
                "development and validation evaluated IDs overlap")
        require(not (set(dev_ids) & independent_ids),
                "a development evaluated ID is in the independent set")
        require(not (set(val_ids) & independent_ids),
                "a validation evaluated ID is in the independent set")

        assignment = reassign_from_manifest(manifest)
        by_id = {sample["id"]: sample for sample in info.samples}
        # Check every member explicitly; this also exercises the reused curator.
        component_members = defaultdict(list)
        for sample in info.samples:
            component_members[sample["near_duplicate_group"]].append(sample)
        for members in component_members.values():
            ids = sorted(sample["id"] for sample in members)
            component_id = "component:" + sha256_bytes(
                "\n".join(ids).encode("utf-8")
            )[:32]
            expected = assignment[component_id]
            require(all(sample["split"] == expected for sample in members),
                    f"deterministic reassignment differs for component {component_id}")

        poetry_samples = [sample for sample in info.samples
                          if sample["source_id"] == ADDITIONAL_POETRY_SOURCE]
        require(poetry_samples, "additional poetry source is absent")
        require(all(sample["split"] == "development" for sample in poetry_samples),
                "additional poetry source is not entirely in development")
        require(ADDITIONAL_POETRY_SOURCE in
                set(manifest["split_policy"].get("forced_to_development", [])),
                "additional poetry source is not declared forced to development")

        access_like = sorted(
            path.name for path in args.corpus.rglob("*")
            if path.is_file() and (
                "access" in path.name.lower() or path.suffix == ".lock"
            )
        )
        require(not access_like,
                f"unexpected access/lock artifacts exist: {access_like}")

        evaluated_hashes = {
            sample_id: by_id[sample_id]["content_sha256"]
            for sample_id in sorted(set(dev_ids) | set(val_ids))
        }
        audit = {
            "schema_version": "1.0.0",
            "status": (
                "independence-audit-passed-retired" if retirement_info
                else "independence-audit-passed"
            ),
            "manifest_sha256": manifest_hash,
            "corpus_content_sha256": computed_content,
            "current_splits": current_splits,
            "current_components": manifest["counts"]["split_components"],
            "recorded_generations": RECORDED_GENERATIONS,
            "metadata_only_change_evidence": {
                "claim": (
                    "No source/component changed split after the first "
                    "development/validation predictions were produced."
                ),
                "reason": (
                    "corpus_content_sha256 includes each sample's id, file, split, "
                    "source_group, label, slice, and content_sha256. It was "
                    "identical in every recorded generation, so the evaluated "
                    "split and sample-ID assignments were identical."
                ),
                "manifest_hashes_changed_only_with_provenance_metadata": True,
                "split_counts_changed": False,
                "sample_ids_changed": False,
                "components_changed": False,
                "no_reshuffle": True,
                "deterministic_reassignment_from_manifest_matches": True,
            },
            "additional_forced_source": {
                "source_id": ADDITIONAL_POETRY_SOURCE,
                "provenance": (
                    "Displayed during response-schema inspection in this session; "
                    "added to SESSION_VIEWED_SOURCE_IDS in the initial curator "
                    "implementation before the first corpus generation."
                ),
                "timing": (
                    "Forced into development before any detector predictions. "
                    "The first generated corpus already had 662 development "
                    "samples and content hash 349a0c..., unchanged through all "
                    "later metadata-only regenerations."
                ),
                "split": "development",
                "all_samples_in_development": True,
                "predictions_after_exclusion": True,
            },
            "evaluated_samples": {
                "development": {
                    "count": len(dev_ids),
                    "sample_ids": sorted(dev_ids),
                    "id_set_sha256": id_set_sha256(dev_ids),
                },
                "validation": {
                    "count": len(val_ids),
                    "sample_ids": sorted(val_ids),
                    "id_set_sha256": id_set_sha256(val_ids),
                },
                "combined_id_set_sha256": id_set_sha256(list(dev_ids) + list(val_ids)),
                "content_sha256_by_id": evaluated_hashes,
                "result_files": {
                    "development": {
                        "path": display_path(args.development_result, args.corpus),
                        "sha256": sha256_file(args.development_result),
                    },
                    "validation": {
                        "path": display_path(args.validation_result, args.corpus),
                        "sha256": sha256_file(args.validation_result),
                    },
                },
            },
            "held_out": {
                "split": "independent-test",
                "sample_count": len(independent_ids),
                "id_set_sha256": id_set_sha256(independent_ids),
                "text_or_detector_results_opened": False,
                "content_exposed_by_git_diff_check": bool(retirement_info),
                "retired_as_selection_data": bool(retirement_info),
                "unopened_claim_superseded": bool(retirement_info),
                "independent_assessment_allowed": not bool(retirement_info),
                "freeze_allowed": not bool(retirement_info),
                "access_record_claimed": False,
                "evaluated_ids_are_disjoint": True,
                "preserved_evaluated_ids_are_reserved_for_development_or_validation": True,
            },
            "retirement": retirement_info or {"status": "not-retired"},
            "checks": {
                "current_manifest_content_hash_matches_declared": True,
                "recorded_generations_share_content_hash": True,
                "recorded_generations_share_split_counts": True,
                "deterministic_reassignment_matches_manifest": True,
                "development_result_ids_match_manifest": True,
                "validation_result_ids_match_manifest": True,
                "evaluated_ids_disjoint": True,
                "evaluated_ids_absent_from_independent": True,
                "additional_forced_source_all_development": True,
                "results_bind_current_manifest": True,
                "independent_text_not_opened": True,
                "no_access_record_claimed": True,
                "no_reshuffle": True,
                "retirement_ledger_matches_manifest": bool(retirement_info),
                "retirement_blocks_independent_assessment": bool(retirement_info),
            },
        }
        args.output.write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (ValueError, OSError) as error:
        print(f"independence-audit: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": audit["status"],
        "manifest_sha256": audit["manifest_sha256"],
        "corpus_content_sha256": audit["corpus_content_sha256"],
        "splits": audit["current_splits"],
        "development_evaluated": audit["evaluated_samples"]["development"]["count"],
        "validation_evaluated": audit["evaluated_samples"]["validation"]["count"],
        "held_out_sample_count": audit["held_out"]["sample_count"],
        "retirement_status": audit["retirement"]["status"],
        "independent_assessment_allowed":
            audit["held_out"]["independent_assessment_allowed"],
        "no_split_or_sample_id_changes": True,
        "no_reshuffle": True,
        "access_record_claimed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
