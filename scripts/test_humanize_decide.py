import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import humanize_decide as h


def member(i, label):
    return {"id": str(i), "label": label, "genre": "civic", "source_group": str(i),
            "path": str(i), "sha256": hashlib.sha256(str(i).encode()).hexdigest(),
            "baseline": "clean", "candidate": "flagged" if label == "ai" else "clean"}


class ScoringDecision(unittest.TestCase):
    def test_power_and_noninferiority(self):
        humans = [member(i, "human") for i in range(73)]
        ai = [member(i + 100, "ai") for i in range(75)]
        criteria = h.read(h.CRITERIA)
        check = lambda rows: h.decide(rows, criteria, ["civic"])["decision"]
        self.assertEqual(check(humans + ai), "ship")
        self.assertEqual(check(humans[:-1] + ai), "informational")
        self.assertEqual(check(humans + ai[:2]), "informational")
        self.assertEqual(h.decide(humans+ai, criteria, ["civic", "news"])["decision"], "informational")
        self.assertEqual(check([{**humans[0], "candidate": "flagged"}] + humans[1:] + ai), "informational")

    def test_freeze_and_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(action="freeze", dev=root/"dev.json", manifest=root/"held.json",
                candidate="burstiness-units", baseline=root/"binary", binary=root/"binary",
                config=root/"config", record=root/"record", genres=["civic"])
            args.config.write_text("{}")
            args.baseline.write_bytes(b"unused mock")
            dev = member(1,"human")
            held = member(2,"human")
            args.dev.write_text(json.dumps([dev]))
            args.manifest.write_text(json.dumps([dev]))
            with self.assertRaisesRegex(ValueError,"overlap"):
                h.run(args)
            args.manifest.write_text(json.dumps([held]))
            with patch.object(h, "verdict", return_value="clean"):
                (root / dev["path"]).write_text(dev["path"])
                with self.assertRaisesRegex(ValueError, "did not qualify"):
                    h.run(args)
            with patch.object(h, "decide", side_effect=lambda *_: {"decision": "ship"}), patch.object(h, "verdict", return_value="clean"):
                h.run(args)
                first_record = args.record
                args.record = root / "second-record"
                with self.assertRaises(FileExistsError):
                    h.run(args)
                args.record = first_record
            args.action = "evaluate"
            # A failed first run still consumes the one available access.
            with self.assertRaises(FileNotFoundError):
                h.run(args)
            with self.assertRaisesRegex(ValueError,"not unopened"):
                h.run(args)

    def test_refuse_incomplete_verdict(self):
        with self.assertRaises(ValueError):
            h.decide([{**member(1,"ai"),"candidate":"timeout"}], h.read(h.CRITERIA), ["civic"])
        criteria=copy.deepcopy(h.read(h.CRITERIA))
        criteria["error_budget"]=None
        with self.assertRaises(ValueError):
            h.decide([],criteria,["civic"])


if __name__ == "__main__":
    unittest.main()
