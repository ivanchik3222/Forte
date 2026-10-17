"""Audit public COCO boxes and potential near-duplicate leakage; no relabeling by guess."""
import collections
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent


def main():
    source = ROOT / 'external/cash_counter_theft_v2'
    rows, invalid, counts = [], [], collections.Counter()
    for path in sorted(source.rglob('_annotations.coco.json')):
        data = json.loads(path.read_text())
        names = {c['id']: c['name'] for c in data['categories']}
        annotations = collections.defaultdict(list)
        for a in data['annotations']:
            label = names[a['category_id']]
            counts[label] += 1
            annotations[a['image_id']].append(dict(label=label, xywh=a['bbox'], annotation_id=a['id']))
        for record in data['images']:
            image_path = path.parent / record['file_name']
            with Image.open(image_path) as raw:
                image = raw.convert('RGB')
            if image.size != (record['width'], record['height']):
                invalid.append(dict(file=record['file_name'], reason='dimension_mismatch'))
            for box in annotations[record['id']]:
                x, y, w, h = box['xywh']
                if not (w > 0 and h > 0 and x >= 0 and y >= 0 and x+w <= image.width+1 and y+h <= image.height+1):
                    invalid.append(dict(file=record['file_name'], reason='invalid_box', annotation_id=box['annotation_id']))
            gray = cv2.resize(np.asarray(image.convert('L')), (32, 32))
            coef = cv2.dct(gray.astype(np.float32))[:8, :8].flatten()[1:]
            phash = sum(int(b) << i for i, b in enumerate(coef > np.median(coef)))
            rows.append(dict(path=str(image_path.resolve()), split=path.parent.name, file_name=record['file_name'],
                image_id=record['id'], sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                phash=phash, boxes=annotations[record['id']]))
    if not rows:
        raise FileNotFoundError('Download Roboflow COCO data first')
    parents = list(range(len(rows)))
    def group(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    pairs = []
    for i, a in enumerate(rows):
        for j, b in enumerate(rows[:i]):
            distance = (a['phash'] ^ b['phash']).bit_count()
            if a['sha256'] == b['sha256'] or distance <= 4:
                parents[group(i)] = group(j)
                pairs.append(dict(a=i, b=j, distance=distance, cross_split=a['split'] != b['split']))
    for i, row in enumerate(rows):
        row['visual_group'] = group(i)
        row['annotation_status'] = 'source_label_semantics_unverified'
    report = dict(images=len(rows), unique_decoded_images=len({r['sha256'] for r in rows}),
        perceptual_groups=len({r['visual_group'] for r in rows}), class_counts=dict(counts), invalid=invalid,
        cross_split_near_duplicate_pairs=sum(p['cross_split'] for p in pairs), near_duplicate_pairs=pairs,
        rows=rows, limitations=['Perceptual matches are review candidates, not proven identical scenes',
        'Valid rectangle geometry does not confirm that the object class is correct',
        'Public original split must not be used as an independent banking evaluation'])
    (source / 'quality_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ['images', 'unique_decoded_images', 'perceptual_groups',
          'class_counts', 'invalid', 'cross_split_near_duplicate_pairs']}, indent=2))


if __name__ == '__main__':
    main()
