import tempfile
import unittest
from pathlib import Path

import numpy as np

from temporal_model import (CONFIG, WEIGHTS_SHA256, candidate_events, export_head, fit_head,
                            load_head, nearest_indices, scan_centers, score_head, training_samples)
from train_temporal import metrics


class TemporalTests(unittest.TestCase):
    def setUp(self):
        times = np.arange(10, dtype=float)
        rng = np.random.default_rng(42)
        self.cache = {'p': (times, rng.normal(size=(10, 512))),
                      'n': (times, rng.normal(size=(10, 512)))}
        self.records = [dict(sha256='p', label=1, timestamps_sec=[5], video_ids=[1]),
                        dict(sha256='n', label=0, timestamps_sec=[], video_ids=[2])]

    def test_point_labels_never_make_unmarked_positive_windows_negative(self):
        x, y, w = training_samples(self.records, self.cache)
        self.assertEqual(int((y == 1).sum()), 3)
        self.assertEqual(int((y == 0).sum()), 10)
        np.testing.assert_array_equal(x[:3], self.cache['p'][1][4:7])
        self.assertAlmostEqual(w[y == 1].sum(), w[y == 0].sum())

    def test_clip_edges_repeat_real_frames_without_inventing_timestamps(self):
        times = np.asarray([0., .27, .51, .77])
        np.testing.assert_array_equal(nearest_indices(times, [-2, .25, 5]), [0, 1, 3])
        np.testing.assert_array_equal(scan_centers(times, 1.), [0., .77])

    def test_independent_events_are_not_merged_across_negative_windows(self):
        events = candidate_events(np.arange(6.), np.asarray([.1, .8, .9, .2, .1, .7]))
        self.assertEqual([e['timecode_sec'] for e in events], [2., 5.])
        self.assertTrue(all(e['type'] is None and e['requires_review'] for e in events))

    def test_non_executable_export_preserves_sklearn_predictions(self):
        head = fit_head(self.records, self.cache)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'head.npz'
            export_head(head, path, dict(format_version=1, backbone_sha256=WEIGHTS_SHA256, config=CONFIG))
            restored, _ = load_head(path)
            x = self.cache['p'][1]
            np.testing.assert_allclose(score_head(restored, x), head.predict_proba(x)[:, 1], atol=1e-12)

    def test_localization_does_not_count_below_threshold_peaks_as_detections(self):
        result = metrics([dict(label=1, score=.2, predicted_time_sec=5., annotated_times_sec=[5.]),
                          dict(label=0, score=.1, predicted_time_sec=2., annotated_times_sec=[])])
        self.assertEqual(result['localization_within_2s'], 1.)
        self.assertEqual(result['positive_videos_detected_and_localized_within_2s'], 0)


if __name__ == '__main__':
    unittest.main()
