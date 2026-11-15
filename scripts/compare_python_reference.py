#!/usr/bin/env python3
"""Compare shared fixtures with the pinned Python reference commit.

The archived reference uses a private package registry in its uv.lock. This
harness installs the matching public PyPI versions into an isolated uv
environment, records that environment difference, and does not require model
weights or the spaCy ``analyze`` extra.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

COMMIT = "0981b9501b7dd2fb37803cf43298e83edfd508e9"
PUBLIC_VERSIONS = {
    "textstat": "0.7.13",
    "lexicalrichness": "0.5.1",
    "nltk": "3.10.0",
    "pyphen": "0.17.2",
    "typer": "0.26.8",
}
EXPECTED_REFERENCE_SHA256 = {
    "src/nobots/cli.py": "7ebab744e3eeb2ece557e121fd8eb996c5c36e5c30d3b443577ff00043c892ff",
    "src/nobots/config.py": "ba60712f5be3c98643944cef635c88c87e6eaf4c1ce6681c5d0ef359a484e441",
    "src/nobots/core/detect.py": "8fcc01252bfa3f99d3cd9f414dedfff7ad56c86380e72fef0510835ee3820e54",
    "src/nobots/core/guide.py": "5f663c5ac2006ec68055a083b5b64e6f92ea8d080da5849c8ee0634fb59964dd",
    "src/nobots/core/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/nobots/core/models.py": "e42f3d61b795d8559b8b5b42681c1a4b0ade505e1e14bd77a47c795a6dde5b74",
    "src/nobots/core/prose.py": "c16807bc62723b1f1fbd978fab4d2699b371b235aaaa9b8b3b467e5854ba928b",
    "src/nobots/core/stylometry.py": "e0ca7abc706a6177432f2f534cdd73ced64c3c39af58f03a34cb353b132b9e69",
    "src/nobots/humanize/agent.py": "2da8806e7650e7f1e4885a7f6e5593e88ab54d5705886d737d734d1d4cb10f6c",
    "src/nobots/humanize/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/nobots/__init__.py": "8c6962d5eacaea3afadd5b4cff99123053f8123d27d9dab76bbc5eed681b9026",
    "src/nobots/mcp/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/nobots/mcp/server.py": "a4536ff5540f72d5156687b87b17fa375b9851628cfc2fa83810b258c8fdd329",
    "src/nobots/tui/app.py": "38cf97d69bd280081b8bfb783739c99ae102eaf01a146de3ba651f8641276431",
    "src/nobots/tui/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "pyproject.toml": "0581cae1b5a434a57229ebde7001813dfff510ab7ca96fcf69137b0c160d0417",
    "uv.lock": "11442657e22cee566d243beae343d0d982122194fa56f2830e93d2622d89494f",
}
REFERENCE_FILES = tuple(EXPECTED_REFERENCE_SHA256)
EXPECTED_DIFFERENCES = {
    "plain": {"context.lzma_ratio"},
    "flagged": {"prose_words", "context.lzma_ratio"},
    "code-only": set(),
    "long-fence": {"prose_words", "context.lzma_ratio"},
    "softbreak": {"context.lzma_ratio"},
    "no-cross-block": {"context.lzma_ratio"},
    "welsh": {"context.mtld", "context.flesch_kincaid", "context.lzma_ratio"},
}
PROBE = r'''
import json, os, sys
from pathlib import Path
payload = json.loads(os.environ["NOBOTRS_PARITY_PAYLOAD"])
root = Path(payload["reference_root"])
sys.path.insert(0, str(root / "src"))
from nobots.core.prose import clean_prose
from nobots.core.detect import (
    detect_text, _sentence_word_lengths, _burstiness_ratio,
)
out = {"fixtures": {}, "burstiness": {}}
for name, path in payload["fixtures"].items():
    text = Path(path).read_text(encoding="utf-8")
    cleaned = clean_prose(text)
    result = detect_text(cleaned)
    out["fixtures"][name] = {
        "clean_words": len(cleaned.split()),
        "clean_sha256": __import__("hashlib").sha256(cleaned.encode()).hexdigest(),
        "clean_preview": cleaned[:160],
        "tells_found": result.tells_found,
        "agree": result.agree,
        "families": {key: {"vote": value[0], "detail": value[1]}
                      for key, value in result.families.items()},
        "context": result.context,
    }
if payload.get("burstiness_fixture"):
    data = json.loads(Path(payload["burstiness_fixture"]).read_text())
    for case in data["cases"]:
        lengths = case["sentence_lengths"]
        text = " ".join(" ".join(["word"] * length) + "." for length in lengths)
        words = _sentence_word_lengths(text)
        out["burstiness"][case["id"]] = {
            "sentence_lengths": words,
            "cv": _burstiness_ratio(words),
        }
print(json.dumps(out))
'''


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_toml(path):
    try:
        import tomllib
    except ImportError:
        raise SystemExit("Python 3.11+ is required to inspect uv.lock") from None
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def reference_metadata(root):
    if root.name != COMMIT:
        raise SystemExit(
            f"reference root must end in the pinned commit {COMMIT}, got {root.name}"
        )
    if not (root / "src/nobots/core/detect.py").is_file():
        raise SystemExit(f"reference source is missing under {root}")
    file_hashes = {name: sha256(root / name) for name in REFERENCE_FILES}
    mismatched_files = {
        name: (file_hashes[name], expected)
        for name, expected in EXPECTED_REFERENCE_SHA256.items()
        if file_hashes[name] != expected
    }
    if mismatched_files:
        raise SystemExit(
            "reference source hashes differ from the verified archive: "
            f"{mismatched_files}"
        )
    lock = load_toml(root / "uv.lock")
    versions = {}
    registries = {}
    for package in lock.get("package", []):
        name = package.get("name")
        if name in PUBLIC_VERSIONS:
            versions[name] = package.get("version")
            registries[name] = package.get("source", {}).get("registry")
    mismatched = {
        name: (versions.get(name), expected)
        for name, expected in PUBLIC_VERSIONS.items()
        if versions.get(name) != expected
    }
    if mismatched:
        raise SystemExit(f"uv.lock core versions differ from the matched public set: {mismatched}")
    return {
        "commit": COMMIT,
        "root": str(root),
        "provenance": (
            "Trusted archive created directly with `git archive` from the exact "
            f"commit {COMMIT} by the supervisor; source hashes are pinned here."
        ),
        "file_sha256": file_hashes,
        "pinned_file_sha256": EXPECTED_REFERENCE_SHA256,
        "lock_core_versions": versions,
        "lock_registries": registries,
        "public_pypi_versions": PUBLIC_VERSIONS,
        "environment_difference": (
            "The archived uv.lock points core packages at an inaccessible private "
            "registry (HTTP 401). The harness installs the matching public PyPI "
            "versions listed above and does not modify the archive or neighboring "
            "checkout."
        ),
    }


def ensure_binary(path):
    path = Path(path)
    if path.is_file():
        return path.resolve()
    result = subprocess.run(["cargo", "build", "--locked"], check=False)
    if result.returncode != 0:
        raise SystemExit("cargo build failed")
    default = Path("target/debug/nobotrs").resolve()
    if not default.is_file():
        raise SystemExit(f"binary not found: {path}")
    return default


def run_probe(reference_root, fixtures, burstiness_fixture):
    command = ["uv", "run", "--no-project"]
    for package, version in PUBLIC_VERSIONS.items():
        command += ["--with", f"{package}=={version}"]
    command += ["python", "-c", PROBE]
    payload = {
        "reference_root": str(reference_root),
        "fixtures": {path.name: str(path) for path in fixtures},
        "burstiness_fixture": str(burstiness_fixture) if burstiness_fixture else None,
    }
    env = os.environ.copy()
    env["NOBOTRS_PARITY_PAYLOAD"] = json.dumps(payload)
    result = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Python reference probe failed:\n{result.stderr}")
    return json.loads(result.stdout)


def run_rust(binary, path, env):
    result = subprocess.run(
        [str(binary), "analyze", str(path), "--format", "json"],
        capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode not in (0, 1, 2, 3):
        raise SystemExit(f"Rust analysis failed for {path}:\n{result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid Rust JSON for {path}: {error}") from error


def rust_context(report):
    context = {"mtld": None, "flesch_kincaid": None, "lzma_ratio": None}
    metrics = {}
    for backend in report["backends"]:
        outcome = backend["outcome"]
        if outcome["status"] == "scored":
            metrics[backend["backend"]] = outcome["details"].get("metrics", {})
    context["mtld"] = metrics.get("lexical-diversity", {}).get("mtld", {}).get("value")
    context["flesch_kincaid"] = metrics.get("readability", {}).get(
        "flesch_kincaid_grade", {}
    ).get("value")
    context["lzma_ratio"] = metrics.get("compression", {}).get("lzma_ratio", {}).get("value")
    return context


def rust_family_votes(report):
    mapping = {
        "Vocabulary": "vocabulary",
        "Punctuation": "punctuation",
        "Burstiness": "burstiness",
    }
    return {
        mapping[family["family"]]: family["vote"]
        for family in report["families"]
        if family["family"] in mapping and family["vote"] != "none"
    }


def python_family_votes(families):
    return {
        name: {1: "suspicious", 2: "strong"}.get(value["vote"], str(value["vote"]))
        for name, value in families.items()
    }


def classify(fixture_id, field, python_value, rust_value):
    expected = field in EXPECTED_DIFFERENCES.get(fixture_id, set())
    if field == "prose_words":
        if fixture_id == "flagged":
            reason = "Python whitespace tokens count em dashes; Rust uses Unicode words."
        elif fixture_id == "long-fence":
            reason = "Python regex fence cleaning differs from the Rust Markdown parser."
        else:
            reason = "Unexpected prose-word difference."
    elif field == "tells_found":
        reason = "Unexpected verdict/tells difference."
    elif field == "family_votes":
        reason = "Unexpected family-threshold or selection difference."
    elif field == "context.mtld":
        reason = (
            "Rust MTLD abstains without an explicit English assertion; "
            "Python computes it on this text."
        )
    elif field == "context.flesch_kincaid":
        reason = (
            "Rust readability abstains without an explicit English assertion; "
            "Python computes it on this text."
        )
    elif field == "context.lzma_ratio":
        if rust_value is None:
            reason = (
                "Rust compression abstains below its 150-word floor; "
                "Python computes a ratio unconditionally."
            )
        else:
            reason = (
                "Python uses lzma preset 6; Rust uses lzma-rs 0.3's literal-only "
                "LZMA-Alone encoder."
            )
    else:
        reason = "Unclassified difference."
    return {"field": field, "python": python_value, "rust": rust_value,
            "expected": expected, "classification": reason}


def compare_fixtures(python, binary, env):
    results = {}
    for fixture_name, py in python["fixtures"].items():
        name = Path(fixture_name).stem
        report = run_rust(binary, Path(env["NOBOTRS_FIXTURE_DIR"]) / fixture_name, env)
        rs = {
            "prose_words": report["prose_words"],
            "verdict": report["verdict"],
            "tells_found": report["verdict"] == "flagged",
            "family_votes": rust_family_votes(report),
            "context": rust_context(report),
        }
        differences = []
        if py["clean_words"] != rs["prose_words"]:
            differences.append(classify(name, "prose_words", py["clean_words"], rs["prose_words"]))
        if py["tells_found"] != rs["tells_found"]:
            differences.append(classify(name, "tells_found", py["tells_found"], rs["tells_found"]))
        py_votes = python_family_votes(py["families"])
        if py_votes != rs["family_votes"]:
            differences.append(classify(name, "family_votes", py_votes, rs["family_votes"]))
        for metric in ("mtld", "flesch_kincaid", "lzma_ratio"):
            py_value = py["context"].get(metric)
            rs_value = rs["context"].get(metric)
            if py_value != rs_value:
                differences.append(classify(name, f"context.{metric}", py_value, rs_value))
        results[name] = {
            "python": py,
            "rust": rs,
            "differences": differences,
            "status": "intended" if all(item["expected"] for item in differences)
            else "regression-candidate",
        }
    return results


def compare_burstiness(python, fixture, binary, env, temp):
    results = {}
    tolerance = fixture["reference"]["comparison_tolerance"]
    for case in fixture["cases"]:
        cid = case["id"]
        lengths = case["sentence_lengths"]
        text = " ".join(" ".join(["word"] * length) + "." for length in lengths)
        path = Path(temp) / f"burstiness-{cid}.txt"
        path.write_text(text, encoding="utf-8")
        report = run_rust(binary, path, env)
        outcome = next(
            backend["outcome"] for backend in report["backends"]
            if backend["backend"] == "burstiness"
        )
        rust_cv = None
        rust_vote = None
        if outcome["status"] == "scored":
            rust_cv = outcome["details"]["metrics"]["sentence_length_cv"]["value"]
            rust_vote = next(
                family["vote"] for family in report["families"]
                if family["family"] == "Burstiness"
            )
        py = python["burstiness"][cid]
        expected = case["expected_cv"]
        differences = []
        if py["sentence_lengths"] != lengths:
            differences.append("Python reference sentence lengths differ")
        if abs(py["cv"] - expected) > tolerance:
            differences.append("Python reference CV differs")
        if case["expected_backend_outcome"] == "scored":
            if rust_cv is None:
                differences.append("Rust did not score the reference vector")
            elif abs(rust_cv - expected) > tolerance:
                differences.append("Rust CV differs from the reference")
            if rust_vote != case["expected_vote"]:
                differences.append("Rust vote differs from the expected vote")
        elif outcome["status"] != "abstained":
            differences.append("Rust should abstain below the word floor")
        results[cid] = {
            "expected_cv": expected,
            "python_cv": py["cv"],
            "rust_cv": rust_cv,
            "rust_vote": rust_vote,
            "status": "matched" if not differences else "regression-candidate",
            "differences": differences,
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=Path(f"/tmp/nobotrs-python-reference/{COMMIT}"),
    )
    parser.add_argument("--binary", default="target/debug/nobotrs")
    parser.add_argument("--fixtures", type=Path,
                        default=Path("tests/fixtures/evaluation"))
    parser.add_argument("--burstiness-fixture", type=Path,
                        default=Path("tests/fixtures/burstiness-reference.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-unexpected", action="store_true")
    args = parser.parse_args()

    reference = reference_metadata(args.reference_root.resolve())
    fixtures = sorted(args.fixtures.glob("*.md"))
    if not fixtures:
        raise SystemExit(f"no shared fixtures under {args.fixtures}")
    binary = ensure_binary(args.binary)
    with tempfile.TemporaryDirectory(prefix="nobotrs-parity-") as temp:
        env = os.environ.copy()
        for name in list(env):
            if name.startswith("NOBOTRS_"):
                env.pop(name)
        env["XDG_CONFIG_HOME"] = str(Path(temp) / "no-config")
        env["NO_COLOR"] = "1"
        env["NOBOTRS_FIXTURE_DIR"] = str(args.fixtures.resolve())
        python = run_probe(
            args.reference_root.resolve(), fixtures, args.burstiness_fixture
        )
        fixture_results = compare_fixtures(python, binary, env)
        burstiness_results = {}
        if args.burstiness_fixture and args.burstiness_fixture.is_file():
            burstiness_fixture = json.loads(args.burstiness_fixture.read_text())
            burstiness_results = compare_burstiness(
                python, burstiness_fixture, binary, env, temp
            )
    unexpected = [
        (name, item["differences"])
        for name, item in fixture_results.items()
        if item["status"] != "intended"
    ]
    unexpected += [
        (f"burstiness:{name}", [{"classification": text}])
        for name, item in burstiness_results.items()
        if item["status"] != "matched"
        for text in item["differences"]
    ]
    report = {
        "schema_version": "1.0.0",
        "reference": reference,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "fixtures": fixture_results,
        "burstiness": burstiness_results,
        "summary": {
            "fixture_count": len(fixture_results),
            "difference_count": sum(
                len(item["differences"]) for item in fixture_results.values()
            ),
            "regression_candidate_count": len(unexpected),
        },
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, item in fixture_results.items():
        print(f"{name}: {item['status']} ({len(item['differences'])} differences)")
        for difference in item["differences"]:
            print(
                f"  {difference['field']}: python={difference['python']!r} "
                f"rust={difference['rust']!r} expected={difference['expected']} "
                f"— {difference['classification']}"
            )
    if burstiness_results:
        print("burstiness reference:")
        for name, item in burstiness_results.items():
            print(
                f"  {name}: {item['status']} "
                f"expected_cv={item['expected_cv']:.12g} "
                f"python_cv={item['python_cv']!r} rust_cv={item['rust_cv']!r}"
            )
    if unexpected and not args.allow_unexpected:
        print(f"parity: {len(unexpected)} regression candidate(s)", file=sys.stderr)
        return 1
    print(f"parity: {report['summary']['difference_count']} expected difference(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
