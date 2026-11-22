#!/usr/bin/env python3
"""Agent rewrite fidelity and blind reader preference harness (Plan 5, Task 5).

HARNESS ONLY. The owner has deferred the form platform, recruitment, consent wording
(roadmap decision 5) and whether Beemo excerpts may be shown to readers (decision 6).
Nothing in this module contacts a participant. Running the reader study needs those
decisions first.

The offline file-based subcommands (prepare/analyze/summary) work with synthetic
data and the real nobotrs binary. The blinded-study helpers (assign, export_packets,
import_ratings, summarize) are preserved for when the study decisions are settled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

# ----------------------------------------------------------------------
# Constants (shared by both the reader-study helpers and the offline CLI)
# ----------------------------------------------------------------------

RESAMPLES = 2000
SEED = 0
CONDITIONS = ("original", "naive", "guided")
COMPARISONS = (("guided", "naive", "primary"), ("guided", "original", "secondary"),
               ("naive", "original", "secondary"))
PII_COLUMNS = {"email", "name", "ip", "ip_address", "user_agent", "address", "phone"}
ATTENTION_FIELD = "attention_passed"

INSTRUCTIONS = (
    "You will read two short passages on the same topic. For each, rate how clear it is "
    "(1 = very unclear, 5 = very clear), and how much the writing distracts from its message "
    "(1 = not at all, 5 = very much). Then choose the passage you prefer, or tie. "
    "Answer from the text alone."
)

DEFAULT_BINARY_HINT = "target/debug/nobotrs"


class StudyError(RuntimeError):
    pass


def sha_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------------
# Fidelity (used by both the functional helpers and the offline CLI)
# ----------------------------------------------------------------------

FIDELITY_KEYS = ("missing_hard", "missing_soft", "added_facts", "removed_by_leverage",
                 "introduced_by_leverage", "length_ratio", "exit")

# Invariant kind values that Invariant::hard() treats as hard facts.
_HARD_KINDS = frozenset(("number", "quote", "url", "code", "link"))


def fidelity(source: Path, rewrite: Path, binary: Path | None = None) -> dict:
    """Run ``nobotrs compare --format json`` on a source/rewrite pair.

    Validates that the response is ``complete``, carries a ``compare_version``,
    and that ``missing`` / ``added`` arrays are present (not absent). An absent
    array is a protocol error, not an empty result.

    ``Invariant::hard()`` is a Rust method that checks ``kind`` — there is no
    ``hard`` boolean in the JSON. Hard kinds are: number, quote, url, code, link.
    Everything else (anchored_claim, name, qualifier, …) is soft.
    """
    if binary is None:
        raise StudyError("fidelity needs the nobotrs binary (compare subcommand)")
    result = subprocess.run([str(binary), "compare", "--format", "json", "--language", "en",
                             str(source), str(rewrite)],
                            capture_output=True, timeout=30, check=False)
    if result.returncode not in (0, 1):
        raise StudyError(f"compare exited {result.returncode}: subcommand missing or failed")
    body = json.loads(result.stdout or b"{}")
    if not body.get("complete"):
        raise StudyError("compare report is not marked complete")
    if body.get("compare_version") != "compare-v1":
        raise StudyError(
            f"unexpected compare_version: {body.get('compare_version')}")
    if "missing" not in body:
        raise StudyError("compare report has no 'missing' key")
    if "added" not in body:
        raise StudyError("compare report has no 'added' key")
    missing_list = body["missing"]
    added_list = body["added"]
    row: dict[str, Any] = {}
    row["missing_hard"] = sum(1 for m in missing_list
                                if m.get("kind") in _HARD_KINDS)
    row["missing_soft"] = sum(1 for m in missing_list
                                if m.get("kind") not in _HARD_KINDS)
    row["added_hard"] = sum(1 for a in added_list
                             if a.get("invariant", {}).get("kind") in _HARD_KINDS)
    row["added_soft"] = sum(1 for a in added_list
                             if a.get("invariant", {}).get("kind")
                             not in _HARD_KINDS)
    row["exit"] = result.returncode
    # Derive length_ratio from the metrics array
    for metric in body.get("metrics", []):
        if metric.get("name") == "prose_words":
            before = metric.get("before")
            after = metric.get("after")
            if before and after and before > 0:
                row["length_ratio"] = after / before
                row["prose_words_before"] = before
                row["prose_words_after"] = after
            break
    return row


def is_fidelity_failure(row: dict) -> bool:
    """True when the rewrite lost or added any measurement.

    A missing measurement (hard or soft fact) makes the rewrite suspect.
    An empty/unknown row also fails: ``is_fidelity_failure({})`` is ``True``.
    """
    if not row:
        return True
    if (row.get("missing_hard") or 0) > 0:
        return True
    if (row.get("missing_soft") or 0) > 0:
        return True
    if (row.get("added_hard") or 0) > 0:
        return True
    if (row.get("added_soft") or 0) > 0:
        return True
    if row.get("exit", 0) not in (0, 1):
        return True
    return False


# ----------------------------------------------------------------------
# Reader-study assignment (preserved for when study decisions are settled)
# ----------------------------------------------------------------------

def assign(readers: int, pairs: list[dict], per_reader: int = 12, seed: int = 0,
           min_ratings: int | None = None) -> dict[str, list[dict]]:
    """Balanced assignment: each pair receives ``min_ratings`` ratings, no reader sees two
    pairs from one source, and each reader receives ``per_reader`` pairs.

    Requires readers * per_reader == len(pairs) * min_ratings. With 120 pairs this holds
    exactly at 70 readers (7 ratings) and at 350 readers (35 ratings).
    """
    if min_ratings is None:
        min_ratings = readers * per_reader // len(pairs)
    if readers * per_reader != len(pairs) * min_ratings:
        raise StudyError("assignment slots do not balance: "
                         f"{readers * per_reader} != {len(pairs) * min_ratings}")
    rng = random.Random(seed)
    for _attempt in range(200):
        slots = [p for p in pairs for _ in range(min_ratings)]
        rng.shuffle(slots)
        plan = _pack(slots, readers, per_reader, pairs)
        if plan is not None:
            return {f"R{index:03d}": plan[index] for index in range(readers)}
    raise StudyError("could not satisfy the one-pair-per-source constraint")


def _pack(slots: list[dict], readers: int, per_reader: int, pairs: list[dict]):
    """Greedy packing with swap repair. Returns per-reader pair lists or None."""
    plan: list[list[dict]] = [[] for _ in range(readers)]
    sources: list[set[str]] = [set() for _ in range(readers)]
    leftovers = []
    for pair in slots:
        placed = False
        for index in range(readers):
            if len(plan[index]) < per_reader and pair["source_id"] not in sources[index]:
                plan[index].append(pair)
                sources[index].add(pair["source_id"])
                placed = True
                break
        if not placed:
            leftovers.append(pair)
    if leftovers:
        return None
    if any(len(reader) != per_reader for reader in plan):
        return None
    return plan


# ----------------------------------------------------------------------
# Reader-study packet export (preserved, no participant contact)
# ----------------------------------------------------------------------

def ab_order(seed: int, reader: str, pair_id: str) -> bool:
    """True when the left condition is shown as version A. Seeded, so packets reproduce."""
    return random.Random(f"{seed}:{reader}:{pair_id}").random() < 0.5


def export_packets(assignment: dict[str, list[dict]], texts: dict[tuple[str, str], str],
                   out_dir: Path, seed: int, key_path: Path) -> list[dict]:
    """Write blind packets and a private orientation key.

    Each (reader, pair) gets its own directory, ``packets/<reader_id>/<pair_id>/``, so readers
    whose orientation differs never overwrite one another. Packets show only versions A and
    B with hashed ids; no condition names. The key maps each (reader_id, pair_id) to the
    condition behind A and B. It must live outside ``out_dir`` and is never sent to readers.
    """
    out_dir = Path(out_dir)
    key_path = Path(key_path)
    if key_path.resolve().is_relative_to(out_dir.resolve()):
        raise StudyError("orientation key must be stored outside the blind packet directory")
    packets_root = out_dir / "packets"
    packets_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    key: dict[str, dict] = {}
    for reader, pairs in sorted(assignment.items()):
        reader_id = sha_id("reader", str(seed), reader)
        for pair in pairs:
            pair_id = sha_id("pair", str(seed), pair["pair_id"])
            ident = f"{reader_id}|{pair_id}"
            if ident in key:
                raise StudyError(f"duplicate reader/pair packet {ident}")
            left_is_a = ab_order(seed, reader, pair["pair_id"])
            version_a_cond, version_b_cond = ((pair["left"], pair["right"]) if left_is_a
                                              else (pair["right"], pair["left"]))
            try:
                text_a = texts[(pair["source_id"], version_a_cond)]
                text_b = texts[(pair["source_id"], version_b_cond)]
            except KeyError as exc:
                raise StudyError(f"missing rewrite text {exc.args[0]!r}; cannot build packet") from exc
            base = packets_root / reader_id / pair_id
            base.mkdir(parents=True, exist_ok=True)
            (base / "A.txt").write_text(text_a, encoding="utf-8")
            (base / "B.txt").write_text(text_b, encoding="utf-8")
            rows.append({"reader_id": reader_id, "pair_id": pair_id,
                         "version_a": f"packets/{reader_id}/{pair_id}/A.txt",
                         "version_b": f"packets/{reader_id}/{pair_id}/B.txt"})
            key[ident] = {"a": version_a_cond, "b": version_b_cond, "left": pair["left"],
                          "right": pair["right"], "source_id": pair["source_id"],
                          "genre": pair.get("genre", "unspecified")}
    with (out_dir / "packets.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["reader_id", "pair_id", "version_a",
                                                    "version_b"])
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "instructions.txt").write_text(INSTRUCTIONS + "\n", encoding="utf-8")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, indent=2, sort_keys=True), encoding="utf-8")
    return rows


def a_is_guided_share(assignment: dict[str, list[dict]], seed: int) -> float:
    """Share of packets involving ``guided`` where guided is shown as A."""
    total = guided_a = 0
    for reader, pairs in assignment.items():
        for pair in pairs:
            if "guided" not in (pair["left"], pair["right"]):
                continue
            total += 1
            left_is_a = ab_order(seed, reader, pair["pair_id"])
            guided_is_a = (pair["left"] == "guided") == left_is_a
            guided_a += guided_is_a
    return guided_a / total if total else 0.0


# ----------------------------------------------------------------------
# Reader-study rating import (preserved, no participant contact)
# ----------------------------------------------------------------------

RATING_FIELDS = ("clarity_a", "clarity_b", "distraction_a", "distraction_b")


def _required_number(raw: dict, field: str, line: int) -> float:
    value = str(raw.get(field, "")).strip()
    if value == "":
        raise StudyError(f"row {line}: missing {field}; incomplete ratings cannot pass")
    try:
        number = float(value)
    except ValueError as exc:
        raise StudyError(f"row {line}: {field} is not a number: {value!r}") from exc
    if not 1 <= number <= 5:
        raise StudyError(f"row {line}: {field} outside 1-5: {number}")
    return number


def import_ratings(path: Path, attention_key: str = ATTENTION_FIELD) -> tuple[list[dict], int]:
    """Parse blinded ratings. Returns (rows, attention_failures_dropped).

    Rows failing the attention check are dropped and counted. Any other incomplete or invalid
    row raises StudyError: missing data must not be filled in or defaulted. Names, emails and
    IP addresses are never copied into the returned rows.
    """
    text = Path(path).read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    dropped = 0
    seen: set[tuple[str, str]] = set()
    for line, raw in enumerate(reader, start=2):
        if str(raw.get(attention_key, "")).strip().lower() not in ("1", "true", "yes", "pass"):
            dropped += 1
            continue
        for required in ("reader_id", "pair_id", "preferred"):
            if not str(raw.get(required, "")).strip():
                raise StudyError(f"row {line}: missing {required}; incomplete ratings cannot pass")
        preferred = raw["preferred"].strip().upper()
        if preferred not in ("A", "B", "TIE"):
            raise StudyError(f"row {line}: preferred must be A, B or TIE, got {preferred!r}")
        ident = (raw["reader_id"].strip(), raw["pair_id"].strip())
        if ident in seen:
            raise StudyError(f"row {line}: duplicate rating for reader/pair {ident}")
        seen.add(ident)
        values = {field: _required_number(raw, field, line) for field in RATING_FIELDS}
        rows.append({"reader_id": ident[0], "pair_id": ident[1], "preferred": preferred, **values})
    return rows, dropped


def decode_ratings(rows: list[dict], key: dict[str, dict]) -> list[dict]:
    """Join each rating to its reader/pair orientation and decode A/B into conditions.

    Raises StudyError for a rating with no key entry; it is never silently dropped.
    """
    decoded = []
    for row in rows:
        ident = f"{row['reader_id']}|{row['pair_id']}"
        if ident not in key:
            raise StudyError(f"rating for unknown reader/pair {ident}; cannot decode orientation")
        entry = key[ident]
        a_cond, b_cond = entry["a"], entry["b"]
        if row["preferred"] == "A":
            preferred = a_cond
        elif row["preferred"] == "B":
            preferred = b_cond
        else:
            preferred = "TIE"
        decoded.append({
            "reader_id": row["reader_id"], "pair_id": row["pair_id"],
            "source_id": entry["source_id"], "genre": entry["genre"],
            "left": entry["left"], "right": entry["right"], "preferred": preferred,
            "clarity": {a_cond: row["clarity_a"], b_cond: row["clarity_b"]},
            "distraction": {a_cond: row["distraction_a"], b_cond: row["distraction_b"]},
        })
    return decoded


# ----------------------------------------------------------------------
# Reader-study summary and success criteria (condition-level, decoded ratings only)
# ----------------------------------------------------------------------

def _win_value(row: dict, condition_a: str, condition_b: str, fidelity_fail: set) -> float:
    """Value of the rating for ``condition_a`` against ``condition_b``: 1.0 win, 0.0 loss,
    0.5 tie. Exactly one failing side loses to the passing side whatever readers prefer.
    Otherwise the decoded preference decides. Equal orientations give equal values."""
    a_fail = (row["source_id"], condition_a) in fidelity_fail
    b_fail = (row["source_id"], condition_b) in fidelity_fail
    if a_fail and not b_fail:
        return 0.0
    if b_fail and not a_fail:
        return 1.0
    if row["preferred"] == condition_a:
        return 1.0
    if row["preferred"] == condition_b:
        return 0.0
    return 0.5


def _clustered_bootstrap(ratings: list[dict], value_fn) -> tuple[float | None, list | None]:
    by_reader: dict[str, list[dict]] = defaultdict(list)
    for row in ratings:
        by_reader[row["reader_id"]].append(row)
    readers = sorted(by_reader)
    if not readers:
        return None, None
    values = {r: value_fn(by_reader[r]) for r in readers}
    point = sum(sum(v) for v in values.values()) / sum(len(v) for v in values.values())
    rng = random.Random(SEED)
    draws = []
    for _ in range(RESAMPLES):
        pick = [readers[rng.randrange(len(readers))] for _ in readers]
        total = sum(sum(values[r]) for r in pick)
        count = sum(len(values[r]) for r in pick)
        if count:
            draws.append(total / count)
    draws.sort()
    ci = [draws[int(0.025 * (len(draws) - 1))], draws[int(0.975 * (len(draws) - 1))]] \
        if draws else None
    return point, ci


def _mean_diff(rows: list[dict], measure: str, cond_a: str, cond_b: str) -> float | None:
    diffs = []
    for row in rows:
        values = row[measure]
        if cond_a not in values or cond_b not in values:
            raise StudyError(f"{measure} missing for {cond_a} or {cond_b} in pair {row['pair_id']}")
        diffs.append(values[cond_a] - values[cond_b])
    return sum(diffs) / len(diffs) if diffs else None


def summarize(ratings: list[dict], fidelity_rows: list[dict]) -> dict:
    """Win rates with reader-clustered bootstrap CIs, clarity and distraction differences,
    per-genre counts and fidelity failure rates. ``ratings`` must be decoded (see
    decode_ratings). Fidelity failures are keyed by (source_id, condition)."""
    fidelity_fail = {(row["source_id"], row["condition"]) for row in fidelity_rows
                     if is_fidelity_failure(row)}
    out: dict = {"comparisons": {}, "fidelity_failure_rate": {}}
    for cond_a, cond_b, kind in COMPARISONS:
        rel = [r for r in ratings if {r["left"], r["right"]} == {cond_a, cond_b}]

        def values(rows, a=cond_a, b=cond_b):
            return [_win_value(r, a, b, fidelity_fail) for r in rows]

        point, ci = _clustered_bootstrap(rel, values)
        genres: dict[str, int] = defaultdict(int)
        for row in rel:
            genres[row["genre"]] += 1
        out["comparisons"][f"{cond_a} vs {cond_b}"] = {
            "kind": kind, "ratings": len(rel), "win_rate": point, "win_rate_ci": ci,
            "clarity_diff": _mean_diff(rel, "clarity", cond_a, cond_b),
            "distraction_diff": _mean_diff(rel, "distraction", cond_a, cond_b),
            "by_genre": dict(sorted(genres.items())),
        }
    for condition in CONDITIONS:
        rows = [row for row in fidelity_rows if row["condition"] == condition]
        failures = sum(1 for row in rows if is_fidelity_failure(row))
        out["fidelity_failure_rate"][condition] = failures / len(rows) if rows else None
    return out


def predeclared_success(summary: dict) -> dict:
    """Plan 5 success criteria. A check passes only with complete data: a missing value
    (None) is a failed check, never a pass."""
    guided_naive = summary["comparisons"]["guided vs naive"]
    guided_original = summary["comparisons"]["guided vs original"]
    rates = summary["fidelity_failure_rate"]
    checks = {
        "guided beats naive (win-rate CI lower bound > 0.5)":
            bool(guided_naive["win_rate_ci"]) and guided_naive["win_rate_ci"][0] > 0.5,
        "guided not worse than original on clarity":
            guided_original["clarity_diff"] is not None and guided_original["clarity_diff"] >= 0,
        "guided fidelity failure rate <= naive":
            rates.get("guided") is not None and rates.get("naive") is not None
            and rates["guided"] <= rates["naive"],
    }
    return checks


# ======================================================================
# Offline file-based CLI (prepare / analyze / summary)
# ======================================================================

def _nobotrs_binary() -> str:
    """Default path to the test binary (overridable via --binary)."""
    return str((ROOT / DEFAULT_BINARY_HINT).resolve())


def _check_binary(bin_path: str) -> None:
    """Verify the binary supports required subcommands."""
    for sub in ("review", "compare"):
        r = subprocess.run(
            [bin_path, sub, "--help"], capture_output=True, timeout=15,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"nobotrs {sub} failed (exit {r.returncode}): "
                f"is the binary built with the right features?"
            )


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def cmd_prepare(args: argparse.Namespace) -> int:
    """Copy source text into the study layout and record its review report."""
    source_path = Path(args.source)
    out_dir = Path(args.out_dir)
    source_id = args.source_id or source_path.stem

    source_dir = out_dir / "sources" / source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    # Copy the source text
    src_text = source_path.read_bytes()
    source_file = source_dir / "original.txt"
    source_file.write_bytes(src_text)

    # Run review on the source text
    bin_path = args.binary
    review_out = source_dir / "review.json"
    r = subprocess.run(
        [bin_path, "review", str(source_file), "--format", "json", "--language", "en"],
        capture_output=True, timeout=30,
    )
    if r.returncode == 2:
        print(f"warning: review returned error for {source_id}", file=sys.stderr)
        if r.stderr:
            print(r.stderr.decode(errors="replace"), file=sys.stderr)
        review_data = {"complete": False, "error": r.stderr.decode(errors="replace")}
    else:
        try:
            review_data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            review_data = {"complete": False, "error": "invalid JSON from review"}

    review_data["source_id"] = source_id
    review_data["source_path"] = str(source_file)
    _write_json(review_out, review_data)

    result = {
        "source_id": source_id,
        "source_text_sha256": hashlib.sha256(src_text).hexdigest(),
        "review_complete": review_data.get("complete", False),
        "source_words": review_data.get("prose_words", 0),
    }
    _write_json(source_dir / "prepared.json", result)

    print(f"Prepared {source_id} ({result['source_words']} words)")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Compare a rewrite against its prepared source and report fidelity."""
    rewrite_path = Path(args.rewrite)
    out_dir = Path(args.out_dir)
    source_id = args.source_id
    condition = args.condition
    rewrite_id = args.rewrite_id or f"{source_id}-{condition}"

    source_file = out_dir / "sources" / source_id / "original.txt"
    if not source_file.exists():
        print(f"error: source {source_id} not prepared (run prepare first)", file=sys.stderr)
        return 2

    bin_path = args.binary

    # Run fidelity via the compare-based helper
    try:
        fidelity_row = fidelity(source_file, rewrite_path, Path(bin_path))
    except StudyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    fidelity_row["rewrite_id"] = rewrite_id
    fidelity_row["source_id"] = source_id
    fidelity_row["condition"] = condition
    # Normalise length_ratio from compare output
    before_words = fidelity_row.pop("prose_words_before", None)
    after_words = fidelity_row.pop("prose_words_after", None)
    if before_words and after_words and before_words > 0:
        fidelity_row["length_ratio"] = after_words / before_words
    else:
        before_metric = None
        after_metric = None
        # Fallback: derive from the compare report if it was stored
        fidelity_row.setdefault("length_ratio", 1.0)
    fidelity_row.setdefault("length_ratio", 1.0)
    fidelity_row.setdefault("prose_words_source", before_words or 0)
    fidelity_row.setdefault("prose_words_rewrite", after_words or 0)

    compare_out = out_dir / "comparisons" / rewrite_id
    _write_json(compare_out / "fidelity.json", fidelity_row)

    status = "FAIL" if is_fidelity_failure(fidelity_row) else "PASS"
    print(f"{rewrite_id}: {status} "
          f"(missing={fidelity_row.get('missing_hard', 0)}"
          f"+{fidelity_row.get('missing_soft', 0)}, "
          f"added={fidelity_row.get('added_hard', 0)}"
          f"+{fidelity_row.get('added_soft', 0)}, "
          f"len_ratio={fidelity_row.get('length_ratio') or 1.0:.3f})")
    return 1 if is_fidelity_failure(fidelity_row) else 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Aggregate fidelity results from all analyze comparisons and print a summary."""
    out_dir = Path(args.out_dir)
    comparisons_dir = out_dir / "comparisons"
    if not comparisons_dir.exists():
        print("No comparisons found — run analyze first.", file=sys.stderr)
        return 2

    fidelity_rows: list[dict] = []
    for comp_dir in sorted(comparisons_dir.iterdir()):
        fpath = comp_dir / "fidelity.json"
        if fpath.exists():
            fidelity_rows.append(_read_json(fpath))

    if not fidelity_rows:
        print("No fidelity results found.", file=sys.stderr)
        return 2

    # Aggregate by condition
    by_condition: dict[str, list[dict]] = defaultdict(list)
    for row in fidelity_rows:
        by_condition[row["condition"]].append(row)

    summary: dict[str, Any] = {
        "total_rewrites": len(fidelity_rows),
        "by_condition": {},
    }

    for condition in sorted(by_condition):
        rows = by_condition[condition]
        failures = sum(1 for r in rows if is_fidelity_failure(r))
        avg_missing = sum(r.get("missing_hard", 0) + r.get("missing_soft", 0)
                          for r in rows) / len(rows)
        avg_length = sum(r.get("length_ratio", 1.0) for r in rows) / len(rows)
        summary["by_condition"][condition] = {
            "count": len(rows),
            "failure_rate": failures / len(rows),
            "failures": failures,
            "avg_missing_facts": avg_missing,
            "avg_length_ratio": avg_length,
        }

    summary["overall_failure_rate"] = (
        sum(s["failures"] for s in summary["by_condition"].values())
        / summary["total_rewrites"]
    )

    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print(f"Total rewrites: {summary['total_rewrites']}")
        print(f"Overall failure rate: {summary['overall_failure_rate']:.1%}")
        for condition, stats in sorted(summary["by_condition"].items()):
            print(f"  {condition}: {stats['count']} rewrites, "
                  f"{stats['failure_rate']:.1%} failed, "
                  f"avg missing: {stats['avg_missing_facts']:.2f}, "
                  f"avg length ratio: {stats['avg_length_ratio']:.3f}")

    return 0


# ======================================================================
# CLI entry point
# ======================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Agent rewrite fidelity and blind reader preference harness",
    )
    parser.add_argument(
        "--binary", default=None,
        help="Path to nobotrs binary (default: auto-detect)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prep = sub.add_parser("prepare", help="Copy source into study layout")
    p_prep.add_argument("source", type=str, help="Source text file")
    p_prep.add_argument("--out-dir", default="rewrite-study",
                        help="Study output directory")
    p_prep.add_argument("--source-id", default=None,
                        help="Identifier for this source (default: filename stem)")
    p_prep.set_defaults(func=cmd_prepare)

    p_ana = sub.add_parser("analyze",
                           help="Compare a rewrite against a prepared source")
    p_ana.add_argument("rewrite", type=str, help="Rewrite text file")
    p_ana.add_argument("--out-dir", default="rewrite-study",
                       help="Study output directory")
    p_ana.add_argument("--source-id", required=True,
                       help="Source identifier (must have been prepared)")
    p_ana.add_argument("--condition", required=True,
                       help="Condition label (e.g. guided, naive, original)")
    p_ana.add_argument("--rewrite-id", default=None,
                       help="Identifier for this comparison (default: source-cond)")
    p_ana.set_defaults(func=cmd_analyze)

    p_sum = sub.add_parser("summary", help="Aggregate fidelity results")
    p_sum.add_argument("--out-dir", default="rewrite-study",
                       help="Study output directory")
    p_sum.add_argument("--format", default="human",
                       choices=("human", "json"))
    p_sum.set_defaults(func=cmd_summary)

    args = parser.parse_args(argv)

    # Resolve binary
    if args.binary is None:
        args.binary = str(_nobotrs_binary())
    args.binary = str(Path(args.binary).resolve())

    # Verify binary before running subcommands that need it
    if hasattr(args, "func") and args.func in (cmd_prepare, cmd_analyze):
        _check_binary(args.binary)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())