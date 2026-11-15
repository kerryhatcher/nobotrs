#!/usr/bin/env python3
"""Check shipped integrations against the real executable and pinned SARIF schema.

Development only: run with jsonschema==4.26.0 and --schema pointing to the
OASIS SARIF 2.1.0 errata01 schema documented in docs/integration-validation.md.
No evaluation corpus is accessed and no source payloads are printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from acceptance import AcceptanceError, Runner, backend, require

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SHA256 = "c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e"


def candidates(report):
    return backend(report, "vocabulary")["details"]["candidates"]


def selected(report):
    return [c["rule_id"] for c in candidates(report) if c["disposition"] == "selected"]


def suppression_checks(r):
    phrase = b"embark on a journey"
    for ignored, expected in (("embark-on-a-journey", ["embark"]),
                              ("embark", ["embark-on-a-journey"]),
                              ("embark,embark-on-a-journey", [])):
        result = r.run(["lint", "-", "--ignore-rule", ignored, "--format", "json"], phrase)
        report = r.json(result, "global ignore")
        require(selected(report) == expected, "global ignore overlap reselection")
        require(result.returncode == (1 if expected else 0), "global ignore status")
        limited = r.run(["lint", "-", "--ignore-rule", ignored,
                         "--display-limit", "0", "--format", "json"], phrase)
        brief = r.json(limited, "suppression display limit")
        require(result.returncode == limited.returncode, "display changed suppression status")
        for key in ("effective_finding_count", "families", "verdict", "complete"):
            require(report[key] == brief[key], f"suppression display changed {key}")
    path = r.work / "ignored.md"
    path.write_bytes(phrase)
    config = r.work / "scopes.json"
    config.write_text(json.dumps({"path_ignores": {str(path): ["embark-on-a-journey"]}}))
    scoped = r.json(r.run(["lint", str(path), "--config", str(config), "--format", "json"]),
                    "per-path suppression")
    require(selected(scoped) == ["embark"], "per-path overlap reselection")
    inline = (b"<!-- nobotrs-ignore-next-line embark-on-a-journey -->\n"
              b"embark on a journey\n\nembark on a journey")
    report = r.json(r.run(["lint", "-", "--markdown", "--format", "json"], inline), "inline")
    require(selected(report) == ["embark", "embark-on-a-journey"], "next-line scope boundary")
    require(any(c["suppression"] for c in candidates(report)), "missing suppression audit")
    fence = b"```\n<!-- nobotrs-ignore-file embark -->\n```\nembark"
    report = r.json(r.run(["lint", "-", "--markdown", "--format", "json"], fence), "fenced ignore")
    require(selected(report) == ["embark"], "code-fenced directive active")
    malformed = r.run(["lint", "-", "--markdown", "--format", "json"],
                      b"<!-- nobotrs-ignore-file unknown-rule -->\ndelve")
    require(malformed.returncode == 2, "unknown suppression did not fail")
    r.check("real CLI suppression, overlap reselection, scope, display, and audit")


def sarif_checks(r, schema_path):
    import jsonschema
    raw = Path(schema_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCHEMA_SHA256, "SARIF schema checksum mismatch")
    schema = json.loads(raw)
    jsonschema.Draft4Validator.check_schema(schema)
    validator = jsonschema.Draft4Validator(schema, format_checker=jsonschema.FormatChecker())
    text = "😀 delve\n<!-- nobotrs-ignore-next-line leverage -->\nleverage\n".encode()
    for args, data in (([], text), (["--display-limit", "0"], text),
                       (["--timeout-ms", "0"], text)):
        result = r.run(["lint", "-", "--markdown", "--format", "sarif", *args], data)
        report = r.json(result, "SARIF")
        validator.validate(report)
        run = report["runs"][0]
        require(run["invocations"][0]["executionSuccessful"] == (result.returncode != 2),
                "SARIF execution status disagrees with CLI")
        if not args:
            require(run.get("columnKind") == "unicodeCodePoints", "SARIF column encoding undeclared")
            delve = next(x for x in run["results"] if x["ruleId"] == "delve")
            region = delve["locations"][0]["physicalLocation"]["region"]
            require(region == {"startLine": 1, "endLine": 1, "startColumn": 3, "endColumn": 8},
                    "SARIF astral source columns")
            leverage = next(x for x in run["results"] if x["ruleId"] == "leverage")
            require(leverage["suppressions"][0]["kind"] == "inSource", "SARIF inline suppression")
            rules = {rule["id"]: rule for rule in run["tool"]["driver"]["rules"]}
            require(delve["level"] == rules["delve"]["defaultConfiguration"]["level"],
                    "SARIF severity and rule metadata disagree")
        elif args[0] == "--display-limit":
            require(run["properties"]["displayTruncated"], "SARIF missing display truncation")
    r.check("pinned OASIS SARIF schema, Unicode columns, suppression and execution metadata")


def hook_checks(r):
    bindir = r.work / "bin"
    bindir.mkdir()
    (bindir / "nobotrs").symlink_to(r.binary)
    env = r.env({"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")})
    hook = ROOT / "scripts/advisory-hook.py"
    for text in (b"delve", b"plain prose", b"\xff"):
        direct = r.run(["lint", "-"], text)
        hooked = subprocess.run([sys.executable, str(hook)], input=text,
                                capture_output=True, env=env, cwd=r.work, timeout=15)
        require(hooked.returncode == (2 if direct.returncode == 1 else 0), "hook status translation")
        require(hooked.stdout == (direct.stdout if direct.returncode == 1 else b""),
                "hook stdout translation")
        if direct.returncode == 2:
            require(bool(hooked.stderr), "hook missing failure diagnostic")
    # Exercise all host status mappings, including inconclusive, independently
    # of whether today's default lint policy can produce each status naturally.
    fake = bindir / "nobotrs"
    fake.unlink()
    fake.write_text("#!/usr/bin/env python3\nimport os,sys\n"
                    "sys.stdin.buffer.read()\nprint('nudge')\n"
                    "print('diagnostic',file=sys.stderr)\n"
                    "sys.exit(int(os.environ['HOOK_TEST_STATUS']))\n")
    fake.chmod(0o755)
    for status in (0, 1, 2, 3):
        hooked = subprocess.run([sys.executable, str(hook)], input=b"test", capture_output=True,
                                env={**env, "HOOK_TEST_STATUS": str(status)}, timeout=15)
        require(hooked.returncode == (2 if status == 1 else 0), "hook simulated status mapping")
        require(bool(hooked.stdout) == (status == 1), "hook simulated silence contract")
    r.check("advisory hook uses installed binary and translates statuses 0/1/2/3")


def example_checks(r):
    # Check the shipped workflow shell, rather than a separately rewritten copy.
    workflow = (ROOT / "integrations/code-scanning.yml").read_text()
    lines = workflow.split("        run: |\n", 1)[1].splitlines()
    shell = "\n".join(line[10:] for line in lines if line.startswith("          "))
    bindir = r.work / "workflow-bin"
    bindir.mkdir()
    fake = bindir / "nobotrs"
    fake.write_text("#!/bin/sh\nprintf '{}\\n'\nexit \"$WORKFLOW_TEST_STATUS\"\n")
    fake.chmod(0o755)
    for status in (0, 1, 2, 3):
        result = subprocess.run(["bash", "-e", "-c", shell], cwd=r.work,
                                env=r.env({"PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                                           "WORKFLOW_TEST_STATUS": str(status)}),
                                capture_output=True, timeout=15)
        require(result.returncode == (2 if status == 2 else 0), "workflow status translation")
        require((r.work / "prose.sarif").read_text().strip() == "{}", "workflow lost SARIF output")
    hook = (ROOT / ".pre-commit-hooks.yaml").read_text()
    require("entry: nobotrs lint\n" in hook and "language: system\n" in hook
            and "pass_filenames: true\n" in hook, "pre-commit installed-binary contract changed")
    first, second = r.work / "clean.txt", r.work / "findings.md"
    first.write_text("plain prose")
    second.write_text("delve")
    require(r.run(["lint", str(first), str(second)]).returncode == 1,
            "pre-commit multi-filename invocation")
    guide = r.run(["guide"])
    require(guide.returncode == 0 and guide.stdout.startswith(b"# Writing guide"), "embedded guide")
    r.check("shipped workflow shell, pre-commit invocation and embedded guide")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(ROOT / "target/debug/nobotrs"))
    parser.add_argument("--schema", required=True, type=Path)
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="nobotrs-integration-") as work:
            runner = Runner(args.binary, work)
            suppression_checks(runner)
            sarif_checks(runner, args.schema)
            hook_checks(runner)
            example_checks(runner)
    except (AcceptanceError, OSError, ValueError, ImportError) as error:
        print(f"integration acceptance: {error}", file=sys.stderr)
        return 1
    print("integration acceptance: 4 groups passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
