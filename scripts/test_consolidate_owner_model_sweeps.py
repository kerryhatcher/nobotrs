#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from consolidate_owner_model_sweeps import consolidate,MODELS

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))
def backend(model,failed=False):
    return {'backend':model,'family':'Model','outcome':{'status':'failed','details':{'ModelLoadFailed':'synthetic'}}} if failed else {'backend':model,'family':'Model','outcome':{'status':'scored','details':{'model_evidence':{'token_coverage':1,'raw_output':1,'full_coverage_output':2}}}}

class ConsolidationTests(unittest.TestCase):
    def test_preserves_initial_failure_and_records_recovered_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original=root/'original';recovery=root/'recovery';out=root/'out';manifest=root/'manifest.json'
            post={'file':'sample.md','sha256':'input','label':'human','confidence':'high'}
            write(manifest,{'posts':[post]})
            entry={'file':'sample.md','input_sha256':'input','label':'human','confidence':'high'}
            write(original/'run.json',{'documents':[entry],'settings':{'models':list(MODELS)},'backend_status_counts':{},'elapsed_ms':1})
            initial_report={'backends':[backend(m,m=='detectorscope') for m in MODELS], 'settings':{},'complete':False,'warnings':[{'family':'Model','error':'synthetic'}],'incomplete_reasons':['old failure']}
            write(original/'sample/report.json',initial_report)
            write(original/'sample/review.json',{'complete':False,'checks':[],'incomplete_reasons':['old failure']})
            before=(original/'sample/report.json').read_bytes()
            for model in MODELS:
                write(recovery/model/'run.json',{'finished':True,'binary_sha256':model,'elapsed_ms':1})
                write(recovery/model/'sample/entry.json',{'input_sha256':'input'})
                write(recovery/model/'sample/backend.json',backend(model))
            result=consolidate(original,recovery,manifest,out)
            self.assertTrue(result['finished'])
            self.assertEqual(result['origin_counts']['desklib']['original_reused'],1)
            self.assertEqual(result['origin_counts']['detectorscope']['recovery_attempt'],1)
            self.assertEqual((original/'sample/report.json').read_bytes(),before)
            merged=json.loads((out/'sample/report.json').read_text())
            self.assertTrue(merged['complete'])
            self.assertFalse(merged['_recovery']['single_concurrent_run'])
            self.assertEqual(json.loads((out/'sample/review.json').read_text())['incomplete_reasons'],[])
    def test_source_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write(root/'manifest.json',{'posts':[{'file':'sample.md','sha256':'right','label':'human','confidence':'high'}]})
            write(root/'original/run.json',{'documents':[{'file':'sample.md','input_sha256':'wrong','label':'human'}]})
            with self.assertRaises(ValueError):
                consolidate(root/'original',root/'recovery',root/'manifest.json',root/'out')

if __name__=='__main__':
    unittest.main()
