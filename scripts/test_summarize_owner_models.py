#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from summarize_owner_models import summarize

class SummaryTests(unittest.TestCase):
    def fixture(self, root, outcome, complete=True):
        run={'settings':{'models':['desklib','conpara']},'documents':[{'file':'sample.md','label':'human','confidence':'medium'}],
             'planned_documents':2,'finished':False,'binary_sha256':'binary','git_revision':'revision','corpus_manifest_sha256':'manifest','elapsed_ms':10}
        (root/'run.json').write_text(json.dumps(run))
        directory=root/'sample';directory.mkdir()
        (directory/'report.json').write_text(json.dumps({'complete':complete,'backends':[{'backend':'desklib','outcome':outcome}]}))
        (directory/'review.json').write_text(json.dumps({'complete':complete,'hotspots':{'reason':'insufficient context'}}))
    def test_partial_run_and_missing_backend_stay_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.fixture(root,{'status':'scored','details':{'model_evidence':{'token_coverage':1,'windows':[{'status':'scored','insufficient_context':True}]}}})
            result=summarize(root)
            self.assertEqual(result['unprocessed_documents'],1)
            self.assertFalse(result['finished'])
            self.assertEqual(result['backend_status_counts']['conpara']['missing_backend'],1)
            self.assertEqual(result['window_counts']['desklib']['insufficient_context'],1)
            self.assertFalse(result['validated_editorial_utility'])
    def test_partial_model_and_document_are_not_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.fixture(root,{'status':'incomplete','details':{'score':{'model_evidence':{'token_coverage':0.5,'windows':[{'status':'timed_out','insufficient_context':False}]}}}},False)
            result=summarize(root)
            self.assertEqual(result['incomplete_documents'],['sample.md'])
            self.assertEqual(result['backend_status_counts']['desklib']['incomplete'],1)
            self.assertEqual(len(result['incomplete_or_failed']),2)

    def test_consolidated_missing_sources_are_not_counted_as_real_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.fixture(root,{'status':'failed','details':{'ModelLoadFailed':'no completed attempt available'}},False)
            run=json.loads((root/'run.json').read_text())
            run['documents'][0]['backends']={'desklib':'missing','conpara':'missing'}
            run['documents'][0]['attempted']=False
            (root/'run.json').write_text(json.dumps(run))
            result=summarize(root)
            self.assertEqual(result['backend_status_counts']['desklib']['missing'],1)
            self.assertEqual(result['backend_status_counts']['desklib']['failed'],0)
            self.assertEqual(result['processed_documents'],0)

if __name__=='__main__':
    unittest.main()
