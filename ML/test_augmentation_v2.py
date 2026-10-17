import hashlib
import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from augment_detection_v2 import apply_view

ROOT=Path(__file__).resolve().parent


class AugmentationV2Tests(unittest.TestCase):
    def test_grayscale_keeps_three_equal_channels_and_original_boxes(self):
        rgb=np.zeros((40,80,3),dtype=np.uint8);rgb[10:30,5:20]=[230,100,20]
        boxes=[dict(label='cash',xyxy=[5,10,20,30])]
        image,labels,_,_=apply_view(rgb,boxes,'grayscale',np.random.default_rng(1))
        data=np.asarray(image)
        self.assertEqual(data.shape,(40,80,3))
        self.assertTrue(np.array_equal(data[:,:,0],data[:,:,1]))
        self.assertTrue(np.array_equal(data[:,:,1],data[:,:,2]))
        self.assertEqual(labels,boxes)

    def test_mirrored_gray_pixels_match_mirrored_labels(self):
        rgb=np.zeros((40,80,3),dtype=np.uint8);rgb[10:30,5:20]=[255,255,255]
        image,labels,_,_=apply_view(rgb,[dict(label='cash',xyxy=[5,10,20,30])],
                                    'mirror_grayscale',np.random.default_rng(1))
        self.assertEqual(labels[0]['xyxy'],[60,10,75,30])
        self.assertEqual(np.asarray(image)[15,65,0],255)
        self.assertEqual(np.asarray(image)[15,10,0],0)

    def test_scaling_changes_relative_size_on_fixed_canvas(self):
        rgb=np.zeros((100,200,3),dtype=np.uint8)
        boxes=[dict(label='cash',xyxy=[60,30,80,50])]
        for variant,sign in [('scale_down',-1),('scale_up',1)]:
            image,labels,_,params=apply_view(rgb,boxes,variant,np.random.default_rng(1))
            self.assertEqual(image.size,(200,100))
            width=labels[0]['xyxy'][2]-labels[0]['xyxy'][0]
            self.assertGreater(sign*(width-20),0)
            self.assertAlmostEqual(width,20*params['applied_scale'])

    def test_zoom_preserves_edge_cash_and_falls_back_for_full_frame_bag(self):
        rgb=np.zeros((100,200,3),dtype=np.uint8)
        boxes=[dict(label='cash',xyxy=[0,0,20,10]),dict(label='person',xyxy=[0,0,200,100])]
        _,labels,matrix,params=apply_view(rgb,boxes,'scale_up',np.random.default_rng(1))
        self.assertFalse(params['fallback'])
        self.assertAlmostEqual(labels[0]['xyxy'][2]-labels[0]['xyxy'][0],20*params['applied_scale'])
        _,labels,_,params=apply_view(rgb,[dict(label='bag',xyxy=[0,0,200,100])],'scale_up',np.random.default_rng(1))
        self.assertTrue(params['fallback']);self.assertLess(params['applied_scale'],1)

    def test_export_keeps_holdout_bytes_groups_and_all_objects(self):
        source=ROOT/'datasets/cash_objects_v1';target=ROOT/'datasets/cash_objects_aug_v2'
        rows=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
        parents={r['name']:r for r in json.loads((source/'manifest.json').read_text(encoding='utf-8'))}
        groups=defaultdict(set)
        for row in rows:
            parent=parents[row['parent_name']]
            groups[row['source_group']].add(row['split'])
            self.assertEqual(Counter(b['label'] for b in row['boxes']),Counter(b['label'] for b in parent['boxes']))
            with Image.open(target/'images'/row['split']/(row['name']+'.jpg')) as image:
                self.assertEqual(image.size,(row['width'],row['height']))
            for b in row['boxes']:
                x,y,right,bottom=b['xyxy']
                self.assertTrue(0<=x<right<=row['width'] and 0<=y<bottom<=row['height'])
            if row['split']!='train':
                self.assertEqual(row['augmentation'],'original')
                for kind,suffix in [('images','.jpg'),('labels','.txt')]:
                    self.assertEqual(hashlib.sha256((source/kind/row['split']/(row['name']+suffix)).read_bytes()).digest(),
                                     hashlib.sha256((target/kind/row['split']/(row['name']+suffix)).read_bytes()).digest())
        self.assertTrue(all(len(s)==1 for s in groups.values()))
        self.assertEqual(Counter(r['split'] for r in rows),dict(train=495,val=10,test=6))

    def test_focused_export_uses_identical_common_views_and_untouched_holdout(self):
        full=ROOT/'datasets/cash_objects_aug_v2';focused=ROOT/'datasets/cash_objects_aug_focused_v2'
        rows=json.loads((focused/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(Counter(r['split'] for r in rows),dict(train=270,val=10,test=6))
        self.assertEqual({r['augmentation'] for r in rows},
                         {'original','mirror','grayscale','scale_up','dark','bright'})
        for row in rows:
            for kind,suffix in [('images','.jpg'),('labels','.txt')]:
                a=full/kind/row['split']/(row['name']+suffix)
                b=focused/kind/row['split']/(row['name']+suffix)
                self.assertEqual(hashlib.sha256(a.read_bytes()).digest(),hashlib.sha256(b.read_bytes()).digest())


if __name__=='__main__':unittest.main()
