"""Make reproducible train-only views. Source/scene groups never cross splits."""
import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
CLASSES = ['person', 'hand', 'cash', 'bag', 'storage_cabinet']
COLORS = ['cyan', 'red', 'lime', 'orange', 'magenta']
VARIANTS = ('dark', 'bright', 'mirror', 'rotate')


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def transform_boxes(boxes, matrix):
    """Axis-aligned envelopes of all four transformed rectangle corners."""
    transformed = []
    for b in boxes:
        x1, y1, x2, y2 = b['xyxy']
        points = np.array([[x1,y1,1], [x2,y1,1], [x2,y2,1], [x1,y2,1]]) @ matrix.T
        lo, hi = points.min(axis=0), points.max(axis=0)
        transformed.append(dict(label=b['label'], xyxy=[*lo.tolist(), *hi.tolist()]))
    return transformed


def make_view(rgb, boxes, variant, rng):
    height, width = rgb.shape[:2]
    matrix = np.array([[1.,0.,0.], [0.,1.,0.]])
    if variant == 'dark':
        gain, offset, gamma = float(rng.uniform(.78,.88)), 0., 1.08
    elif variant == 'bright':
        gain, offset, gamma = float(rng.uniform(1.07,1.15)), 5., .98
    elif variant == 'mirror':
        rgb = np.ascontiguousarray(rgb[:, ::-1])
        matrix = np.array([[-1.,0.,float(width)], [0.,1.,0.]])
        gain, offset, gamma = float(rng.uniform(.94,1.06)), 0., 1.
    elif variant == 'rotate':
        angle = float(rng.choice([-1,1]) * rng.uniform(1.,3.))
        matrix = cv2.getRotationMatrix2D((width/2, height/2), angle, 1.)
        corners = np.array([[0,0,1], [width,0,1], [width,height,1], [0,height,1]]) @ matrix.T
        lo, hi = corners.min(axis=0), corners.max(axis=0)
        matrix[:,2] -= lo
        # Expanded canvas preserves objects touching the edge; no dropped positive labels.
        size = tuple(np.ceil(hi-lo).astype(int))
        rgb = cv2.warpAffine(rgb, matrix, size, flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(114,114,114))
        gain, offset, gamma = float(rng.uniform(.94,1.06)), 0., 1.
    else:
        raise ValueError(variant)
    pixels = ((rgb.astype(np.float32)/255.) ** gamma) * (255.*gain) + offset
    if variant in ('dark', 'bright'):
        pixels += rng.normal(0, 1.2, pixels.shape)
    pixels = np.clip(pixels, 0, 255).astype(np.uint8)
    out_boxes = transform_boxes(boxes, matrix)
    h, w = pixels.shape[:2]
    for b in out_boxes:
        x1,y1,x2,y2 = b['xyxy']
        b['xyxy'] = [max(0.,x1),max(0.,y1),min(float(w),x2),min(float(h),y2)]
        if not all(math.isfinite(v) for v in b['xyxy']) or x2-x1 < 2 or y2-y1 < 2:
            raise ValueError('Invalid transformed box')
    return Image.fromarray(pixels), out_boxes, matrix.tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT/'datasets/cash_objects_v1')
    parser.add_argument('--output', type=Path, default=ROOT/'datasets/cash_objects_aug_v1')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    if source == out:
        raise ValueError('Output must differ from source')
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    records, images = [], {}
    for r in manifest:
        original = source/'images'/r['split']/(r['name']+'.jpg')
        record = dict(r, parent_name=r['name'], augmentation='original',
                      parent_image_sha256=hashlib.sha256(original.read_bytes()).hexdigest())
        records.append(record)
        images[r['name']] = original
        if r['split'] != 'train':
            continue
        with Image.open(original) as pixels:
            rgb = np.asarray(pixels.convert('RGB'))
        for variant in VARIANTS:
            seed = int.from_bytes(hashlib.sha256(f'{args.seed}:{r["name"]}:{variant}'.encode()).digest()[:8], 'little')
            image, boxes, matrix = make_view(rgb, r['boxes'], variant, np.random.default_rng(seed))
            name = r['name']+'__'+variant
            rec = dict(record, name=name, augmentation=variant, boxes=boxes,
                       width=image.width, height=image.height, affine_from_parent=matrix)
            ignore_boxes=[dict(label='ignore',xyxy=b) for b in record.get('ignore_regions_masked',[])]
            rec['ignore_regions_masked']=[b['xyxy'] for b in transform_boxes(ignore_boxes,np.asarray(matrix))]
            rec['scope'] = 'Derived from visually reviewed parent; transformed boxes, not independently reviewed'
            rec['review_status'] = 'derived_from_codex_visual_review'
            records.append(rec)
            images[name] = image
    for split in ('train','val','test'):
        (out/'images'/split).mkdir(parents=True, exist_ok=True)
        (out/'labels'/split).mkdir(parents=True, exist_ok=True)
        coco = dict(images=[], annotations=[], categories=[dict(id=i+1,name=c) for i,c in enumerate(CLASSES)])
        for r in [r for r in records if r['split']==split]:
            destination = out/'images'/split/(r['name']+'.jpg')
            pixels = images[r['name']]
            if isinstance(pixels, Path):
                shutil.copyfile(pixels, destination)  # Originals, including val/test, stay byte-identical.
            else:
                pixels.save(destination, quality=95)
            image_id = len(coco['images'])+1
            coco['images'].append(dict(id=image_id,file_name=f'../images/{split}/{r["name"]}.jpg',width=r['width'],height=r['height']))
            labels = []
            for b in r['boxes']:
                cls = CLASSES.index(b['label']); x1,y1,x2,y2 = b['xyxy']; w,h = x2-x1,y2-y1
                coco['annotations'].append(dict(id=len(coco['annotations'])+1,image_id=image_id,category_id=cls+1,
                                               bbox=[x1,y1,w,h],area=w*h,iscrowd=0))
                labels.append(f'{cls} {(x1+x2)/2/r["width"]:.8f} {(y1+y2)/2/r["height"]:.8f} {w/r["width"]:.8f} {h/r["height"]:.8f}')
            label_path = out/'labels'/split/(r['name']+'.txt')
            if r['augmentation']=='original':
                shutil.copyfile(source/'labels'/split/(r['name']+'.txt'), label_path)
            else:
                label_path.write_text('\n'.join(labels)+'\n',encoding='utf-8')
        save_json(out/'coco'/(split+'.json'),coco)
    (out/'data.yaml').write_text('path: '+out.as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'+
                               ''.join(f'  {i}: {c}\n' for i,c in enumerate(CLASSES)),encoding='utf-8')
    save_json(out/'manifest.json',records)
    summary = dict(source_images=len(manifest),images=len(records),
                   splits={s:sum(r['split']==s for r in records) for s in ('train','val','test')},
                   boxes=sum(len(r['boxes']) for r in records),seed=args.seed,train_variants=list(VARIANTS),
                   note='180 derived views are not 180 independent observations; validation/test untouched')
    save_json(out/'summary.json',summary)
    shutil.copyfile(source/'ATTRIBUTION.md',out/'ATTRIBUTION.md')
    with (out/'ATTRIBUTION.md').open('a',encoding='utf-8') as f:
        f.write('\nAdditional changes: train-only brightness/gamma, weak noise, horizontal mirror and expanded-canvas rotation <=3 degrees; bbox coordinates transformed.\n')
    previews=out/'previews';previews.mkdir(exist_ok=True)
    # Native bank and auxiliary bag/cash examples, each alongside all four generated views.
    examples=[r for r in manifest if r['split']=='train' and r['source']=='forte'][:2]
    examples += [next(r for r in manifest if r['source']=='roboflow_cash_counter_theft_v2' and any(b['label']=='cash' for b in r['boxes']))]
    examples += [next(r for r in manifest if r['source']=='openimages')]
    for example in examples:
        group=[r for r in records if r['parent_name']==example['name']]
        sheet=Image.new('RGB',(500*len(group),370),'white');draw=ImageDraw.Draw(sheet)
        for i,r in enumerate(group):
            with Image.open(out/'images'/r['split']/(r['name']+'.jpg')) as src:
                im=src.convert('RGB')
            d=ImageDraw.Draw(im)
            for b in r['boxes']:
                d.rectangle(b['xyxy'],outline=COLORS[CLASSES.index(b['label'])],width=2)
            im.thumbnail((500,340));sheet.paste(im,(i*500,25));draw.text((i*500+5,5),r['augmentation'],fill='black')
        sheet.save(previews/(example['name']+'.jpg'),quality=95)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
