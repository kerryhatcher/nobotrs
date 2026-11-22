#!/usr/bin/env python3
"""Freeze one development-selected candidate, then assess it once on a fresh manifest."""
import argparse
from copy import copy
import hashlib
import json
import os
from pathlib import Path
import random
from math import log, sqrt
import subprocess
from collections import Counter

from evaluation_protocol import canonical_json_bytes, claim_independent_access, wilson

CRITERIA = Path(__file__).resolve().parents[1] / "evaluation/release-criteria/humanize-v1.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def members(path, *, development=False):
    data = read(path)
    if development and isinstance(data, dict) and data.get("corpus") == "owner-posts-v1":
        return [{"id": r["sha256"][:20], "source_group": r["sha256"], "genre": r["genre"],
                 "path": str(Path("samples") / r["file"]), "sha256": r["sha256"],
                 "label": "ai" if r["label"] == "ai_drafted" else "human"}
                for r in data["posts"] if r["confidence"] == "high"]
    if not isinstance(data, list):
        raise ValueError("expected a manifest array")
    return data


def validate_members(rows):
    if not rows:
        raise ValueError("empty manifest")
    for row in rows:
        for key in ("id", "source_group", "genre", "path", "sha256"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"missing {key}")
        if row.get("label") not in ("human", "ai"):
            raise ValueError("require verified human or AI labels")
        if len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]):
            raise ValueError("invalid content sha256")
    for key in ("id", "source_group", "sha256"):
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError(f"duplicate {key}: select one independently sourced example per group")


def rate(rows, budget):
    fp = sum(r["candidate"] == "flagged" for r in rows)
    base = sum(r["baseline"] == "flagged" for r in rows)
    interval = wilson(fp, len(rows))
    return {"n": len(rows), "false_positives": fp, "baseline_false_positives": base,
            "interval": interval, "pass": bool(interval and interval[1] <= budget and fp <= base)}


def decide(rows, criteria, genres):
    budget = criteria["error_budget"]
    if not genres or not budget:
        raise ValueError("predeclare genres and budget")
    for row in rows:
        for field in ("candidate", "baseline"):
            if row.get(field) not in ("flagged", "clean", "inconclusive"):
                raise ValueError(f"missing verdict for {row['id']} ({field})")
    human = [r for r in rows if r["label"] == "human"]
    generated = [r for r in rows if r["label"] == "ai"]
    overall = rate(human, budget["human_fp_wilson_upper_95"])
    by_genre = {g: rate([r for r in human if r["genre"] == g], budget["human_fp_wilson_upper_95"])
                for g in sorted(set(genres) | {r["genre"] for r in human})}
    changes = [int(r["candidate"] == "flagged") - int(r["baseline"] == "flagged") for r in generated]
    gain = sum(changes) / len(changes) if changes else None
    interval = None
    if len(changes) >= 2:
        rng = random.Random(0)
        samples = sorted(sum(rng.choices(changes, k=len(changes))) / len(changes) for _ in range(2000))
        interval = [samples[49], samples[1950]]
        if interval[0] == interval[1]:
            # Hoeffding bound for the paired difference in [-1,1].
            radius = sqrt(2 * log(40) / len(changes))
            interval = [max(-1, gain - radius), min(1, gain + radius)]
    passed = (overall["pass"] and all(g["pass"] and g["n"] >= criteria["minimum_independent_human_sources_per_genre"] for g in by_genre.values())
              and interval and interval[0] > budget["recall_gain_interval_lower_exclusive"]
              and gain >= budget["minimum_recall_gain"])
    return {"decision": "ship" if passed else "informational", "human": overall, "genres": by_genre,
            "generated": len(generated), "recall_gain": gain, "recall_gain_interval": interval,
            "abstentions": dict(Counter(r["label"] for r in rows if r["candidate"] == "inconclusive"))}


def identity(args):
    criteria = read(CRITERIA)
    if not criteria.get("error_budget") or args.candidate not in criteria["candidate_ids"]:
        raise ValueError("invalid candidate or missing error budget")
    development, held = members(args.dev, development=True), members(args.manifest)
    validate_members(development)
    validate_members(held)
    for key in ("id", "source_group", "sha256"):
        if {r[key] for r in development} & {r[key] for r in held}:
            raise ValueError(f"development and held-out overlap in {key}")
    if not args.genres or len(set(args.genres)) != len(args.genres):
        raise ValueError("declare distinct target genres")
    return {"criteria_sha256": digest(CRITERIA.read_bytes()), "baseline_revision": criteria["baseline_revision"],
            "candidate": args.candidate, "genres": sorted(args.genres),
            "dev_manifest_sha256": digest(canonical_json_bytes(development)),
            "heldout_manifest_sha256": digest(canonical_json_bytes(held)),
            "baseline_binary_sha256": digest(args.baseline.read_bytes()),
            "candidate_binary_sha256": digest(args.binary.read_bytes()),
            "config_sha256": digest(args.config.read_bytes())}


def verdict(binary, config, candidate, path, timeout):
    # Explicit config and clean environment make user config and service opt-ins irrelevant.
    env = {"PATH": os.defpath, "NOBOTRS_EXPERIMENT": candidate}
    proc = subprocess.run([str(binary.resolve()), "detect", str(path), "--language", "en",
                           "--format", "json", "--config", str(config.resolve())],
                          env=env, capture_output=True, timeout=timeout)
    if proc.returncode not in (0, 1, 3):
        raise ValueError(f"detection failed for {path.name}")
    result = json.loads(proc.stdout)
    if result.get("complete") is not True or result.get("external") or result.get("openrouter"):
        raise ValueError("incomplete or nonlocal run")
    if result["settings"].get("experiment", []) != ([candidate] if candidate else []):
        raise ValueError("binary did not apply the selected experiment")
    return result["verdict"]


def run(args):
    if args.action == "development":
        if args.candidate not in read(CRITERIA)["candidate_ids"]:
            raise ValueError("unknown candidate")
        validate_members(members(args.dev,development=True))
    else:
        if args.manifest is None or args.record is None:
            raise ValueError("freeze and evaluate require --manifest and --record")
        key = identity(args)
    config = read(args.config)
    if any(config.get(k) for k in ("models", "gptzero", "openrouter_judge", "experiment")):
        raise ValueError("freeze requires an offline config without preconfigured experiments")
    if args.action == "freeze":
        selection_args = copy(args)
        selection_args.action = "development"
        selection = run(selection_args)
        if not selection["eligible_on_development"]:
            raise ValueError("candidate did not qualify on development")
        # Bind this membership to one record even when callers choose different record names.
        fingerprint = digest(canonical_json_bytes(sorted(r["sha256"] for r in members(args.manifest))))
        receipt = args.manifest.parent / (".humanize-access-" + fingerprint)
        with receipt.open("x", encoding="utf-8") as lock:
            lock.write(str(args.record.resolve()) + "\n")
        with args.record.open("x", encoding="utf-8") as f:
            json.dump({"status": "frozen-unopened", **key}, f, indent=2)
        return {"status": "frozen-unopened"}
    if args.action == "evaluate":
        claim_independent_access(args.record, key)
    manifest = args.manifest if args.action == "evaluate" else args.dev
    rows = []
    selected_rows=members(manifest,development=args.action=="development")
    if args.action=="evaluate" and digest(canonical_json_bytes(selected_rows)) != key["heldout_manifest_sha256"]:
        raise ValueError("manifest changed after freeze")
    for row in selected_rows:
        path = manifest.parent / row["path"]
        if digest(path.read_bytes()) != row["sha256"]:
            raise ValueError("sample byte hash mismatch")
        rows.append({**row, "baseline": verdict(args.baseline, args.config, "", path, 60),
                     "candidate": verdict(args.binary, args.config, args.candidate, path, 60)})
    report = decide(rows, read(CRITERIA), args.genres)
    if args.action=="development":
        report["eligible_on_development"]=report.pop("decision")=="ship"
    return {"split": "heldout" if args.action == "evaluate" else "development", **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "evaluate", "development"))
    for name in ("dev", "baseline", "binary", "config"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--genres", nargs="+", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True))
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
