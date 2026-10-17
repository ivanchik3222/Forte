import json
import unittest
from pathlib import Path

import av
import numpy as np

from augment_native_videos_v2 import resample_indices
from train_native_video_aug import pooled,balanced_group_weights

ROOT=Path(__file__).resolve().parent


class VideoAugmentationTests(unittest.TestCase):
    def test_fps_resampling_preserves_event_time(self):
        source=np.arange(180)/30
        for fps in (2,6,12):
            desired=np.arange(6*fps)/fps
            selected=resample_indices(source,desired)
            self.assertEqual(source[selected[3*fps]],3.)
            self.assertLessEqual(np.max(np.abs(source[selected]-desired)),1/60+1e-9)

    def test_motion_feature_uses_time_instead_of_frame_count(self):
        rates=[]
        for fps in (2,12):
            times=np.arange(6*fps)/fps
            features=(times*2)[:,None]
            rates.append(pooled(times,features)[-1])
        np.testing.assert_allclose(rates,[2.,2.],rtol=1e-6)

    def test_repeated_views_keep_equal_source_weights(self):
        control=[dict(source_group=g,source_binary_label=y) for g,y in [('a',0),('b',1)]]
        augmented=control[:1]*2+control[1:]*6
        weights=balanced_group_weights(augmented)
        self.assertAlmostEqual(weights[:2].sum(),1.)
        self.assertAlmostEqual(weights[2:].sum(),1.)
        self.assertAlmostEqual(weights.sum(),balanced_group_weights(control).sum())

    def test_video_exports_holdout_guard_and_encoded_fps(self):
        root=ROOT/'datasets/cash_video_aug_v2'
        rows=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        original=json.loads((ROOT/'datasets/cash_objects_v1/manifest.json').read_text(encoding='utf-8'))
        heldout={r['source_group'] for r in original if r['split']!='train'}
        self.assertEqual(len(rows),150)
        self.assertEqual(len({r['source_group'] for r in rows}),24)
        for row in rows:
            self.assertEqual(row['split'],'train');self.assertNotIn(row['source_group'],heldout)
            self.assertGreaterEqual(row['anchor_clip_sec'],0)
            self.assertLessEqual(row['anchor_clip_sec'],row['source_duration_sec'])
            mapping=row['source_frame_mapping']
            self.assertEqual(len(mapping),row['frames'])
            self.assertLess(max(abs(r['source_sec']-(row['clip_start_source_sec']+r['output_sec'])) for r in mapping),.035)
        for row in rows[:6]:
            with av.open(str(root/row['file_name'])) as video:
                stream=video.streams.video[0]
                self.assertEqual(float(stream.average_rate),row['fps'])
                times=[float(f.time) for f in video.decode(stream)]
            self.assertEqual(len(times),row['frames'])
            self.assertAlmostEqual(times[0],0)
            self.assertAlmostEqual(times[-1],(len(times)-1)/row['fps'],places=5)


if __name__=='__main__':unittest.main()
