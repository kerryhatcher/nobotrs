#!/usr/bin/env python3
"""Real-executable acceptance checks for the functional-core release.

This runner executes the built CLI rather than asserting library contracts alone.
It covers the documented file/stdin, Markdown, language, failure, resource,
candidate/selection, source-location, determinism, and package/install gates.
It does not claim authorship accuracy and does not require a corpus.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE_BUDGET = 8_000_000


class AcceptanceError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AcceptanceError(message)


class Runner:
    def __init__(self, binary, work, timeout=60):
        self.binary = Path(binary).resolve()
        self.work = Path(work)
        self.timeout = timeout
        self.config_home = self.work / "no-config"
        self.checks = 0

    def env(self, extra=None):
        env = os.environ.copy()
        for name in list(env):
            if name.startswith("NOBOTRS_"):
                env.pop(name)
        env["XDG_CONFIG_HOME"] = str(self.config_home)
        env["NO_COLOR"] = "1"
        if extra:
            env.update(extra)
        return env

    def run(self, args, stdin=b"", env=None, cwd=None, timeout=None):
        result = subprocess.run(
            [str(self.binary), *args],
            input=stdin,
            capture_output=True,
            cwd=cwd or self.work,
            env=self.env(env),
            timeout=timeout or self.timeout,
            check=False,
        )
        return result

    def json(self, result, context):
        require(result.returncode != 0 or result.stdout,
                f"{context}: expected JSON output")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AcceptanceError(
                f"{context}: invalid JSON ({error}): {result.stderr.decode(errors='replace')}"
            ) from None

    def check(self, name):
        self.checks += 1
        print(f"PASS {name}")


def backend(report, name):
    matches = [b for b in report["backends"] if b["backend"] == name]
    require(len(matches) == 1, f"expected one {name} backend outcome")
    return matches[0]["outcome"]


def details(report, name):
    outcome = backend(report, name)
    require(outcome["status"] in ("scored", "incomplete"), f"{name}: {outcome['status']}")
    return outcome["details"]


def evidence(report):
    found = []
    for item in report["backends"]:
        outcome = item["outcome"]
        if outcome["status"] in ("scored", "incomplete"):
            found.extend(outcome["details"]["evidence"])
    return found


def rule_ids(report):
    return [item["rule_id"] for item in evidence(report)]


def check_cli_surface(r):
    help_result = r.run(["--help"])
    require(help_result.returncode == 0, "help failed")
    help_text = help_result.stdout.decode()
    for command in ("detect", "lint", "analyze", "scan", "config", "guide"):
        require(command in help_text, f"help omits {command}")
    guide = r.run(["guide"])
    require(guide.returncode == 0, "guide failed")
    require(guide.stdout.startswith(b"# Writing guide"), "guide is not packaged")
    config = r.json(r.run(["config", "--format", "json"]), "config")
    require(config["schema_version"] == "1.0.0", "config schema")
    require(config["configuration"]["settings"]["quorum"] == 2, "config quorum default")
    require(len(config["backends"]) == 6, "config backend count")
    require(all(item["availability"] == "ready" for item in config["backends"]),
            "default backends must be ready offline")
    r.check("CLI help, packaged guide, and offline config")


def check_file_stdin_equivalence(r):
    text = "# Heading\n\nexperts\nagree\n"
    path = r.work / "sample.md"
    path.write_text(text)
    file_report = r.json(
        r.run(["lint", str(path), "--format", "json"]), "file lint")
    stdin_report = r.json(
        r.run(["lint", "-", "--markdown", "--format", "json"], text.encode()),
        "stdin lint")
    for key in (
        "complete", "analyzed_coverage", "prose_words", "sentence_count",
        "effective_finding_count", "actionable_finding_count", "verdict",
        "families",
    ):
        require(file_report[key] == stdin_report[key], f"file/stdin differ on {key}")
    file_findings = [
        (e["rule_id"], e["line"], e["column"], e["matched_text"])
        for e in evidence(file_report)
    ]
    stdin_findings = [
        (e["rule_id"], e["line"], e["column"], e["matched_text"])
        for e in evidence(stdin_report)
    ]
    require(file_findings == stdin_findings, "file/stdin findings differ")
    require(file_report["schema_version"] == "1.0.0", "report schema version")
    r.check("file and Markdown stdin analyses agree")


def check_markdown_normalization(r):
    def lint(text):
        return r.json(
            r.run(["lint", "-", "--markdown", "--format", "json"], text.encode()),
            f"markdown lint: {text!r}")
    for text in (
        "experts agree",
        "experts\nagree",
        "experts *agree*",
        "experts [agree](https://example.com)",
        "````\ncode\n```\nmore\n````\nexperts agree",
    ):
        require("experts-agree" in rule_ids(lint(text)), f"expected phrase for {text!r}")
    for text in (
        "experts\n\nagree",
        "- experts\n- agree",
        "experts `code` agree",
        "del`code`ve",
    ):
        ids = rule_ids(lint(text))
        require("experts-agree" not in ids, f"cross-block phrase for {text!r}")
        require("delve" not in ids, f"inline-code fuse for {text!r}")
    code_only = lint("---\na: 1\n---\n```\nonly code\n```")
    require(code_only["prose_words"] == 0, "code/front matter became prose")
    require(code_only["verdict"] == "inconclusive", "code-only verdict")
    for expected in ("&mdash;", "&#8212;", "—"):
        raw = f"x {expected} x {expected} x {expected} x"
        report = r.json(
            r.run(["analyze", "-", "--markdown", "--format", "json"], raw.encode()),
            f"entity analysis: {expected}")
        metrics = details(report, "punctuation")["metrics"]
        require(metrics["em_dash_count"]["value"] == 3.0, f"entity count: {expected}")
        dashes = [
            e for e in evidence(report)
            if e["rule_id"] == "punctuation.em-dash-density"
        ]
        require(len(dashes) == 3, f"entity evidence: {expected}")
        for dash in dashes:
            start, end = dash["raw_offset"]["start"], dash["raw_offset"]["end"]
            require(raw.encode()[start:end].decode() == expected,
                    f"entity source range points at {expected}")
    crlf = r.json(
        r.run(["lint", "-", "--markdown", "--format", "json"],
              "é\r\n\r\nx — x — x — x".encode()),
        "CRLF Unicode lint")
    dashes = [
        e for e in evidence(crlf)
        if e["rule_id"] == "punctuation.em-dash-density"
    ]
    require((dashes[0]["line"], dashes[0]["column"]) == (3, 3),
            "CRLF Unicode source location")
    r.check("Markdown soft breaks, entities, fences, gaps, and locations")


def check_candidates_and_families(r):
    def analyze(text):
        return r.json(
            r.run(["analyze", "-", "--format", "json"], text.encode()),
            f"analyze: {text!r}")
    report = analyze("embark on a journey")
    vocab = details(report, "vocabulary")
    require([e["rule_id"] for e in vocab["evidence"]] == ["embark-on-a-journey"],
            "longest phrase was not selected")
    dispositions = {c["rule_id"]: c["disposition"] for c in vocab["candidates"]}
    require(dispositions.get("embark") == "overlap_excluded",
            "overlapping embark candidate was not retained")
    require(dispositions.get("embark-on-a-journey") == "selected",
            "selected phrase candidate missing")
    require(all(c["suppression"] is None for c in vocab["candidates"]),
            "unsuppressed candidate has suppression metadata")
    report = analyze("embark on a journeyx")
    require([e["rule_id"] for e in evidence(report)] == ["embark"],
            "rejected boundary did not retain shorter candidate")
    report = analyze("delvex delve")
    found = evidence(report)
    require([e["rule_id"] for e in found] == ["delve"], "whole-word boundary")
    require(found[0]["column"] == 8, "whole-word boundary location")
    report = analyze("it's not just a tool, it's a system")
    require("not-just-x-but-y" in rule_ids(report), "regex candidate")
    flagged = r.json(
        r.run(["detect", "-", "--format", "json"],
              "delve leverage — — — — — —".encode()),
        "flagged detect")
    families = flagged["families"]
    require(len({f["family"] for f in families}) == len(families),
            "duplicate family decision")
    require(flagged["verdict"] == "flagged", "two-family quorum did not flag")
    require(all(len(f["backends"]) >= 1 for f in families), "family without backend")
    r.check("candidate disposal, boundaries, stable IDs, and family reduction")


def check_language_policy(r):
    text = ("The quick brown fox jumps over the lazy dog. " * 30).encode()
    default = r.json(r.run(["analyze", "-", "--format", "json"], text),
                     "default language")
    require(default["language"]["applicability"] == "unknown", "default language")
    require(backend(default, "readability")["status"] == "abstained",
            "readability abstained by default")
    require(backend(default, "lexical-diversity")["status"] == "abstained",
            "MTLD abstained by default")
    english = r.json(r.run(["analyze", "-", "--language", "en", "--format", "json"], text),
                     "English override")
    require(english["language"]["source"] == "user_override", "override source")
    require(english["language"]["applicability"] == "supported", "English applicability")
    require(backend(english, "readability")["status"] == "scored",
            "English readability did not score")
    require(backend(english, "lexical-diversity")["status"] == "scored",
            "English MTLD did not score")
    other = r.json(r.run(["analyze", "-", "--language", "cy", "--format", "json"], text),
                   "unsupported override")
    require(other["language"]["applicability"] == "unsupported", "unsupported language")
    require(backend(other, "readability")["status"] == "abstained",
            "unsupported readability did not abstain")
    r.check("unknown, asserted-English, and unsupported language policy")


def check_failures_and_scan(r):
    missing = r.run(["detect", str(r.work / "missing.txt"), "--format", "json"])
    require(missing.returncode == 2, "missing path status")
    payload = r.json(missing, "missing path")
    require(payload["errors"] and not payload["reports"], "missing path payload")
    require(payload["exit_code"] == 2, "missing path exit_code")
    require(missing.stderr, "missing path diagnostic")
    invalid = r.run(["detect", "-", "--format", "json"], b"\xff")
    require(invalid.returncode == 2, "invalid UTF-8 status")
    bad_config = r.work / "bad.json"
    bad_config.write_text('{"quorum": 0}')
    invalid_config = r.run(["config", "--config", str(bad_config)])
    require(invalid_config.returncode == 2, "invalid configuration status")
    require(b"quorum" in invalid_config.stderr, "invalid configuration diagnostic")

    empty = r.json(r.run(["detect", "-", "--format", "json"]), "empty input")
    require(empty["verdict"] == "inconclusive" and empty["prose_words"] == 0,
            "empty input semantics")
    require(empty["complete"] is True, "empty input completeness")
    code = r.json(
        r.run(["detect", "-", "--markdown", "--format", "json"], b"```\ncode\n```"),
        "code-only input")
    require(code["verdict"] == "inconclusive" and code["prose_words"] == 0,
            "code-only input semantics")
    require(all(b["outcome"]["status"] == "abstained" for b in code["backends"]),
            "code-only backend abstention")

    scan_root = r.work / "scan"
    (scan_root / "target").mkdir(parents=True)
    (scan_root / "b.txt").write_text("quiet plain prose")
    (scan_root / "a.md").write_text("delve leverage")
    (scan_root / "bad.txt").write_bytes(b"\xff")
    (scan_root / "target" / "ignored.md").write_text("delve leverage")
    first = r.run(["scan", str(scan_root), "--format", "json"])
    require(first.returncode == 2, "mixed scan status")
    mixed = r.json(first, "mixed scan")
    require(len(mixed["reports"]) == 2, "mixed scan retained reports")
    require(len(mixed["errors"]) == 1, "mixed scan retained error")
    paths = [Path(item["path"]).name for item in mixed["reports"]]
    require(paths == ["a.md", "b.txt"], f"scan order/ignore: {paths}")
    second = r.run(["scan", str(scan_root), "--format", "json"])
    require(first.stdout == second.stdout, "scan output is not deterministic")
    r.check("missing/invalid inputs, empty prose, mixed scan, and deterministic order")


def check_budgets_and_display(r):
    truncated = r.json(
        r.run(["lint", "-", "--max-bytes", "6", "--format", "json"],
              b"delve more text"),
        "input truncation")
    truncated_result = r.run(
        ["lint", "-", "--max-bytes", "6", "--format", "json"], b"delve more text")
    require(truncated_result.returncode == 2, "input truncation status")
    require(truncated["complete"] is False, "input truncation completeness")
    require(truncated["analyzed_coverage"] == 0.0, "input truncation coverage")
    require(truncated["effective_finding_count"] == 1, "truncation lost retained finding")
    require(any("input byte budget" in reason for reason in truncated["incomplete_reasons"]),
            "input truncation reason")

    timeout_result = r.run(
        ["lint", "-", "--timeout-ms", "0", "--format", "json"], b"delve leverage")
    timeout = r.json(timeout_result, "timeout")
    require(timeout_result.returncode == 2, "timeout status")
    require(timeout["complete"] is False and timeout["analyzed_coverage"] == 0.0,
            "timeout completeness")
    require(timeout["prose_words"] == 0, "timeout retained unfinished prose")
    require(all(b["outcome"]["status"] == "failed" for b in timeout["backends"]),
            "timeout backend status")

    candidate_result = r.run(
        ["lint", "-", "--max-candidates", "1", "--format", "json"],
        b"delve leverage nuanced multifaceted")
    candidate = r.json(candidate_result, "candidate budget")
    require(candidate_result.returncode == 2, "candidate budget status")
    require(candidate["complete"] is False, "candidate budget completeness")
    require(candidate["analyzed_coverage"] < 1.0, "candidate budget coverage")
    require(candidate["effective_finding_count"] == 1, "candidate budget retention")
    vocab = backend(candidate, "vocabulary")
    require(vocab["status"] == "incomplete", "candidate budget backend status")
    require("candidate budget" in str(vocab["details"]["reason"]),
            "candidate budget reason")

    text = b"delve leverage \xe2\x80\x94 \xe2\x80\x94 \xe2\x80\x94 \xe2\x80\x94 \xe2\x80\x94 \xe2\x80\x94"
    full_result = r.run(["detect", "-", "--format", "json"], text)
    full = r.json(full_result, "full display")
    limited_result = r.run(
        ["detect", "-", "--display-limit", "0", "--format", "json"], text)
    limited = r.json(limited_result, "limited display")
    require(full_result.returncode == limited_result.returncode == 1,
            "display limit changed status")
    for key in ("complete", "analyzed_coverage", "verdict", "effective_finding_count",
                "families"):
        require(full[key] == limited[key], f"display limit changed {key}")
    require(full["emitted_findings"] == full["effective_finding_count"],
            "full display omitted findings")
    require(limited["emitted_findings"] == 0, "display limit emitted findings")
    require(limited["omitted_findings"] == limited["effective_finding_count"],
            "display limit omitted count")
    require(limited["emitted_candidates"] == 0 and limited["omitted_candidates"] > 0,
            "display limit candidate accounting")
    r.check("input/timeout/candidate budgets and display-only truncation")


def check_long_unicode(r):
    raw = (("é " * 50_000) + "delve " + ("é " * 50_000) + "leverage").encode()
    result = r.run(["lint", "-", "--format", "json"], raw)
    report = r.json(result, "long Unicode line")
    require(result.returncode == 1, "long Unicode line status")
    found = evidence(report)
    require([e["rule_id"] for e in found] == ["delve", "leverage"],
            "long Unicode findings")
    require([(e["line"], e["column"]) for e in found] == [(1, 100_001), (1, 200_007)],
            "long Unicode columns")
    require(report["complete"] is True, "long Unicode completeness")
    r.check("long single-line Unicode source locations")


def cpu_name():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def check_package(r, package_timeout):
    with tempfile.TemporaryDirectory(prefix="nobotrs-accept-package-") as temp:
        temp = Path(temp)
        package_target = temp / "package-target"
        packaged = subprocess.run(
            ["cargo", "package", "--locked", "--offline", "--allow-dirty",
             "--no-verify", "--target-dir", str(package_target)],
            cwd=ROOT, capture_output=True, timeout=package_timeout, check=False)
        require(packaged.returncode == 0,
                f"cargo package failed: {packaged.stderr.decode(errors='replace')}")
        crate = package_target / "package" / "nobotrs-0.1.0.crate"
        require(crate.is_file(), "package archive missing")
        unpacked = temp / "unpacked"
        with tarfile.open(crate, "r:gz") as archive:
            names = archive.getnames()
            require(any(name.endswith("docs/writing-guide.md") for name in names),
                    "packaged guide missing")
            require(any(name.endswith("dictionary/entries.json") for name in names),
                    "packaged dictionary missing")
            require(not any("docs/research/thor-ai-writing" in name for name in names),
                    "imported research was packaged")
            require(not any(
                "__pycache__" in name or name.endswith((".pyc", ".pyo"))
                or ".pytest_cache" in name for name in names
            ), "Python cache artifact was packaged")
            archive.extractall(unpacked)
        source = unpacked / "nobotrs-0.1.0"
        install_root = temp / "install"
        installed = subprocess.run(
            ["cargo", "install", "--locked", "--offline", "--path", str(source),
             "--root", str(install_root), "--target-dir", str(temp / "install-target")],
            cwd=temp, capture_output=True, timeout=package_timeout, check=False)
        require(installed.returncode == 0,
                f"cargo install failed: {installed.stderr.decode(errors='replace')}")
        binary = install_root / "bin" / "nobotrs"
        require(binary.is_file(), "installed binary missing")
        size = binary.stat().st_size
        require(size <= SIZE_BUDGET,
                f"release binary {size} exceeds {SIZE_BUDGET}-byte budget")
        installed_runner = Runner(binary, temp / "installed-work", timeout=60)
        installed_runner.work.mkdir()
        lint = installed_runner.run(["lint", "-", "--format", "json"], b"delve leverage")
        report = installed_runner.json(lint, "installed lint")
        require(lint.returncode == 1, "installed binary status")
        require(report["schema_version"] == "1.0.0", "installed JSON schema")
        guide = installed_runner.run(["guide"])
        require(guide.returncode == 0 and guide.stdout.startswith(b"# Writing guide"),
                "installed packaged guide")
        missing = installed_runner.run(["detect", str(temp / "absent.txt"), "--format", "json"])
        require(missing.returncode == 2, "installed missing-path status")
        print(f"MEASURE installed_binary_bytes={size}")
        print(f"MEASURE host_cpu={cpu_name()}")
        if Path("/usr/bin/time").is_file():
            measured = subprocess.run(
                ["/usr/bin/time", "-v", str(binary), "detect", "README.md",
                 "--format", "json"],
                cwd=ROOT, env=installed_runner.env(), capture_output=True,
                timeout=60, check=False)
            require(measured.returncode == 0, "release measurement run failed")
            for line in measured.stderr.decode(errors="replace").splitlines():
                if "Maximum resident set size" in line or "Elapsed (wall clock)" in line:
                    print(f"MEASURE {line.strip()}")
        else:
            print("MEASURE /usr/bin/time unavailable; runtime/RSS not recorded")
        r.check("package contents, clean install, installed CLI, and size budget")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default=str(ROOT / "target/debug/nobotrs"))
    parser.add_argument("--skip-package", action="store_true")
    parser.add_argument("--package-timeout", type=int, default=900)
    args = parser.parse_args()
    binary = Path(args.binary)
    if not binary.is_file():
        built = subprocess.run(["cargo", "build", "--locked"], cwd=ROOT, check=False)
        require(built.returncode == 0, "cargo build failed")
        binary = ROOT / "target/debug/nobotrs"
    with tempfile.TemporaryDirectory(prefix="nobotrs-accept-") as work:
        r = Runner(binary, work)
        try:
            check_cli_surface(r)
            check_file_stdin_equivalence(r)
            check_markdown_normalization(r)
            check_candidates_and_families(r)
            check_language_policy(r)
            check_failures_and_scan(r)
            check_budgets_and_display(r)
            check_long_unicode(r)
            if not args.skip_package:
                check_package(r, args.package_timeout)
            else:
                print("SKIP package/install verification (--skip-package)")
        except AcceptanceError as error:
            print(f"FAIL {error}", file=sys.stderr)
            return 1
    print(f"acceptance: {r.checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
