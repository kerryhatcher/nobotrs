#!/usr/bin/env python3
"""Standard-library regressions for the local corpus registry (Plan 5, Task 1)."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpora  # noqa: E402
from corpora import (  # noqa: E402
    ChecksumMismatch,
    CorpusError,
    Sample,
    beemo_samples,
    apt_samples,
    gao_samples,
    iter_samples,
    leaked,
    load_registry,
    owner_label,
    primary,
    verify_corpus,
    wi_locness_samples,
)

ROOT = corpora.ROOT
REAL_INTERNAL = corpora.DEFAULT_INTERNAL_DIR


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_internal(base: Path, files: dict[str, bytes]) -> Path:
    """Build a fake internal dir: test-artifacts/<rel> plus a SHA256SUMS for those files."""
    artifacts = base / "test-artifacts"
    lines = []
    for rel, data in files.items():
        target = artifacts / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        lines.append(f"{_sha(data)}  {rel}")
    (artifacts / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return base


def stub_entry(corpus_id: str, root_dir: str) -> dict:
    return {"id": corpus_id, "owner": False, "root": f"test-artifacts/{root_dir}",
            "checksums": "test-artifacts/SHA256SUMS", "licence": "stub", "labels": ["human"],
            "group_key": "stub", "use": "stub"}


class OwnerLabelTests(unittest.TestCase):
    def test_owner_label_rule(self):
        self.assertEqual(owner_label("2025-03-10-using-rust-to-make-python-more-manageable-2.md"),
                         "ai_drafted")
        self.assertEqual(owner_label("2025-03-07-crossover-2025.md"), "ai_drafted")
        self.assertEqual(owner_label("2025-03-07-better-python-logging.md"), "human")
        self.assertEqual(owner_label("2025-03-09-something-else.md"), "human")
        self.assertEqual(owner_label("2011-05-03-ssh-to-aws-quick-and-dirty.md"), "human")

    def test_owner_label_rejects_undated_names(self):
        with self.assertRaises(CorpusError):
            owner_label("notes.md")

    def test_manifest_totals_and_primary_exclude_medium(self):
        manifest = corpora.load_owner_manifest()
        labels = [p["label"] for p in manifest["posts"]]
        self.assertEqual(labels.count("ai_drafted"), 28)
        self.assertEqual(labels.count("human"), 15)
        medium = [p for p in manifest["posts"] if p["confidence"] == "medium"]
        self.assertEqual([p["file"] for p in medium], ["2025-03-07-better-python-logging.md"])
        self.assertIn("provenance_note", medium[0])

        samples = [Sample("owner-posts-v1", p["file"], p["file"], p["label"], p["genre"],
                          p["date"], "", True, p["confidence"]) for p in manifest["posts"]]
        kept = primary(samples)
        self.assertEqual(sum(s.label == "ai_drafted" for s in kept), 28)
        self.assertEqual(sum(s.label == "human" for s in kept), 14)

    def test_manifest_label_must_follow_rule(self):
        manifest = corpora.load_owner_manifest()
        tampered = json.loads(json.dumps(manifest))
        tampered["posts"][0]["label"] = "ai_drafted" if tampered["posts"][0]["label"] == "human" \
            else "human"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(CorpusError):
                corpora.load_owner_manifest(path)


class ChecksumTests(unittest.TestCase):
    def test_checksum_mismatch_stops_and_names_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"beemo/data/a.bin": b"alpha", "beemo/b.txt": b"bravo"})
            entry = stub_entry("beemo", "beemo")
            self.assertEqual(verify_corpus(entry, base), ["beemo/b.txt", "beemo/data/a.bin"])
            (base / "test-artifacts/beemo/b.txt").write_bytes(b"bravo!")  # one byte changed
            with self.assertRaises(ChecksumMismatch) as ctx:
                verify_corpus(entry, base)
            self.assertIn("beemo/b.txt", str(ctx.exception))

    def test_missing_file_is_a_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"beemo/x.txt": b"x"})
            (base / "test-artifacts/beemo/x.txt").unlink()
            with self.assertRaises(ChecksumMismatch):
                verify_corpus(stub_entry("beemo", "beemo"), base)

    def test_iter_samples_verifies_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"gao/reports/GAO-1.txt": b"Report body."})
            (base / "test-artifacts/gao/reports/GAO-1.txt").write_bytes(b"Report bodY.")
            registry = {"govinfo-gao-2008": stub_entry("govinfo-gao-2008", "gao")}
            with self.assertRaises(ChecksumMismatch):
                list(iter_samples("govinfo-gao-2008", base, registry))

    def test_real_corpora_match_checksums(self):
        if not REAL_INTERNAL.is_dir():
            self.skipTest("internal corpus directory not present")
        registry = load_registry()
        for cid, entry in registry.items():
            if entry.get("owner"):
                continue
            with self.subTest(corpus=cid):
                self.assertTrue(verify_corpus(entry, REAL_INTERNAL))


class RegistryTests(unittest.TestCase):
    def test_registry_entries_have_licence_and_use(self):
        registry = load_registry()
        self.assertEqual(
            set(registry),
            {"owner-posts-v1", "beemo", "apt-eval", "coauthor", "govinfo-gao-2008", "wi-locness"})
        for cid, entry in registry.items():
            with self.subTest(corpus=cid):
                self.assertTrue(entry["licence"].strip())
                self.assertTrue(entry["use"].strip())
                self.assertTrue(entry["labels"])
                self.assertTrue(entry["group_key"].strip())
                self.assertTrue(entry["root"].startswith("test-artifacts/"))
                self.assertEqual(entry["checksums"], "test-artifacts/SHA256SUMS")

    def test_non_owner_corpora_exclude_owner(self):
        registry = load_registry()
        self.assertNotIn("owner-posts-v1", corpora.non_owner_corpora(registry))
        self.assertIn("beemo", corpora.non_owner_corpora(registry))

    def test_coauthor_reader_reconstructs_sessions_from_zip(self):
        import io, json as _json, zipfile
        def events(doc, *ops_list):
            out = [{"eventName": "system-initialize", "currentDoc": doc, "textDelta": ""}]
            for ops in ops_list:
                out.append({"eventName": "text-insert", "textDelta": {"ops": ops}})
            return out
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("coauthor-v1.0/s1.jsonl", "\n".join(_json.dumps(e) for e in events(
                "Hello world", [{"retain": 5}, {"insert": ","}])) + "\n")
            zf.writestr("coauthor-v1.0/s2.jsonl", "\n".join(_json.dumps(e) for e in events(
                "Budget", [{"retain": 6}, {"insert": " passed"}])) + "\n")
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"coauthor/chi2022-coauthor-v1.0.zip": buf.getvalue()})
            registry = {"coauthor": stub_entry("coauthor", "coauthor")}
            samples = {s.id: s.text for s in iter_samples("coauthor", base, registry)}
        self.assertEqual(samples, {"s1": "Hello, world", "s2": "Budget passed"})

    def test_apply_delta_retain_insert_delete(self):
        self.assertEqual(corpora.apply_delta("Hello world", [{"retain": 5}, {"insert": ","},
                                                             {"delete": 6}]), "Hello,")
        self.assertEqual(corpora.apply_delta("abc", [{"retain": 1}, {"delete": 1}]), "ac")

    def test_reconstruct_session_counts_events(self):
        events = [{"eventName": "system-initialize", "currentDoc": "x"},
                  {"eventName": "text-insert", "textDelta": {"ops": [{"retain": 1}, {"insert": "y"}]}},
                  {"eventName": "suggestion-accept", "textDelta": ""}]
        text, counts = corpora.reconstruct_session(events)
        self.assertEqual(text, "xy")
        self.assertEqual(counts["text-insert"], 1)

class BeemoTests(unittest.TestCase):
    def test_beemo_groups_by_prompt_id(self):
        rows = []
        for prompt in ("p1", "p2"):
            for variant in range(3):
                rows.append({"prompt_id": prompt, "model_output": f"{prompt} model {variant}",
                             "human_output": f"{prompt} human {variant}",
                             "human_edits": f"{prompt} edits {variant}"})
        samples = list(beemo_samples(rows))
        self.assertEqual(len(samples), 18)
        by_group: dict[str, set[str]] = {}
        for s in samples:
            by_group.setdefault(s.group, set()).add(s.label)
        self.assertEqual(set(by_group), {"p1", "p2"})
        self.assertEqual(by_group["p1"], {"human", "ai", "ai_edited_by_human"})
        labels = {s.label for s in samples}
        self.assertEqual(labels, {"human", "ai", "ai_edited_by_human"})

    def test_beemo_reader_uses_pyarrow_rows_and_checksums(self):
        rows = [{"prompt_id": "p" + str(i), "model_output": "m", "human_output": "h",
                 "human_edits": ""} for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {
                "beemo/data/train-00000-of-00001.parquet": b"PAR1stub"})
            registry = {"beemo": stub_entry("beemo", "beemo")}
            with mock.patch.object(corpora, "_parquet_rows", return_value=rows) as reader:
                samples = list(iter_samples("beemo", base, registry))
            reader.assert_called_once()
            self.assertEqual(len(samples), 12)  # empty human_edits skipped

    def test_missing_pyarrow_gives_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {
                "beemo/data/train-00000-of-00001.parquet": b"PAR1stub"})
            registry = {"beemo": stub_entry("beemo", "beemo")}
            with mock.patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
                with self.assertRaises(CorpusError) as ctx:
                    list(iter_samples("beemo", base, registry))
            self.assertIn("pyarrow", str(ctx.exception))


class AptTests(unittest.TestCase):
    def test_polished_variants_link_to_best_original(self):
        originals = [
            {"id": "1", "generation": "The council voted to delay the budget vote until March. "
                                      "Residents packed the room and asked hard questions about pay.",
             "domain": "news"},
            {"id": "2", "generation": "My garden grew tomatoes, peppers and a surprising "
                                      "number of zucchini this summer, which nobody expected at all.",
             "domain": "blog"},
        ]
        polished = [
            {"id": "10", "generation": "The council voted to delay the budget vote until March, "
                                       "and residents packed the room to ask hard questions about pay.",
             "domain": "news"},
            {"id": "11", "generation": "This summer my garden produced tomatoes, peppers and a "
                                       "surprising number of zucchini, which nobody expected.",
             "domain": "blog"},
        ]
        samples = list(apt_samples(originals, polished))
        polished_groups = {s.id: s.group for s in samples if s.label == "ai_polished"}
        self.assertEqual(polished_groups["polished-10"], "1")
        self.assertEqual(polished_groups["polished-11"], "2")
        self.assertEqual(sum(s.label == "human" for s in samples), 2)

    def test_unrelated_polished_variant_stays_a_singleton(self):
        originals = [{"id": "1", "generation": "alpha beta gamma delta epsilon zeta eta theta.",
                      "domain": "news"}]
        polished = [{"id": "9", "generation": "completely unrelated words appear in this sentence "
                                              "about different things entirely here now.",
                     "domain": "news"}]
        samples = list(apt_samples(originals, polished))
        self.assertEqual([s.group for s in samples if s.label == "ai_polished"], ["unlinked-9"])


class WiLocnessTests(unittest.TestCase):
    def test_splits_of_one_band_do_not_collide(self):
        lines = {"wi+locness/json/A.dev.json": [json.dumps({"cefr": "A", "text": "dev essay."})],
                 "wi+locness/json/A.train.json": [json.dumps({"cefr": "A", "text": "train essay."})]}
        samples = list(wi_locness_samples(lines))
        self.assertEqual(len({s.id for s in samples}), 2)
        self.assertEqual(len({s.group for s in samples}), 2)

    def test_bands_and_native_are_separated(self):
        lines = {
            "wi+locness/json/A.dev.json": [json.dumps({"cefr": "A", "text": "learner text one."})],
            "wi+locness/json/N.dev.json": [json.dumps({"cefr": "N", "text": "native text."}),
                                          json.dumps({"cefr": "N", "text": "native two."})],
        }
        samples = list(wi_locness_samples(lines))
        genres = [s.genre for s in samples]
        self.assertEqual(genres, ["learner", "native", "native"])
        self.assertEqual(len({s.group for s in samples}), 3)


class GaoTests(unittest.TestCase):
    def test_each_report_is_one_civic_human_document(self):
        samples = list(gao_samples({"GAOREPORTS-GAO-08-1.txt": "body one",
                                    "GAOREPORTS-GAO-08-2.txt": "body two"}))
        self.assertEqual([s.group for s in samples], ["GAOREPORTS-GAO-08-1", "GAOREPORTS-GAO-08-2"])
        self.assertTrue(all(s.label == "human" and s.genre == "civic" for s in samples))


class GuardTests(unittest.TestCase):
    def test_guard_ignores_owner_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "post.md"
            f.write_text("text", encoding="utf-8")
            with self.assertRaises(CorpusError):
                leaked([f], ["owner-posts-v1"], internal=Path(tmp))

    def test_owner_text_never_matches_guard_sources(self):
        # Owner text is excluded from the guard's sources by construction.
        self.assertNotIn("owner-posts-v1", corpora.non_owner_corpora(load_registry()))

    def test_leaked_flags_fifteen_word_excerpt(self):
        excerpt = ("After consolidating schools, freezing pay, packing classes, and contracting "
                   "out custodial work, the district still faces a shortfall of about eight")
        beemo_text = "Lead in. " + excerpt + " million dollars next year."
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"beemo/data/train-00000-of-00001.parquet": b"PAR1"})
            registry = {"beemo": stub_entry("beemo", "beemo")}
            rows = [{"prompt_id": "p", "model_output": "", "human_output": beemo_text,
                     "human_edits": ""}]
            leak = Path(tmp) / "draft.md"
            leak.write_text("Draft intro. " + excerpt + " million dollars.", encoding="utf-8")
            clean = Path(tmp) / "clean.md"
            clean.write_text("Counts only: 3 documents, rate 0.25.", encoding="utf-8")
            with mock.patch.object(corpora, "_parquet_rows", return_value=rows):
                hits = leaked([leak, clean], ["beemo"], internal=base, registry=registry)
            self.assertEqual({h[0].name for h in hits}, {"draft.md"})
            self.assertEqual(hits[0][1], "beemo")
            self.assertEqual(len(hits[0][2]), 12)  # hashed sample id, not the text

    def test_leaked_clean_file_has_no_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_internal(Path(tmp), {"beemo/data/train-00000-of-00001.parquet": b"PAR1"})
            registry = {"beemo": stub_entry("beemo", "beemo")}
            rows = [{"prompt_id": "p", "model_output": "", "human_output": "Completely different "
                     "prose with no shared run at all in this short stub passage.",
                     "human_edits": ""}]
            clean = Path(tmp) / "clean.md"
            clean.write_text("Counts only: 3 documents, rate 0.25.", encoding="utf-8")
            with mock.patch.object(corpora, "_parquet_rows", return_value=rows):
                self.assertEqual(leaked([clean], ["beemo"], internal=base, registry=registry), [])


if __name__ == "__main__":
    unittest.main()
