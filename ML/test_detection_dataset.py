import json,math,unittest
from collections import defaultdict
from pathlib import Path
from PIL import Image
import numpy as np
from detection_data import CashDetectionDataset,collate_detection
from torch.utils.data import DataLoader

ROOT=Path(__file__).resolve().parent/'datasets/cash_objects_v1'

class DetectionDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.records=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))

    def test_no_source_or_scene_leakage(self):
        for field in ['source_group','source_sha256','scene_group']:
            groups=defaultdict(set)
            for r in self.records:groups[r[field]].add(r['split'])
            self.assertFalse([k for k,v in groups.items() if len(v)>1],field)
        self.assertTrue(all(r['split']=='train' for r in self.records if r['source']!='forte'))

    def test_coco_yolo_and_pixel_sizes_match(self):
        for split in ['train','val','test']:
            coco=json.loads((ROOT/'coco'/(split+'.json')).read_text(encoding='utf-8'))
            groups=defaultdict(list)
            for a in coco['annotations']:groups[a['image_id']].append(a)
            expected={Path(i['file_name']).name for i in coco['images']}
            self.assertEqual(expected,{p.name for p in (ROOT/'images'/split).glob('*.jpg')})
            for image in coco['images']:
                path=(ROOT/'coco'/image['file_name']).resolve()
                with Image.open(path) as pixels:
                    w,h=pixels.size
                self.assertEqual((w,h),(image['width'],image['height']))
                lines=(ROOT/'labels'/split/(path.stem+'.txt')).read_text().splitlines()
                self.assertEqual(len(lines),len(groups[image['id']]))
                for line,a in zip(lines,groups[image['id']]):
                    c,cx,cy,bw,bh=map(float,line.split());x,y,ww,hh=a['bbox']
                    self.assertEqual(int(c),a['category_id']-1)
                    self.assertTrue(all(math.isfinite(v) for v in [cx,cy,bw,bh]))
                    self.assertTrue(0<=x<x+ww<=w and 0<=y<y+hh<=h)
                    np.testing.assert_allclose([cx,cy,bw,bh],[(x+ww/2)/w,(y+hh/2)/h,ww/w,hh/h],atol=1e-7)

    def test_labels_review_and_attribution_present(self):
        self.assertTrue(all(r['review_status']=='codex_visual_review' for r in self.records))
        for r in self.records:
            self.assertTrue(r['boxes'])
            if r['source']=='openimages':
                self.assertTrue(r['author']);self.assertIn('creativecommons.org/licenses/by/',r['license'])
                self.assertTrue(r['original_landing_url'] or r['original_url'])
        self.assertTrue((ROOT/'ATTRIBUTION.md').exists())

    def test_detector_batch_loads(self):
        for split in ['train','val','test']:
            ds=CashDetectionDataset(ROOT,split)
            images,targets=next(iter(DataLoader(ds,batch_size=2,collate_fn=collate_detection)))
            self.assertEqual(len(images),2)
            for image,target in zip(images,targets):
                self.assertEqual(image.shape[0],3)
                self.assertEqual(target['boxes'].shape[1],4)
                self.assertTrue((target['labels']>=1).all())
                self.assertTrue((target['labels']<=5).all())

if __name__=='__main__':unittest.main()
