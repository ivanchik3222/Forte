"""Authenticated-worker adapter preserves partial coverage and real evidence."""
import base64
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from caption_worker import convert_report
from caption_worker import CaptionAnalyzer
from unittest.mock import patch


def fixture():
    image=io.BytesIO();Image.new('RGB',(10,10)).save(image,format='JPEG')
    frame=dict(timestamp_sec=1.,image_base64=base64.b64encode(image.getvalue()).decode())
    event=dict(kind='object_handover',description='A person passes an object.',start_sec=1.,end_sec=2.,evidence_frames=[frame])
    return dict(automatic_violation_detection=False,status='partial',duration_sec=24.,
        observations=[event,dict(event)],windows=[dict(start_sec=0.,end_sec=12.,status='done'),
            dict(start_sec=12.,end_sec=24.,status='not_processed')],
        sampled_frames=[dict(timestamp_sec=1.,window_index=0),dict(timestamp_sec=13.,window_index=1)],
        elapsed_sec=20.,model_sha256='a'*64,sampling_max_gap_sec=1.7,limitations=['sampled frames'])


class CaptionWorkerTests(unittest.TestCase):
    def test_no_fake_confidence_and_no_unprocessed_frames_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            result=convert_report(fixture(),folder)
            self.assertEqual(result['coverage_status'],'partial')
            self.assertEqual(result['processed_frames'],1)
            self.assertEqual(result['frames'][0]['timestamp_sec'],1.)
            self.assertEqual(len(result['evidence_frames']),1)
            self.assertEqual(result['events'][0]['evidence_indices'],[0])
            self.assertEqual(result['events'][1]['evidence_indices'],[0])
            self.assertIsNone(result['events'][0]['mean_detector_confidence'])
            self.assertEqual(result['violations'],[])
            self.assertTrue((Path(folder)/'evidence-000.jpg').is_file())

    def test_wrong_time_and_nonjpeg_evidence_are_rejected(self):
        for field,value in [('timestamp_sec',20.),('image_base64',base64.b64encode(b'not jpeg').decode())]:
            report=fixture();report['observations'][0]['evidence_frames'][0][field]=value
            with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):
                convert_report(report,folder)

    def test_unapproved_legal_result_is_rejected(self):
        report=fixture();report['automatic_violation_detection']=True
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):
            convert_report(report,folder)

    def test_serving_passes_explicit_inference_permission_to_caption_subprocess(self):
        # Stop at the process boundary; no holdout frames or models are loaded.
        for enabled in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                runner = CaptionAnalyzer('python', folder, allow_reserved_test=enabled)
                with patch('caption_worker.subprocess.run', side_effect=RuntimeError('stop before inference')) as run:
                    with self.assertRaisesRegex(RuntimeError, 'stop before inference'):
                        runner.analyze(Path(folder)/'video.mov', Path(folder)/'output')
                self.assertEqual('--allow-reserved-test' in run.call_args.args[0], enabled)


if __name__=='__main__':unittest.main()
