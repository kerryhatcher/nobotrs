#!/usr/bin/env python3
"""Reproducible regression/evaluation runner with explicit identity binding.

Unknown labels never become authorship truth. Independent-test text is not read
until a frozen access record has been claimed exactly once.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from evaluation_protocol import (
    SCHEMA_VERSION,
    ProtocolError,
    canonical_json_bytes,
    claim_independent_access,
    corpus_content_sha256,
    decode_sample_bytes,
    load_json,
    markdown_hint,
    metrics,
    read_sample_bytes,
    sha256_bytes,
    sha256_file,
    sweep_rows,
    validate_config,
    validate_criteria,
    validate_grouping,
    validate_manifest,
)


def detector_environment():
    """Remove NOBOTRS_* overrides so they cannot supersede the frozen config."""
    return {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("NOBOTRS_")
    }


def sanitized_nobotrs_variables():
    return sorted(
        key for key in os.environ if key.upper().startswith("NOBOTRS_")
    )


def write_empty_config(path: pathlib.Path) -> str:
    """Force serde defaults through an explicit isolated empty config."""
    path.write_text("{}\n", encoding="utf-8")
    return sha256_file(path)


def dimension_metrics(rows, dimensions):
    """Report optional manifest dimensions (domain/generator/language/etc.)."""
    if not dimensions:
        return {}
    output = {}
    for name in sorted(dimensions):
        values = sorted({
            str(row.get("dimension_values", {}).get(name))
            for row in rows
            if row.get("dimension_values", {}).get(name) is not None
        })
        output[name] = {
            value: metrics([
                row for row in rows
                if str(row.get("dimension_values", {}).get(name)) == value
            ])
            for value in values
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="target/debug/nobotrs")
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--check", type=pathlib.Path)
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--release-criteria", type=pathlib.Path)
    parser.add_argument(
        "--split",
        choices=["regression", "development", "validation", "independent-test"],
        default="regression",
    )
    parser.add_argument("--sweep-quorum", type=int, nargs="+")
    parser.add_argument("--release-access-record", type=pathlib.Path)
    args = parser.parse_args()
    temp_config_dir = None

    try:
        manifest = load_json(args.manifest, "manifest")
        independent = args.split == "independent-test"
        non_regression = args.split != "regression"
        info = validate_manifest(
            manifest,
            args.manifest,
            split=args.split,
            require_content_hashes=non_regression,
            require_near_duplicate_groups=non_regression,
        )
        selected = [sample for sample in info.samples if sample["split"] == args.split]
        if not selected:
            raise ProtocolError(f"selected split {args.split!r} has no samples")

        try:
            binary_sha256 = sha256_bytes(pathlib.Path(args.binary).read_bytes())
        except OSError as error:
            raise ProtocolError(f"cannot read binary {args.binary}: {error}") from None
        config_hash = None
        config_path = args.config
        config_source = None
        config_supplied_keys = []
        config_data = None
        criteria = None
        access_record = None
        if args.config:
            config_path, config_hash = validate_config(args.config)
            config_data = load_json(config_path, "configuration")
            config_supplied_keys = sorted(config_data)
            config_source = "explicit --config"
        elif not independent:
            temp_config_dir = tempfile.mkdtemp(prefix="nobotrs-eval-config-")
            config_path = pathlib.Path(temp_config_dir) / "empty-defaults.json"
            config_hash = write_empty_config(config_path)
            config_source = (
                "synthesized empty config; binary defaults; platform config "
                "and NOBOTRS_CONFIG lookup isolated"
            )
        detector_env = detector_environment()
        sanitized_vars = sanitized_nobotrs_variables()
        if independent:
            if args.sweep_quorum:
                raise ProtocolError("independent-test forbids threshold sweeps")
            if not args.config or not args.release_criteria or not args.release_access_record:
                raise ProtocolError(
                    "independent-test requires --config, --release-criteria, "
                    "and --release-access-record"
                )
            criteria = validate_criteria(args.release_criteria)
            expected_identity = {
                "schema_version": SCHEMA_VERSION,
                "split": args.split,
                "corpus_revision": info.corpus_revision,
                "manifest_sha256": info.raw_sha256,
                "corpus_content_sha256": info.corpus_content_sha256,
                "configuration_sha256": config_hash,
                "release_criteria_sha256": criteria.raw_sha256,
                "release_criteria_id": criteria.criteria_id,
                "binary_sha256": binary_sha256,
            }
            # Claim before reading any independent-test text.
            access_record = claim_independent_access(
                args.release_access_record, expected_identity
            )
            contents = read_sample_bytes(
                info.samples, args.manifest.parent, verify_hashes=True
            )
            texts = decode_sample_bytes(contents)
            actual_content = corpus_content_sha256([
                {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
                for sample in info.samples
            ])
            if actual_content != info.corpus_content_sha256:
                raise ProtocolError("independent corpus content changed after access was claimed")
            metadata_grouping = validate_grouping(
                info.samples, None, threshold=info.near_duplicate_threshold
            )
            text_grouping = validate_grouping(
                info.samples, texts, threshold=info.near_duplicate_threshold
            )
            grouping = {
                "all_manifest_samples": metadata_grouping,
                "verified_samples": text_grouping,
            }
            verified_content = actual_content
            held_out_ids = []
            verified_ids = sorted(contents)
            verified_splits = sorted({sample["split"] for sample in info.samples})
            independent_held_out_verified = True
        else:
            if args.release_criteria:
                criteria = validate_criteria(args.release_criteria)
            readable = [
                sample for sample in info.samples
                if sample["split"] != "independent-test"
            ]
            contents = read_sample_bytes(
                readable, args.manifest.parent, verify_hashes=True
            )
            texts = decode_sample_bytes(contents)
            verified_samples = [
                sample for sample in info.samples if sample["id"] in contents
            ]
            verified_content = corpus_content_sha256([
                {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
                for sample in verified_samples
            ])
            metadata_grouping = validate_grouping(
                info.samples, None, threshold=info.near_duplicate_threshold
            )
            text_grouping = validate_grouping(
                [
                    {**sample, "content_sha256": sha256_bytes(contents[sample["id"]])}
                    for sample in verified_samples
                ],
                texts,
                threshold=info.near_duplicate_threshold,
            )
            grouping = {
                "all_manifest_samples": metadata_grouping,
                "verified_samples": text_grouping,
            }
            held_out_ids = sorted(
                sample["id"] for sample in info.samples if sample["id"] not in contents
            )
            verified_ids = sorted(contents)
            verified_splits = sorted({sample["split"] for sample in verified_samples})
            independent_held_out_verified = not held_out_ids

        rows = []
        for sample in selected:
            command = [
                args.binary, "detect", "-", "--format", "json",
                "--config", str(config_path),
            ]
            if markdown_hint(sample):
                command.append("--markdown")
            start = time.perf_counter()
            process = subprocess.run(
                command, input=contents[sample["id"]], capture_output=True,
                check=False, timeout=60, env=detector_env,
            )
            elapsed = time.perf_counter() - start
            try:
                report = json.loads(process.stdout)
            except json.JSONDecodeError as error:
                raise ProtocolError(
                    f"{sample['id']}: no analysis report: {process.stderr.decode(errors='replace')}"
                ) from error
            if "verdict" not in report:
                raise ProtocolError(
                    f"{sample['id']}: no analysis report: {process.stderr.decode(errors='replace')}"
                )
            row = {
                "id": sample["id"],
                "label": sample.get("label"),
                "slice": sample["slice"],
                "dimension_values": sample.get("dimension_values", {}),
                "verdict": report["verdict"],
                "complete": report["complete"],
                "settings": report.get("settings"),
                "status": process.returncode,
                "runtime_seconds": elapsed,
                "families": report["families"],
                "metrics": {
                    backend["backend"]: backend["outcome"].get("details", {}).get("metrics", {})
                    for backend in report["backends"]
                },
                "engine_version": report.get("engine_version"),
                "dictionary_version": report.get("dictionary_version"),
                "metric_contract": report.get("metric_contract"),
            }
            expected = sample.get("expected")
            if expected and (
                row["verdict"] != expected["verdict"]
                or row["status"] != expected["status"]
            ):
                raise ProtocolError(
                    f"regression {sample['id']}: {row['verdict']}/{row['status']} "
                    f"!= {expected}"
                )
            rows.append(row)
        if not rows:
            raise ProtocolError("selected split has no samples; no performance claim can be produced")
        effective_settings = rows[0].get("settings")
        if not isinstance(effective_settings, dict):
            raise ProtocolError("detector report does not expose effective settings")
        for row in rows[1:]:
            other = row.get("settings")
            if not isinstance(other, dict) or canonical_json_bytes(other) != canonical_json_bytes(
                effective_settings
            ):
                raise ProtocolError("effective settings changed between detector runs")
        if config_data is not None:
            for key in config_supplied_keys:
                if effective_settings.get(key) != config_data[key]:
                    raise ProtocolError(
                        f"effective setting {key!r} does not match the supplied configuration"
                    )
        effective_settings_sha256 = sha256_bytes(canonical_json_bytes(effective_settings))

        metric_versions = {}
        for row in rows:
            for backend, metric_map in row["metrics"].items():
                destination = metric_versions.setdefault(backend, {})
                for name, value in metric_map.items():
                    destination[name] = value.get("method")
        metric_versions = {
            backend: dict(sorted(metric_map.items()))
            for backend, metric_map in sorted(metric_versions.items())
        }
        stable = [
            {key: row[key] for key in ("id", "label", "verdict", "complete", "status")}
            for row in rows
        ]
        if args.check:
            baseline = load_json(args.check, "CI baseline")
            if baseline.get("regression_results") != stable:
                raise ProtocolError("CI regression baseline changed")

        output = {
            "schema_version": SCHEMA_VERSION,
            "corpus_version": manifest["corpus_version"],
            "split": args.split,
            "purpose": manifest["purpose"],
            "metrics": metrics(rows),
            "slice_metrics": {
                slice_name: metrics([row for row in rows if row["slice"] == slice_name])
                for slice_name in sorted({row["slice"] for row in rows})
            },
            "dimension_metrics": dimension_metrics(rows, manifest.get("dimensions")),
            "regression_results": stable,
            "raw_feature_cache": rows,
            "runtime_seconds": sum(row["runtime_seconds"] for row in rows),
            "corpus_identity": {
                "corpus_revision": info.corpus_revision,
                "manifest_sha256": info.raw_sha256,
                "corpus_content_sha256": (
                    info.corpus_content_sha256 if independent
                    else manifest.get("corpus_content_sha256", verified_content)
                ),
                "configuration_sha256": config_hash,
                "configuration_source": config_source,
                "release_criteria_sha256": criteria.raw_sha256 if criteria else None,
                "release_criteria_id": criteria.criteria_id if criteria else None,
                "binary_sha256": binary_sha256,
                "access_id": access_record["access_id"] if access_record else None,
            },
            "content_verification": {
                "verified_sample_ids": verified_ids,
                "verified_splits": verified_splits,
                "held_out_not_read": held_out_ids,
                "verified_content_sha256": verified_content,
                "manifest_corpus_content_sha256": info.corpus_content_sha256,
                "independent_held_out_verified": independent_held_out_verified,
            },
            "grouping": grouping,
            "effective_configuration": {
                "settings": effective_settings,
                "settings_sha256": effective_settings_sha256,
                "supplied_keys": config_supplied_keys,
                "source": config_source,
                "environment_sanitized": True,
                "sanitized_nobotrs_variables": sanitized_vars,
            },
            "engine_identity": {
                "binary_sha256": binary_sha256,
                "engine_versions": sorted({row["engine_version"] for row in rows if row["engine_version"]}),
                "dictionary_versions": sorted({row["dictionary_version"] for row in rows if row["dictionary_version"]}),
                "metric_contracts": sorted({row["metric_contract"] for row in rows if row["metric_contract"]}),
            },
            "metric_versions": metric_versions,
        }
        if args.sweep_quorum:
            if args.split not in ("development", "validation"):
                raise ProtocolError(
                    "sweeps are development/validation selection, not regression "
                    "or independent-test evidence"
                )
            output["sweeps"] = [
                {
                    "quorum": quorum,
                    "metrics": metrics(sweep_rows(rows, quorum)),
                    "use": "selection evidence only",
                }
                for quorum in args.sweep_quorum
            ]
        args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    except (ProtocolError, OSError, subprocess.TimeoutExpired) as error:
        print(f"evaluate: {error}", file=sys.stderr)
        return 1
    finally:
        if temp_config_dir:
            shutil.rmtree(temp_config_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
