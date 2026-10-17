import unittest
import numpy as np
from pipeline import ROOT,manifest,contextual,train_samples

class DataIntegrityTests(unittest.TestCase):
    def test_duplicate_annotations_are_merged_without_losing_event_points(self):
        records=manifest(ROOT/'open/open')
        self.assertEqual(len(records),40)
        self.assertEqual(len({r['sha256'] for r in records}),40)
        duplicate=next(r for r in records if r['video_ids']==[4,47])
        self.assertEqual(duplicate['timestamps_sec'],[57,68])
        self.assertEqual(sum(len(r['video_ids']) for r in records),42)

    def test_unmarked_positive_frames_are_not_negative_training_labels(self):
        times=np.arange(30,dtype=np.float32)
        features=np.stack([times,times**2],axis=1)
        records=[dict(sha256='p',label=1,timestamps_sec=[10]),dict(sha256='n',label=0,timestamps_sec=[])]
        x,y,w=train_samples(records,{'p':(times,features),'n':(times,features)})
        self.assertEqual(int((y==1).sum()),3)
        self.assertEqual(int((y==0).sum()),8)
        self.assertAlmostEqual(float(w[y==1].sum()),float(w[y==0].sum()))
        self.assertTrue(np.isfinite(x).all())

    def test_constant_scene_has_zero_motion_and_no_nan_at_boundaries(self):
        x=contextual(np.arange(3),np.ones((3,2)),[-10,0,1,10])
        self.assertEqual(x.shape,(4,8))
        self.assertTrue(np.isfinite(x).all())
        np.testing.assert_array_equal(x[:,-2:],0)

if __name__=='__main__':unittest.main()
