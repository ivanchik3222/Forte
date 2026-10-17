"""Evidence bounds, missing coverage, and local report safety (synthetic frames)."""
import json
import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dense_observations import plan_windows, parse_observations, render_report


class DenseObservationTests(unittest.TestCase):
    def test_longest_case_duration_is_covered_without_out_of_bounds_sampling(self):
        windows=plan_windows(145.)
        self.assertEqual(len(windows),13)
        self.assertEqual(windows[0]['start_sec'],0.)
        self.assertEqual(windows[-1]['end_sec'],145.)
        for a,b in zip(windows,windows[1:]): self.assertEqual(a['end_sec'],b['start_sec'])
        for w in windows:
            self.assertTrue(all(w['start_sec']<=t<w['end_sec'] for t in w['requested']))

    def test_invalid_duration_is_rejected(self):
        for duration in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): plan_windows(duration)

    def test_evidence_timestamps_come_only_from_decoded_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'frame.jpg';Image.new('RGB',(10,10)).save(path)
            frames=[dict(timestamp_sec=t,image=str(path)) for t in [1.033,2.067,3.1,4.133,5.167]]
            text=json.dumps(dict(observations=[dict(kind='other_visible_action',first_frame=1,last_frame=4,description='An object moves.')]))
            row=parse_observations(text,frames,['other_visible_action'])['observations'][0]
            self.assertEqual(row['start_sec'],2.067);self.assertEqual(row['end_sec'],5.167)
            self.assertEqual(len(row['evidence_frames']),3)
            self.assertTrue(all(2.067<=f['timestamp_sec']<=5.167 for f in row['evidence_frames']))
            self.assertTrue(row['requires_human_review'])

    def test_timestamp_instead_of_index_and_unknown_type_fail_closed(self):
        frames=[dict(timestamp_sec=100.,image='unused')]
        for kind,first in [('other_visible_action',100),('theft',0)]:
            text=json.dumps(dict(observations=[dict(kind=kind,first_frame=first,last_frame=first,description='x')]))
            with self.assertRaises(ValueError):parse_observations(text,frames,['other_visible_action'])

    def test_intent_or_guilt_cannot_become_a_factual_observation(self):
        text=json.dumps(dict(observations=[dict(kind='other_visible_action',first_frame=0,last_frame=0,
            description='A nervous person intends to steal money.')]))
        with self.assertRaises(ValueError):
            parse_observations(text,[dict(timestamp_sec=0,image='unused')],['other_visible_action'])

    def test_evidence_uses_separate_full_resolution_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            low=Path(folder)/'low.jpg';high=Path(folder)/'high.jpg'
            Image.new('RGB',(10,10),'red').save(low);Image.new('RGB',(40,40),'blue').save(high)
            frames=[dict(timestamp_sec=0,image=str(low),evidence_image=str(high))]
            text=json.dumps(dict(observations=[dict(kind='other_visible_action',first_frame=0,last_frame=0,description='An object is visible.')]))
            encoded=parse_observations(text,frames,['other_visible_action'])['observations'][0]['evidence_frames'][0]['image_base64']
            self.assertEqual(base64.b64decode(encoded),high.read_bytes())

    def test_report_escapes_model_text_and_marks_unprocessed_intervals(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.html'
            report=dict(sampling_max_gap_sec=1.7,windows=[dict(status='not_processed')],observations=[dict(
                start_sec=0,end_sec=1,kind='other_visible_action',description='<img src=x onerror=alert(1)>',evidence_frames=[])])
            render_report(report,Path(folder)/'video.mov',path)
            text=path.read_text()
            self.assertNotIn('<img src=x',text)
            self.assertIn('&lt;img src=x',text)
            self.assertIn('без результата: 1',text)
            self.assertIn("connect-src 'none'",text)


if __name__=='__main__':unittest.main()
