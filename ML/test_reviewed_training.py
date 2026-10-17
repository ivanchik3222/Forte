import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from import_reviewed_annotations import make_split, validate_export
from reviewed_model import (ACTION_KINDS, PROTOCOL, VIEWS, ReviewedAdapter, action_samples,
                            export_model, fit_reviewed, join_views, load_model, merged_observations)
from temporal_model import WEIGHTS_SHA256
from training_split import assert_training_sources, development_records
from train_reviewed_actions import fit_actions


class ReviewedTrainingTests(unittest.TestCase):
    def setUp(self):
        self.records = [dict(sha256='a'*64, video_ids=[1], label=1, timestamps_sec=[2.], duration_sec=8.),
                        dict(sha256='b'*64, video_ids=[3], label=0, timestamps_sec=[], duration_sec=8.)]
        self.split = dict(version=1, development_source_hashes=['a'*64, 'b'*64], holdout_source_hashes=['c'*64])
        self.queue = dict(tasks=[dict(id='task', source_sha256='a'*64, video_ids=[1],
                                     source_label=1, original_points_sec=[2.])])
        self.row = dict(kind='cash_handling', start_sec=1., end_sec=3., description='Human observation',
                        review_status='human_reviewed', legal_rule_id=None)
        self.document = dict(version=1, review_source='explicit_user_review', tasks=[dict(
            task_id='task', source_sha256='a'*64, video_ids=[1], source_label=1,
            original_points_sec=[2.], reviewed=True, observations=[self.row])])

    def test_import_rejects_changed_provenance_machine_labels_and_invalid_times(self):
        for field, value in [('kind', 'theft_intent'), ('review_status', 'machine_proposal'),
                             ('start_sec', -1), ('start_sec', float('nan')), ('end_sec', 9),
                             ('start_sec', True), ('legal_rule_id', 'invented-rule')]:
            with self.subTest(field=field, value=value):
                document = copy.deepcopy(self.document)
                document['tasks'][0]['observations'][0][field] = value
                with self.assertRaises(ValueError):
                    validate_export(document, self.queue, self.records)
        document = copy.deepcopy(self.document)
        document['tasks'][0]['source_sha256'] = 'b'*64
        with self.assertRaises(ValueError):
            validate_export(document, self.queue, self.records)

    def test_empty_review_is_unknown_and_cannot_create_a_negative(self):
        self.document['tasks'][0]['observations'] = []
        rows, audit = validate_export(self.document, self.queue, self.records)
        self.assertEqual(rows, [])
        self.assertEqual(audit['empty_reviewed_tasks'], ['task'])
        # No cache is provided: empty reviews must not even request footage.
        samples = action_samples(self.records, {}, rows)
        self.assertEqual(len(samples[0]), 0)
        self.assertEqual(self.records[0]['label'], 1)

    def test_reserved_hash_excludes_all_duplicate_ids_and_rejects_unknown_sources(self):
        self.records[0]['video_ids'] = [4, 47]
        split = dict(version=1, development_source_hashes=['b'*64], holdout_source_hashes=['a'*64])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'split.json'; path.write_text(json.dumps(split))
            self.assertEqual(development_records(self.records, path), [self.records[1]])
            with self.assertRaises(ValueError):
                development_records([dict(sha256='x'*64)], path)
        with self.assertRaises(ValueError):
            assert_training_sources(['a'*64], split)

    def test_reservation_cannot_split_a_scene_group(self):
        records = self.records + [dict(sha256='c'*64, video_ids=[16], label=0, path='/videos/16.mov'),
                                  dict(sha256='d'*64, video_ids=[17], label=1, path='/videos/17.mov')]
        split = make_split(records)
        self.assertEqual(len(split['development_source_hashes']), 2)
        self.assertFalse(set(split['development_source_hashes']) & set(split['holdout_source_hashes']))
        with self.assertRaises(ValueError):
            make_split(records, holdout_ids=(1, 16))

    def test_only_known_intervals_are_targets_and_overlaps_are_multiaction(self):
        rows = [dict(self.row, annotation_id='1', source_sha256='a'*64),
                dict(self.row, annotation_id='2', source_sha256='a'*64, start_sec=3., end_sec=4.),
                dict(self.row, annotation_id='3', source_sha256='a'*64, kind='document_presented', start_sec=2., end_sec=2.),
                dict(self.row, annotation_id='4', source_sha256='b'*64, kind='other_visible_action')]
        cache = {'a'*64:(np.arange(8.), np.ones((8,1024), np.float32))}
        x, target, _, sources, times, support = action_samples(self.records, cache, rows)
        np.testing.assert_array_equal(times, [1.,2.,3.,4.])
        self.assertEqual(len(x), 4)
        self.assertEqual(set(sources), {'a'*64})
        self.assertEqual(target[1, ACTION_KINDS.index('cash_handling')], .5)
        self.assertEqual(target[1, ACTION_KINDS.index('document_presented')], .5)
        merged = merged_observations(rows, {'a'*64})
        cash = [r for r in merged if r['kind'] == 'cash_handling']
        self.assertEqual(len(cash), 1)
        self.assertEqual(cash[0]['annotation_ids'], ['1','2'])

    def test_poison_reserved_annotations_and_augmentations_do_not_change_training(self):
        torch.set_num_threads(2)
        rng = np.random.default_rng(11)
        cache = {r['sha256']:(np.arange(8.), rng.normal(size=(8,1024)).astype(np.float32)) for r in self.records}
        rows = [dict(self.row, source_sha256=r['sha256'], annotation_id=f'{i}:{kind}', kind=kind)
                for i,r in enumerate(self.records) for kind in ('cash_handling','document_presented')]
        previous = PROTOCOL['epochs']; PROTOCOL['epochs'] = 3
        try:
            clean, _ = fit_reviewed(self.records, cache, rows, self.split, augmented_cache=cache)
            poison = dict(cache, **{'c'*64:(np.arange(8.), np.full((8,1024), np.nan))})
            poisoned_rows = rows + [dict(self.row, source_sha256='c'*64, annotation_id='held', start_sec=float('nan'))]
            test, _ = fit_reviewed(self.records, poison, poisoned_rows, self.split, augmented_cache=poison)
            for key, value in clean.state_dict().items():
                torch.testing.assert_close(value, test.state_dict()[key], rtol=0, atol=0)
            with self.assertRaises(ValueError):
                fit_reviewed(self.records + [dict(sha256='c'*64)], poison, rows, self.split)
        finally:
            PROTOCOL['epochs'] = previous

    def test_artifact_roundtrip_and_timestamp_alignment(self):
        torch.manual_seed(5); model = ReviewedAdapter().eval(); model.active[:2] = True
        x = np.random.default_rng(8).normal(size=(4,1024)).astype(np.float32)
        metadata = dict(format_version=1, model_family='reviewed_dual_view_r3d18',
            backbone_sha256=WEIGHTS_SHA256, view_configs=VIEWS, action_kinds=ACTION_KINDS,
            split=self.split, training_source_hashes=['a'*64,'b'*64])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.npz'; export_model(model, path, metadata)
            restored, _ = load_model(path)
            np.testing.assert_array_equal(restored.predict_proba(x), model.predict_proba(x))
            np.testing.assert_array_equal(restored.action_scores(x), model.action_scores(x))
        desk = {'a':(np.arange(4.), x[:,:512])}; context = {'a':(np.arange(4.)+.1, x[:,512:])}
        with self.assertRaises(ValueError):
            join_views(desk, context)

    def test_separate_action_fit_keeps_reserved_sources_out_of_scaling_and_weights(self):
        torch.set_num_threads(2)
        rng = np.random.default_rng(7)
        cache = {r['sha256']:(np.arange(8.), rng.normal(size=(8,1024)).astype(np.float32)) for r in self.records}
        rows = [dict(self.row, source_sha256=r['sha256'], annotation_id=f'{i}:{kind}', kind=kind,
                     start_sec=start, end_sec=start+1)
                for i,r in enumerate(self.records) for kind,start in [('cash_handling',1.),('document_presented',5.)]]
        clean, _ = fit_actions(self.records, cache, rows, self.split, cache)
        poisoned_cache = dict(cache, **{'c'*64:(np.arange(8.), np.full((8,1024), np.nan))})
        poisoned_rows = rows + [dict(self.row, source_sha256='c'*64, annotation_id='reserved', start_sec=float('nan'))]
        test, _ = fit_actions(self.records, poisoned_cache, poisoned_rows, self.split, poisoned_cache)
        for key, value in clean.state_dict().items():
            torch.testing.assert_close(value, test.state_dict()[key], rtol=0, atol=0)
        self.assertTrue(np.isfinite(test.action_scores(cache['a'*64][1])).all())


if __name__ == '__main__':
    unittest.main()
