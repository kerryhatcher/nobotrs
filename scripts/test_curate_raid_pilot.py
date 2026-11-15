#!/usr/bin/env python3
"""Standard-library regressions for the limited RAID pilot curator."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import curate_raid_pilot as curator  # noqa: E402
from evaluation_protocol import (  # noqa: E402
    sha256_bytes,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = curator.PINNED_DATASET
REVISION = curator.PINNED_REVISION
FORCED = list(curator.FORCED_SOURCE_IDS)
OTHER = [
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
    "77777777-7777-4777-8777-777777777777",
    "88888888-8888-4888-8888-888888888888",
    "99999999-9999-4999-8999-999999999999",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    "ffffffff-ffff-4fff-8fff-ffffffffffff",
    "abababab-abab-4bab-8bab-abababababab",
]
TEXTS = [
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "omicron pi rho sigma tau upsilon phi chi psi omega one two three",
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "omicron pi rho sigma tau upsilon phi chi psi omega one two four",
    "red orange yellow green blue indigo violet black white gray brown pink "
    "silver gold copper bronze iron steel glass wood stone sand clay water fire",
    "quiet river stone bridge willow bank reeds current ripple foam shallow deep "
    "cold clear slow fast silver green blue gray wind rain cloud sun moon star",
    "market street corner bakery coffee bread morning newspaper bicycle window "
    "delivery neighbor sidewalk crossing signal bus train station ticket clock",
    "poem line verse stanza meter rhythm image metaphor sound silence echo breath "
    "light shadow river memory winter spring summer autumn evening morning",
    "harbor boat sail rope anchor tide current wind salt gull dock pier lighthouse "
    "fog horn bell net crate rope ladder cabin deck stern bow wake",
    "code function value return argument module package import export build test "
    "compile runtime memory buffer stream file path directory source binary",
    "table row column header cell format parse render output input schema field "
    "record query index cache store load save delete update create validate",
    "winter frost snow ice wind coat glove scarf boot sled hill valley forest "
    "branch pine birch trail cabin fire warm quiet cold bright pale",
    "signal tower antenna cable router packet network address socket request "
    "response header body status error timeout retry backoff server client",
    "garden soil seed root stem leaf flower petal pollen fruit harvest basket "
    "watering sunlight shade fence gate path bench quiet green warm",
    "unique-marker-ZZZSECRET alpha beta gamma delta epsilon zeta eta theta iota "
    "kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega",
]


def uuid_for(index):
    return f"{index:08x}-0000-4000-8000-{index:012x}"


def row(row_id, source_id, text, *, model=None, domain=None, attack=None,
        truncated=None, include_source=True):
    value = {
        "id": row_id,
        "adv_source_id": row_id,
        "source_id": source_id,
        "model": model,
        "decoding": "greedy",
        "repetition_penalty": "no",
        "attack": attack,
        "domain": domain,
        "title": "metadata title",
        "prompt": None,
        "generation": text,
    }
    if not include_source:
        del value["source_id"]
    item = {"row_idx": 1, "row": value, "truncated_cells": []}
    if truncated is not None:
        item["truncated_cells"] = truncated
    return item


class PilotFixture:
    """Build a tiny synthetic response cache with the real pinned identities."""

    def __init__(self, root: Path):
        self.root = root
        self.cache = root / "cache"
        self.cache.mkdir()
        self.queries = []
        self.row_counter = 0

    def add_query(self, domain, model, attack, upstream_split, rows):
        self.row_counter += 1
        name = f"{domain}-{model}-{attack}.json"
        payload = {"features": [], "rows": rows}
        data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        (self.cache / name).write_bytes(data)
        self.queries.append({
            "domain": domain,
            "model": model,
            "upstream_split": upstream_split,
            "revision": REVISION,
            "url": f"https://example.invalid/query/{name}",
            "file": str(self.cache / name),
            "sha256": sha256_bytes(data),
            "rows": len(rows),
            "available": len(rows) + 10,
            "partial_view": True,
            "attack": attack,
        })

    def finalize(self, errors=None):
        acquisition = {
            "dataset": DATASET,
            "revision": REVISION,
            "upstream_license": "MIT (dataset card declaration)",
            "license_url": f"https://example.invalid/{REVISION}/README.md",
            "retrieved": "2026-11-14",
            "retrieved_timezone": "America/New_York",
            "queries": self.queries,
            "errors": errors or [],
            "notes": "Synthetic pilot fixture; no upstream text is copied.",
        }
        (self.cache / "acquisition.json").write_text(
            json.dumps(acquisition, indent=2) + "\n", encoding="utf-8"
        )
        (self.cache / "dataset-card.md").write_text(
            "---\nlicense: mit\n---\nSynthetic card fixture.\n", encoding="utf-8"
        )
        (self.cache / "LICENSE").write_text(
            "MIT License\n\nCopyright (c) 2024- Liam Dugan\n\n"
            "Permission is hereby granted, free of charge.\n",
            encoding="utf-8",
        )
        return self.cache


def make_fixture(root: Path) -> Path:
    fixture = PilotFixture(root)
    # Forced source plus a near-duplicate from another source: the union must
    # keep both source members in development.
    fixture.add_query("abstracts", "human", "none", "train", [
        row(uuid_for(1), FORCED[0], TEXTS[0], model="human",
            domain="abstracts", attack="none"),
        row(uuid_for(2), OTHER[0], TEXTS[1], model="human",
            domain="abstracts", attack="none"),
    ])
    fixture.add_query("abstracts", "gpt4", "paraphrase", "train", [
        row(uuid_for(3), FORCED[1], TEXTS[2], model="gpt4",
            domain="abstracts", attack="paraphrase"),
        row(uuid_for(4), OTHER[1], TEXTS[3], model="gpt4",
            domain="abstracts", attack="paraphrase"),
    ])
    # Exact normalized duplicate across two sources.
    fixture.add_query("books", "gpt4", "none", "train", [
        row(uuid_for(5), FORCED[2], TEXTS[4], model="gpt4",
            domain="books", attack="none"),
        row(uuid_for(6), OTHER[2], "Market, street; corner bakery coffee bread "
            "morning newspaper bicycle window delivery neighbor sidewalk crossing "
            "signal bus train station ticket clock.", model="gpt4",
            domain="books", attack="none"),
        row(uuid_for(7), OTHER[3], TEXTS[6], model="gpt4",
            domain="books", attack="none"),
    ])
    fixture.add_query("news", "mistral-chat", "none", "train", [
        row(uuid_for(8), FORCED[3], TEXTS[7], model="mistral-chat",
            domain="news", attack="none"),
        row(uuid_for(9), OTHER[4], TEXTS[8], model="mistral-chat",
            domain="news", attack="none"),
    ])
    fixture.add_query("poetry", "human", "none", "train", [
        row(uuid_for(10), FORCED[4], TEXTS[9], model="human",
            domain="poetry", attack="none"),
        row(uuid_for(11), FORCED[5], TEXTS[10], model="human",
            domain="poetry", attack="none"),
    ])
    fixture.add_query("czech", "chatgpt", "none", "extra", [
        row(uuid_for(12), OTHER[5], TEXTS[11], model="chatgpt",
            domain="czech", attack="none"),
        row(uuid_for(13), OTHER[6], TEXTS[12], model="chatgpt",
            domain="czech", attack="none"),
    ])
    fixture.add_query("german", "gpt4", "none", "extra", [
        row(uuid_for(14), OTHER[7], "german text alpha beta gamma delta epsilon "
            "zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau",
            model="gpt4", domain="german", attack="none"),
        row(uuid_for(15), OTHER[8], "german text one two three four five six "
            "seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen",
            model="gpt4", domain="german", attack="none"),
    ])
    # Rejected rows are recorded, not silently discarded.
    fixture.add_query("abstracts", "gpt4", "none", "train", [
        row(uuid_for(16), OTHER[9], TEXTS[0], model="gpt4",
            domain="abstracts", attack="none"),
        row(uuid_for(17), OTHER[10], "", model="gpt4",
            domain="abstracts", attack="none"),
        row(uuid_for(18), OTHER[11], TEXTS[1], model="gpt4",
            domain="abstracts", attack="none", include_source=False),
        row(uuid_for(16), OTHER[12], TEXTS[2], model="gpt4",
            domain="abstracts", attack="none"),
        row(uuid_for(19), OTHER[13], TEXTS[3], model="mystery",
            domain="abstracts", attack="none"),
        row(uuid_for(20), OTHER[14], TEXTS[4], model="gpt4",
            domain="abstracts", attack="none", truncated=["generation"]),
        row(uuid_for(21), OTHER[15], TEXTS[5], model="gpt4",
            domain="books", attack="none"),
    ])
    return fixture.finalize(errors=[{"job": ["code", "human"],
                                     "error": "synthetic timeout"}])


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = make_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def curate(self, name="corpus", cache=None):
        out = self.root / name
        summary = curator.write_corpus(out, cache or self.cache, "2026-11-14")
        return out, summary

    def load(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_rejections_are_recorded_without_text(self):
        out, summary = self.curate()
        audit = self.load(out / "curation.json")
        reasons = audit["row_accounting"]["rejected_by_reason"]
        for reason in ("empty_generation", "missing_fields", "duplicate_upstream_id",
                       "unsupported_model", "truncated_cells", "query_domain_mismatch"):
            self.assertIn(reason, reasons)
        self.assertEqual(audit["row_accounting"]["rows_seen"], 22)
        self.assertEqual(audit["row_accounting"]["accepted"], 16)
        self.assertEqual(audit["row_accounting"]["rejected"], 6)
        self.assertNotIn("ZZZSECRET", json.dumps(audit))
        self.assertNotIn("ZZZSECRET", json.dumps(summary))
        self.assertNotIn("ZZZSECRET", (out / "manifest.json").read_text())

    def test_source_and_near_duplicate_union_precedes_splits(self):
        out, _ = self.curate()
        manifest = self.load(out / "manifest.json")
        audit = self.load(out / "curation.json")
        by_source = {}
        for sample in manifest["samples"]:
            by_source.setdefault(sample["source_id"], set()).add(sample["split"])
        for source_id in FORCED:
            self.assertEqual(by_source[source_id], {"development"})
        # The forced source and its near duplicate share one component.
        forced = [sample for sample in manifest["samples"]
                  if sample["source_id"] == FORCED[0]][0]
        near = [sample for sample in manifest["samples"]
                if sample["source_id"] == OTHER[0]][0]
        self.assertEqual(forced["source_group"], near["source_group"])
        self.assertEqual(forced["near_duplicate_group"], near["near_duplicate_group"])
        self.assertEqual(forced["split"], "development")
        self.assertEqual(near["split"], "development")
        # The exact normalized duplicate is also one component, in one split.
        exact = [sample for sample in manifest["samples"]
                 if sample["source_id"] in (FORCED[2], OTHER[2])]
        self.assertEqual(len(exact), 2)
        self.assertEqual(len({sample["source_group"] for sample in exact}), 1)
        self.assertEqual(len({sample["split"] for sample in exact}), 1)
        self.assertGreater(
            audit["grouping"]["components_with_multiple_source_ids"], 0
        )
        self.assertGreater(len(audit["grouping"]["near_duplicate_links"]), 0)
        self.assertGreater(len(audit["grouping"]["exact_normalized_duplicate_links"]), 0)
        for source_group in {
            sample["source_group"] for sample in manifest["samples"]
        }:
            splits = {
                sample["split"] for sample in manifest["samples"]
                if sample["source_group"] == source_group
            }
            self.assertEqual(len(splits), 1)

    def test_splits_are_deterministic_and_hash_ordered(self):
        first, first_summary = self.curate("first")
        second, second_summary = self.curate("second")
        self.assertEqual(
            (first / "manifest.json").read_bytes(),
            (second / "manifest.json").read_bytes(),
        )
        self.assertEqual(
            (first / "curation.json").read_bytes(),
            (second / "curation.json").read_bytes(),
        )
        self.assertEqual(first_summary["corpus_content_sha256"],
                         second_summary["corpus_content_sha256"])
        manifest = self.load(first / "manifest.json")
        self.assertEqual(manifest["split_policy"]["seed"], curator.SEED)
        self.assertEqual(set(first_summary["splits"]),
                         {"development", "validation", "independent-test"})

    def test_labels_and_dimensions_are_preserved(self):
        out, _ = self.curate()
        manifest = self.load(out / "manifest.json")
        labels = {sample["model"]: sample["label"] for sample in manifest["samples"]}
        self.assertEqual(labels["human"], "human")
        self.assertEqual(labels["gpt4"], "generated")
        self.assertEqual(labels["mistral-chat"], "generated")
        self.assertIn("dimensions", manifest)
        self.assertFalse(manifest["language_policy"]["per_sample_overrides"])
        for sample in manifest["samples"]:
            self.assertTrue(sample["content_sha256"])
            self.assertTrue(sample["source_id"])
            self.assertTrue(sample["near_duplicate_group"])
            self.assertIn(sample["dimension_values"]["language_hint"],
                          {"czech-domain", "german-domain", "unknown"})
            self.assertNotIn("native", json.dumps(sample).lower())

    def test_source_snapshot_is_copied_and_hashes_match(self):
        out, _ = self.curate()
        manifest = self.load(out / "manifest.json")
        provenance = self.load(out / "source" / "PROVENANCE.json")
        self.assertEqual(sha256_file(out / "source" / "acquisition.json"),
                         provenance["acquisition_sha256"])
        self.assertEqual(manifest["source_snapshot"]["upstream_acquisition_sha256"],
                         provenance["upstream_acquisition_sha256"])
        self.assertEqual(provenance["retrieved"], "2026-11-14")
        self.assertEqual(provenance["retrieved_timezone"], "America/New_York")
        self.assertEqual(provenance["upstream_retrieved"], "2026-11-14")
        self.assertEqual(provenance["upstream_retrieved_timezone"], "America/New_York")
        self.assertFalse(provenance["retrieved_override"])
        self.assertEqual(sha256_file(out / "source" / "LICENSE"),
                         provenance["license_sha256"])
        self.assertEqual(sha256_file(out / "source" / "dataset-card.md"),
                         provenance["dataset_card_sha256"])
        self.assertEqual(len(provenance["queries"]), 8)
        self.assertEqual(manifest["source_snapshot"]["response_count"], 8)
        portable = self.load(out / "source" / "acquisition.json")
        self.assertTrue(portable["portable_snapshot"])
        self.assertNotIn("/tmp/", (out / "source" / "acquisition.json").read_text())
        for item in provenance["queries"]:
            self.assertFalse(Path(item["file"]).is_absolute())
            copied = out / "source" / Path(item["file"])
            self.assertEqual(sha256_file(copied), item["sha256"])

    def test_reproduction_from_copied_source_matches(self):
        out, _ = self.curate("original")
        reproduced, _ = self.curate("reproduced", out / "source")
        self.assertEqual((out / "manifest.json").read_bytes(),
                         (reproduced / "manifest.json").read_bytes())
        self.assertEqual((out / "curation.json").read_bytes(),
                         (reproduced / "curation.json").read_bytes())
        self.assertEqual(sha256_file(out / "summary.json"),
                         sha256_file(reproduced / "summary.json"))

    def test_nonempty_unrelated_output_is_preserved(self):
        out = self.root / "unrelated-experiment"
        out.mkdir()
        marker = out / "do-not-delete.txt"
        marker.write_text("preserve this experiment history\n", encoding="utf-8")
        with self.assertRaises(curator.CurationError):
            curator.prepare_output(out)
        self.assertEqual(marker.read_text(encoding="utf-8"),
                         "preserve this experiment history\n")
        self.assertEqual(sorted(path.name for path in out.iterdir()),
                         ["do-not-delete.txt"])

        # The CLI must refuse before reading/importing inputs and must not delete.
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/curate_raid_pilot.py"),
            "--cache", str(self.cache), "--out", str(out),
        ], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not empty", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"),
                         "preserve this experiment history\n")

        empty = self.root / "empty-output"
        empty.mkdir()
        curator.prepare_output(empty)
        self.assertEqual(list(empty.iterdir()), [])

    def test_tampered_response_is_rejected(self):
        path = next((self.cache).glob("abstracts-human-none.json"))
        path.write_bytes(path.read_bytes() + b" ")
        out = self.root / "tampered"
        with self.assertRaises(curator.CurationError) as raised:
            curator.write_corpus(out, self.cache, "2026-11-14")
        self.assertIn("hash mismatch", str(raised.exception))

    def test_preflight_does_not_open_independent_text_and_dimensions_report(self):
        out, _ = self.curate()
        config = self.root / "config.json"
        config.write_text('{"quorum": 2}\n', encoding="utf-8")
        criteria = self.root / "criteria.json"
        criteria.write_text(
            '{"criteria_id": "pilot-v1", "criteria_version": "1"}\n',
            encoding="utf-8",
        )
        binary = self.root / "fake-binary"
        binary.write_text("not executed by preflight\n", encoding="utf-8")
        preflight = self.root / "preflight.json"
        command = [
            sys.executable, str(ROOT / "scripts/raid_pilot_preflight.py"),
            "--corpus", str(out), "--config", str(config),
            "--release-criteria", str(criteria), "--binary", str(binary),
            "--output", str(preflight),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.load(preflight)
        self.assertEqual(report["status"], "preflight-passed")
        self.assertEqual(report["independent_access"]["status"], "not-claimed")
        self.assertFalse(report["content_verification"]["independent_held_out_verified"])
        self.assertTrue(report["content_verification"]["held_out_not_read"])
        self.assertTrue(report["forced_sources"]["all_development"])
        self.assertEqual(report["language"]["runtime_default"], "unknown")

        # A development run must not read the independent files; delete them
        # and use a fake detector to prove the runner only consumes readable data.
        manifest = self.load(out / "manifest.json")
        independent = [sample for sample in manifest["samples"]
                       if sample["split"] == "independent-test"]
        self.assertTrue(independent)
        for sample in independent:
            (out / sample["file"]).unlink()
        detector = self.root / "fake-detector"
        detector.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "sys.stdin.buffer.read()\n"
            "print(json.dumps({'schema_version':'1.0.0','engine_version':'fake-0.1',"
            "'dictionary_version':'fake-dict','metric_contract':'fake-v1',"
            "'verdict':'clean','complete':True,'families':[],'backends':[],'settings':{'quorum':2}}))\n",
            encoding="utf-8",
        )
        detector.chmod(0o755)
        results = self.root / "results.json"
        run = subprocess.run([
            sys.executable, str(ROOT / "scripts/evaluate.py"),
            "--binary", str(detector), "--manifest", str(out / "manifest.json"),
            "--output", str(results), "--split", "development",
            "--config", str(config), "--release-criteria", str(criteria),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = self.load(results)
        self.assertEqual(set(report["dimension_metrics"]), set(curator.DIMENSIONS))
        self.assertIn("domain", report["dimension_metrics"])
        self.assertTrue(report["dimension_metrics"]["domain"])
        self.assertEqual(
            set(report["content_verification"]["held_out_not_read"]),
            {sample["id"] for sample in independent},
        )
        self.assertNotIn("ZZZSECRET", results.read_text())

    def test_freeze_writes_unopened_record_without_claiming(self):
        out, _ = self.curate()
        config = self.root / "config.json"
        config.write_text('{"quorum": 2}\n', encoding="utf-8")
        criteria = self.root / "criteria.json"
        criteria.write_text(
            '{"criteria_id": "pilot-v1", "criteria_version": "1"}\n',
            encoding="utf-8",
        )
        binary = self.root / "fake-binary"
        binary.write_text("frozen binary identity\n", encoding="utf-8")
        preflight = self.root / "preflight.json"
        record = self.root / "access.json"
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/raid_pilot_preflight.py"),
            "--corpus", str(out), "--config", str(config),
            "--release-criteria", str(criteria), "--binary", str(binary),
            "--output", str(preflight), "--access-record-out", str(record),
            "--freeze",
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = self.load(record)
        self.assertEqual(value["status"], "frozen-unopened")
        self.assertNotIn("access_id", value)
        self.assertFalse(record.with_name(record.name + ".lock").exists())
        report = self.load(preflight)
        self.assertTrue(report["independent_access"]["access_record_written"])
        self.assertEqual(report["independent_access"]["status"], "not-claimed")


if __name__ == "__main__":
    unittest.main()
