#!/usr/bin/env python3
"""Preflight the joint HC3 + fresh RAID assessment pilot without detector runs.

Only development/validation sample text is read for hash/grouping verification.
Independent-test files are never opened. Output is metadata and identity only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    SCHEMA_VERSION,
    ProtocolError,
    corpus_content_sha256,
    decode_sample_bytes,
    load_json,
    read_sample_bytes,
    sha256_bytes,
    sha256_file,
    validate_config,
    validate_criteria,
    validate_grouping,
    validate_manifest,
)

HC3_DATASET = "Hello-SimpleAI/HC3"
HC3_REVISION = "4d0ff18143b5a7e1b1e79beb540c04549d1e59d3"
HC3_LICENSE = "CC-BY-SA-4.0"
RAID_DATASET = "liamdugan/raid"
RAID_REVISION = "865cac74188466cb0c3b7574a10204007b57a459"
RAID_LICENSE = "MIT"
HC3_FORCED_IDS = set(range(15))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def validate_retrieval(value: dict, label: str) -> None:
    require(isinstance(value.get("retrieved"), str) and value["retrieved"],
            f"{label} retrieved is missing")
    require(isinstance(value.get("retrieved_timezone"), str)
            and value["retrieved_timezone"], f"{label} retrieved_timezone is missing")


def verify_hc3(corpus: pathlib.Path, manifest: dict) -> dict:
    root = corpus / "source" / "hc3"
    acquisition_path = root / "acquisition.json"
    card_path = root / "dataset-card.md"
    require(acquisition_path.is_file() and card_path.is_file(),
            "HC3 source snapshot is incomplete")
    acquisition = load_json(acquisition_path, "HC3 acquisition")
    snapshot = manifest["source_snapshots"]["hc3"]
    require(sha256_file(acquisition_path) == snapshot["acquisition_sha256"],
            "HC3 portable acquisition hash mismatch")
    require(acquisition.get("dataset") == HC3_DATASET, "HC3 dataset pin mismatch")
    require(acquisition.get("revision") == HC3_REVISION, "HC3 revision pin mismatch")
    require(str(acquisition.get("declared_license", "")).upper() == HC3_LICENSE,
            "HC3 license mismatch")
    require(acquisition.get("portable_snapshot") is True,
            "HC3 acquisition is not portable")
    require(acquisition.get("acquisition_sha256") ==
            snapshot["upstream_acquisition_sha256"],
            "HC3 upstream acquisition hash mismatch")
    require(sha256_file(card_path) == snapshot["dataset_card_sha256"],
            "HC3 dataset card hash mismatch")
    require(acquisition.get("dataset_card_sha256") == snapshot["dataset_card_sha256"],
            "HC3 acquisition card hash mismatch")
    require("license: cc-by-sa-4.0" in card_path.read_text(encoding="utf-8").lower(),
            "HC3 card does not declare CC-BY-SA-4.0")
    validate_retrieval(acquisition, "HC3 acquisition")
    require(acquisition["retrieved"] == snapshot["retrieved"],
            "HC3 retrieval date mismatch")
    require(acquisition["retrieved_timezone"] == snapshot["retrieved_timezone"],
            "HC3 retrieval timezone mismatch")
    require("/tmp/" not in acquisition_path.read_text(encoding="utf-8"),
            "HC3 acquisition embeds an absolute temporary path")
    responses = acquisition.get("responses")
    require(isinstance(responses, list) and responses, "HC3 responses are missing")
    for index, response in enumerate(responses):
        declared = pathlib.Path(str(response.get("file")))
        require(not declared.is_absolute() and ".." not in declared.parts
                and declared.parts[:1] == ("responses",),
                f"HC3 response {index} path is not relative")
        path = root / declared
        require(path.is_file(), f"HC3 response {path.name} is missing")
        require(sha256_file(path) == response.get("sha256"),
                f"HC3 response {path.name} hash mismatch")
    require(snapshot["response_count"] == len(responses),
            "HC3 response count mismatch")
    return {
        "acquisition_sha256": snapshot["acquisition_sha256"],
        "upstream_acquisition_sha256": snapshot["upstream_acquisition_sha256"],
        "dataset_card_sha256": snapshot["dataset_card_sha256"],
        "response_count": len(responses),
        "license": HC3_LICENSE,
        "retrieved": snapshot["retrieved"],
        "retrieved_timezone": snapshot["retrieved_timezone"],
    }


def verify_raid(corpus: pathlib.Path, manifest: dict) -> dict:
    root = corpus / "source" / "raid-fresh"
    acquisition_path = root / "acquisition.json"
    card_path = root / "dataset-card.md"
    license_path = root / "LICENSE"
    require(all(path.is_file() for path in (acquisition_path, card_path, license_path)),
            "RAID fresh source snapshot is incomplete")
    acquisition = load_json(acquisition_path, "RAID fresh acquisition")
    snapshot = manifest["source_snapshots"]["raid_fresh"]
    require(sha256_file(acquisition_path) == snapshot["acquisition_sha256"],
            "RAID fresh portable acquisition hash mismatch")
    require(acquisition.get("dataset") == RAID_DATASET, "RAID fresh dataset pin mismatch")
    require(acquisition.get("revision") == RAID_REVISION, "RAID fresh revision pin mismatch")
    require(RAID_LICENSE.lower() in str(acquisition.get("upstream_license", "")).lower(),
            "RAID fresh license mismatch")
    require(acquisition.get("portable_snapshot") is True,
            "RAID fresh acquisition is not portable")
    require(acquisition.get("original_acquisition_sha256") ==
            snapshot["upstream_acquisition_sha256"],
            "RAID fresh upstream acquisition hash mismatch")
    require(sha256_file(card_path) == snapshot["dataset_card_sha256"],
            "RAID fresh card hash mismatch")
    require(sha256_file(license_path) == snapshot["license_sha256"],
            "RAID fresh license hash mismatch")
    require("license: mit" in card_path.read_text(encoding="utf-8").lower(),
            "RAID fresh card does not declare MIT")
    license_text = license_path.read_text(encoding="utf-8")
    require("MIT License" in license_text and "Liam Dugan" in license_text,
            "RAID fresh LICENSE is not the upstream Liam Dugan notice")
    validate_retrieval(acquisition, "RAID fresh acquisition")
    require(acquisition["retrieved"] == snapshot["retrieved"],
            "RAID fresh retrieval date mismatch")
    require(acquisition["retrieved_timezone"] == snapshot["retrieved_timezone"],
            "RAID fresh retrieval timezone mismatch")
    require("/tmp/" not in acquisition_path.read_text(encoding="utf-8"),
            "RAID fresh acquisition embeds an absolute temporary path")
    queries = acquisition.get("queries")
    require(isinstance(queries, list) and queries, "RAID fresh queries are missing")
    for index, query in enumerate(queries):
        declared = pathlib.Path(str(query.get("file")))
        require(not declared.is_absolute() and ".." not in declared.parts
                and declared.parts[:1] == ("responses",),
                f"RAID fresh query {index} path is not relative")
        path = root / declared
        require(path.is_file(), f"RAID fresh response {path.name} is missing")
        require(sha256_file(path) == query.get("sha256"),
                f"RAID fresh response {path.name} hash mismatch")
    require(snapshot["response_count"] == len(queries),
            "RAID fresh response count mismatch")
    return {
        "acquisition_sha256": snapshot["acquisition_sha256"],
        "upstream_acquisition_sha256": snapshot["upstream_acquisition_sha256"],
        "dataset_card_sha256": snapshot["dataset_card_sha256"],
        "license_sha256": snapshot["license_sha256"],
        "response_count": len(queries),
        "license": RAID_LICENSE,
        "retrieved": snapshot["retrieved"],
        "retrieved_timezone": snapshot["retrieved_timezone"],
    }


def verify_old_exclusion(corpus: pathlib.Path, manifest: dict, info) -> dict:
    policy = manifest.get("exclusion_policy", {})
    old_path = corpus.parent / str(policy.get("old_corpus", "raid-pilot-v1"))
    if not old_path.exists():
        old_path = pathlib.Path(str(policy.get("old_corpus", "evaluation/corpora/raid-pilot-v1")))
    if not old_path.exists():
        old_path = corpus.parent / "raid-pilot-v1"
    manifest_path = old_path / "manifest.json"
    retirement_path = old_path / "retirement.json"
    require(manifest_path.is_file() and retirement_path.is_file(),
            "old RAID v1 identity is missing")
    old_manifest = load_json(manifest_path, "old RAID v1 manifest")
    retirement = load_json(retirement_path, "old RAID v1 retirement")
    require(sha256_file(manifest_path) == policy.get("old_manifest_sha256"),
            "old RAID v1 manifest hash mismatch")
    require(old_manifest.get("corpus_content_sha256") ==
            policy.get("old_corpus_content_sha256"),
            "old RAID v1 content hash mismatch")
    require(sha256_file(retirement_path) == policy.get("old_retirement_sha256"),
            "old RAID v1 retirement hash mismatch")
    require(retirement.get("status") == "retired-exposed-selection-data",
            "old RAID v1 is not retired")
    old_sources = {sample["source_id"] for sample in old_manifest["samples"]}
    leaking = [sample["id"] for sample in info.samples
               if sample.get("corpus_source") == "raid-fresh"
               and sample.get("source_id") in old_sources]
    require(not leaking, f"fresh RAID source_id overlaps old RAID v1: {leaking[:5]}")
    audit_path = corpus / str(manifest.get("curation_audit", "curation.json"))
    audit = load_json(audit_path, "assessment curation audit")
    require(audit.get("manifest_sha256") == info.raw_sha256,
            "assessment audit does not bind the manifest")
    require(audit.get("corpus_content_sha256") == info.corpus_content_sha256,
            "assessment audit does not bind the content hash")
    require(audit.get("claims", {}).get("detector_run") is False,
            "assessment audit claims a detector run")
    require(audit.get("claims", {}).get("independent_test_opened") is False,
            "assessment audit claims independent-test access")
    exclusions = audit.get("old_corpus_exclusions", {}).get("excluded_counts", {})
    require(exclusions == policy.get("excluded_counts"),
            "exclusion counts do not match the manifest")
    return {
        "old_manifest_sha256": policy["old_manifest_sha256"],
        "old_corpus_content_sha256": policy["old_corpus_content_sha256"],
        "old_retirement_sha256": policy["old_retirement_sha256"],
        "old_retirement_status": retirement["status"],
        "excluded_counts": exclusions,
        "curation_audit_sha256": sha256_file(audit_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/assessment-pilot-v1"))
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--release-criteria", required=True, type=pathlib.Path)
    parser.add_argument("--binary", default="target/debug/nobotrs", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/assessment-pilot-v1/preflight.json"))
    args = parser.parse_args()
    try:
        manifest_path = args.corpus / "manifest.json"
        manifest = load_json(manifest_path, "assessment manifest")
        info = validate_manifest(manifest, manifest_path, split="development",
                                 require_content_hashes=True,
                                 require_near_duplicate_groups=True)
        hc3 = verify_hc3(args.corpus, manifest)
        raid = verify_raid(args.corpus, manifest)
        old = verify_old_exclusion(args.corpus, manifest, info)
        require(manifest.get("retrieved") == hc3["retrieved"] == raid["retrieved"],
                "source retrieval dates do not match the manifest")
        require(manifest.get("retrieved_timezone") ==
                hc3["retrieved_timezone"] == raid["retrieved_timezone"],
                "source retrieval timezones do not match the manifest")
        forced_wrong = [sample["id"] for sample in info.samples
                        if sample.get("corpus_source") == "hc3"
                        and sample.get("question_id") in HC3_FORCED_IDS
                        and sample["split"] != "development"]
        require(not forced_wrong,
                f"forced HC3 question samples are outside development: {forced_wrong[:5]}")

        readable = [sample for sample in info.samples
                    if sample["split"] != "independent-test"]
        independent = [sample for sample in info.samples
                       if sample["split"] == "independent-test"]
        contents = read_sample_bytes(readable, args.corpus, verify_hashes=True)
        texts = decode_sample_bytes(contents)
        for sample in independent:
            require(sample["id"] not in contents,
                    f"independent sample {sample['id']} was opened")
        verified_content = corpus_content_sha256([
            {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
            for sample in readable
        ])
        metadata_grouping = validate_grouping(info.samples, None,
                                              threshold=info.near_duplicate_threshold)
        text_grouping = validate_grouping(
            [{**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
             for sample in readable],
            texts, threshold=info.near_duplicate_threshold,
        )

        _, config_hash = validate_config(args.config)
        criteria = validate_criteria(args.release_criteria)
        binary_hash = sha256_bytes(args.binary.read_bytes())
        split_counts = {split: sum(1 for sample in info.samples if sample["split"] == split)
                        for split in ("development", "validation", "independent-test")}
        identity = {
            "schema_version": SCHEMA_VERSION,
            "split": "independent-test",
            "corpus_revision": info.corpus_revision,
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "configuration_sha256": config_hash,
            "release_criteria_sha256": criteria.raw_sha256,
            "release_criteria_id": criteria.criteria_id,
            "binary_sha256": binary_hash,
        }
        output = {
            "schema_version": SCHEMA_VERSION,
            "corpus_version": manifest.get("corpus_version"),
            "corpus_revision": info.corpus_revision,
            "status": "assessment-preflight-passed",
            "purpose": manifest.get("purpose"),
            "retrieved": manifest.get("retrieved"),
            "retrieved_timezone": manifest.get("retrieved_timezone"),
            "corpus_identity": {
                "manifest_sha256": info.raw_sha256,
                "corpus_content_sha256": info.corpus_content_sha256,
                "curation_audit_sha256": old["curation_audit_sha256"],
                "source_snapshots": {"hc3": hc3, "raid_fresh": raid},
                "old_raid_v1_exclusion": old,
            },
            "configuration_sha256": config_hash,
            "release_criteria_sha256": criteria.raw_sha256,
            "release_criteria_id": criteria.criteria_id,
            "binary_sha256": binary_hash,
            "counts": {
                "samples": len(info.samples),
                "splits": split_counts,
                "components": len({sample["source_group"] for sample in info.samples}),
                "near_duplicate_groups": len({sample["near_duplicate_group"] for sample in info.samples}),
                "cross_corpus_components": manifest.get("counts", {}).get("cross_corpus_components"),
            },
            "grouping": {
                "all_manifest_samples": metadata_grouping,
                "verified_development_validation_samples": text_grouping,
            },
            "content_verification": {
                "verified_sample_ids": sorted(contents),
                "verified_splits": ["development", "validation"],
                "held_out_not_read": sorted(sample["id"] for sample in independent),
                "verified_content_sha256": verified_content,
                "manifest_corpus_content_sha256": info.corpus_content_sha256,
                "independent_held_out_verified": False,
            },
            "independent_access": {
                "status": "not-claimed",
                "access_record_written": False,
                "note": "No detector run or freeze; supervisor review is required.",
            },
            "access_record_identity": identity,
            "claims": {
                "complete_hc3_or_raid_benchmark": False,
                "general_accuracy_certification": False,
                "detector_run": False,
                "independent_test_opened": False,
                "thresholds_or_defaults_changed": False,
                "native_speaker_inferred": False,
            },
        }
        args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    except (ProtocolError, OSError) as error:
        print(f"assessment-preflight: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": output["status"],
        "samples": output["counts"]["samples"],
        "splits": output["counts"]["splits"],
        "verified_splits": output["content_verification"]["verified_splits"],
        "held_out_not_read": len(output["content_verification"]["held_out_not_read"]),
        "old_exclusions": output["corpus_identity"]["old_raid_v1_exclusion"]["excluded_counts"],
        "manifest_sha256": output["corpus_identity"]["manifest_sha256"],
        "corpus_content_sha256": output["corpus_identity"]["corpus_content_sha256"],
        "binary_sha256": output["binary_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
