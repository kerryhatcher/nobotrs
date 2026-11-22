#!/usr/bin/env python3
"""Synthetic regressions for the rewrite fidelity and reader-study harness (Plan 5, Task 5).

No participant data, no real rewrites and no network use. The study itself is not run:
platform, recruitment, consent and Beemo inclusion are owner decisions still pending.
Uses the real ``nobotrs`` binary for integration tests.
"""
import argparse
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rewrite_eval as re_  # noqa: E402


def _binary() -> str:
    return re_._nobotrs_binary()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sources(n):
    return [f"s{i:02d}" for i in range(n)]


def pairs_for(source_ids):
    out = []
    for sid in source_ids:
        for left, right, kind in re_.COMPARISONS:
            out.append({"pair_id": f"{sid}-{left}-{right}", "source_id": sid,
                        "left": left, "right": right, "kind": kind, "genre": "civic"})
    return out


# ======================================================================
# Fidelity tests
# ======================================================================

class FidelityTests(unittest.TestCase):
    def test_empty_dict_is_failure(self):
        """is_fidelity_failure({}) must be True — unknown state fails."""
        self.assertTrue(re_.is_fidelity_failure({}))

    def test_clean_row_passes(self):
        row = {"missing_hard": 0, "missing_soft": 0,
               "added_hard": 0, "added_soft": 0, "exit": 0}
        self.assertFalse(re_.is_fidelity_failure(row))

    def test_failure_on_missing_hard(self):
        row = {"missing_hard": 1, "missing_soft": 0,
               "added_hard": 0, "added_soft": 0, "exit": 0}
        self.assertTrue(re_.is_fidelity_failure(row))

    def test_failure_on_missing_soft(self):
        row = {"missing_hard": 0, "missing_soft": 1,
               "added_hard": 0, "added_soft": 0, "exit": 0}
        self.assertTrue(re_.is_fidelity_failure(row))

    def test_failure_on_added_hard(self):
        row = {"missing_hard": 0, "missing_soft": 0,
               "added_hard": 1, "added_soft": 0, "exit": 0}
        self.assertTrue(re_.is_fidelity_failure(row))

    def test_failure_on_added_soft(self):
        row = {"missing_hard": 0, "missing_soft": 0,
               "added_hard": 0, "added_soft": 1, "exit": 0}
        self.assertTrue(re_.is_fidelity_failure(row))

    def test_failure_on_bad_exit(self):
        row = {"missing_hard": 0, "missing_soft": 0,
               "added_hard": 0, "added_soft": 0, "exit": 2}
        self.assertTrue(re_.is_fidelity_failure(row))


# ======================================================================
# Reader-study assignment tests (original preserved)
# ======================================================================

class AssignmentTests(unittest.TestCase):
    def _check(self, readers, min_ratings):
        pairs = pairs_for(sources(40))
        plan = re_.assign(readers, pairs, per_reader=12, seed=0, min_ratings=min_ratings)
        self.assertEqual(len(plan), readers)
        counts = {}
        for reader, assigned in plan.items():
            self.assertEqual(len(assigned), 12)
            seen_sources = [p["source_id"] for p in assigned]
            self.assertEqual(len(seen_sources), len(set(seen_sources)),
                             f"{reader} saw two pairs from one source")
            for p in assigned:
                counts[p["pair_id"]] = counts.get(p["pair_id"], 0) + 1
        self.assertEqual(len(counts), 120)
        self.assertTrue(all(c >= min_ratings for c in counts.values()))

    def test_balance_at_70_readers(self):
        self._check(70, 7)

    def test_balance_at_350_readers(self):
        self._check(350, 35)

    def test_unbalanced_slots_are_rejected(self):
        with self.assertRaises(re_.StudyError):
            re_.assign(71, pairs_for(sources(40)), per_reader=12, min_ratings=7)


# ======================================================================
# Packet tests (original preserved)
# ======================================================================

class PacketTests(unittest.TestCase):
    def test_packets_hide_condition_and_randomize_order(self):
        assignment = {"R000": [p for p in pairs_for(sources(4)) if "guided" in
                               (p["left"], p["right"])]}
        shares = [re_.a_is_guided_share(assignment, seed) for seed in range(100)]
        overall = sum(shares) / len(shares)
        self.assertGreaterEqual(overall, 0.40)
        self.assertLessEqual(overall, 0.60)

    def _texts(self, assignment):
        return {(p["source_id"], c): f"neutral passage {p['source_id']} v{len(c)}"
                for pairs in assignment.values() for p in pairs for c in re_.CONDITIONS}

    def test_export_hides_condition_names_and_keeps_key_outside(self):
        assignment = {"R000": pairs_for(sources(2))[:3]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "packets"
            key = Path(tmp) / "private" / "orientation.json"
            re_.export_packets(assignment, self._texts(assignment), out, seed=1, key_path=key)
            blob = (out / "packets.csv").read_text() + (out / "instructions.txt").read_text()
            for path in out.rglob("*.txt"):
                blob += path.read_text()
            for name in ("guided", "naive", "original"):
                self.assertNotIn(name, blob)
            self.assertTrue(key.exists())
            self.assertFalse(str(key).startswith(str(out)))

    def test_key_inside_packet_directory_is_refused(self):
        assignment = {"R000": pairs_for(sources(1))[:1]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "packets"
            with self.assertRaises(re_.StudyError):
                re_.export_packets(assignment, self._texts(assignment), out, seed=1,
                                   key_path=out / "key.json")

    def test_each_reader_gets_distinct_packet_paths(self):
        """Readers whose orientation flips must not overwrite each other's A/B files."""
        pairs = pairs_for(sources(1))[:2]
        assignment = {f"R{i:03d}": list(pairs) for i in range(12)}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "packets"
            key_path = Path(tmp) / "key.json"
            rows = re_.export_packets(assignment, self._texts(assignment), out, seed=3,
                                      key_path=key_path)
            paths = {row["version_a"] for row in rows} | {row["version_b"] for row in rows}
            self.assertEqual(len(paths), 2 * len(rows))
            key = json.loads(key_path.read_text())
            self.assertEqual(len(key), len(rows))
            orientations = {(entry["a"], entry["b"]) for entry in key.values()}
            self.assertGreater(len(orientations), 1, "test needs both orientations to occur")

    def test_missing_rewrite_text_cannot_build_a_packet(self):
        assignment = {"R000": pairs_for(sources(1))[:1]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(re_.StudyError):
                re_.export_packets(assignment, {}, Path(tmp) / "packets", seed=1,
                                   key_path=Path(tmp) / "key.json")


class ImportTests(unittest.TestCase):
    HEADER = ("reader_id,pair_id,preferred,clarity_a,clarity_b,distraction_a,distraction_b,"
              "attention_passed,email,ip_address,name\n")

    def _import(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ratings.csv"
            path.write_text(self.HEADER + body, encoding="utf-8")
            return re_.import_ratings(path)

    def test_attention_failures_dropped_and_counted(self):
        rows, dropped = self._import(
            "r1,p1,A,4,3,2,3,yes,a@example.invalid,203.0.113.5,Ada\n"
            "r2,p1,B,2,4,3,2,no,b@example.invalid,203.0.113.6,Ben\n")
        self.assertEqual([r["reader_id"] for r in rows], ["r1"])
        self.assertEqual(dropped, 1)

    def test_no_pii_columns_survive_import(self):
        rows, _ = self._import("r1,p1,A,4,3,2,3,yes,a@example.invalid,203.0.113.5,Ada\n")
        self.assertEqual(set(rows[0]), {"reader_id", "pair_id", "preferred", "clarity_a",
                                        "clarity_b", "distraction_a", "distraction_b"})
        self.assertNotIn("a@example.invalid", str(rows))
        self.assertNotIn("203.0.113.5", str(rows))

    def test_missing_clarity_is_an_error_not_a_zero(self):
        with self.assertRaises(re_.StudyError):
            self._import("r1,p1,A,,3,2,3,yes,,,\n")

    def test_out_of_range_rating_is_an_error(self):
        with self.assertRaises(re_.StudyError):
            self._import("r1,p1,A,9,3,2,3,yes,,,\n")

    def test_duplicate_reader_pair_is_an_error(self):
        with self.assertRaises(re_.StudyError):
            self._import("r1,p1,A,4,3,2,3,yes,,,\nr1,p1,B,3,4,2,3,yes,,,\n")


class DecodeTests(unittest.TestCase):
    """Orientation decoding: the same underlying preference must give the same result
    whichever version the reader saw as A."""

    def _ratings(self, a_cond, b_cond, preferred):
        return [{"reader_id": "r1", "pair_id": "p1", "preferred": preferred,
                 "clarity_a": 5.0, "clarity_b": 2.0, "distraction_a": 1.0, "distraction_b": 4.0}]

    def _key(self, a_cond, b_cond):
        return {"r1|p1": {"a": a_cond, "b": b_cond, "left": "guided", "right": "naive",
                          "source_id": "s1", "genre": "civic"}}

    def test_opposite_orders_same_preferred_condition_same_win(self):
        # Reader prefers guided. Orientation 1: guided is A. Orientation 2: guided is B.
        first = re_.decode_ratings(self._ratings("guided", "naive", "A"),
                                   self._key("guided", "naive"))
        second = re_.decode_ratings(self._ratings("naive", "guided", "B"),
                                    self._key("naive", "guided"))
        self.assertEqual(first[0]["preferred"], "guided")
        self.assertEqual(second[0]["preferred"], "guided")
        self.assertEqual(re_._win_value(first[0], "guided", "naive", set()),
                         re_._win_value(second[0], "guided", "naive", set()))
        self.assertEqual(re_._win_value(first[0], "guided", "naive", set()), 1.0)

    def test_clarity_follows_the_condition_not_the_slot(self):
        decoded = re_.decode_ratings(self._ratings("guided", "naive", "A"),
                                     self._key("guided", "naive"))
        self.assertEqual(decoded[0]["clarity"], {"guided": 5.0, "naive": 2.0})
        flipped = re_.decode_ratings(self._ratings("naive", "guided", "A"),
                                     self._key("naive", "guided"))
        self.assertEqual(flipped[0]["clarity"], {"naive": 5.0, "guided": 2.0})

    def test_rating_without_key_entry_is_an_error(self):
        with self.assertRaises(re_.StudyError):
            re_.decode_ratings(self._ratings("guided", "naive", "A"), {})


class SummaryTests(unittest.TestCase):
    def decoded(self, pair_id, source_id, left, right, preferred, reader="r1", clarity=None,
                genre="civic"):
        clarity = clarity or {left: 4.0, right: 3.0}
        return {"reader_id": reader, "pair_id": pair_id, "source_id": source_id, "genre": genre,
                "left": left, "right": right, "preferred": preferred, "clarity": clarity,
                "distraction": {left: 2.0, right: 2.0}}

    def test_dropped_number_is_fidelity_failure_even_if_preferred(self):
        ratings = [self.decoded("p1", "s1", "guided", "naive", "guided")]
        fidelity_rows = [{"source_id": "s1", "condition": "guided", "missing_hard": 1},
                         {"source_id": "s1", "condition": "naive", "missing_hard": 0}]
        summary = re_.summarize(ratings, fidelity_rows)
        self.assertTrue(re_.is_fidelity_failure(fidelity_rows[0]))
        self.assertEqual(summary["fidelity_failure_rate"]["guided"], 1.0)
        self.assertEqual(summary["comparisons"]["guided vs naive"]["win_rate"], 0.0)

    def test_reader_clustered_bootstrap(self):
        ratings = [self.decoded(f"p{i}", f"s{i}", "guided", "naive", "guided", reader="a",
                                clarity={"guided": 4.0, "naive": 3.0}) for i in range(4)]
        ratings += [self.decoded("p0", "s0", "guided", "naive", "naive", reader="b",
                                 clarity={"guided": 3.0, "naive": 4.0})]
        summary = re_.summarize(ratings, [])
        comp = summary["comparisons"]["guided vs naive"]
        self.assertAlmostEqual(comp["win_rate"], 4 / 5)
        low, high = comp["win_rate_ci"]
        self.assertLessEqual(low, comp["win_rate"])
        self.assertGreaterEqual(high, comp["win_rate"])

    def test_missing_clarity_in_decoded_rating_is_an_error(self):
        ratings = [self.decoded("p1", "s1", "guided", "original", "guided",
                                clarity={"guided": 4.0})]
        with self.assertRaises(re_.StudyError):
            re_.summarize(ratings, [])

    def test_predeclared_success_checks_pass_with_complete_data(self):
        summary = {"comparisons": {"guided vs naive": {"win_rate_ci": [0.6, 0.8]},
                                   "guided vs original": {"clarity_diff": 0.2}},
                   "fidelity_failure_rate": {"guided": 0.0, "naive": 0.1}}
        self.assertTrue(all(re_.predeclared_success(summary).values()))

    def test_predeclared_success_cannot_pass_on_missing_data(self):
        summary = {"comparisons": {"guided vs naive": {"win_rate_ci": None},
                                   "guided vs original": {"clarity_diff": None}},
                   "fidelity_failure_rate": {"guided": None, "naive": None}}
        checks = re_.predeclared_success(summary)
        self.assertFalse(any(checks.values()))

    def test_summary_with_no_comparisons(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = re_.main([
                "summary",
                "--out-dir", tmp,
                "--format", "json",
            ])
        self.assertEqual(code, 2)

    def test_summary_with_fixture_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            comp_dir = Path(tmp) / "comparisons" / "test01"
            comp_dir.mkdir(parents=True)
            _write(comp_dir / "fidelity.json", json.dumps({
                "rewrite_id": "test01", "source_id": "s01",
                "condition": "guided",
                "missing_hard": 1, "missing_soft": 0,
                "added_hard": 0, "added_soft": 0,
                "removed_by_leverage": 2, "introduced_by_leverage": 0,
                "length_ratio": 0.95, "exit": 1, "compare_complete": True,
            }))
            comp_dir2 = Path(tmp) / "comparisons" / "test02"
            comp_dir2.mkdir(parents=True)
            _write(comp_dir2 / "fidelity.json", json.dumps({
                "rewrite_id": "test02", "source_id": "s02",
                "condition": "naive",
                "missing_hard": 0, "missing_soft": 0,
                "added_hard": 0, "added_soft": 0,
                "removed_by_leverage": 1, "introduced_by_leverage": 1,
                "length_ratio": 0.88, "exit": 0, "compare_complete": True,
            }))
            code = re_.main([
                "summary",
                "--out-dir", tmp,
                "--format", "json",
            ])
        self.assertEqual(code, 0)

    def test_sha_id_is_deterministic(self):
        self.assertEqual(re_.sha_id("a", "b"), re_.sha_id("a", "b"))
        self.assertNotEqual(re_.sha_id("a", "b"), re_.sha_id("a", "c"))


# ======================================================================
# Integration tests (offline file-based CLI)
# ======================================================================

class PrepareAnalyzeTests(unittest.TestCase):
    """Integration tests using the real nobotrs binary and temporary files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rewrite_test_"))
        self.bin = _binary()
        self.source = self.tmp / "original.txt"
        _write(self.source, "The budget gap is $8 million. We need to cut spending.\n")

    def test_prepare_creates_layout(self):
        code = re_.main([
            "--binary", self.bin,
            "prepare", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test01",
        ])
        self.assertEqual(code, 0)
        review_json = self.tmp / "study" / "sources" / "test01" / "review.json"
        prepared_json = self.tmp / "study" / "sources" / "test01" / "prepared.json"
        self.assertTrue(review_json.exists())
        self.assertTrue(prepared_json.exists())
        prepared = json.loads(prepared_json.read_text())
        self.assertEqual(prepared["source_id"], "test01")

    def test_analyze_missing_source_reports_error(self):
        code = re_.main([
            "--binary", self.bin,
            "analyze", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "nonexistent",
            "--condition", "guided",
        ])
        self.assertEqual(code, 2)

    def test_analyze_identical_rewrite_has_no_failures(self):
        re_.main([
            "--binary", self.bin,
            "prepare", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test03",
        ])
        code = re_.main([
            "--binary", self.bin,
            "analyze", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test03",
            "--condition", "original",
            "--rewrite-id", "test03-original",
        ])
        self.assertEqual(code, 0)

    def test_analyze_dropped_number_is_failure(self):
        rewrite = self.tmp / "bad_rewrite.txt"
        _write(rewrite, "The gap is large. We need to cut spending.\n")
        re_.main([
            "--binary", self.bin,
            "prepare", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test04",
        ])
        code = re_.main([
            "--binary", self.bin,
            "analyze", str(rewrite),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test04",
            "--condition", "guided",
            "--rewrite-id", "test04-guided",
        ])
        self.assertEqual(code, 1)

    def test_analyze_added_fact_is_failure(self):
        _write(self.source, "The gap is large.\n")
        rewrite = self.tmp / "bad_rewrite.txt"
        _write(rewrite, "The gap is $8 million.\n")
        re_.main([
            "--binary", self.bin,
            "prepare", str(self.source),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test05",
        ])
        code = re_.main([
            "--binary", self.bin,
            "analyze", str(rewrite),
            "--out-dir", str(self.tmp / "study"),
            "--source-id", "test05",
            "--condition", "guided",
            "--rewrite-id", "test05-guided",
        ])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()