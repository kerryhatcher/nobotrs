#!/usr/bin/env python3
import os
from pathlib import Path
import tempfile
import unittest
from run_owner_model_sweeps import memory, processes, atomic

class ResourceTests(unittest.TestCase):
    def test_current_process_memory_is_measured_without_model_loading(self):
        available,swap=memory()
        self.assertGreater(available,0)
        self.assertGreaterEqual(swap,0)
        observed=processes(os.getpid())
        own=observed[str(os.getpid())]
        self.assertGreater(own['rss_kib'],0)
        self.assertGreaterEqual(own['hwm_kib'],own['rss_kib'])
    def test_checkpoint_replacement_is_complete_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'monitor.json'
            atomic(path,{'status':'running'})
            atomic(path,{'status':'incomplete','peak_group_rss_kib':42})
            import json
            self.assertEqual(json.loads(path.read_text())['status'],'incomplete')
            self.assertFalse(path.with_suffix('.json.tmp').exists())

if __name__=='__main__':
    unittest.main()
