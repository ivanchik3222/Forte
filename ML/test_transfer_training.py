import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from temporal_model import CONFIG, WEIGHTS_SHA256, load_head, score_head
from train_transfer import PROTOCOL, export_adapter, fit_bank, new_adapter, normalize
from video_training_augmentation import augment_frames, parameters
from review_with_local_vlm import parse_proposal
from prepare_external_features import cache_directory
from prepare_bank_augmentation import AUGMENT_CONFIG


class TransferTests(unittest.TestCase):
    def test_normalization_matches_training_dtype_and_handles_blank_features(self):
        features = normalize(np.zeros((2, 512), dtype=np.float32))
        self.assertEqual(features.dtype, np.float32)
        self.assertTrue(np.isfinite(features).all())

    def test_mlp_export_matches_pytorch_without_executable_pickle(self):
        model = new_adapter().eval()
        x = np.random.default_rng(1).normal(size=(5, 512)).astype(np.float32)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'head.npz'
            export_adapter(model, path, dict(format_version=2, head_type='mil_mlp64',
                backbone_sha256=WEIGHTS_SHA256, config=CONFIG))
            head, _ = load_head(path)
            np.testing.assert_allclose(score_head(head, x), model.predict_proba(x)[:, 1], atol=1e-6)

    def test_augmented_training_cannot_read_held_out_videos(self):
        torch.set_num_threads(2)
        rng = np.random.default_rng(3)
        records = [dict(sha256='p', label=1, timestamps_sec=[2.], video_ids=[1]),
                   dict(sha256='n', label=0, timestamps_sec=[], video_ids=[2])]
        original = {key: (np.arange(5.), rng.normal(size=(5, 512)).astype(np.float32)) for key in ('p', 'n')}
        augmented = {key: (t, f + .1) for key, (t, f) in original.items()}
        # A poison holdout cache entry must never enter fit_bank's training arrays.
        augmented['held_out'] = (np.arange(5.), np.full((5, 512), np.nan))
        model = fit_bank(records, original, augmented_cache=augmented)
        self.assertTrue(np.isfinite(model.predict_proba(original['p'][1])).all())
        previous = PROTOCOL['hard_negative_fraction']
        try:
            PROTOCOL['hard_negative_fraction'] = .2
            model = fit_bank(records, original, augmented_cache=augmented)
            self.assertTrue(np.isfinite(model.predict_proba(original['p'][1])).all())
        finally:
            PROTOCOL['hard_negative_fraction'] = previous

    def test_augmentation_preserves_geometry_and_has_no_temporal_flicker(self):
        frame = np.random.default_rng(5).integers(0, 256, (12, 16, 3), dtype=np.uint8)
        frames = np.stack([frame] * 4)
        result = augment_frames(frames, parameters('a' * 64))
        self.assertEqual(result.shape, frames.shape)
        for i in range(1, len(result)):
            np.testing.assert_array_equal(result[0], result[i])
        self.assertNotEqual(cache_directory(CONFIG), cache_directory(AUGMENT_CONFIG))

    def test_local_teacher_cannot_introduce_unknown_types_or_out_of_range_evidence(self):
        frames = [dict(timestamp_sec=1.), dict(timestamp_sec=2.)]
        with self.assertRaises(ValueError):
            parse_proposal('{"observations":[{"kind":"theft_intent","first_frame":0,"last_frame":1,"description":"x"}]}', ['cash_handling'], frames)
        with self.assertRaises(ValueError):
            parse_proposal('{"observations":[{"kind":"cash_handling","first_frame":0,"last_frame":9,"description":"x"}]}', ['cash_handling'], frames)
        valid = parse_proposal('{"observations":[],"uncertainties":["cash not distinguishable"]}', ['cash_handling'], frames)
        self.assertEqual(valid['review_status'], 'machine_proposal')


if __name__ == '__main__':
    unittest.main()
