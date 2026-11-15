"""Evaluation protocol primitives: identity binding, grouping, access, metrics.

The module is deliberately dependency-free so the protocol can be tested with
the Python standard library. It does not run the detector or read independent
test text before an access record has been claimed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0.0"
RETIREMENT_STATUS = "retired-exposed-selection-data"
RETIREMENT_FILE = "retirement.json"
SPLITS = ("regression", "development", "validation", "independent-test")
LABELS = ("human", "generated")
VERDICTS = ("clean", "flagged", "inconclusive")
PLACEHOLDER_LICENSES = {
    "", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "test",
    "unlicensed", "proprietary", "all rights reserved",
}
PLACEHOLDER_PROVENANCE = {
    "", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "test",
    "synthetic", "fixture", "placeholder",
}
SPDX_TOKEN = re.compile(r"^[A-Za-z0-9.+-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DIMENSION_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


class ProtocolError(ValueError):
    """A manifest, identity, grouping, or access-record protocol violation."""


@dataclass(frozen=True)
class ManifestInfo:
    path: Path
    raw_sha256: str
    corpus_revision: str
    corpus_content_sha256: str | None
    near_duplicate_threshold: float
    samples: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CriteriaInfo:
    path: Path
    raw_sha256: str
    criteria_id: str
    criteria_version: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def load_retirement(directory: Path) -> dict[str, Any] | None:
    path = Path(directory) / RETIREMENT_FILE
    if not path.exists():
        return None
    value = load_json(path, "retirement ledger")
    if not isinstance(value, dict):
        raise ProtocolError("retirement ledger must be a JSON object")
    return value


def validate_retirement(ledger: dict[str, Any], info: "ManifestInfo") -> dict[str, Any]:
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError("unsupported retirement ledger schema_version")
    if ledger.get("status") != RETIREMENT_STATUS:
        raise ProtocolError(
            f"retirement ledger status is {ledger.get('status')!r}; expected {RETIREMENT_STATUS!r}"
        )
    if ledger.get("manifest_sha256") != info.raw_sha256:
        raise ProtocolError("retirement ledger does not bind the current manifest")
    if ledger.get("corpus_content_sha256") != info.corpus_content_sha256:
        raise ProtocolError("retirement ledger does not bind the current corpus content hash")
    retired_split = ledger.get("retired_split")
    if retired_split not in SPLITS:
        raise ProtocolError("retirement ledger retired_split is invalid")
    retired_ids = sorted(
        sample["id"] for sample in info.samples if sample["split"] == retired_split
    )
    if ledger.get("retired_sample_count") != len(retired_ids):
        raise ProtocolError("retirement ledger retired_sample_count is stale")
    expected_hash = sha256_bytes(
        ("\n".join(retired_ids) + "\n").encode("utf-8")
    )
    if ledger.get("retired_id_set_sha256") != expected_hash:
        raise ProtocolError("retirement ledger retired ID-set hash is stale")
    declared_ids = ledger.get("retired_sample_ids")
    if not isinstance(declared_ids, list) or sorted(declared_ids) != retired_ids:
        raise ProtocolError("retirement ledger retired sample IDs are stale")
    disposition = ledger.get("disposition")
    if not isinstance(disposition, dict):
        raise ProtocolError("retirement ledger disposition must be an object")
    for key in ("not_independent_test", "preserve_original_manifest_splits_results"):
        if disposition.get(key) is not True:
            raise ProtocolError(f"retirement ledger disposition.{key} must be true")
    return {
        "status": RETIREMENT_STATUS,
        "retirement_id": ledger.get("retirement_id"),
        "retired_split": retired_split,
        "retired_sample_count": len(retired_ids),
        "retired_id_set_sha256": expected_hash,
        "independent_test_allowed": False,
        "freeze_allowed": False,
        "exposure": ledger.get("exposure"),
        "disposition": disposition,
    }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ProtocolError(f"{label}: cannot read {path}: {error}") from None
    except json.JSONDecodeError as error:
        raise ProtocolError(f"{label}: invalid JSON in {path}: {error}") from None


def _require_text(value: Any, field: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ProtocolError(f"{field} must be a nonempty string of at least {minimum} characters")
    return value.strip()


def _validate_license(value: Any, field: str) -> str:
    text = _require_text(value, field)
    if text.lower() in PLACEHOLDER_LICENSES:
        raise ProtocolError(f"{field} is a placeholder, not a verifiable license")
    tokens = re.split(r"[\s()]+", text)
    for token in tokens:
        if token in ("AND", "OR", "WITH"):
            continue
        if not SPDX_TOKEN.match(token):
            raise ProtocolError(f"{field} is not an SPDX-like license expression: {text!r}")
    return text


def _validate_provenance(value: Any, field: str, split: str) -> None:
    if isinstance(value, dict):
        source = _require_text(value.get("source"), f"{field}.source", minimum=8)
        if source.lower() in PLACEHOLDER_PROVENANCE:
            raise ProtocolError(f"{field}.source is a placeholder")
        retrieved = _require_text(value.get("retrieved"), f"{field}.retrieved")
        if not DATE.match(retrieved):
            raise ProtocolError(f"{field}.retrieved must be YYYY-MM-DD")
        return
    text = _require_text(value, field, minimum=20)
    if text.lower() in PLACEHOLDER_PROVENANCE:
        raise ProtocolError(f"{field} is a placeholder")
    if split != "regression":
        raise ProtocolError(
            f"{field} must be an object with source and retrieved for {split} data"
        )


def _validate_expected(value: Any, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ProtocolError(f"{field} must be an object")
    verdict = value.get("verdict")
    status = value.get("status")
    if verdict not in VERDICTS:
        raise ProtocolError(f"{field}.verdict must be one of {VERDICTS}")
    if not isinstance(status, int) or isinstance(status, bool) or status not in (0, 1, 2, 3):
        raise ProtocolError(f"{field}.status must be an integer 0..3")


def _validate_sample(sample: Any, index: int) -> dict[str, Any]:
    if not isinstance(sample, dict):
        raise ProtocolError(f"samples[{index}] must be an object")
    sample_id = _require_text(sample.get("id"), f"samples[{index}].id")
    if not SAFE_ID.match(sample_id):
        raise ProtocolError(f"samples[{index}].id is not a safe identifier: {sample_id!r}")
    file_name = _require_text(sample.get("file"), f"samples[{index}].file")
    file_path = Path(file_name)
    if file_path.is_absolute() or ".." in file_path.parts:
        raise ProtocolError(f"samples[{index}].file must be a relative path without '..'")
    sample_split = sample.get("split")
    if sample_split not in SPLITS:
        raise ProtocolError(f"samples[{index}].split must be one of {SPLITS}")
    _require_text(sample.get("source_group"), f"samples[{index}].source_group")
    _require_text(sample.get("slice"), f"samples[{index}].slice")
    label = sample.get("label")
    if label is not None and label not in LABELS:
        raise ProtocolError(
            f"samples[{index}].label must be null, human, or generated"
        )
    _validate_license(sample.get("license"), f"samples[{index}].license")
    _validate_provenance(sample.get("provenance"), f"samples[{index}].provenance", sample_split)
    content_hash = sample.get("content_sha256")
    if content_hash is not None:
        if not isinstance(content_hash, str) or not SHA256.match(content_hash):
            raise ProtocolError(f"samples[{index}].content_sha256 must be lowercase SHA-256")
    near_group = sample.get("near_duplicate_group")
    if near_group is not None:
        _require_text(near_group, f"samples[{index}].near_duplicate_group")
    _validate_expected(sample.get("expected"), f"samples[{index}].expected")
    return sample


def validate_manifest(
    manifest: Any,
    manifest_path: Path,
    *,
    split: str,
    require_content_hashes: bool = False,
    require_near_duplicate_groups: bool = False,
) -> ManifestInfo:
    if split not in SPLITS:
        raise ProtocolError(f"split must be one of {SPLITS}")
    if not isinstance(manifest, dict):
        raise ProtocolError("manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError(f"unsupported manifest schema_version: {manifest.get('schema_version')!r}")
    corpus_version = _require_text(manifest.get("corpus_version"), "corpus_version")
    corpus_revision = manifest.get("corpus_revision", corpus_version)
    corpus_revision = _require_text(corpus_revision, "corpus_revision")
    _require_text(manifest.get("purpose"), "purpose", minimum=10)
    samples_value = manifest.get("samples")
    if not isinstance(samples_value, list) or not samples_value:
        raise ProtocolError("samples must be a nonempty list")
    samples = tuple(
        _validate_sample(sample, index)
        for index, sample in enumerate(samples_value)
    )
    ids = [sample["id"] for sample in samples]
    if len(ids) != len(set(ids)):
        raise ProtocolError("duplicate sample identity")
    if not any(sample["split"] == split for sample in samples):
        raise ProtocolError(f"manifest has no samples for selected split {split!r}")
    threshold = manifest.get("near_duplicate_threshold", 0.8)
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ProtocolError("near_duplicate_threshold must be a number")
    if not 0.0 < float(threshold) <= 1.0:
        raise ProtocolError("near_duplicate_threshold must be in (0, 1]")
    if require_content_hashes:
        missing = [sample["id"] for sample in samples if not sample.get("content_sha256")]
        if missing:
            raise ProtocolError(f"content_sha256 is required for {split} samples: {missing}")
    if require_near_duplicate_groups:
        missing = [sample["id"] for sample in samples if not sample.get("near_duplicate_group")]
        if missing:
            raise ProtocolError(
                f"near_duplicate_group is required for {split} samples: {missing}"
            )
    declared_content = manifest.get("corpus_content_sha256")
    if declared_content is not None:
        if not isinstance(declared_content, str) or not SHA256.match(declared_content):
            raise ProtocolError("corpus_content_sha256 must be lowercase SHA-256")
    if require_content_hashes and declared_content is None:
        raise ProtocolError(f"corpus_content_sha256 is required for {split} data")
    _validate_dimensions(manifest, samples)
    computed_content = corpus_content_sha256(samples)
    if declared_content is not None and computed_content != declared_content:
        raise ProtocolError(
            "corpus_content_sha256 does not match the manifest sample identities/content hashes"
        )
    return ManifestInfo(
        path=Path(manifest_path),
        raw_sha256=sha256_file(manifest_path),
        corpus_revision=corpus_revision,
        corpus_content_sha256=computed_content,
        near_duplicate_threshold=float(threshold),
        samples=samples,
    )


def _validate_dimensions(manifest: dict[str, Any],
                         samples: Iterable[dict[str, Any]]) -> None:
    """Validate optional reporting dimensions without requiring them everywhere."""
    dimensions = manifest.get("dimensions")
    if dimensions is None:
        return
    if not isinstance(dimensions, dict) or not dimensions:
        raise ProtocolError("dimensions must be a nonempty object when present")
    for name, description in dimensions.items():
        if not isinstance(name, str) or not DIMENSION_NAME.match(name):
            raise ProtocolError(f"invalid dimension name: {name!r}")
        _require_text(description, f"dimensions.{name}", minimum=8)
    for index, sample in enumerate(samples):
        values = sample.get("dimension_values")
        if not isinstance(values, dict):
            raise ProtocolError(
                f"samples[{index}].dimension_values is required when dimensions are declared"
            )
        unknown = sorted(set(values) - set(dimensions))
        missing = sorted(set(dimensions) - set(values))
        if unknown:
            raise ProtocolError(
                f"samples[{index}].dimension_values has unknown dimensions: {unknown}"
            )
        if missing:
            raise ProtocolError(
                f"samples[{index}].dimension_values is missing dimensions: {missing}"
            )
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ProtocolError(
                    f"samples[{index}].dimension_values.{name} must be a string or integer"
                )
            if isinstance(value, str) and not value.strip():
                raise ProtocolError(
                    f"samples[{index}].dimension_values.{name} must be nonempty"
                )


def corpus_content_sha256(samples: Iterable[dict[str, Any]]) -> str:
    lines = []
    for sample in sorted(samples, key=lambda item: item["id"]):
        lines.append("\0".join([
            sample["id"],
            sample["file"],
            sample["split"],
            sample["source_group"],
            sample.get("label") or "",
            sample["slice"],
            sample.get("content_sha256") or "",
        ]))
    return sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def validate_config(path: Path) -> tuple[Path, str]:
    value = load_json(path, "configuration")
    if not isinstance(value, dict) or not value:
        raise ProtocolError("configuration must be a nonempty JSON object")
    return Path(path), sha256_file(path)


def validate_criteria(path: Path) -> CriteriaInfo:
    value = load_json(path, "release criteria")
    if not isinstance(value, dict):
        raise ProtocolError("release criteria must be a JSON object")
    criteria_id = _require_text(value.get("criteria_id"), "criteria_id")
    criteria_version = _require_text(value.get("criteria_version"), "criteria_version")
    return CriteriaInfo(
        path=Path(path),
        raw_sha256=sha256_file(path),
        criteria_id=criteria_id,
        criteria_version=criteria_version,
    )


def read_sample_bytes(
    samples: Iterable[dict[str, Any]],
    manifest_dir: Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, bytes]:
    """Read exact file bytes; hashes are over those bytes, not newline-normalized text."""
    contents: dict[str, bytes] = {}
    for sample in samples:
        path = Path(manifest_dir) / sample["file"]
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ProtocolError(f"{sample['id']}: cannot read {path}: {error}") from None
        expected = sample.get("content_sha256")
        if verify_hashes and expected is not None:
            actual = sha256_bytes(data)
            if actual != expected:
                raise ProtocolError(
                    f"{sample['id']}: content_sha256 mismatch ({actual} != {expected})"
                )
        contents[sample["id"]] = data
    return contents


def decode_sample_bytes(contents: dict[str, bytes]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for sample_id, data in contents.items():
        try:
            texts[sample_id] = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProtocolError(f"{sample_id}: invalid UTF-8: {error}") from None
    return texts


def read_sample_texts(
    samples: Iterable[dict[str, Any]],
    manifest_dir: Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, str]:
    return decode_sample_bytes(
        read_sample_bytes(samples, manifest_dir, verify_hashes=verify_hashes)
    )


def markdown_hint(sample: dict[str, Any]) -> bool:
    return Path(sample["file"]).suffix.lower() in (".md", ".markdown")


def _normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def _shingles(tokens: list[str], size: int = 5) -> set[tuple[str, ...]]:
    if not tokens:
        return set()
    if len(tokens) <= size:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def _jaccard(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def validate_grouping(
    samples: Iterable[dict[str, Any]],
    texts: dict[str, str] | None,
    *,
    threshold: float = 0.8,
) -> dict[str, int]:
    samples = list(samples)
    source_splits: dict[str, set[str]] = {}
    near_splits: dict[str, set[str]] = {}
    content_splits: dict[str, set[str]] = {}
    normalized_splits: dict[str, set[str]] = {}
    for sample in samples:
        source_splits.setdefault(sample["source_group"], set()).add(sample["split"])
        if sample.get("near_duplicate_group"):
            near_splits.setdefault(sample["near_duplicate_group"], set()).add(sample["split"])
        if sample.get("content_sha256"):
            content_splits.setdefault(sample["content_sha256"], set()).add(sample["split"])
        if texts is not None:
            normalized = " ".join(_normalized_tokens(texts[sample["id"]]))
            normalized_splits.setdefault(sha256_bytes(normalized.encode()), set()).add(
                sample["split"]
            )
    for label, groups in (
        ("source_group", source_splits),
        ("near_duplicate_group", near_splits),
        ("content_sha256", content_splits),
        ("normalized content", normalized_splits),
    ):
        leaked = sorted(key for key, splits in groups.items() if len(splits) > 1)
        if leaked:
            raise ProtocolError(f"{label} crosses splits: {leaked}")
    near_pairs = 0
    if texts is not None:
        shingles = {
            sample["id"]: _shingles(_normalized_tokens(texts[sample["id"]]))
            for sample in samples
        }
        index: dict[tuple[str, ...], list[int]] = {}
        for position, sample in enumerate(samples):
            for shingle in shingles[sample["id"]]:
                index.setdefault(shingle, []).append(position)
        seen: set[tuple[int, int]] = set()
        for positions in index.values():
            for left_index in range(len(positions)):
                for right_index in range(left_index + 1, len(positions)):
                    pair = (positions[left_index], positions[right_index])
                    if pair in seen:
                        continue
                    seen.add(pair)
                    left, right = samples[pair[0]], samples[pair[1]]
                    if left["split"] == right["split"]:
                        continue
                    near_pairs += 1
                    similarity = _jaccard(shingles[left["id"]], shingles[right["id"]])
                    if similarity >= threshold:
                        raise ProtocolError(
                            "near-duplicate content crosses splits: "
                            f"{left['id']} and {right['id']} (Jaccard {similarity:.3f})"
                        )
    return {
        "source_groups": len(source_splits),
        "near_duplicate_groups": len(near_splits),
        "content_hashes": len(content_splits),
        "near_duplicate_pairs_checked": near_pairs,
    }


def _identity_mismatches(record: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    mismatches = []
    for key, value in expected.items():
        if record.get(key) != value:
            mismatches.append(f"{key}: record={record.get(key)!r} expected={value!r}")
    return mismatches


def claim_independent_access(
    record_path: Path,
    expected: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Claim a frozen independent-test record exactly once.

    The record is re-read under an exclusive lock, then replaced atomically.
    A stale, reused, mismatched, or already-claimed record is rejected. A lock
    left by a crash is treated as a conservative refusal, not reset.
    """
    record_path = Path(record_path)
    if record_path.is_symlink():
        raise ProtocolError("access record must not be a symlink")
    record = load_json(record_path, "access record")
    if not isinstance(record, dict):
        raise ProtocolError("access record must be a JSON object")
    if record.get("status") != "frozen-unopened":
        raise ProtocolError(
            f"access record status is {record.get('status')!r}; independent test is not unopened"
        )
    for key in ("access_id", "accessed_at", "consumed_at"):
        if key in record:
            raise ProtocolError(f"access record already contains {key}; refusing reuse")
    mismatches = _identity_mismatches(record, expected)
    if mismatches:
        raise ProtocolError("access record identity is stale or incomplete: " + "; ".join(mismatches))
    lock_path = record_path.with_name(record_path.name + ".lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ProtocolError(
            f"access lock already exists at {lock_path}; refusing concurrent or repeated access"
        ) from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
            json.dump({
                "pid": os.getpid(),
                "claimed_at": (now or datetime.now(timezone.utc)).isoformat(),
                "identity": expected,
            }, lock, sort_keys=True)
            lock.flush()
            os.fsync(lock.fileno())
        # Re-read after acquiring the lock to close the check/claim race.
        record = load_json(record_path, "access record")
        if record.get("status") != "frozen-unopened":
            raise ProtocolError("access record changed while claiming; refusing access")
        for key in ("access_id", "accessed_at", "consumed_at"):
            if key in record:
                raise ProtocolError(f"access record gained {key} while claiming; refusing access")
        mismatches = _identity_mismatches(record, expected)
        if mismatches:
            raise ProtocolError(
                "access record identity changed while claiming: " + "; ".join(mismatches)
            )
        updated = dict(record)
        updated["status"] = "accessed"
        updated["accessed_at"] = (now or datetime.now(timezone.utc)).isoformat()
        updated["access_id"] = secrets.token_hex(16)
        updated["identity"] = expected
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=record_path.parent,
            prefix=record_path.name + ".", suffix=".tmp", delete=False,
        ) as temporary:
            json.dump(updated, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, record_path)
        return updated
    finally:
        # A successful replace leaves the lock until this unlink. A crash before
        # the replace leaves the lock in place, which conservatively blocks reuse.
        try:
            lock_path.unlink()
        except OSError:
            pass


def wilson(hits: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = 1.96
    p = hits / count
    center = (p + z * z / (2 * count)) / (1 + z * z / count)
    radius = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / (
        1 + z * z / count
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    labeled = [row for row in rows if row.get("label") in LABELS]
    unknown = [row for row in rows if row.get("label") not in LABELS]
    covered = [
        row for row in labeled
        if row.get("complete") and row.get("verdict") != "inconclusive"
    ]
    unknown_covered = [
        row for row in unknown
        if row.get("complete") and row.get("verdict") != "inconclusive"
    ]
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
        "unknown_label_coverage": ratio(len(unknown_covered), len(unknown)),
        "unknown_label_abstentions": sum(
            row.get("complete") and row.get("verdict") == "inconclusive"
            for row in unknown
        ),
        "unknown_label_operational_failures": sum(
            not row.get("complete") for row in unknown
        ),
        "abstentions": sum(
            row.get("complete") and row.get("verdict") == "inconclusive"
            for row in labeled
        ),
        "operational_failures": sum(not row.get("complete") for row in rows),
        "confusion_matrix": counts,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "false_positive_rate_wilson_95": wilson(fp, fp + tn),
        "false_positive_rate_wilson_95_assumption": (
            "Exploratory individual-row binomial interval; assumes independent "
            "rows and must not certify clustered HC3/RAID data. Use the "
            "cluster-aware summary and disclose degenerate bounds."
        ),
        "auc": None,
        "auc_reason": (
            "No calibrated or defined continuous ensemble score; "
            "discrete verdicts are not an AUC score."
        ),
    }


def sweep_rows(rows: Iterable[dict[str, Any]], quorum: int) -> list[dict[str, Any]]:
    if not isinstance(quorum, int) or isinstance(quorum, bool) or not 1 <= quorum <= 3:
        raise ProtocolError("quorum must be an integer 1..3")
    selected = []
    for row in rows:
        copy = dict(row)
        families = copy.get("families") or []
        if len(families) < quorum:
            copy["verdict"] = "inconclusive"
        elif sum(family.get("vote") != "none" for family in families) >= quorum:
            copy["verdict"] = "flagged"
        else:
            copy["verdict"] = "clean"
        selected.append(copy)
    return selected
