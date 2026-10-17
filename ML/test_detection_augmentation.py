import hashlib
import json
import unittest
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from augment_detection_dataset import make_view

ROOT=Path(__file__).resolve().parent/'datasets'


class AugmentationTests(unittest.TestCase):
    def test_mirror_transforms_pixels_and_boxes_together(self):
        image=np.zeros((40,80,3),dtype=np.uint8);image[10:30,5:20]=[240,0,0]
        boxes=[dict(label='cash',xyxy=[5,10,20,30])]
        pixels,labels,_=make_view(image,boxes,'mirror',np.random.default_rng(1))
        self.assertEqual(labels[0]['xyxy'],[60,10,75,30])
        self.assertGreater(np.asarray(pixels)[15,65,0],200)
        self.assertEqual(np.asarray(pixels)[15,10,0],0)

    def test_expanded_rotation_preserves_all_positive_regions(self):
        image=np.zeros((40,80,3),dtype=np.uint8)
        pixels,boxes,_=make_view(image,[dict(label='cash',xyxy=[0,0,80,40])],'rotate',np.random.default_rng(1))
        x1,y1,x2,y2=boxes[0]['xyxy']
        self.assertTrue(0<=x1<x2<=pixels.width and 0<=y1<y2<=pixels.height)
        self.assertGreater(pixels.width,80);self.assertGreater(pixels.height,40)

    def test_augmented_groups_and_holdout_integrity(self):
        src=ROOT/'cash_objects_v1';aug=ROOT/'cash_objects_aug_v1'
        records=json.loads((aug/'manifest.json').read_text(encoding='utf-8'))
        groups=defaultdict(set)
        for r in records:
            groups[r['source_group']].add(r['split'])
            if r['split']!='train':
                self.assertEqual(r['augmentation'],'original')
                for kind,suffix in [('images','.jpg'),('labels','.txt')]:
                    a=(src/kind/r['split']/(r['name']+suffix)).read_bytes()
                    b=(aug/kind/r['split']/(r['name']+suffix)).read_bytes()
                    self.assertEqual(hashlib.sha256(a).digest(),hashlib.sha256(b).digest())
            with Image.open(aug/'images'/r['split']/(r['name']+'.jpg')) as image:
                self.assertEqual(image.size,(r['width'],r['height']))
            for box in r['boxes']:
                x1,y1,x2,y2=box['xyxy']
                self.assertTrue(0<=x1<x2<=r['width'] and 0<=y1<y2<=r['height'])
        self.assertTrue(all(len(s)==1 for s in groups.values()))
        self.assertEqual(sum(r['augmentation']!='original' for r in records),180)


if __name__=='__main__':
    unittest.main()
