#!/usr/bin/env python3
"""Curate a joint HC3 + fresh RAID assessment pilot from copied local caches.

Only metadata and content hashes are printed. Raw questions, answers, payloads,
and diffs are never displayed. The old RAID v1 corpus is read for exclusion
metadata only and is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import uuid
from collections import Counter, defaultdict
from typing import Any, Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    SCHEMA_VERSION,
    ProtocolError,
    corpus_content_sha256,
    load_json,
    load_retirement,
    read_sample_texts,
    sha256_bytes,
    sha256_file,
    validate_grouping,
    validate_manifest,
    validate_retirement,
)

HC3_DATASET = "Hello-SimpleAI/HC3"
HC3_REVISION = "4d0ff18143b5a7e1b1e79beb540c04549d1e59d3"
HC3_LICENSE = "CC-BY-SA-4.0"
RAID_DATASET = "liamdugan/raid"
RAID_REVISION = "865cac74188466cb0c3b7574a10204007b57a459"
RAID_LICENSE = "MIT"
CORPUS_VERSION = "assessment-pilot-v1"
SEED = "assessment-pilot-v1-2026-11-14"
NEAR_THRESHOLD = 0.8
SHINGLE_SIZE = 5
SPLITS = ("development", "validation", "independent-test")
FRACTIONS = {"development": 0.6, "validation": 0.2, "independent-test": 0.2}
HC3_VIEWED_QUESTION_IDS = tuple(range(15))
HC3_SOURCES = ("finance", "medicine", "open_qa", "reddit_eli5", "wiki_csai")
RAID_MODELS = {
    "chatgpt", "gpt4", "gpt3", "gpt2", "llama-chat", "mistral",
    "mistral-chat", "mpt", "mpt-chat", "cohere", "cohere-chat", "human",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIMENSIONS = {
    "corpus_source": "Pinned source corpus: hc3 or raid-fresh.",
    "domain": "HC3 source file or upstream RAID domain.",
    "generator": "human, chatgpt, or an upstream RAID model name.",
    "attack": "none, or an upstream RAID attack name.",
    "language_hint": "unknown; no per-sample language assertion or native-speaker inference.",
    "length_bucket": "Word-count bucket computed from the frozen sample bytes.",
    "label": "Upstream answer/model assertion mapped to human/generated; not universal truth.",
    "pairing": "single answer, or a deterministic mixed control when present.",
    "hc3_question_band": "HC3 question ordinal band; 0-14 is the externally viewed band.",
}
LIMITATIONS = [
    "Limited pilot, not a complete HC3 or RAID benchmark and not an accuracy certification.",
    "HC3 uses only the first 50 pinned records from five source files.",
    "HC3 question ordinals are local nonempty record positions; the source has no stable row id.",
    "HC3 source IDs/question IDs 0-14 are forced to development conservatively across all five sources.",
    "Fresh RAID is a 350-row partial API window with 100 human rows; most RAID cells are absent.",
    "Fresh RAID rows overlapping any old RAID v1 source_id are excluded.",
    "HC3 and fresh RAID samples overlapping any old RAID v1 normalized text or 5-shingle Jaccard >=0.8 are excluded.",
    "No native-speaker labels are present or inferred.",
    "The default unknown-language policy is retained; no per-sample overrides are frozen.",
    "No mixed human-prefix/generated-suffix controls are included in this version.",
    "No detector has been run on these corpora; independent-test text is not read by curation preflight.",
]


class CurationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CurationError(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def word_tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


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


def length_bucket(count: int) -> str:
    if count < 100:
        return "lt-100"
    if count < 250:
        return "100-249"
    if count < 500:
        return "250-499"
    return "500-plus"


def stable_hash(value: str) -> str:
    return hashlib.sha256((SEED + ":" + value).encode("utf-8")).hexdigest()


def label_for_model(model: str) -> str | None:
    if model == "human":
        return "human"
    if model in RAID_MODELS:
        return "generated"
    return None


def resolve_response(cache: pathlib.Path, name: str) -> pathlib.Path:
    declared = pathlib.Path(str(name))
    candidates = [cache / declared, cache / declared.name, cache / "responses" / declared.name]
    if declared.is_absolute():
        candidates.insert(0, declared)
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    raise CurationError(f"missing response file {declared.name}")


def validate_retrieval(value: dict[str, Any], label: str) -> None:
    require(isinstance(value.get("retrieved"), str) and DATE_RE.match(value["retrieved"]),
            f"{label} must pin retrieved as YYYY-MM-DD")
    require(isinstance(value.get("retrieved_timezone"), str) and value["retrieved_timezone"].strip(),
            f"{label} must pin retrieved_timezone")


def load_hc3(cache: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    acquisition_path = cache / "acquisition.json"
    acquisition = load_json(acquisition_path, "HC3 acquisition")
    require(acquisition.get("dataset") == HC3_DATASET, "HC3 dataset pin mismatch")
    require(acquisition.get("revision") == HC3_REVISION, "HC3 revision pin mismatch")
    require(str(acquisition.get("declared_license", "")).upper() == HC3_LICENSE,
            "HC3 declared license mismatch")
    validate_retrieval(acquisition, "HC3 acquisition")
    card_path = cache / "dataset-card.md"
    require(card_path.is_file(), "HC3 dataset card missing")
    require(sha256_file(card_path) == acquisition.get("dataset_card_sha256"),
            "HC3 dataset card hash mismatch")
    card_text = card_path.read_text(encoding="utf-8").lower()
    require("license: cc-by-sa-4.0" in card_text, "HC3 card does not declare CC-BY-SA-4.0")
    responses = acquisition.get("responses")
    require(isinstance(responses, list) and len(responses) == 5, "HC3 response list is incomplete")
    verified = []
    records = []
    rejected = []
    for response in responses:
        source = response.get("source")
        require(source in HC3_SOURCES, f"unexpected HC3 source {source!r}")
        path = resolve_response(cache, response["file"])
        require(sha256_file(path) == response["sha256"], f"HC3 response hash mismatch for {source}")
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(lines) == response["rows"], f"HC3 row count mismatch for {source}")
        verified.append({
            "source": source,
            "file": "responses/" + path.name,
            "sha256": response["sha256"],
            "rows": response["rows"],
            "url": response.get("url"),
            "selection": response.get("selection"),
        })
        for question_id, line in enumerate(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                rejected.append({"source": source, "question_id": question_id,
                                 "reason": "invalid_jsonl_record"})
                continue
            if not isinstance(record, dict):
                rejected.append({"source": source, "question_id": question_id,
                                 "reason": "record_not_object"})
                continue
            question = record.get("question")
            if not isinstance(question, str) or not question.strip():
                rejected.append({"source": source, "question_id": question_id,
                                 "reason": "missing_or_empty_question"})
                continue
            for role, key, label in (
                ("human", "human_answers", "human"),
                ("generated", "chatgpt_answers", "generated"),
            ):
                answers = record.get(key)
                if not isinstance(answers, list):
                    rejected.append({"source": source, "question_id": question_id,
                                     "reason": f"{key}_not_list"})
                    continue
                for answer_index, text in enumerate(answers):
                    if not isinstance(text, str) or not text.strip():
                        rejected.append({"source": source, "question_id": question_id,
                                         "reason": "empty_answer"})
                        continue
                    tokens = word_tokens(text)
                    if not tokens:
                        rejected.append({"source": source, "question_id": question_id,
                                         "reason": "empty_normalized_answer"})
                        continue
                    records.append({
                        "id": f"hc3-{source}-q{question_id}-{role[0]}{answer_index}",
                        "dataset": HC3_DATASET,
                        "corpus_source": "hc3",
                        "source": source,
                        "question_id": question_id,
                        "answer_index": answer_index,
                        "answer_role": role,
                        "text": text,
                        "tokens": tokens,
                        "normalized": " ".join(tokens),
                        "shingles": shingles(tokens),
                        "label": label,
                        "source_id": f"hc3@{HC3_REVISION}:{source}:q{question_id}",
                        "base_group": f"hc3@{HC3_REVISION}:{source}:q{question_id}",
                        "domain": source,
                        "model": "human" if role == "human" else "chatgpt",
                        "attack": "none",
                        "license": HC3_LICENSE,
                        "provenance": {
                            "source": f"{response.get('url')}; response_sha256:{response['sha256']}",
                            "retrieved": acquisition["retrieved"],
                        },
                        "forced_development": question_id in HC3_VIEWED_QUESTION_IDS,
                    })
    metadata = {
        "dataset": HC3_DATASET,
        "revision": HC3_REVISION,
        "declared_license": HC3_LICENSE,
        "license_url": acquisition.get("license_url"),
        "retrieved": acquisition["retrieved"],
        "retrieved_timezone": acquisition["retrieved_timezone"],
        "acquisition_sha256": sha256_file(acquisition_path),
        "dataset_card_sha256": sha256_file(card_path),
        "responses": verified,
        "viewed_question_ids_force_development": list(HC3_VIEWED_QUESTION_IDS),
    }
    return acquisition, verified, records, {"metadata": metadata, "rejected": rejected,
                                            "acquisition_path": acquisition_path,
                                            "card_path": card_path}


def load_raid_fresh(cache: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    acquisition_path = cache / "acquisition.json"
    acquisition = load_json(acquisition_path, "RAID fresh acquisition")
    require(acquisition.get("dataset") == RAID_DATASET, "RAID fresh dataset pin mismatch")
    require(acquisition.get("revision") == RAID_REVISION, "RAID fresh revision pin mismatch")
    require(RAID_LICENSE.lower() in str(acquisition.get("upstream_license", "")).lower(),
            "RAID fresh license mismatch")
    validate_retrieval(acquisition, "RAID fresh acquisition")
    card_path = cache / "dataset-card.md"
    license_path = cache / "LICENSE"
    require(card_path.is_file() and license_path.is_file(), "RAID fresh card/license missing")
    require("license: mit" in card_path.read_text(encoding="utf-8").lower(),
            "RAID fresh card does not declare MIT")
    license_text = license_path.read_text(encoding="utf-8")
    require("MIT License" in license_text and "Liam Dugan" in license_text,
            "RAID fresh LICENSE is not the upstream Liam Dugan MIT notice")
    queries = acquisition.get("queries")
    require(isinstance(queries, list) and queries, "RAID fresh acquisition has no queries")
    verified = []
    records = []
    rejected = []
    seen_ids = set()
    for query in queries:
        path = resolve_response(cache, query["file"])
        require(sha256_file(path) == query["sha256"],
                f"RAID fresh response hash mismatch for {path.name}")
        payload = load_json(path, "RAID fresh response")
        rows = payload.get("rows")
        require(isinstance(rows, list) and len(rows) == query["rows"],
                f"RAID fresh row count mismatch for {path.name}")
        verified.append({
            "file": "responses/" + path.name,
            "sha256": query["sha256"],
            "rows": query["rows"],
            "available": query.get("available"),
            "partial_view": query.get("partial_view"),
            "offset": query.get("offset"),
            "length": query.get("length"),
            "url": query.get("url"),
        })
        for item in rows:
            row = item.get("row") if isinstance(item, dict) else None
            base = {"file": path.name, "row_idx": item.get("row_idx") if isinstance(item, dict) else None}
            if not isinstance(row, dict):
                rejected.append({**base, "reason": "malformed_row"})
                continue
            missing = [key for key in ("id", "source_id", "model", "domain", "attack", "generation")
                       if key not in row]
            if missing:
                rejected.append({**base, "reason": "missing_fields", "missing": missing})
                continue
            try:
                upstream_id = str(uuid.UUID(row["id"]))
                source_id = str(uuid.UUID(row["source_id"]))
            except (ValueError, TypeError):
                rejected.append({**base, "reason": "invalid_identity"})
                continue
            if upstream_id in seen_ids:
                rejected.append({**base, "reason": "duplicate_upstream_id", "id": upstream_id})
                continue
            if row["model"] not in RAID_MODELS:
                rejected.append({**base, "reason": "unsupported_model", "id": upstream_id})
                continue
            if row["domain"] != query.get("domain") or row["model"] != query.get("model") \
                    or row["attack"] != query.get("attack"):
                rejected.append({**base, "reason": "query_mismatch", "id": upstream_id})
                continue
            generation = row["generation"]
            if not isinstance(generation, str) or not generation.strip():
                rejected.append({**base, "reason": "empty_generation", "id": upstream_id})
                continue
            tokens = word_tokens(generation)
            if not tokens:
                rejected.append({**base, "reason": "empty_normalized_generation", "id": upstream_id})
                continue
            seen_ids.add(upstream_id)
            records.append({
                "id": "raid-" + upstream_id,
                "dataset": RAID_DATASET,
                "corpus_source": "raid-fresh",
                "upstream_id": upstream_id,
                "source_id": source_id,
                "base_group": f"raid@{RAID_REVISION}:source:{source_id}",
                "domain": row["domain"],
                "model": row["model"],
                "attack": row["attack"],
                "decoding": row.get("decoding"),
                "repetition_penalty": row.get("repetition_penalty"),
                "text": generation,
                "tokens": tokens,
                "normalized": " ".join(tokens),
                "shingles": shingles(tokens),
                "label": label_for_model(row["model"]),
                "license": RAID_LICENSE,
                "provenance": {
                    "source": f"https://huggingface.co/datasets/{RAID_DATASET}@{RAID_REVISION}; response_sha256:{query['sha256']}",
                    "retrieved": acquisition["retrieved"],
                },
                "forced_development": False,
            })
    metadata = {
        "dataset": RAID_DATASET,
        "revision": RAID_REVISION,
        "upstream_license": RAID_LICENSE,
        "license_url": acquisition.get("license_url"),
        "retrieved": acquisition["retrieved"],
        "retrieved_timezone": acquisition["retrieved_timezone"],
        "acquisition_sha256": sha256_file(acquisition_path),
        "dataset_card_sha256": sha256_file(card_path),
        "license_sha256": sha256_file(license_path),
        "queries": verified,
        "errors": acquisition.get("errors", []),
    }
    return acquisition, verified, records, {"metadata": metadata, "rejected": rejected,
                                            "acquisition_path": acquisition_path,
                                            "card_path": card_path,
                                            "license_path": license_path}


def load_old_exclusions(old_root: pathlib.Path) -> dict[str, Any]:
    manifest_path = old_root / "manifest.json"
    manifest = load_json(manifest_path, "old RAID v1 manifest")
    info = validate_manifest(
        manifest, manifest_path, split="independent-test",
        require_content_hashes=True, require_near_duplicate_groups=True,
    )
    retirement_path = old_root / "retirement.json"
    retirement = load_retirement(old_root)
    require(retirement is not None, "old RAID v1 retirement ledger is missing")
    retirement_info = validate_retirement(retirement, info)
    texts = read_sample_texts(info.samples, old_root, verify_hashes=True)
    source_ids = set()
    normalized = set()
    shingle_list = []
    index = defaultdict(list)
    for sample in info.samples:
        tokens = word_tokens(texts[sample["id"]])
        norm = " ".join(tokens)
        sh = shingles(tokens)
        source_ids.add(sample["source_id"])
        normalized.add(norm)
        position = len(shingle_list)
        shingle_list.append(sh)
        for value in sh:
            index[value].append(position)
    return {
        "root": str(old_root),
        "manifest_sha256": sha256_file(manifest_path),
        "corpus_content_sha256": info.corpus_content_sha256,
        "retirement_sha256": sha256_file(retirement_path),
        "retirement_status": retirement_info["status"],
        "source_ids": source_ids,
        "normalized": normalized,
        "shingles": shingle_list,
        "index": index,
        "sample_count": len(info.samples),
    }


def old_exclusion(record: dict[str, Any], old: dict[str, Any]) -> str | None:
    if record["corpus_source"] == "raid-fresh" and record["source_id"] in old["source_ids"]:
        return "old_raid_v1_source_id_overlap"
    if record["normalized"] in old["normalized"]:
        return "old_raid_v1_exact_overlap"
    candidates = set()
    for value in record["shingles"]:
        candidates.update(old["index"].get(value, ()))
    if any(jaccard(record["shingles"], old["shingles"][i]) >= NEAR_THRESHOLD
           for i in candidates):
        return "old_raid_v1_near_duplicate_overlap"
    return None


def build_components(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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
        union(record["id"], "base:" + record["base_group"])
    exact_links = []
    by_norm = {}
    for record in records:
        if record["normalized"] in by_norm:
            exact_links.append({"left": by_norm[record["normalized"]], "right": record["id"]})
            union(by_norm[record["normalized"]], record["id"])
        else:
            by_norm[record["normalized"]] = record["id"]
    inverted = defaultdict(list)
    for record in records:
        for value in record["shingles"]:
            inverted[value].append(record["id"])
    near_links = []
    seen_pairs = set()
    by_id = {record["id"]: record for record in records}
    for ids in inverted.values():
        unique = sorted(set(ids))
        for left in range(len(unique)):
            for right in range(left + 1, len(unique)):
                pair = (unique[left], unique[right])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                similarity = jaccard(by_id[pair[0]]["shingles"], by_id[pair[1]]["shingles"])
                if similarity >= NEAR_THRESHOLD:
                    near_links.append({"left": pair[0], "right": pair[1],
                                       "jaccard": round(similarity, 6)})
                    union(pair[0], pair[1])
    grouped = defaultdict(list)
    for record in records:
        grouped[find(record["id"])].append(record)
    components = []
    for members in grouped.values():
        members.sort(key=lambda record: record["id"])
        ids = [record["id"] for record in members]
        component_hash = sha256_bytes("\n".join(ids).encode("utf-8"))
        bases = sorted({record["base_group"] for record in members})
        source_group = bases[0] if len(bases) == 1 else "component:" + component_hash[:32]
        components.append({
            "id": "component:" + component_hash[:32],
            "source_group": source_group,
            "near_duplicate_group": "nd:" + component_hash[:32],
            "members": members,
            "bases": bases,
            "forced": any(record["forced_development"] for record in members),
            "cross_corpus": len({record["corpus_source"] for record in members}) > 1,
        })
    components.sort(key=lambda component: component["id"])
    return components, exact_links, near_links


def assign_splits(components: list[dict[str, Any]]) -> dict[str, str]:
    forced = [component for component in components if component["forced"]]
    remainder = [component for component in components if not component["forced"]]
    require(bool(forced), "no forced HC3 components found")
    assignment = {component["id"]: "development" for component in forced}
    counts = {split: 0 for split in SPLITS}
    for component in forced:
        counts["development"] += len(component["members"])
    total = sum(len(component["members"]) for component in components)
    capacity = {split: total * FRACTIONS[split] for split in SPLITS}
    for component in sorted(remainder, key=lambda item: stable_hash(item["id"])):
        split = max(SPLITS, key=lambda name: (capacity[name] - counts[name], -SPLITS.index(name)))
        assignment[component["id"]] = split
        counts[split] += len(component["members"])
    for split in SPLITS:
        require(any(value == split for value in assignment.values()),
                f"split {split!r} received no component")
    return assignment


def dimensions(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "corpus_source": record["corpus_source"],
        "domain": record["domain"],
        "generator": record["model"],
        "attack": record["attack"],
        "language_hint": "unknown",
        "length_bucket": length_bucket(len(record["tokens"])),
        "label": record["label"],
        "pairing": "single",
        "hc3_question_band": (
            "0-14" if record["corpus_source"] == "hc3" and record["question_id"] <= 14
            else ("15-49" if record["corpus_source"] == "hc3" else "not-applicable")
        ),
    }


def count_dimensions(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts = {name: Counter() for name in DIMENSIONS}
    for record in records:
        for name, value in record["dimension_values"].items():
            counts[name][str(value)] += 1
    return {name: dict(sorted(values.items())) for name, values in counts.items()}


def copy_snapshot(source_cache: pathlib.Path, metadata: dict[str, Any], out: pathlib.Path,
                  kind: str) -> dict[str, Any]:
    root = out / "source" / kind
    responses = root / "responses"
    responses.mkdir(parents=True)
    if kind == "hc3":
        portable = dict(metadata)
        portable["responses"] = [
            {**item, "file": "responses/" + pathlib.Path(item["file"]).name}
            for item in metadata["responses"]
        ]
        portable["portable_snapshot"] = True
        (root / "acquisition.json").write_text(canonical_json(portable), encoding="utf-8")
        shutil.copyfile(source_cache / "dataset-card.md", root / "dataset-card.md")
        response_items = metadata["responses"]
        card_name = "dataset-card.md"
        license_name = None
    else:
        acquisition = load_json(source_cache / "acquisition.json", "RAID fresh acquisition")
        queries = []
        for query in acquisition["queries"]:
            copy = dict(query)
            copy["file"] = "responses/" + pathlib.Path(str(query["file"])).name
            queries.append(copy)
        portable = dict(acquisition)
        portable["queries"] = queries
        portable["portable_snapshot"] = True
        portable["original_acquisition_sha256"] = metadata["acquisition_sha256"]
        (root / "acquisition.json").write_text(canonical_json(portable), encoding="utf-8")
        shutil.copyfile(source_cache / "dataset-card.md", root / "dataset-card.md")
        shutil.copyfile(source_cache / "LICENSE", root / "LICENSE")
        response_items = metadata["queries"]
        card_name = "dataset-card.md"
        license_name = "LICENSE"
    for item in response_items:
        origin = resolve_response(source_cache, item["file"])
        destination = responses / pathlib.Path(item["file"]).name
        shutil.copyfile(origin, destination)
        require(sha256_file(destination) == item["sha256"],
                f"copied {kind} response changed")
    snapshot = {
        "path": f"source/{kind}",
        "acquisition_sha256": sha256_file(root / "acquisition.json"),
        "upstream_acquisition_sha256": metadata["acquisition_sha256"],
        "dataset_card_sha256": sha256_file(root / card_name),
        "retrieved": metadata["retrieved"],
        "retrieved_timezone": metadata["retrieved_timezone"],
        "response_count": len(response_items),
    }
    if license_name:
        snapshot["license_sha256"] = sha256_file(root / license_name)
    return snapshot


def prepare_output(out: pathlib.Path) -> None:
    """Refuse occupied/symlinked outputs before reading or copying any source."""
    if out.is_symlink():
        raise CurationError("output directory must not be a symlink")
    if out.exists():
        if not out.is_dir():
            raise CurationError("output path exists and is not a directory")
        if any(out.iterdir()):
            raise CurationError("output directory must be fresh or empty")
    out.mkdir(parents=True, exist_ok=True)


def write_corpus(out: pathlib.Path, hc3_cache: pathlib.Path, raid_cache: pathlib.Path,
                 old_root: pathlib.Path, retrieved: str | None = None) -> dict[str, Any]:
    prepare_output(out)
    hc3_acq, hc3_verified, hc3_records, hc3_info = load_hc3(hc3_cache)
    raid_acq, raid_verified, raid_records, raid_info = load_raid_fresh(raid_cache)
    old = load_old_exclusions(old_root)
    fixed_retrieved = hc3_acq["retrieved"]
    fixed_timezone = hc3_acq["retrieved_timezone"]
    require(raid_acq["retrieved"] == fixed_retrieved, "source retrieval dates differ")
    require(raid_acq["retrieved_timezone"] == fixed_timezone, "source retrieval timezones differ")
    retrieved = retrieved or fixed_retrieved
    require(DATE_RE.match(retrieved), "retrieved must be YYYY-MM-DD")

    rejected = list(hc3_info["rejected"]) + list(raid_info["rejected"])
    candidates = hc3_records + raid_records
    all_components, all_exact_links, all_near_links = build_components(candidates)
    direct_reasons = {record["id"]: old_exclusion(record, old) for record in candidates}
    exclusion_counts = Counter()
    excluded_examples = []
    excluded_component_total = 0
    excluded_ids = set()
    for component in all_components:
        direct = [(member["id"], direct_reasons[member["id"]])
                  for member in component["members"] if direct_reasons[member["id"]]]
        if not direct:
            continue
        excluded_component_total += 1
        for member in component["members"]:
            excluded_ids.add(member["id"])
            exclusion_counts[direct_reasons[member["id"]] or "transitive_old_overlap"] += 1
        if len(excluded_examples) < 50:
            excluded_examples.append({
                "component": component["id"],
                "member_count": len(component["members"]),
                "direct_reasons": sorted({reason for _, reason in direct}),
                "cross_corpus": component["cross_corpus"],
            })
    accepted = [record for record in candidates if record["id"] not in excluded_ids]
    require(accepted, "no accepted assessment samples")
    components, exact_links, near_links = build_components(accepted)
    assignment = assign_splits(components)
    (out / "samples").mkdir()
    hc3_snapshot = copy_snapshot(hc3_cache, hc3_info["metadata"], out, "hc3")
    raid_snapshot = copy_snapshot(raid_cache, raid_info["metadata"], out, "raid-fresh")

    samples = []
    for component in components:
        split = assignment[component["id"]]
        for record in component["members"]:
            values = dimensions(record)
            record["dimension_values"] = values
            data = record["text"].encode("utf-8")
            file_name = f"samples/{record['id']}.txt"
            (out / file_name).write_bytes(data)
            sample = {
                "id": record["id"],
                "file": file_name,
                "split": split,
                "slice": "corpus:" + record["corpus_source"],
                "source_group": component["source_group"],
                "near_duplicate_group": component["near_duplicate_group"],
                "label": record["label"],
                "license": record["license"],
                "provenance": record["provenance"],
                "content_sha256": sha256_bytes(data),
                "dataset": record["dataset"],
                "corpus_source": record["corpus_source"],
                "source_id": record["source_id"],
                "base_group": record["base_group"],
                "domain": record["domain"],
                "model": record["model"],
                "attack": record["attack"],
                "word_count": len(record["tokens"]),
                "dimension_values": values,
                "label_source": "Upstream answer/model assertion; not universal authorship truth.",
            }
            if record["corpus_source"] == "hc3":
                sample.update({
                    "source": record["source"],
                    "question_id": record["question_id"],
                    "answer_index": record["answer_index"],
                    "answer_role": record["answer_role"],
                })
            else:
                sample.update({
                    "upstream_id": record["upstream_id"],
                    "decoding": record.get("decoding"),
                    "repetition_penalty": record.get("repetition_penalty"),
                })
            samples.append(sample)
    samples.sort(key=lambda sample: sample["id"])
    content_hash = corpus_content_sha256(samples)
    split_counts = Counter(sample["split"] for sample in samples)
    split_components = {
        split: sum(1 for component in components if assignment[component["id"]] == split)
        for split in SPLITS
    }
    split_labels = {
        split: dict(sorted(Counter(str(sample["label"]) for sample in samples
                                   if sample["split"] == split).items()))
        for split in SPLITS
    }
    dimension_counts = count_dimensions(accepted)
    split_by_id = {sample["id"]: sample["split"] for sample in samples}
    split_dimensions = {
        split: count_dimensions([record for record in accepted
                                 if split_by_id.get(record["id"]) == split])
        for split in SPLITS
    }
    forced_questions = sorted({
        sample["question_id"] for sample in samples
        if sample["corpus_source"] == "hc3" and sample["question_id"] in HC3_VIEWED_QUESTION_IDS
    })
    forced_wrong = [sample["id"] for sample in samples
                    if sample["corpus_source"] == "hc3"
                    and sample["question_id"] in HC3_VIEWED_QUESTION_IDS
                    and sample["split"] != "development"]
    require(not forced_wrong, "viewed HC3 question samples are outside development")
    cross_components = sum(1 for component in components if component["cross_corpus"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "corpus_version": CORPUS_VERSION,
        "corpus_revision": f"{HC3_DATASET}@{HC3_REVISION}+{RAID_DATASET}@{RAID_REVISION}",
        "purpose": "Limited joint HC3 + fresh RAID assessment pilot; no detector run, no release certification.",
        "near_duplicate_threshold": NEAR_THRESHOLD,
        "license": "CC-BY-SA-4.0 AND MIT",
        "retrieved": retrieved,
        "retrieved_timezone": fixed_timezone,
        "dimensions": DIMENSIONS,
        "language_policy": {
            "runtime_default": "unknown",
            "per_sample_overrides": False,
            "overrides_recorded": [],
        },
        "split_policy": {
            "seed": SEED,
            "method": "Union qualified source/question groups, exact normalized text, and 5-shingle Jaccard >= 0.8 before deterministic 60/20/20 splits.",
            "target_fractions": FRACTIONS,
            "forced_hc3_question_ids": list(HC3_VIEWED_QUESTION_IDS),
            "forced_scope": "all five HC3 sources; conservative interpretation of externally viewed source IDs 0-14",
        },
        "exclusion_policy": {
            "old_corpus": os.path.relpath(old_root.resolve(), out.parent.resolve()),
            "old_manifest_sha256": old["manifest_sha256"],
            "old_corpus_content_sha256": old["corpus_content_sha256"],
            "old_retirement_sha256": old["retirement_sha256"],
            "old_sample_count": old["sample_count"],
            "rules": [
                "fresh RAID source_id matching any old sample",
                "exact normalized text matching any old sample",
                "5-shingle Jaccard >= 0.8 matching any old sample",
            ],
            "excluded_counts": dict(sorted(exclusion_counts.items())),
        },
        "source_snapshots": {"hc3": hc3_snapshot, "raid_fresh": raid_snapshot},
        "curation_audit": "curation.json",
        "limitations": LIMITATIONS,
        "counts": {
            "samples": len(samples),
            "components": len(components),
            "cross_corpus_components": cross_components,
            "splits": dict(sorted(split_counts.items())),
            "split_components": split_components,
            "split_labels": split_labels,
            "dimensions": dimension_counts,
            "split_dimensions": split_dimensions,
            "forced_hc3_question_ids_present": forced_questions,
            "rejections": dict(sorted(Counter(item["reason"] for item in rejected).items())),
            "exclusions": dict(sorted(exclusion_counts.items())),
        },
        "samples": samples,
    }
    manifest["corpus_content_sha256"] = content_hash
    manifest_path = out / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    validate_manifest(manifest, manifest_path, split="development",
                      require_content_hashes=True, require_near_duplicate_groups=True)
    validate_grouping(samples, None, threshold=NEAR_THRESHOLD)

    audit = {
        "schema_version": "1.0.0",
        "corpus_version": CORPUS_VERSION,
        "generated_by": "scripts/curate_assessment_pilot.py",
        "manifest_sha256": sha256_file(manifest_path),
        "corpus_content_sha256": content_hash,
        "retrieved": retrieved,
        "retrieved_timezone": fixed_timezone,
        "sources": {
            "hc3": hc3_info["metadata"],
            "raid_fresh": raid_info["metadata"],
        },
        "source_snapshots": {"hc3": hc3_snapshot, "raid_fresh": raid_snapshot},
        "row_accounting": {
            "hc3_answers_seen": len(hc3_records) + sum(1 for r in hc3_info["rejected"] if r["reason"].startswith("empty")),
            "raid_rows_seen": len(raid_records) + len(raid_info["rejected"]),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "rejected_by_reason": dict(sorted(Counter(item["reason"] for item in rejected).items())),
            "rejected_rows": rejected,
            "excluded": sum(exclusion_counts.values()),
            "excluded_by_reason": dict(sorted(exclusion_counts.items())),
        },
        "old_corpus_exclusions": {
            "old_manifest_sha256": old["manifest_sha256"],
            "old_corpus_content_sha256": old["corpus_content_sha256"],
            "old_retirement_sha256": old["retirement_sha256"],
            "old_retirement_status": old["retirement_status"],
            "old_sample_count": old["sample_count"],
            "excluded_counts": dict(sorted(exclusion_counts.items())),
            "excluded_component_count": excluded_component_total,
            "excluded_components": excluded_examples,
            "pre_exclusion_components": len(all_components),
            "pre_exclusion_exact_links": len(all_exact_links),
            "pre_exclusion_near_links": len(all_near_links),
            "universe": "all old RAID v1 samples, conservative",
        },
        "grouping": {
            "component_count": len(components),
            "component_size_distribution": dict(sorted(Counter(len(c["members"]) for c in components).items())),
            "components_with_multiple_bases": sum(1 for c in components if len(c["bases"]) > 1),
            "cross_corpus_components": cross_components,
            "exact_normalized_duplicate_links": exact_links,
            "near_duplicate_links": near_links,
            "near_duplicate_threshold": NEAR_THRESHOLD,
            "shingle_size": SHINGLE_SIZE,
        },
        "splits": {
            "seed": SEED,
            "target_fractions": FRACTIONS,
            "samples_per_split": dict(sorted(split_counts.items())),
            "components_per_split": split_components,
            "labels_per_split": split_labels,
            "dimensions_per_split": split_dimensions,
            "dimensions_overall": dimension_counts,
        },
        "forced_development": {
            "hc3_question_ids": list(HC3_VIEWED_QUESTION_IDS),
            "scope": "all HC3 sources; conservative",
            "questions_present": forced_questions,
            "all_forced_samples_development": True,
        },
        "licenses": {
            "hc3": {"license": HC3_LICENSE, "attribution": "Hello-SimpleAI/HC3, Guo et al. 2023", "share_alike": True},
            "raid_fresh": {"license": RAID_LICENSE, "attribution": "Liam Dugan et al., RAID 2024"},
        },
        "claims": {
            "complete_hc3_or_raid_benchmark": False,
            "general_accuracy_certification": False,
            "detector_run": False,
            "independent_test_opened": False,
            "thresholds_or_defaults_changed": False,
            "native_speaker_inferred": False,
        },
        "limitations": LIMITATIONS,
    }
    (out / "curation.json").write_text(canonical_json(audit), encoding="utf-8")
    summary = {
        "corpus_version": CORPUS_VERSION,
        "manifest_sha256": sha256_file(manifest_path),
        "curation_sha256": sha256_file(out / "curation.json"),
        "corpus_content_sha256": content_hash,
        "samples": len(samples),
        "splits": dict(sorted(split_counts.items())),
        "split_components": split_components,
        "split_labels": split_labels,
        "dimensions": dimension_counts,
        "cross_corpus_components": cross_components,
        "rejections": dict(sorted(Counter(item["reason"] for item in rejected).items())),
        "exclusions": dict(sorted(exclusion_counts.items())),
        "limitations": LIMITATIONS,
    }
    (out / "summary.json").write_text(canonical_json(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hc3-cache", type=pathlib.Path, default=pathlib.Path("/tmp/nobotrs-hc3-cache"))
    parser.add_argument("--raid-cache", type=pathlib.Path, default=pathlib.Path("/tmp/nobotrs-raid-fresh-cache"))
    parser.add_argument("--old-corpus", type=pathlib.Path, default=pathlib.Path("evaluation/corpora/raid-pilot-v1"))
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("evaluation/corpora/assessment-pilot-v1"))
    parser.add_argument("--retrieved", default=None)
    args = parser.parse_args()
    try:
        summary = write_corpus(args.out, args.hc3_cache, args.raid_cache,
                               args.old_corpus, args.retrieved)
    except (CurationError, ProtocolError, OSError) as error:
        print(f"assessment-curate: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "corpus_version": summary["corpus_version"],
        "samples": summary["samples"],
        "splits": summary["splits"],
        "split_components": summary["split_components"],
        "split_labels": summary["split_labels"],
        "cross_corpus_components": summary["cross_corpus_components"],
        "rejections": summary["rejections"],
        "exclusions": summary["exclusions"],
        "corpus_content_sha256": summary["corpus_content_sha256"],
        "manifest_sha256": summary["manifest_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
