import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
import hashlib

from reviewed_pipeline import merge_reports, ReviewedPipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for part in ('candidate', 'caption'):
            (self.root/part).mkdir(); (self.root/part/'evidence-000.jpg').write_bytes(part.encode())
        self.base = dict(engine='reviewed_temporal', verdict='requires_review', violations=[], rule_evaluation='not_performed',
            candidate_status='candidates_found', frames=[dict(timestamp_sec=2, boxes=[])],
            evidence_frames=[dict(timestamp_sec=2, image_file='evidence-000.jpg', boxes=[])],
            events=[dict(kind='bank_event_candidate', start_sec=1, end_sec=3, timecode_sec=2, evidence_indices=[0])])
        self.caption = dict(self.base, events=[dict(kind='object_held', start_sec=2, end_sec=4, evidence_indices=[0])],
            model_sha256='a'*64, coverage_status='done', coverage_windows=[])

    def test_evidence_indices_remain_attached_to_correct_stage(self):
        result = merge_reports(self.base, self.caption, self.root, 'done', 10)
        self.assertEqual(result['events'][0]['evidence_indices'], [0])
        self.assertEqual(result['observations'][0]['evidence_indices'], [1])
        self.assertEqual((self.root/result['evidence_frames'][0]['image_file']).read_bytes(), b'candidate')
        self.assertEqual((self.root/result['evidence_frames'][1]['image_file']).read_bytes(), b'caption')
        self.assertEqual(result['verdict'], 'requires_review')

    def test_caption_failure_keeps_candidates_and_never_reports_no_violation(self):
        source = self.root/'video.mov'; source.write_bytes(b'video')
        self.base['source_sha256'] = hashlib.sha256(b'video').hexdigest()
        (self.root/'candidate/result.json').write_text(json.dumps(self.base))
        class BrokenCaption:
            def analyze(self, *args): raise RuntimeError('Local caption failure')
        runner = ReviewedPipeline('python', self.root, self.root/'bundle', self.root/'backbone', caption=BrokenCaption())
        with patch('reviewed_pipeline.subprocess.run'):
            result = runner.analyze(source, self.root)
        self.assertEqual(result['caption_status'], 'failed')
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['observations'], [])
        self.assertEqual(result['verdict'], 'requires_review')

    def test_evidence_path_cannot_escape_job_directory(self):
        self.base['evidence_frames'][0]['image_file'] = '../outside.jpg'
        with self.assertRaises(ValueError):
            merge_reports(self.base, None, self.root, 'failed', 1)

    def test_full_pipeline_keeps_trained_positive_when_caption_subprocess_fails(self):
        source = self.root/'video.mov'; source.write_bytes(b'video')
        self.base['source_sha256'] = hashlib.sha256(b'video').hexdigest()
        (self.root/'candidate/result.json').write_text(json.dumps(self.base))
        class BrokenAssessment:
            assess_rules = True
            def analyze(self, *args): raise RuntimeError('Caption subprocess failed')
        runner = ReviewedPipeline('python', self.root, self.root/'bundle', self.root/'backbone',
            caption=BrokenAssessment(), allow_reserved_test=True)
        with patch('reviewed_pipeline.subprocess.run') as run:
            result = runner.analyze(source, self.root)
        self.assertIn('--allow-reserved-test', run.call_args.args[0])
        self.assertEqual(result['verdict'], 'violation')
        self.assertEqual(result['rule_evaluation'], 'not_performed')
        self.assertEqual(result['assessment_coverage'], 'partial')
        self.assertEqual(result['violations'][0]['classification_status'], 'unclassified')
        self.assertIsNone(result['violations'][0]['rule'])
        self.assertEqual(result['violations'][0]['timecode_sec'], 2)
        self.assertEqual((self.root/result['evidence_frames'][0]['image_file']).read_bytes(), b'candidate')
        # A failed caption plus NO candidate is never silently a clean decision.
        self.base['events'] = []
        (self.root/'candidate/result.json').write_text(json.dumps(self.base))
        with patch('reviewed_pipeline.subprocess.run'), self.assertRaisesRegex(RuntimeError, 'Rule assessment'):
            runner.analyze(source, self.root)

    def test_deferred_qwen_preserves_positive_and_never_produces_clean_verdict(self):
        from caption_worker import DeferredCaptionAnalyzer
        source = self.root/'video.mov'; source.write_bytes(b'video')
        self.base['source_sha256'] = hashlib.sha256(b'video').hexdigest()
        (self.root/'candidate/result.json').write_text(json.dumps(self.base))
        caption = DeferredCaptionAnalyzer()
        runner = ReviewedPipeline('python', self.root, self.root/'bundle', self.root/'backbone', caption=caption)
        with patch('reviewed_pipeline.subprocess.run'), patch.object(caption, 'analyze') as call:
            result = runner.analyze(source, self.root)
        call.assert_not_called()
        self.assertEqual(result['caption_status'], 'not_configured')
        self.assertEqual(result['verdict'], 'violation')
        self.assertEqual(result['rule_evaluation'], 'not_performed')
        self.assertEqual(result['violations'][0]['classification_status'], 'unclassified')
        self.base['events'] = []
        (self.root/'candidate/result.json').write_text(json.dumps(self.base))
        with patch('reviewed_pipeline.subprocess.run'), self.assertRaisesRegex(RuntimeError, 'Rule assessment'):
            runner.analyze(source, self.root)

    def test_rule_finding_keeps_its_own_evidence_after_stage_merge(self):
        self.caption.update(verdict='violation',rule_evaluation='performed',assessment_coverage='done',
            assessment_version='test',decision_scope='visible_signs_of_possible_violations',
            violations=[dict(rule_id='cashier_leaves_customer',start_sec=1,end_sec=3,timecode_sec=2,
                evidence=[dict(evidence_index=0,timestamp_sec=2,explanation='Action')])])
        result=merge_reports(self.base,self.caption,self.root,'done',10)
        self.assertEqual(result['verdict'],'violation')
        self.assertEqual(result['violations'][0]['evidence'][0]['evidence_index'],1)
        self.assertEqual((self.root/result['evidence_frames'][1]['image_file']).read_bytes(),b'caption')

    def test_missing_normative_classification_does_not_erase_positive_bank_prediction(self):
        self.caption.update(verdict='no_violation',violations=[],rule_evaluation='performed',assessment_coverage='done',
            assessment_version='test',decision_scope='visible_signs_of_possible_violations')
        result=merge_reports(self.base,self.caption,self.root,'done',10)
        self.assertEqual(result['verdict'],'violation')
        finding=result['violations'][0]
        self.assertEqual(finding['classification_status'],'unclassified')
        self.assertIsNone(finding['rule']);self.assertIsNone(finding['rule_id'])
        self.assertEqual(finding['evidence'][0]['evidence_index'],0)
        self.assertEqual(finding['timecode_sec'],2)

    def test_reserved_video_is_rejected_before_decoding_or_encoder_load(self):
        import reviewed_inference
        root = Path(__file__).resolve().parent
        split = json.loads((root/'validation/bank_holdout_v1.json').read_text())
        source = self.root/'reserved.mov'; source.write_bytes(b'test')
        actual_hash = reviewed_inference.sha256
        def digest(path):
            return split['holdout_source_hashes'][0] if Path(path) == source else actual_hash(path)
        with patch('reviewed_inference.sha256', side_effect=digest), \
             patch('av.open') as decode, patch('temporal_model.load_encoder') as encoder:
            with self.assertRaisesRegex(ValueError, 'Reserved test'):
                reviewed_inference.analyze(source, self.root/'held', root/'deployment/reviewed/model_bundle.json',
                    root/'models/r3d_18-b3b3357e.pth')
            decode.assert_not_called(); encoder.assert_not_called()

    def test_serving_can_analyze_reserved_input_and_records_usage_without_training(self):
        import reviewed_inference
        from unittest.mock import MagicMock
        root = Path(__file__).resolve().parent
        split = json.loads((root/'validation/bank_holdout_v1.json').read_text())
        source = self.root/'reserved.mov'; source.write_bytes(b'test')
        actual_hash = reviewed_inference.sha256
        def digest(path):
            return split['holdout_source_hashes'][0] if Path(path) == source else actual_hash(path)
        container = MagicMock()
        container.__enter__.return_value.streams.video[0].codec_context.width = 640
        container.__enter__.return_value.streams.video[0].codec_context.height = 480
        output = self.root/'served'
        with patch('reviewed_inference.sha256', side_effect=digest), \
             patch('av.open', return_value=container) as decode:
            report = reviewed_inference.analyze(source, output, root/'deployment/reviewed/model_bundle.json',
                root/'models/r3d_18-b3b3357e.pth', allow_reserved_test=True)
        decode.assert_called_once()
        self.assertTrue(report['reserved_test'])
        self.assertFalse(report['source_seen_during_training'])
        self.assertFalse(json.loads((output/'test-use.json').read_text())['weights_updated'])


if __name__ == '__main__': unittest.main()
