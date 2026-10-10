#!/usr/bin/env python3
"""Explicit advisory adapter: CLI 1 -> hook 2 (nudge); CLI 2 -> stderr and silence."""
import subprocess
import sys

def main():
    try:
        result = subprocess.run(["nobotrs", "lint", "-"], input=sys.stdin.buffer.read(1_048_577), capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"nobotrs advisory hook: {error}", file=sys.stderr)
        return 0
    if result.returncode == 1:
        sys.stdout.buffer.write(result.stdout)
        return 2
    if result.returncode == 2:
        sys.stderr.buffer.write(result.stderr or b"nobotrs advisory analysis incomplete\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
