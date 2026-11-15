#!/usr/bin/env python3
"""Curate a limited, auditable RAID pilot from copied local API responses.

The importer deliberately uses only the Python standard library. It verifies the
pinned upstream revision and every copied response hash before accepting a row,
unions source derivatives and exact/near duplicates before splitting, forces the
supervisor-identified viewed sources into development, and writes a manifest plus
a metadata-only curation audit. It never prints sample text.

This is a pilot viewer of partial API responses, not the complete RAID benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    SCHEMA_VERSION,
    ProtocolError,
    corpus_content_sha256,
    sha256_bytes,
    sha256_file,
    validate_grouping,
    validate_manifest,
)

PINNED_DATASET = "liamdugan/raid"
PINNED_REVISION = "865cac74188466cb0c3b7574a10204007b57a459"
PINNED_LICENSE = "MIT"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CORPUS_VERSION = "raid-pilot-v1"
SEED = "raid-pilot-v1-2026-11-14"
NEAR_DUPLICATE_THRESHOLD = 0.8
SHINGLE_SIZE = 5
SPLITS = ("development", "validation", "independent-test")
SPLIT_FRACTIONS = {
    "development": 0.6,
    "validation": 0.2,
    "independent-test": 0.2,
}
KNOWN_MODELS = {
    "chatgpt", "gpt4", "gpt3", "gpt2", "llama-chat", "mistral",
    "mistral-chat", "mpt", "mpt-chat", "cohere", "cohere-chat",
}
RAID_MODELS = KNOWN_MODELS | {"human"}
RAID_DOMAINS = {
    "abstracts", "books", "code", "czech", "german", "news", "poetry",
    "recipes", "reddit", "reviews", "wiki",
}
RAID_ATTACKS = {
    "homoglyph", "number", "article_deletion", "insert_paragraphs",
    "perplexity_misspelling", "upper_lower", "whitespace", "zero_width_space",
    "synonym", "paraphrase", "alternative_spelling",
}
# Supervisor-identified source IDs already viewed before this milestone.
SUPERVISOR_FORCED_SOURCE_IDS = (
    "e5e058ce-be2b-459d-af36-32532aaba5ff",
    "f95b107b-d176-4af5-90f7-4d0bb20caf93",
    "856d8972-9e3d-4544-babc-0fe16f21e04d",
    "fbc8a5ea-90fa-47b8-8fa7-73dd954f1524",
    "72c41b8d-0069-4886-b734-a4000ffca286",
)
# Displayed while inspecting the response schema during this session. It is
# forced into development defensively and recorded as an operator observation.
SESSION_VIEWED_SOURCE_IDS = (
    "527dc536-7b69-4c2f-94af-afeb85894a07",
)
FORCED_SOURCE_IDS = SUPERVISOR_FORCED_SOURCE_IDS + SESSION_VIEWED_SOURCE_IDS
DIMENSIONS = {
    "domain": "Upstream RAID genre field. It is not a language or native-speaker assertion.",
    "generator": "Upstream RAID model field: human or a named generator.",
    "attack": "Upstream RAID attack field; non-none values are adversarial derivatives.",
    "language_hint": (
        "Coarse upstream-domain hint only (czech-domain, german-domain, or unknown). "
        "It is not a per-sample language assertion, and no runtime language override is frozen."
    ),
    "length_bucket": (
        "Word-count bucket computed from the frozen sample bytes for reporting only."
    ),
    "upstream_split": (
        "Upstream RAID split field (train or extra), not the nobotrs evaluation split."
    ),
    "label": (
        "Upstream model assertion mapped to human/generated; not universal authorship truth."
    ),
}
LIMITATIONS = [
    "Only copied datasets-server filter views were available; every view is partial.",
    "The pilot is not the complete RAID benchmark and must not be presented as one.",
    "Rows are capped by the acquisition response length; available counts are much larger.",
    "Only abstracts, books, czech, german, news, and poetry are represented.",
    "Code, recipes, reddit, reviews, and wiki responses were absent, empty, or failed.",
    "Most upstream domain/generator/attack cells were never requested or failed.",
    "Only abstracts, books, and news contain GPT-4 paraphrase rows in this snapshot.",
    "Some domains have no human cell (german and news) and some have no chatbot cell.",
    "RAID supplies no native-speaker attribution, so none is inferred or reported.",
    "RAID supplies no per-row language field, so language_hint is only a domain hint.",
    "The detector runs with its default unknown-language policy; no overrides are frozen.",
    "The 12 failed queries and empty responses are recorded, not filled or re-requested.",
    "No RAID test split was requested; the pilot was built only from train/extra views.",
    "Source IDs and exact/near content are grouped before splitting; no text is displayed.",
]


class CurationError(ValueError):
    """A provenance, response, or curation invariant was violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CurationError(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def word_tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def normalized_text(text: str) -> str:
    return " ".join(word_tokens(text))


def shingles(tokens: Iterable[str], size: int = SHINGLE_SIZE) -> frozenset[tuple[str, ...]]:
    tokens = list(tokens)
    if not tokens:
        return frozenset()
    if len(tokens) <= size:
        return frozenset([tuple(tokens)])
    return frozenset(tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1))


def jaccard(left: frozenset[Any], right: frozenset[Any]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def length_bucket(word_count: int) -> str:
    if word_count < 100:
        return "lt-100"
    if word_count < 250:
        return "100-249"
    if word_count < 500:
        return "250-499"
    return "500-plus"


def language_hint(domain: str) -> str:
    if domain == "czech":
        return "czech-domain"
    if domain == "german":
        return "german-domain"
    return "unknown"


def label_for_model(model: str) -> str | None:
    if model == "human":
        return "human"
    if model in KNOWN_MODELS:
        return "generated"
    return None


def load_json_bytes(path: Path) -> tuple[Any, bytes]:
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise CurationError(f"cannot read {path}: {error}") from None
    try:
        return json.loads(data.decode("utf-8")), data
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurationError(f"invalid JSON in {path}: {error}") from None


def resolve_response(cache: Path, query: dict[str, Any]) -> Path:
    """Resolve a response from either the original cache or a copied snapshot."""
    declared = Path(str(query["file"]))
    candidates = []
    if declared.is_absolute():
        candidates.append(declared)
    candidates.extend([
        cache / declared,
        cache / declared.name,
        cache / "responses" / declared.name,
    ])
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    raise CurationError(f"response file for {query.get('url', query.get('file'))} is missing")


def validate_acquisition(cache: Path) -> tuple[dict[str, Any], str]:
    path = cache / "acquisition.json"
    require(path.is_file(), f"missing acquisition record at {path}")
    value, raw = load_json_bytes(path)
    require(isinstance(value, dict), "acquisition record must be a JSON object")
    require(value.get("dataset") == PINNED_DATASET, "unexpected dataset in acquisition record")
    require(value.get("revision") == PINNED_REVISION, "unexpected pinned revision")
    require(PINNED_LICENSE.lower() in str(value.get("upstream_license", "")).lower(),
            "acquisition record does not declare the pinned MIT upstream license")
    require(isinstance(value.get("retrieved"), str)
            and DATE_RE.match(value["retrieved"]),
            "acquisition record must pin retrieved as YYYY-MM-DD")
    require(isinstance(value.get("retrieved_timezone"), str)
            and value["retrieved_timezone"].strip(),
            "acquisition record must pin retrieved_timezone")
    if "original_acquisition_sha256" in value:
        require(isinstance(value["original_acquisition_sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", value["original_acquisition_sha256"]),
                "portable acquisition original hash is invalid")
    queries = value.get("queries")
    require(isinstance(queries, list) and queries, "acquisition record has no queries")
    errors = value.get("errors", [])
    require(isinstance(errors, list), "acquisition errors must be a list")
    seen_queries = set()
    for index, query in enumerate(queries):
        require(isinstance(query, dict), f"queries[{index}] must be an object")
        for field in ("domain", "model", "upstream_split", "revision", "url",
                      "file", "sha256", "rows", "available", "partial_view", "attack"):
            require(field in query, f"queries[{index}] is missing {field}")
        require(query["domain"] in RAID_DOMAINS, f"queries[{index}] has an unknown domain")
        require(query["model"] in RAID_MODELS, f"queries[{index}] has an unknown model")
        require(query["attack"] in RAID_ATTACKS or query["attack"] == "none",
                f"queries[{index}] has an unknown attack")
        require(query["upstream_split"] in ("train", "extra"),
                f"queries[{index}] requested an unsupported or test split")
        require(query["revision"] == PINNED_REVISION,
                f"queries[{index}] revision does not match the pin")
        require(isinstance(query["rows"], int) and not isinstance(query["rows"], bool)
                and query["rows"] >= 0, f"queries[{index}].rows is invalid")
        require(isinstance(query["available"], int) and not isinstance(query["available"], bool)
                and query["available"] >= 0, f"queries[{index}].available is invalid")
        require(isinstance(query["partial_view"], bool),
                f"queries[{index}].partial_view must be boolean")
        require(isinstance(query["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", query["sha256"]),
                f"queries[{index}].sha256 is not lowercase SHA-256")
        key = (query["domain"], query["model"], query["attack"], query["upstream_split"])
        require(key not in seen_queries, f"duplicate acquisition query for {key}")
        seen_queries.add(key)
    for index, error in enumerate(errors):
        require(isinstance(error, dict) and isinstance(error.get("job"), list)
                and len(error["job"]) >= 2 and isinstance(error.get("error"), str),
                f"errors[{index}] is malformed")
    return value, sha256_bytes(raw)


def verify_responses(cache: Path, acquisition: dict[str, Any]) -> list[dict[str, Any]]:
    verified = []
    for query in acquisition["queries"]:
        path = resolve_response(cache, query)
        actual = sha256_file(path)
        require(actual == query["sha256"],
                f"response hash mismatch for {path.name}: {actual} != {query['sha256']}")
        value, raw = load_json_bytes(path)
        require(isinstance(value, dict) and isinstance(value.get("rows"), list),
                f"{path.name} has no rows list")
        require(len(value["rows"]) == query["rows"],
                f"{path.name} row count {len(value['rows'])} != declared {query['rows']}")
        verified.append({
            "domain": query["domain"],
            "model": query["model"],
            "attack": query["attack"],
            "upstream_split": query["upstream_split"],
            "url": query["url"],
            "file": "responses/" + path.name,
            "sha256": actual,
            "rows": query["rows"],
            "available": query["available"],
            "partial_view": query["partial_view"],
            "empty": query["rows"] == 0,
        })
    return verified


def validate_uuid(value: Any, field: str) -> str:
    require(isinstance(value, str), f"{field} must be a string")
    try:
        uuid.UUID(value)
    except ValueError:
        raise CurationError(f"{field} is not a UUID") from None
    return value


def parse_rows(cache: Path, acquisition: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                                   list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for query in acquisition["queries"]:
        path = resolve_response(cache, query)
        value, _ = load_json_bytes(path)
        for item in value["rows"]:
            row_idx = item.get("row_idx") if isinstance(item, dict) else None
            row = item.get("row") if isinstance(item, dict) else None
            truncated = item.get("truncated_cells", []) if isinstance(item, dict) else None
            base = {
                "row_idx": row_idx,
                "response_file": path.name,
                "query_domain": query["domain"],
                "query_model": query["model"],
                "query_attack": query["attack"],
            }
            def reject(reason: str, **details: Any) -> None:
                entry = dict(base)
                entry["reason"] = reason
                entry.update(details)
                rejected.append(entry)

            if not isinstance(item, dict) or not isinstance(row, dict):
                reject("malformed_row_item")
                continue
            if truncated not in (None, []):
                reject("truncated_cells", truncated_cells=truncated)
                continue
            missing = [key for key in ("id", "source_id", "model", "domain", "attack",
                                       "generation") if key not in row]
            if missing:
                reject("missing_fields", missing=missing)
                continue
            try:
                upstream_id = validate_uuid(row["id"], "id")
                source_id = validate_uuid(row["source_id"], "source_id")
            except CurationError as error:
                reject("invalid_identity", detail=str(error))
                continue
            if upstream_id in seen_ids:
                reject("duplicate_upstream_id", id=upstream_id)
                continue
            if row["model"] not in RAID_MODELS:
                reject("unsupported_model", id=upstream_id, model=row["model"])
                continue
            if row["domain"] != query["domain"]:
                reject("query_domain_mismatch", id=upstream_id, row_domain=row["domain"])
                continue
            if row["model"] != query["model"]:
                reject("query_model_mismatch", id=upstream_id, row_model=row["model"])
                continue
            if row["attack"] != query["attack"]:
                reject("query_attack_mismatch", id=upstream_id, row_attack=row["attack"])
                continue
            generation = row["generation"]
            if not isinstance(generation, str):
                reject("generation_not_text", id=upstream_id)
                continue
            if not generation.strip():
                reject("empty_generation", id=upstream_id)
                continue
            tokens = word_tokens(generation)
            if not tokens:
                reject("empty_normalized_generation", id=upstream_id)
                continue
            seen_ids.add(upstream_id)
            accepted.append({
                "id": upstream_id,
                "source_id": source_id,
                "row_idx": row_idx,
                "model": row["model"],
                "domain": row["domain"],
                "attack": row["attack"],
                "decoding": row.get("decoding"),
                "repetition_penalty": row.get("repetition_penalty"),
                "upstream_split": query["upstream_split"],
                "generation": generation,
                "tokens": tokens,
                "normalized": " ".join(tokens),
                "shingles": shingles(tokens),
                "query_url": query["url"],
                "response_file": path.name,
                "response_sha256": query["sha256"],
            })
    return accepted, rejected


def build_components(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                              list[dict[str, str]],
                                                              list[dict[str, Any]]]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for record in records:
        union(record["id"], "source:" + record["source_id"])

    exact_links: list[dict[str, str]] = []
    by_normalized: dict[str, str] = {}
    for record in records:
        key = record["normalized"]
        if key in by_normalized:
            exact_links.append({"left": by_normalized[key], "right": record["id"]})
            union(by_normalized[key], record["id"])
        else:
            by_normalized[key] = record["id"]

    inverted: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for record in records:
        for shingle in record["shingles"]:
            inverted[shingle].append(record["id"])
    seen_pairs: set[tuple[str, str]] = set()
    near_links: list[dict[str, Any]] = []
    by_id = {record["id"]: record for record in records}
    for ids in inverted.values():
        unique_ids = sorted(set(ids))
        for left_index in range(len(unique_ids)):
            for right_index in range(left_index + 1, len(unique_ids)):
                pair = (unique_ids[left_index], unique_ids[right_index])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                similarity = jaccard(by_id[pair[0]]["shingles"], by_id[pair[1]]["shingles"])
                if similarity >= NEAR_DUPLICATE_THRESHOLD:
                    near_links.append({
                        "left": pair[0],
                        "right": pair[1],
                        "jaccard": round(similarity, 6),
                    })
                    union(pair[0], pair[1])

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[find(record["id"])].append(record)
    components = []
    for members in grouped.values():
        members.sort(key=lambda record: record["id"])
        ids = [record["id"] for record in members]
        sources = sorted({record["source_id"] for record in members})
        component_hash = sha256_bytes("\n".join(sorted(ids)).encode("utf-8"))
        if len(sources) == 1:
            source_group = "source:" + sources[0]
        else:
            source_group = "source-group:" + sha256_bytes(
                "\n".join(sources).encode("utf-8")
            )[:32]
        components.append({
            "id": "component:" + component_hash[:32],
            "source_group": source_group,
            "near_duplicate_group": "nd:" + component_hash[:32],
            "sources": sources,
            "members": members,
            "forced": bool(set(sources) & set(FORCED_SOURCE_IDS)),
        })
    components.sort(key=lambda component: component["id"])
    return components, exact_links, near_links


def stable_hash(value: str) -> str:
    return hashlib.sha256((SEED + ":" + value).encode("utf-8")).hexdigest()


def assign_splits(components: list[dict[str, Any]]) -> dict[str, str]:
    forced = [component for component in components if component["forced"]]
    remainder = [component for component in components if not component["forced"]]
    require(bool(forced), "no forced development component was found")
    assignment = {component["id"]: "development" for component in forced}
    counts = {split: 0 for split in SPLITS}
    for component in forced:
        counts["development"] += len(component["members"])
    total = sum(len(component["members"]) for component in components)
    capacity = {split: total * SPLIT_FRACTIONS[split] for split in SPLITS}
    ordered = sorted(remainder, key=lambda component: stable_hash(component["id"]))
    for component in ordered:
        split = max(
            SPLITS,
            key=lambda name: (capacity[name] - counts[name], -SPLITS.index(name)),
        )
        assignment[component["id"]] = split
        counts[split] += len(component["members"])
    for split in SPLITS:
        require(any(value == split for value in assignment.values()),
                f"split {split!r} received no component")
    for component in forced:
        require(assignment[component["id"]] == "development",
                "a forced source component was not assigned to development")
    return assignment


def dimension_values(record: dict[str, Any], label: str | None) -> dict[str, Any]:
    return {
        "domain": record["domain"],
        "generator": record["model"],
        "attack": record["attack"],
        "language_hint": language_hint(record["domain"]),
        "length_bucket": length_bucket(len(record["tokens"])),
        "upstream_split": record["upstream_split"],
        "label": label,
    }


def count_dimensions(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {name: Counter() for name in DIMENSIONS}
    for record in records:
        for name, value in record["dimension_values"].items():
            counts[name][str(value)] += 1
    return {
        name: dict(sorted(values.items()))
        for name, values in counts.items()
    }


def portable_acquisition(acquisition: dict[str, Any], acquisition_sha: str) -> dict[str, Any]:
    """Emit a self-contained acquisition record with only relative paths."""
    upstream_sha = acquisition.get("original_acquisition_sha256", acquisition_sha)
    queries = []
    for query in acquisition["queries"]:
        copy = dict(query)
        copy["file"] = "responses/" + Path(str(query["file"])).name
        queries.append(copy)
    return {
        "dataset": acquisition["dataset"],
        "revision": acquisition["revision"],
        "upstream_license": acquisition["upstream_license"],
        "license_url": acquisition.get("license_url"),
        "retrieved": acquisition["retrieved"],
        "retrieved_timezone": acquisition["retrieved_timezone"],
        "queries": queries,
        "errors": acquisition.get("errors", []),
        "notes": acquisition.get("notes"),
        "portable_snapshot": True,
        "original_acquisition_sha256": upstream_sha,
    }


def copy_snapshot(cache: Path, acquisition: dict[str, Any], acquisition_sha: str,
                  out: Path, verified: list[dict[str, Any]]) -> dict[str, Any]:
    source = out / "source"
    responses = source / "responses"
    responses.mkdir(parents=True)
    portable = portable_acquisition(acquisition, acquisition_sha)
    (source / "acquisition.json").write_text(canonical_json(portable), encoding="utf-8")
    copied = {
        "acquisition.json": sha256_file(source / "acquisition.json"),
    }
    for name in ("dataset-card.md", "LICENSE"):
        origin = cache / name
        require(origin.is_file(), f"missing source snapshot file {name}")
        shutil.copyfile(origin, source / name)
        copied[name] = sha256_file(source / name)
    for item in verified:
        origin = resolve_response(cache, item)
        destination = responses / Path(str(item["file"])).name
        shutil.copyfile(origin, destination)
        require(sha256_file(destination) == item["sha256"],
                f"copied response {item['file']} changed")
    return {
        "path": "source",
        "acquisition_sha256": copied["acquisition.json"],
        "upstream_acquisition_sha256": portable["original_acquisition_sha256"],
        "dataset_card_sha256": copied["dataset-card.md"],
        "license_sha256": copied["LICENSE"],
        "response_count": len(verified),
        "responses": verified,
        "provenance_file": "source/PROVENANCE.json",
    }


def write_provenance(out: Path, acquisition: dict[str, Any],
                     retrieved: str, retrieved_timezone: str,
                     verified: list[dict[str, Any]],
                     snapshot: dict[str, Any]) -> str:
    value = {
        "dataset": PINNED_DATASET,
        "revision": PINNED_REVISION,
        "upstream_license": acquisition.get("upstream_license"),
        "license_url": acquisition.get("license_url"),
        "retrieved": retrieved,
        "retrieved_timezone": retrieved_timezone,
        "upstream_retrieved": acquisition["retrieved"],
        "upstream_retrieved_timezone": acquisition["retrieved_timezone"],
        "retrieved_override": (
            retrieved != acquisition["retrieved"]
            or retrieved_timezone != acquisition["retrieved_timezone"]
        ),
        "acquisition_sha256": snapshot["acquisition_sha256"],
        "upstream_acquisition_sha256": snapshot["upstream_acquisition_sha256"],
        "dataset_card_sha256": snapshot["dataset_card_sha256"],
        "license_sha256": snapshot["license_sha256"],
        "license_note": (
            "The dataset card declares MIT. The copied LICENSE is the upstream "
            "Liam Dugan MIT notice; it is not replaced or relicensed here."
        ),
        "queries": verified,
        "errors": acquisition.get("errors", []),
        "notes": acquisition.get("notes"),
        "reproduction": (
            "Run scripts/curate_raid_pilot.py with --cache pointing at this "
            "source directory. Response paths in the portable acquisition.json "
            "are relative to source/responses/; exact bytes and hashes are preserved."
        ),
    }
    path = out / "source" / "PROVENANCE.json"
    path.write_text(canonical_json(value), encoding="utf-8")
    return sha256_file(path)


def write_corpus(out: Path, cache: Path, retrieved: str | None = None,
                 retrieved_timezone: str | None = None) -> dict[str, Any]:
    acquisition, acquisition_sha = validate_acquisition(cache)
    fixed_retrieved = acquisition["retrieved"]
    fixed_timezone = acquisition["retrieved_timezone"]
    retrieved = retrieved or fixed_retrieved
    retrieved_timezone = retrieved_timezone or fixed_timezone
    require(isinstance(retrieved, str) and DATE_RE.match(retrieved),
            "retrieved must be an explicit YYYY-MM-DD value")
    require(isinstance(retrieved_timezone, str) and retrieved_timezone.strip(),
            "retrieved_timezone must be explicit")
    retrieved_override = (
        retrieved != fixed_retrieved or retrieved_timezone != fixed_timezone
    )
    verified = verify_responses(cache, acquisition)
    records, rejected = parse_rows(cache, acquisition)
    require(bool(records), "no valid rows were imported")
    components, exact_links, near_links = build_components(records)
    assignment = assign_splits(components)

    samples_dir = out / "samples"
    samples_dir.mkdir(parents=True)
    snapshot = copy_snapshot(cache, acquisition, acquisition_sha, out, verified)
    provenance_sha = write_provenance(
        out, acquisition, retrieved, retrieved_timezone, verified, snapshot
    )

    samples = []
    for component in components:
        split = assignment[component["id"]]
        for record in component["members"]:
            label = label_for_model(record["model"])
            values = dimension_values(record, label)
            record["dimension_values"] = values
            data = record["generation"].encode("utf-8")
            file_name = f"samples/{record['id']}.txt"
            (out / file_name).write_bytes(data)
            content_sha = sha256_bytes(data)
            provenance = {
                "source": (
                    f"https://huggingface.co/datasets/{PINNED_DATASET}@"
                    f"{PINNED_REVISION}; response_sha256:{record['response_sha256']}"
                ),
                "retrieved": retrieved,
            }
            samples.append({
                "id": record["id"],
                "file": file_name,
                "split": split,
                "slice": "domain:" + record["domain"],
                "source_group": component["source_group"],
                "near_duplicate_group": component["near_duplicate_group"],
                "label": label,
                "license": PINNED_LICENSE,
                "provenance": provenance,
                "content_sha256": content_sha,
                "source_id": record["source_id"],
                "model": record["model"],
                "domain": record["domain"],
                "attack": record["attack"],
                "decoding": record["decoding"],
                "repetition_penalty": record["repetition_penalty"],
                "upstream_split": record["upstream_split"],
                "upstream_row_idx": record["row_idx"],
                "response_file": "source/responses/" + record["response_file"],
                "response_sha256": record["response_sha256"],
                "query_url": record["query_url"],
                "word_count": len(record["tokens"]),
                "label_source": (
                    "Upstream RAID model field assertion; human when model=human, "
                    "generated for other known models. Not universal authorship truth."
                ),
                "upstream_assertion": {
                    "dataset": PINNED_DATASET,
                    "revision": PINNED_REVISION,
                    "row_id": record["id"],
                    "source_id": record["source_id"],
                    "model": record["model"],
                    "domain": record["domain"],
                    "attack": record["attack"],
                    "decoding": record["decoding"],
                    "repetition_penalty": record["repetition_penalty"],
                },
                "dimension_values": values,
            })
    samples.sort(key=lambda sample: sample["id"])
    content_hash = corpus_content_sha256(samples)

    split_counts = Counter(sample["split"] for sample in samples)
    dimension_counts = count_dimensions([
        {**sample, "tokens": [""] * sample["word_count"]}
        for sample in samples
    ])
    split_dimensions = {
        split: count_dimensions([
            {**sample, "tokens": [""] * sample["word_count"]}
            for sample in samples if sample["split"] == split
        ])
        for split in SPLITS
    }
    label_counts = Counter(str(sample["label"]) for sample in samples)
    split_label_counts = {
        split: dict(sorted(Counter(
            str(sample["label"]) for sample in samples if sample["split"] == split
        ).items()))
        for split in SPLITS
    }
    component_counts = {
        split: sum(1 for component in components
                   if assignment[component["id"]] == split)
        for split in SPLITS
    }
    forced_found = sorted({
        sample["source_id"] for sample in samples
        if sample["source_id"] in FORCED_SOURCE_IDS
    })
    forced_not_development = sorted({
        sample["source_id"] for sample in samples
        if sample["source_id"] in FORCED_SOURCE_IDS and sample["split"] != "development"
    })
    require(not forced_not_development,
            "a forced source has a non-development sample")
    missing_forced = sorted(set(FORCED_SOURCE_IDS) - set(forced_found))
    require(not missing_forced, f"forced source IDs not found: {missing_forced}")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "corpus_version": CORPUS_VERSION,
        "corpus_revision": f"{PINNED_DATASET}@{PINNED_REVISION}",
        "purpose": (
            "Limited RAID pilot for development/validation plumbing and methodology. "
            "It is not the complete RAID benchmark, not independent accuracy "
            "certification, and held-out text is unopened."
        ),
        "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
        "license": PINNED_LICENSE,
        "retrieved": retrieved,
        "retrieved_timezone": retrieved_timezone,
        "retrieved_override": retrieved_override,
        "source_snapshot": {
            "path": "source",
            "acquisition_sha256": snapshot["acquisition_sha256"],
            "upstream_acquisition_sha256": snapshot["upstream_acquisition_sha256"],
            "dataset_card_sha256": snapshot["dataset_card_sha256"],
            "license_sha256": snapshot["license_sha256"],
            "provenance_sha256": provenance_sha,
            "response_count": snapshot["response_count"],
        },
        "dimensions": DIMENSIONS,
        "language_policy": {
            "runtime_default": "unknown",
            "per_sample_overrides": False,
            "overrides_recorded": [],
            "note": (
                "No frozen language overrides were designed. Default-runtime "
                "evaluation keeps the unknown-language policy; language_hint is "
                "only a coarse upstream-domain reporting dimension."
            ),
        },
        "split_policy": {
            "seed": SEED,
            "method": (
                "Union source_id derivatives, exact normalized duplicates, and "
                "5-word-shingle Jaccard >= 0.8 before deterministic SHA-256 "
                "ordering and greedy target-capacity assignment."
            ),
            "target_fractions": SPLIT_FRACTIONS,
            "forced_to_development": list(FORCED_SOURCE_IDS),
            "supervisor_forced_source_ids": list(SUPERVISOR_FORCED_SOURCE_IDS),
            "session_viewed_source_ids": list(SESSION_VIEWED_SOURCE_IDS),
        },
        "curation_audit": "curation.json",
        "limitations": LIMITATIONS,
        "counts": {
            "samples": len(samples),
            "components": len(components),
            "splits": dict(sorted(split_counts.items())),
            "split_components": component_counts,
            "labels": dict(sorted(label_counts.items())),
            "split_labels": split_label_counts,
            "dimensions": dimension_counts,
            "split_dimensions": split_dimensions,
        },
        "samples": samples,
    }
    manifest["corpus_content_sha256"] = content_hash
    # Validate our own output with the same protocol used by the runner.
    manifest_path = out / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    validate_manifest(
        manifest, manifest_path, split="development", require_content_hashes=True,
        require_near_duplicate_groups=True,
    )
    validate_grouping(samples, None, threshold=NEAR_DUPLICATE_THRESHOLD)

    audit = {
        "schema_version": "1.0.0",
        "corpus_version": CORPUS_VERSION,
        "generated_by": "scripts/curate_raid_pilot.py",
        "dataset": PINNED_DATASET,
        "revision": PINNED_REVISION,
        "upstream_license": PINNED_LICENSE,
        "retrieved": retrieved,
        "retrieved_timezone": retrieved_timezone,
        "retrieved_override": retrieved_override,
        "manifest_sha256": sha256_file(manifest_path),
        "corpus_content_sha256": content_hash,
        "acquisition": {
            "portable_sha256": snapshot["acquisition_sha256"],
            "upstream_acquisition_sha256": snapshot["upstream_acquisition_sha256"],
            "queries": verified,
            "query_count": len(verified),
            "empty_query_count": sum(1 for item in verified if item["empty"]),
            "errors": acquisition.get("errors", []),
            "error_count": len(acquisition.get("errors", [])),
            "notes": acquisition.get("notes"),
        },
        "source_snapshot": snapshot,
        "row_accounting": {
            "rows_seen": sum(item["rows"] for item in verified),
            "accepted": len(records),
            "rejected": len(rejected),
            "rejected_by_reason": dict(sorted(Counter(
                item["reason"] for item in rejected
            ).items())),
            "rejected_rows": rejected,
        },
        "grouping": {
            "source_id_count": len({record["source_id"] for record in records}),
            "component_count": len(components),
            "component_size_distribution": dict(sorted(Counter(
                len(component["members"]) for component in components
            ).items())),
            "components_with_multiple_source_ids": sum(
                1 for component in components if len(component["sources"]) > 1
            ),
            "exact_normalized_duplicate_links": exact_links,
            "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
            "shingle_size": SHINGLE_SIZE,
            "near_duplicate_links": near_links,
            "forced_source_ids": {
                "supervisor": list(SUPERVISOR_FORCED_SOURCE_IDS),
                "session_inspection": list(SESSION_VIEWED_SOURCE_IDS),
                "found": forced_found,
                "all_related_members_development": True,
            },
        },
        "splits": {
            "seed": SEED,
            "target_fractions": SPLIT_FRACTIONS,
            "method": (
                "Forced components first; remaining components ordered by "
                "SHA-256(seed:component_id), assigned to the split with the "
                "largest remaining target capacity."
            ),
            "components_per_split": component_counts,
            "samples_per_split": dict(sorted(split_counts.items())),
            "labels_per_split": split_label_counts,
            "dimensions_per_split": split_dimensions,
            "dimensions_overall": dimension_counts,
        },
        "labels": {
            "rule": "model=human -> human; other known RAID models -> generated",
            "known_models": sorted(RAID_MODELS),
            "provenance_claim": (
                "Labels preserve the upstream RAID assertion. They are not a "
                "universal truth claim or independent authorship verification."
            ),
            "counts": dict(sorted(label_counts.items())),
        },
        "language": {
            "runtime_policy": "unknown-language default",
            "per_sample_overrides": False,
            "overrides_recorded": [],
            "language_hint_values": dimension_counts.get("language_hint", {}),
            "native_speaker_status": "not provided by RAID; not inferred",
        },
        "coverage_gaps": {
            "partial_api_views": True,
            "domains_present": sorted({record["domain"] for record in records}),
            "domains_absent_from_pilot": sorted(
                RAID_DOMAINS - {record["domain"] for record in records}
            ),
            "models_present": sorted({record["model"] for record in records}),
            "models_absent_from_pilot": sorted(
                RAID_MODELS - {record["model"] for record in records}
            ),
            "attacks_present": sorted({record["attack"] for record in records}),
            "domains_with_paraphrase": sorted({
                record["domain"] for record in records if record["attack"] == "paraphrase"
            }),
            "domains_without_human": sorted(
                {record["domain"] for record in records}
                - {record["domain"] for record in records if record["model"] == "human"}
            ),
            "empty_queries": [item for item in verified if item["empty"]],
            "failed_queries": acquisition.get("errors", []),
            "no_test_split_requested": True,
            "native_speaker_attribution": "absent upstream; not inferred",
            "per_sample_language_field": "absent upstream; language_hint is a domain hint",
        },
        "claims": {
            "complete_raid_benchmark": False,
            "general_accuracy_certification": False,
            "independent_test_opened": False,
            "thresholds_or_defaults_changed": False,
            "held_out_text_or_results_displayed": False,
        },
        "limitations": LIMITATIONS,
        "operator_notes": [
            "The five supervisor-listed source IDs and all related component members were forced to development.",
            "One additional poetry source was displayed during schema inspection; it was forced to development defensively.",
            "Only metadata and counts are included in this audit; sample text is in samples/ and is not summarized.",
            "No detector was run on independent-test samples and no access record was claimed or reset.",
        ],
    }
    curation_path = out / "curation.json"
    curation_path.write_text(canonical_json(audit), encoding="utf-8")
    summary = {
        "corpus_version": CORPUS_VERSION,
        "revision": PINNED_REVISION,
        "manifest_sha256": sha256_file(manifest_path),
        "curation_sha256": sha256_file(curation_path),
        "corpus_content_sha256": content_hash,
        "samples": len(samples),
        "splits": dict(sorted(split_counts.items())),
        "split_components": component_counts,
        "labels": dict(sorted(label_counts.items())),
        "split_labels": split_label_counts,
        "dimensions": dimension_counts,
        "split_dimensions": split_dimensions,
        "row_accounting": audit["row_accounting"],
        "coverage_gaps": audit["coverage_gaps"],
        "limitations": LIMITATIONS,
    }
    (out / "summary.json").write_text(canonical_json(summary), encoding="utf-8")
    return summary


def prepare_output(out: Path) -> None:
    """Require a fresh or empty output directory; never replace existing data."""
    if out.is_symlink():
        raise CurationError("output directory must not be a symlink")
    if out.exists():
        if not out.is_dir():
            raise CurationError(f"output path {out} exists and is not a directory")
        if any(out.iterdir()):
            raise CurationError(
                f"output directory {out} is not empty; use a fresh directory"
            )
    out.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/nobotrs-raid-cache"))
    parser.add_argument("--out", type=Path,
                        default=Path("evaluation/corpora/raid-pilot-v1"))
    parser.add_argument("--retrieved", default=None,
                        help="explicit YYYY-MM-DD; defaults to the acquisition record")
    parser.add_argument("--retrieved-timezone", default=None,
                        help="explicit IANA timezone; defaults to the acquisition record")
    args = parser.parse_args()
    try:
        prepare_output(args.out)
        summary = write_corpus(
            args.out, args.cache, args.retrieved, args.retrieved_timezone
        )
    except (CurationError, ProtocolError, OSError) as error:
        print(f"curate: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "corpus_version": summary["corpus_version"],
        "samples": summary["samples"],
        "splits": summary["splits"],
        "split_components": summary["split_components"],
        "labels": summary["labels"],
        "rejected": summary["row_accounting"]["rejected"],
        "corpus_content_sha256": summary["corpus_content_sha256"],
        "manifest_sha256": summary["manifest_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
