#!/usr/bin/env python3
"""Build a separate development-only HC3 mixed-controls corpus.

Controls are mechanical human-prefix + generated-suffix concatenations from the
same HC3 question. Only assessment-pilot-v1 development samples are read. The
control label is null and the transformation provenance is exact. No detector is
run and no assessment manifest/split is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from evaluation_protocol import (  # noqa: E402
    SCHEMA_VERSION,
    ProtocolError,
    corpus_content_sha256,
    load_json,
    load_retirement,
    read_sample_bytes,
    sha256_bytes,
    sha256_file,
    validate_manifest,
)

CONTROL_VERSION = "mixed-controls-v1"
SEPARATOR = b"\n\n"
HC3_DATASET = "Hello-SimpleAI/HC3"
HC3_REVISION = "4d0ff18143b5a7e1b1e79beb540c04549d1e59d3"
HC3_LICENSE = "CC-BY-SA-4.0"
DIMENSIONS = {
    "corpus_source": "hc3-mixed-control; derived from assessment development samples.",
    "domain": "Upstream HC3 source file.",
    "generator": "mixed-human-prefix-generated-suffix.",
    "language_hint": "unknown; no language or native-speaker inference.",
    "length_bucket": "Word-count bucket of the concatenated control.",
    "transformation": "Exact mechanical human-prefix + generated-suffix construction.",
}
LIMITATIONS = [
    "Development-only mixed controls; not an independent test set.",
    "Derived only from assessment-pilot-v1 development HC3 samples; held-out samples are never read.",
    "Label is null because origin is mixed; unknown labels are excluded from precision/recall denominators.",
    "No native-speaker, nonnative-speaker, or human-edited evidence is available or inferred.",
    "No detector has been run on these controls.",
    "These controls are not a complete HC3 benchmark or authorship certification.",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def prepare_output(out: pathlib.Path) -> None:
    if out.is_symlink():
        raise ProtocolError("output directory must not be a symlink")
    if out.exists():
        if not out.is_dir():
            raise ProtocolError("output path exists and is not a directory")
        if any(out.iterdir()):
            raise ProtocolError("output directory must be fresh or empty")
    out.mkdir(parents=True, exist_ok=True)


def length_bucket(count: int) -> str:
    if count < 100:
        return "lt-100"
    if count < 250:
        return "100-249"
    if count < 500:
        return "250-499"
    return "500-plus"


def word_tokens(text: str) -> list[str]:
    import re
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def write_json(path: pathlib.Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(out: pathlib.Path, assessment: pathlib.Path) -> dict:
    prepare_output(out)
    manifest_path = assessment / "manifest.json"
    manifest = load_json(manifest_path, "assessment manifest")
    info = validate_manifest(manifest, manifest_path, split="development",
                             require_content_hashes=True,
                             require_near_duplicate_groups=True)
    require(load_retirement(assessment) is None,
            "assessment corpus is retired; mixed controls refuse it")
    source_hc3 = manifest.get("source_snapshots", {}).get("hc3")
    require(isinstance(source_hc3, dict), "assessment HC3 source snapshot is missing")

    by_group = defaultdict(list)
    for sample in info.samples:
        if sample.get("corpus_source") == "hc3" and sample["split"] == "development":
            by_group[sample["base_group"]].append(sample)
    selected = []
    for base_group, samples in sorted(by_group.items()):
        humans = sorted((sample for sample in samples if sample["label"] == "human"),
                        key=lambda sample: (sample.get("answer_index", 0), sample["id"]))
        generated = sorted((sample for sample in samples if sample["label"] == "generated"),
                           key=lambda sample: (sample.get("answer_index", 0), sample["id"]))
        if humans and generated:
            selected.append((base_group, humans[0], generated[0]))
    require(selected, "no development HC3 question has both human and generated answers")

    selected_ids = {human["id"] for _, human, _ in selected} | {
        generated["id"] for _, _, generated in selected
    }
    selected_samples = [sample for sample in info.samples if sample["id"] in selected_ids]
    require(all(sample["split"] == "development" for sample in selected_samples),
            "mixed-control source selection includes non-development samples")
    contents = read_sample_bytes(selected_samples, assessment, verify_hashes=True)

    (out / "samples").mkdir()
    samples = []
    mappings = []
    for base_group, human, generated in selected:
        human_bytes = contents[human["id"]]
        generated_bytes = contents[generated["id"]]
        control_bytes = human_bytes + SEPARATOR + generated_bytes
        control_id = "mixed-" + sha256_bytes(base_group.encode("utf-8"))[:24]
        file_name = f"samples/{control_id}.txt"
        (out / file_name).write_bytes(control_bytes)
        text = control_bytes.decode("utf-8")
        values = {
            "corpus_source": "hc3-mixed-control",
            "domain": human["domain"],
            "generator": "mixed-human-prefix-generated-suffix",
            "language_hint": "unknown",
            "length_bucket": length_bucket(len(word_tokens(text))),
            "transformation": "human-prefix+generated-suffix",
        }
        provenance = {
            "source": (
                f"https://huggingface.co/datasets/{HC3_DATASET}@{HC3_REVISION}; "
                "derived from assessment-pilot-v1 development samples"
            ),
            "retrieved": manifest["retrieved"],
            "transformation": {
                "version": CONTROL_VERSION,
                "operator": "human_prefix_generated_suffix_concat",
                "separator_hex": SEPARATOR.hex(),
                "human_sample_id": human["id"],
                "human_content_sha256": human["content_sha256"],
                "generated_sample_id": generated["id"],
                "generated_content_sha256": generated["content_sha256"],
                "assessment_manifest_sha256": info.raw_sha256,
                "assessment_corpus_content_sha256": info.corpus_content_sha256,
                "hc3_revision": HC3_REVISION,
                "hc3_license": HC3_LICENSE,
                "label": "null-mixed-origin",
                "held_out_used": False,
            },
        }
        samples.append({
            "id": control_id,
            "file": file_name,
            "split": "development",
            "slice": "corpus:hc3-mixed-control",
            "source_group": "mixed-control:" + base_group,
            "near_duplicate_group": "mixed-control-near:" + base_group,
            "label": None,
            "license": HC3_LICENSE,
            "provenance": provenance,
            "content_sha256": sha256_bytes(control_bytes),
            "dataset": HC3_DATASET,
            "domain": human["domain"],
            "base_group": base_group,
            "human_sample_id": human["id"],
            "generated_sample_id": generated["id"],
            "dimension_values": values,
            "label_source": "mechanically mixed origin; no authorship truth claim",
        })
        mappings.append({
            "control_id": control_id,
            "base_group": base_group,
            "human_sample_id": human["id"],
            "generated_sample_id": generated["id"],
            "control_content_sha256": sha256_bytes(control_bytes),
        })
    samples.sort(key=lambda sample: sample["id"])
    content_hash = corpus_content_sha256(samples)

    source_dir = out / "source" / "hc3"
    (source_dir).mkdir(parents=True)
    for name in ("acquisition.json", "dataset-card.md"):
        origin = assessment / "source" / "hc3" / name
        require(origin.is_file(), f"assessment HC3 source file {name} is missing")
        shutil.copyfile(origin, source_dir / name)
    source_snapshot = {
        "path": "source/hc3",
        "acquisition_sha256": sha256_file(source_dir / "acquisition.json"),
        "dataset_card_sha256": sha256_file(source_dir / "dataset-card.md"),
        "assessment_source_snapshot": source_hc3,
    }
    provenance = {
        "control_version": CONTROL_VERSION,
        "assessment": {
            "manifest_sha256": info.raw_sha256,
            "corpus_content_sha256": info.corpus_content_sha256,
            "source_split": "development only",
            "retirement_status": "not-retired",
        },
        "hc3": {
            "dataset": HC3_DATASET,
            "revision": HC3_REVISION,
            "license": HC3_LICENSE,
            "attribution": "Hello-SimpleAI / Guo et al. 2023; CC-BY-SA-4.0",
        },
        "transformation": {
            "version": CONTROL_VERSION,
            "operator": "human_prefix_generated_suffix_concat",
            "separator_hex": SEPARATOR.hex(),
            "same_question_only": True,
            "held_out_used": False,
        },
        "mappings": mappings,
    }
    write_json(out / "source" / "PROVENANCE.json", provenance)
    source_snapshot["provenance_sha256"] = sha256_file(out / "source" / "PROVENANCE.json")

    labels = Counter(str(sample["label"]) for sample in samples)
    manifest_out = {
        "schema_version": SCHEMA_VERSION,
        "corpus_version": CONTROL_VERSION,
        "corpus_revision": f"assessment-pilot-v1@{info.raw_sha256}+{CONTROL_VERSION}",
        "purpose": "Development-only mechanical HC3 mixed controls; label null; no detector run.",
        "near_duplicate_threshold": 0.8,
        "license": HC3_LICENSE,
        "retrieved": manifest["retrieved"],
        "retrieved_timezone": manifest["retrieved_timezone"],
        "dimensions": DIMENSIONS,
        "language_policy": {
            "runtime_default": "unknown",
            "per_sample_overrides": False,
            "overrides_recorded": [],
        },
        "split_policy": {
            "all_samples": "development",
            "source_filter": "assessment-pilot-v1 development HC3 samples only",
            "held_out_used": False,
        },
        "transformation": provenance["transformation"],
        "source_snapshots": {"hc3": source_snapshot},
        "curation_audit": "curation.json",
        "limitations": LIMITATIONS,
        "counts": {
            "samples": len(samples),
            "splits": {"development": len(samples)},
            "labels": dict(sorted(labels.items())),
            "questions": len({mapping["base_group"] for mapping in mappings}),
            "dimensions": {
                "corpus_source": {"hc3-mixed-control": len(samples)},
                "domain": dict(sorted(Counter(sample["domain"] for sample in samples).items())),
                "generator": {"mixed-human-prefix-generated-suffix": len(samples)},
                "language_hint": {"unknown": len(samples)},
                "length_bucket": dict(sorted(Counter(
                    sample["dimension_values"]["length_bucket"] for sample in samples
                ).items())),
                "transformation": {"human-prefix+generated-suffix": len(samples)},
            },
        },
        "corpus_content_sha256": content_hash,
        "samples": samples,
    }
    manifest_out_path = out / "manifest.json"
    write_json(manifest_out_path, manifest_out)
    validate_manifest(manifest_out, manifest_out_path, split="development",
                      require_content_hashes=True, require_near_duplicate_groups=True)

    audit = {
        "schema_version": "1.0.0",
        "control_version": CONTROL_VERSION,
        "manifest_sha256": sha256_file(manifest_out_path),
        "corpus_content_sha256": content_hash,
        "assessment": provenance["assessment"],
        "source_snapshot": source_snapshot,
        "selection": {
            "source_split": "development",
            "source_samples_read": sorted(selected_ids),
            "source_samples_outside_development_read": [],
            "held_out_used": False,
            "questions": len({mapping["base_group"] for mapping in mappings}),
            "controls": len(samples),
            "mappings": mappings,
        },
        "labels": {
            "sample_label": "null",
            "reason": "mixed human-prefix/generated-suffix origin",
            "excluded_from_precision_recall_denominators": True,
        },
        "licenses": {
            "content": HC3_LICENSE,
            "attribution": "Hello-SimpleAI / Guo et al. 2023",
            "share_alike": True,
        },
        "claims": {
            "detector_run": False,
            "independent_test_or_heldout_used": False,
            "native_speaker_inferred": False,
            "general_accuracy_certification": False,
        },
        "limitations": LIMITATIONS,
    }
    write_json(out / "curation.json", audit)
    summary = {
        "control_version": CONTROL_VERSION,
        "manifest_sha256": sha256_file(manifest_out_path),
        "curation_sha256": sha256_file(out / "curation.json"),
        "corpus_content_sha256": content_hash,
        "samples": len(samples),
        "questions": len({mapping["base_group"] for mapping in mappings}),
        "labels": dict(sorted(labels.items())),
        "splits": {"development": len(samples)},
        "limitations": LIMITATIONS,
    }
    write_json(out / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment-corpus", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/assessment-pilot-v1"))
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("evaluation/corpora/mixed-controls-v1"))
    args = parser.parse_args()
    try:
        summary = build(args.out, args.assessment_corpus)
    except (ProtocolError, OSError) as error:
        print(f"mixed-controls: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
