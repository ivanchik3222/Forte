import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from rule_assessment import load_rules, parse_assessment, decision, assessment_prompt


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.frames=[]
        for i in range(4):
            path=Path(self.temp.name)/f'{i}.jpg';Image.new('RGB',(12,12),(i*60,0,0)).save(path)
            self.frames.append(dict(timestamp_sec=5.033+i*.8,image=str(path)))
        self.registry=load_rules()
        self.row=dict(rule_id='cashier_leaves_customer',type='Новый визуальный вариант ухода кассира',
            first_frame=0,last_frame=3,key_frame=2,visible_fact='Кассир уходит от стола, клиент остаётся у окна.',
            reason='Обслуживание продолжается, что может противоречить пункту 22.',
            conditions={'c1':'Приём наличных продолжается.','c2':'Клиент стоит у окна.','c3':'Кассир вышел за рабочую зону.'},
            excluded=['x1','x2','x3'],evidence=[dict(frame=0,explanation='Начало обслуживания.'),dict(frame=2,explanation='Кассир покидает место.')])

    def parse(self,row=None):
        return parse_assessment(json.dumps(dict(violations=[row or self.row])),self.frames,self.registry)

    def test_novel_title_is_not_limited_to_training_actions_and_evidence_is_selected(self):
        result=self.parse()['violations'][0]
        self.assertEqual(result['type'],self.row['type'])
        self.assertEqual(result['timecode_sec'],self.frames[2]['timestamp_sec'])
        self.assertEqual([e['timestamp_sec'] for e in result['evidence_frames']],[self.frames[i]['timestamp_sec'] for i in (0,2)])
        self.assertEqual(result['rule']['section'],'22')
        self.assertNotIn('rule_id',assessment_prompt(self.frames,self.registry).split('Rules: ')[0])

    def test_missing_conditions_unknown_source_and_disabled_omission_do_not_become_violations(self):
        for updates in ({'conditions':{'c1':'x'}},{'excluded':[]},{'rule_id':'invented_rule'},
                        {'rule_id':'id_check_not_visible'},{'visible_fact':'Кассир намеревается украсть деньги.'}):
            r=self.parse(dict(self.row,**updates))
            self.assertEqual(r['violations'],[]);self.assertEqual(r['rejected_findings'],1)

    def test_outside_duplicate_four_or_unrelated_key_frames_are_rejected(self):
        for updates in ({'key_frame':1},{'evidence':[dict(frame=8,explanation='x')]},
                        {'evidence':[dict(frame=2,explanation='x')]*2},
                        {'evidence':[dict(frame=i,explanation='x') for i in range(4)]}):
            self.assertEqual(self.parse(dict(self.row,**updates))['rejected_findings'],1)

    def test_binary_verdict_distinguishes_clean_windows_and_processing_failure(self):
        self.assertEqual(decision([], [{'assessment_status':'done'}]),'no_violation')
        self.assertEqual(decision([self.row],[{'assessment_status':'partial'}]),'violation')
        for windows in ([],[{'assessment_status':'invalid_model_output'}],[{'assessment_status':'partial'}]):
            with self.assertRaises(ValueError):decision([],windows)

if __name__=='__main__':unittest.main()
