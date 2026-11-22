#!/usr/bin/env python3
"""Translate an English prose review on stdin into optional host feedback."""
import json
import subprocess
import sys


def feedback(report):
    if not isinstance(report, dict) or report.get("complete") is not True:
        return []
    active = []
    for key in ("findings", "document"):
        items = report.get(key, [])
        if not isinstance(items, list):
            return []
        for item in items:
            if (isinstance(item, dict) and item.get("suppressed") is False
                    and type(item.get("leverage")) is int and 1 <= item["leverage"] <= 2):
                active.append(item)
    if not active:
        return []
    active.sort(key=lambda f: (f["leverage"], str(f.get("rule_id", ""))))
    lines = [f"nobotrs: {len(active)} high-leverage findings."]
    for item in active[:3]:
        location = item.get("location")
        line = location.get("line") if isinstance(location, dict) else None
        where = f" at line {line}" if isinstance(line, int) else ""
        fix = " ".join(str(item.get("fix", "")).split()).split(". ", 1)[0]
        lines.append(f"  {item.get('rule_id', 'editorial finding')}{where} — {fix[:160]}")
    return lines + ["Run the review-writing skill to revise."]


def main():
    text = sys.stdin.buffer.read(1_048_577)
    if not text:
        return 0
    try:
        proc = subprocess.run(["nobotrs", "review", "-", "--markdown", "--format", "json", "--language", "en"],
                              input=text, capture_output=True, timeout=10)
        if proc.returncode != 0:
            print("nobotrs advisory hook: review incomplete or unavailable", file=sys.stderr)
            return 0
        lines = feedback(json.loads(proc.stdout))
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        print(f"nobotrs advisory hook: {error}", file=sys.stderr)
        return 0
    if lines:
        print("\n".join(lines))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
