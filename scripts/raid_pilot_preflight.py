#!/usr/bin/env python3
"""Preflight/freeze tooling for the limited RAID pilot.

The preflight verifies the manifest, source snapshot, copied response hashes,
development/validation sample bytes, grouping metadata, config, release
criteria, and binary identity. It never opens independent-test sample text and
never claims an independent access record. A frozen-unopened record is written
only with the explicit --freeze flag; supervisor review remains the decision
point.
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
    load_retirement,
    read_sample_bytes,
    sha256_bytes,
    sha256_file,
    validate_config,
    validate_criteria,
    validate_grouping,
    validate_manifest,
    validate_retirement,
    RETIREMENT_STATUS,
)

PINNED_DATASET = "liamdugan/raid"
PINNED_REVISION = "865cac74188466cb0c3b7574a10204007b57a459"
PINNED_LICENSE = "MIT"
SUPERVISOR_FORCED_SOURCE_IDS = {
    "e5e058ce-be2b-459d-af36-32532aaba5ff",
    "f95b107b-d176-4af5-90f7-4d0bb20caf93",
    "856d8972-9e3d-4544-babc-0fe16f21e04d",
    "fbc8a5ea-90fa-47b8-8fa7-73dd954f1524",
    "72c41b8d-0069-4886-b734-a4000ffca286",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def verify_source_snapshot(corpus: pathlib.Path, manifest: dict) -> dict:
    source = corpus / "source"
    provenance_path = source / "PROVENANCE.json"
    provenance = load_json(provenance_path, "source provenance")
    require(isinstance(provenance, dict), "source provenance must be an object")
    require(provenance.get("dataset") == PINNED_DATASET,
            "source provenance dataset does not match the pin")
    require(provenance.get("revision") == PINNED_REVISION,
            "source provenance revision does not match the pin")
    require(PINNED_LICENSE.lower() in str(provenance.get("upstream_license", "")).lower(),
            "source provenance does not declare the MIT upstream license")
    require(isinstance(provenance.get("retrieved"), str)
            and provenance["retrieved"],
            "source provenance must pin retrieved")
    require(isinstance(provenance.get("retrieved_timezone"), str)
            and provenance["retrieved_timezone"],
            "source provenance must pin retrieved_timezone")

    acquisition_path = source / "acquisition.json"
    card_path = source / "dataset-card.md"
    license_path = source / "LICENSE"
    for path in (acquisition_path, card_path, license_path):
        require(path.is_file(), f"missing source snapshot file {path}")
    require(sha256_file(acquisition_path) == provenance["acquisition_sha256"],
            "copied portable acquisition hash does not match source provenance")
    require(isinstance(provenance.get("upstream_acquisition_sha256"), str)
            and len(provenance["upstream_acquisition_sha256"]) == 64,
            "source provenance must retain the original acquisition hash")
    require(sha256_file(card_path) == provenance["dataset_card_sha256"],
            "copied dataset card hash does not match source provenance")
    require(sha256_file(license_path) == provenance["license_sha256"],
            "copied upstream license hash does not match source provenance")
    card_text = card_path.read_text(encoding="utf-8").lower()
    license_text = license_path.read_text(encoding="utf-8")
    require("license: mit" in card_text,
            "copied dataset card does not pin the MIT declaration")
    require("MIT License" in license_text and "Liam Dugan" in license_text,
            "copied LICENSE is not the upstream Liam Dugan MIT notice")

    acquisition = load_json(acquisition_path, "acquisition")
    require(acquisition.get("dataset") == PINNED_DATASET,
            "copied acquisition dataset does not match the pin")
    require(acquisition.get("revision") == PINNED_REVISION,
            "copied acquisition revision does not match the pin")
    require(acquisition.get("portable_snapshot") is True,
            "copied acquisition must be the portable relative-path snapshot")
    require(acquisition.get("original_acquisition_sha256") ==
            provenance["upstream_acquisition_sha256"],
            "portable acquisition does not retain the original acquisition hash")
    require(acquisition.get("retrieved") == provenance.get("upstream_retrieved"),
            "portable acquisition retrieved date does not match upstream provenance")
    require(acquisition.get("retrieved_timezone") ==
            provenance.get("upstream_retrieved_timezone"),
            "portable acquisition timezone does not match upstream provenance")
    expected_override = (
        provenance["retrieved"] != provenance["upstream_retrieved"]
        or provenance["retrieved_timezone"] != provenance["upstream_retrieved_timezone"]
    )
    require(provenance.get("retrieved_override") is expected_override,
            "source provenance override flag is inconsistent")
    require("/tmp/" not in acquisition_path.read_text(encoding="utf-8"),
            "portable acquisition embeds an absolute temporary path")
    queries = acquisition.get("queries")
    require(isinstance(queries, list) and queries,
            "copied acquisition has no queries")
    verified = []
    for index, query in enumerate(queries):
        require(isinstance(query, dict), f"acquisition query {index} is malformed")
        declared_path = pathlib.Path(str(query["file"]))
        require(not declared_path.is_absolute(),
                f"acquisition query {index} embeds an absolute response path")
        require(".." not in declared_path.parts,
                f"acquisition query {index} escapes the responses directory")
        require(declared_path.parts[:1] == ("responses",),
                f"acquisition query {index} does not use a relative responses/ path")
        response = source / declared_path
        require(response.is_file(), f"missing copied response {response.name}")
        actual = sha256_file(response)
        require(actual == query["sha256"],
                f"copied response hash mismatch for {response.name}")
        verified.append({
            "file": response.name,
            "sha256": actual,
            "rows": query["rows"],
            "available": query["available"],
            "partial_view": query["partial_view"],
            "empty": query["rows"] == 0,
        })
    declared = manifest.get("source_snapshot", {})
    require(declared.get("acquisition_sha256") == provenance["acquisition_sha256"],
            "manifest source snapshot does not bind the copied portable acquisition")
    require(declared.get("upstream_acquisition_sha256") ==
            provenance["upstream_acquisition_sha256"],
            "manifest source snapshot does not bind the original acquisition hash")
    require(declared.get("dataset_card_sha256") == provenance["dataset_card_sha256"],
            "manifest source snapshot does not bind the copied dataset card")
    require(declared.get("license_sha256") == provenance["license_sha256"],
            "manifest source snapshot does not bind the copied LICENSE")
    require(declared.get("provenance_sha256") == sha256_file(provenance_path),
            "manifest source snapshot does not bind source provenance")
    require(declared.get("response_count") == len(queries),
            "manifest source snapshot response count is stale")
    require(manifest.get("retrieved") == provenance["retrieved"],
            "manifest retrieved date does not match source provenance")
    require(manifest.get("retrieved_timezone") == provenance["retrieved_timezone"],
            "manifest timezone does not match source provenance")
    require(manifest.get("retrieved_override") is provenance["retrieved_override"],
            "manifest retrieval override flag does not match source provenance")
    return {
        "acquisition_sha256": provenance["acquisition_sha256"],
        "upstream_acquisition_sha256": provenance["upstream_acquisition_sha256"],
        "retrieved": provenance["retrieved"],
        "retrieved_timezone": provenance["retrieved_timezone"],
        "upstream_retrieved": provenance["upstream_retrieved"],
        "upstream_retrieved_timezone": provenance["upstream_retrieved_timezone"],
        "retrieved_override": provenance["retrieved_override"],
        "dataset_card_sha256": provenance["dataset_card_sha256"],
        "license_sha256": provenance["license_sha256"],
        "provenance_sha256": sha256_file(provenance_path),
        "response_count": len(queries),
        "empty_response_count": sum(1 for item in verified if item["empty"]),
        "failed_query_count": len(acquisition.get("errors", [])),
        "responses": verified,
    }


def verify_curation_audit(corpus: pathlib.Path, manifest: dict, info) -> dict:
    audit_path = corpus / str(manifest.get("curation_audit", "curation.json"))
    audit = load_json(audit_path, "curation audit")
    require(isinstance(audit, dict), "curation audit must be an object")
    require(audit.get("manifest_sha256") == info.raw_sha256,
            "curation audit does not bind the manifest")
    require(audit.get("corpus_content_sha256") == info.corpus_content_sha256,
            "curation audit does not bind the corpus content hash")
    require(audit.get("revision") == PINNED_REVISION,
            "curation audit revision does not match the pin")
    require(audit.get("retrieved") == manifest.get("retrieved"),
            "curation audit retrieved date does not match the manifest")
    require(audit.get("retrieved_timezone") == manifest.get("retrieved_timezone"),
            "curation audit timezone does not match the manifest")
    claims = audit.get("claims", {})
    require(claims.get("complete_raid_benchmark") is False,
            "curation audit must not claim a complete RAID benchmark")
    require(claims.get("general_accuracy_certification") is False,
            "curation audit must not claim accuracy certification")
    require(claims.get("independent_test_opened") is False,
            "curation audit must not claim to have opened independent text")
    require(claims.get("thresholds_or_defaults_changed") is False,
            "curation audit must not claim threshold/default changes")
    return {
        "sha256": sha256_file(audit_path),
        "manifest_sha256": audit["manifest_sha256"],
        "corpus_content_sha256": audit["corpus_content_sha256"],
        "rejected_rows": audit.get("row_accounting", {}).get("rejected"),
    }


def check_forced_sources(manifest: dict, info) -> dict:
    declared = set(manifest.get("split_policy", {}).get("forced_to_development", []))
    require(SUPERVISOR_FORCED_SOURCE_IDS <= declared,
            "manifest split policy does not declare all supervisor-forced source IDs")
    found = {sample.get("source_id") for sample in info.samples}
    missing = sorted(declared - found)
    require(not missing, f"declared forced source IDs are absent from the manifest: {missing}")
    wrong = sorted(
        sample["id"] for sample in info.samples
        if sample.get("source_id") in declared
        and sample["split"] != "development"
    )
    require(not wrong, f"forced source samples are outside development: {wrong}")
    return {
        "supervisor_required": sorted(SUPERVISOR_FORCED_SOURCE_IDS),
        "declared": sorted(declared),
        "found": sorted(declared & found),
        "all_development": True,
    }


def check_language_policy(manifest: dict, info) -> dict:
    policy = manifest.get("language_policy")
    require(isinstance(policy, dict), "manifest must declare a language policy")
    require(policy.get("runtime_default") == "unknown",
            "pilot must keep the default unknown-language runtime policy")
    require(policy.get("per_sample_overrides") is False,
            "pilot must not declare undeclared per-sample language overrides")
    require(policy.get("overrides_recorded") == [],
            "pilot language override list must be empty")
    for sample in info.samples:
        require("language_override" not in sample,
                f"sample {sample['id']} unexpectedly declares a language override")
        require(sample.get("dimension_values", {}).get("language_hint") is not None,
                f"sample {sample['id']} lacks a language_hint reporting value")
    return {
        "runtime_default": "unknown",
        "per_sample_overrides": False,
        "overrides_recorded": [],
        "native_speaker_status": "not provided; not inferred",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/raid-pilot-v1"))
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--release-criteria", required=True, type=pathlib.Path)
    parser.add_argument("--binary", default="target/debug/nobotrs", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/raid-pilot-v1/preflight.json"))
    parser.add_argument("--access-record-out", type=pathlib.Path)
    parser.add_argument("--freeze", action="store_true",
                        help="write a frozen-unopened access record; does not claim it")
    args = parser.parse_args()
    try:
        require(not args.freeze or args.access_record_out is not None,
                "--freeze requires --access-record-out")
        manifest_path = args.corpus / "manifest.json"
        manifest = load_json(manifest_path, "manifest")
        retirement = load_retirement(args.corpus)
        if args.freeze and retirement and retirement.get("status") == RETIREMENT_STATUS:
            raise ProtocolError(
                "corpus is retired as exposed selection data; freeze is refused"
            )
        info = validate_manifest(
            manifest, manifest_path, split="development",
            require_content_hashes=True, require_near_duplicate_groups=True,
        )
        retirement_info = (
            validate_retirement(retirement, info) if retirement else None
        )
        pilot_splits = ("development", "validation", "independent-test")
        split_counts = {
            split: sum(1 for sample in info.samples if sample["split"] == split)
            for split in pilot_splits
        }
        for split, count in split_counts.items():
            require(count > 0, f"manifest has no {split} samples")

        source = verify_source_snapshot(args.corpus, manifest)
        audit = verify_curation_audit(args.corpus, manifest, info)
        forced = check_forced_sources(manifest, info)
        language = check_language_policy(manifest, info)

        readable = [sample for sample in info.samples
                    if sample["split"] != "independent-test"]
        independent = [sample for sample in info.samples
                       if sample["split"] == "independent-test"]
        contents = read_sample_bytes(readable, args.corpus, verify_hashes=True)
        texts = decode_sample_bytes(contents)
        require(sorted(contents) == sorted(sample["id"] for sample in readable),
                "development/validation verification did not cover every readable sample")
        for sample in independent:
            require(sample["id"] not in contents,
                    f"independent sample {sample['id']} was opened during preflight")
        verified_content = corpus_content_sha256([
            {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
            for sample in readable
        ])
        metadata_grouping = validate_grouping(
            info.samples, None, threshold=info.near_duplicate_threshold
        )
        text_grouping = validate_grouping(
            [
                {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
                for sample in readable
            ],
            texts,
            threshold=info.near_duplicate_threshold,
        )

        _, config_hash = validate_config(args.config)
        criteria = validate_criteria(args.release_criteria)
        try:
            binary_hash = sha256_bytes(args.binary.read_bytes())
        except OSError as error:
            raise ProtocolError(f"cannot read binary {args.binary}: {error}") from None

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
        if args.freeze:
            if retirement_info:
                raise ProtocolError(
                    "corpus is retired as exposed selection data; freeze is refused"
                )
            record_path = args.access_record_out
            if record_path.exists():
                raise ProtocolError(f"refusing to overwrite access record {record_path}")
            record = {"status": "frozen-unopened", **identity}
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        output = {
            "schema_version": SCHEMA_VERSION,
            "corpus_version": manifest.get("corpus_version"),
            "corpus_revision": info.corpus_revision,
            "status": (
                "preflight-passed-retired" if retirement_info
                else ("preflight-passed" if not args.freeze
                      else "frozen-unopened-record-written")
            ),
            "purpose": manifest.get("purpose"),
            "retrieved": source["retrieved"],
            "retrieved_timezone": source["retrieved_timezone"],
            "upstream_retrieved": source["upstream_retrieved"],
            "upstream_retrieved_timezone": source["upstream_retrieved_timezone"],
            "retrieved_override": source["retrieved_override"],
            "corpus_identity": {
                "manifest_sha256": info.raw_sha256,
                "corpus_content_sha256": info.corpus_content_sha256,
                "curation_audit_sha256": audit["sha256"],
                "source_snapshot": source,
            },
            "configuration_sha256": config_hash,
            "release_criteria_sha256": criteria.raw_sha256,
            "release_criteria_id": criteria.criteria_id,
            "binary_sha256": binary_hash,
            "counts": {
                "samples": len(info.samples),
                "splits": split_counts,
                "components": len({
                    sample["source_group"] for sample in info.samples
                }),
                "near_duplicate_groups": len({
                    sample["near_duplicate_group"] for sample in info.samples
                }),
            },
            "forced_sources": forced,
            "language": language,
            "grouping": {
                "all_manifest_samples": metadata_grouping,
                "verified_development_validation_samples": text_grouping,
            },
            "content_verification": {
                "verified_sample_ids": sorted(contents),
                "verified_splits": sorted({
                    sample["split"] for sample in readable
                }),
                "held_out_not_read": sorted(sample["id"] for sample in independent),
                "verified_content_sha256": verified_content,
                "manifest_corpus_content_sha256": info.corpus_content_sha256,
                "independent_held_out_verified": False,
            },
            "retirement": retirement_info or {"status": "not-retired"},
            "independent_access": {
                "status": "refused-retired" if retirement_info else "not-claimed",
                "access_record_written": bool(args.freeze) and not retirement_info,
                "access_record_path": (
                    str(args.access_record_out)
                    if args.freeze and not retirement_info else None
                ),
                "note": (
                    "Preflight refuses freeze/access for retired corpora. It "
                    "never claims the one-shot access record; the supervisor "
                    "decides whether a non-retired corpus may be frozen."
                ),
            },
            "access_record_identity": identity,
            "claims": {
                "complete_raid_benchmark": False,
                "general_accuracy_certification": False,
                "independent_test_opened": False,
                "thresholds_or_defaults_changed": False,
            },
        }
        args.output.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (ProtocolError, OSError) as error:
        print(f"preflight: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": output["status"],
        "samples": output["counts"]["samples"],
        "splits": output["counts"]["splits"],
        "splits_verified": output["content_verification"]["verified_splits"],
        "held_out_not_read": len(output["content_verification"]["held_out_not_read"]),
        "manifest_sha256": output["corpus_identity"]["manifest_sha256"],
        "corpus_content_sha256": output["corpus_identity"]["corpus_content_sha256"],
        "configuration_sha256": output["configuration_sha256"],
        "release_criteria_id": output["release_criteria_id"],
        "binary_sha256": output["binary_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
