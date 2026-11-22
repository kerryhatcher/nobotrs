#!/usr/bin/env python3
import unittest
from types import SimpleNamespace
from survey_detectorscope_features import rates, survey

class SurveyTests(unittest.TestCase):
    def test_lift_math_and_unique_sample_presence(self):
        result = rates([{'label':'ai','features':[1,1]}, {'label':'ai','features':[1,2]},
                        {'label':'human','features':[1]}, {'label':'human','features':[]}])
        self.assertEqual(result[0]['ai_rate'],1.0)
        self.assertEqual(result[0]['human_rate'],0.5)
        self.assertEqual(result[0]['lift'],2.0)
        self.assertIsNone(result[1]['lift'])

    def test_stub_binary_and_incomplete_sample_are_visible(self):
        samples=[SimpleNamespace(label='ai',corpus='beemo',id='private-id',confidence='high',text='private text',markdown=False)]
        rows,statuses=survey(samples,lambda *_:{'complete':False})
        self.assertEqual(rows,[])
        self.assertEqual(statuses[0]['status'],'incomplete_or_no_windows')
        self.assertNotIn('private',str(statuses))
        rows,statuses=survey(samples,lambda *_:{'complete':True,'hotspots':{'provenance':[{'backend':'detectorscope','token_coverage':1.0}],
            'hotspots':[{'features':[{'feature_id':9,'max_activation':1.2}]}]}})
        self.assertEqual(rows[0]['ai_count'],1)
        self.assertEqual(statuses[0]['status'],'completed')

if __name__=='__main__':
    unittest.main()
