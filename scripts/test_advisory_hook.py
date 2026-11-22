import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from io import BytesIO

spec = importlib.util.spec_from_file_location("hook", Path(__file__).with_name("advisory-hook.py"))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class HookTests(unittest.TestCase):
    def test_nudge_uses_actual_review_schema(self):
        hit = dict(rule_id="r", leverage=2, suppressed=False, location={"line": 12}, fix="Split these clauses.")
        report = dict(complete=True, findings=[hit], document=[{**hit,"location":None}])
        lines = hook.feedback(report)
        self.assertIn("2 high-leverage", lines[0])
        self.assertIn("line 12", lines[1])
        self.assertNotIn("line", lines[2])
        self.assertLessEqual(len(hook.feedback({**report,"findings":[hit]*30})), 6)

    def test_suppressed_low_priority_and_incomplete(self):
        hit = dict(rule_id="r", leverage=5, severity="high", suppressed=False)
        self.assertEqual(hook.feedback(dict(complete=True,findings=[hit,{**hit,"leverage":1,"suppressed":True}])), [])
        for malformed in (None, [], {"findings":{}}, {"complete":False,"findings":[hit]}):
            self.assertEqual(hook.feedback(malformed), [])

    def test_host_status(self):
        for action, expected in [(FileNotFoundError(),0),(subprocess.TimeoutExpired("nobotrs",10),0),
                                 (subprocess.CompletedProcess([],2,b"",b"error"),0),
                                 (subprocess.CompletedProcess([],0,b"invalid",b""),0),
                                 (subprocess.CompletedProcess([],0,json.dumps({"complete":True,"findings":[
                                     {"leverage":2,"suppressed":False}]}).encode(),b""),2)]:
            with patch.object(hook.sys,"stdin") as stdin, patch.object(hook.subprocess,"run") as run:
                stdin.buffer = BytesIO(b"Sample.")
                if isinstance(action, Exception):
                    run.side_effect=action
                else:
                    run.return_value=action
                self.assertEqual(hook.main(), expected)
                self.assertIn("--markdown",run.call_args.args[0])


if __name__=="__main__":
    unittest.main()
