"""Train-only mirror, grayscale, scale and camera-quality variants with valid boxes."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from augment_detection_dataset import CLASSES, COLORS, ROOT, make_view, save_json, transform_boxes

VARIANTS = ('mirror', 'grayscale', 'mirror_grayscale', 'scale_down', 'scale_up',
            'dark', 'bright', 'rotate', 'motion_blur', 'jpeg')


def variant_seed(name, variant, seed=42):
    return int.from_bytes(hashlib.sha256(f'{seed}:{name}:{variant}'.encode()).digest()[:8], 'little')


def clip_boxes(boxes, width, height):
    result = []
    for box in boxes:
        x1,y1,x2,y2 = box['xyxy']
        clipped = [max(0.,x1), max(0.,y1), min(float(width),x2), min(float(height),y2)]
        if not all(np.isfinite(clipped)) or clipped[2]-clipped[0]<2 or clipped[3]-clipped[1]<2:
            raise ValueError('Transform would remove a labelled object')
        result.append(dict(label=box['label'],xyxy=clipped))
    return result


def scale_matrix(boxes, width, height, requested, rng):
    """Change relative object size on a FIXED canvas, keeping cash/hands fully visible."""
    factor = requested
    params = dict(requested_scale=requested, fallback=False)
    if requested > 1:
        critical = [b['xyxy'] for b in boxes if b['label']!='person'] or [b['xyxy'] for b in boxes]
        if critical:
            x1=min(b[0] for b in critical);y1=min(b[1] for b in critical)
            x2=max(b[2] for b in critical);y2=max(b[3] for b in critical)
            factor=min(factor,width/max(x2-x1,1),height/max(y2-y1,1))
            if factor>1.01:
                tx=float(np.clip(width*(1-factor)/2,-factor*x1,width-factor*x2))
                ty=float(np.clip(height*(1-factor)/2,-factor*y1,height-factor*y2))
                matrix=np.array([[factor,0.,tx],[0.,factor,ty]])
                transformed=transform_boxes(boxes,matrix)
                retained=[]
                for old,new in zip(boxes,transformed):
                    a,b,c,d=new['xyxy']
                    area=max(0,min(c,width)-max(a,0))*max(0,min(d,height)-max(b,0))
                    retained.append(area/max((c-a)*(d-b),1e-9))
                if all(v >= (.65 if b['label']=='person' else .995) for b,v in zip(boxes,retained)):
                    return matrix,dict(params,applied_scale=factor,retained_fractions=retained)
        # Product bags filling the image cannot be enlarged without losing labels.
        factor=float(rng.uniform(.90,.95));params['fallback']=True
    tx=float(rng.uniform(0,width*(1-factor)))
    ty=float(rng.uniform(0,height*(1-factor)))
    return np.array([[factor,0.,tx],[0.,factor,ty]]),dict(params,applied_scale=factor)


def apply_view(rgb, boxes, variant, rng):
    height,width=rgb.shape[:2]
    matrix=np.array([[1.,0.,0.],[0.,1.,0.]])
    params={}
    if variant in ('mirror','dark','bright','rotate'):
        image,result,matrix=make_view(rgb,boxes,variant,rng)
        return image,result,matrix,params
    if variant=='original':
        return Image.fromarray(rgb),boxes,matrix.tolist(),params
    if variant in ('grayscale','mirror_grayscale'):
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        rgb=np.repeat(gray[:,:,None],3,axis=2)
        if variant=='mirror_grayscale':
            rgb=np.ascontiguousarray(rgb[:,::-1])
            matrix=np.array([[-1.,0.,float(width)],[0.,1.,0.]])
    elif variant in ('scale_down','scale_up'):
        requested=float(rng.uniform(.88,.95) if variant=='scale_down' else rng.uniform(1.05,1.15))
        matrix,params=scale_matrix(boxes,width,height,requested,rng)
        rgb=cv2.warpAffine(rgb,matrix,(width,height),flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT,borderValue=(114,114,114))
    elif variant=='motion_blur':
        kernel=np.zeros((3,3),dtype=np.float32)
        horizontal=bool(rng.integers(0,2))
        if horizontal:kernel[1,:]=1/3
        else:kernel[:,1]=1/3
        rgb=cv2.filter2D(rgb,-1,kernel,borderType=cv2.BORDER_REFLECT_101)
        params=dict(kernel_size=3,direction='horizontal' if horizontal else 'vertical')
    elif variant=='jpeg':
        quality=int(rng.integers(70,91))
        ok,encoded=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,quality])
        if not ok:raise ValueError('JPEG encoding failed')
        rgb=cv2.cvtColor(cv2.imdecode(encoded,cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
        params=dict(jpeg_quality=quality)
    else:
        raise ValueError(variant)
    transformed=clip_boxes(transform_boxes(boxes,matrix),width,height)
    return Image.fromarray(rgb),transformed,matrix.tolist(),params


def export(source, output, seed=42, variants=VARIANTS):
    if not variants or len(set(variants))!=len(variants) or any(v not in VARIANTS for v in variants):
        raise ValueError('Choose distinct supported augmentation variants')
    if output.exists():raise FileExistsError(f'Choose a new output: {output}')
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True)
    records=[];fallbacks=0
    for split in ('train','val','test'):
        (output/'images'/split).mkdir(parents=True)
        (output/'labels'/split).mkdir(parents=True)
    for parent in manifest:
        original=source/'images'/parent['split']/(parent['name']+'.jpg')
        digest=hashlib.sha256(original.read_bytes()).hexdigest()
        parent_variants=('original',)+tuple(variants) if parent['split']=='train' else ('original',)
        with Image.open(original) as image:rgb=np.asarray(image.convert('RGB'))
        for variant in parent_variants:
            name=parent['name'] if variant=='original' else parent['name']+'__v2_'+variant
            pixels,boxes,matrix,params=apply_view(rgb,parent['boxes'],variant,
                                               np.random.default_rng(variant_seed(parent['name'],variant,seed)))
            record=dict(parent,name=name,parent_name=parent['name'],parent_image_sha256=digest,
                        augmentation=variant,augmentation_parameters=params,affine_from_parent=matrix,
                        width=pixels.width,height=pixels.height,boxes=boxes)
            destination=output/'images'/parent['split']/(name+'.jpg')
            label_path=output/'labels'/parent['split']/(name+'.txt')
            if variant=='original':
                shutil.copyfile(original,destination)
                shutil.copyfile(source/'labels'/parent['split']/(name+'.txt'),label_path)
            else:
                pixels.save(destination,quality=95)
                record['review_status']='derived_from_codex_visual_review'
                record['scope']='Affine/photometric derivation of reviewed parent; no newly annotated scene'
                ignored=transform_boxes([dict(label='ignore',xyxy=b) for b in parent.get('ignore_regions_masked',[])],np.asarray(matrix))
                record['ignore_regions_masked']=[[max(0.,b['xyxy'][0]),max(0.,b['xyxy'][1]),
                    min(float(pixels.width),b['xyxy'][2]),min(float(pixels.height),b['xyxy'][3])]
                    for b in ignored if min(pixels.width,b['xyxy'][2])>max(0,b['xyxy'][0])
                    and min(pixels.height,b['xyxy'][3])>max(0,b['xyxy'][1])]
                lines=[]
                for b in boxes:
                    a,y,c,d=b['xyxy']
                    lines.append(f'{CLASSES.index(b["label"])} {(a+c)/2/pixels.width:.8f} {(y+d)/2/pixels.height:.8f} {(c-a)/pixels.width:.8f} {(d-y)/pixels.height:.8f}')
                label_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            fallbacks+=bool(params.get('fallback'))
            records.append(record)
    for split in ('train','val','test'):
        coco=dict(images=[],annotations=[],categories=[dict(id=i+1,name=c) for i,c in enumerate(CLASSES)])
        for row in (r for r in records if r['split']==split):
            image_id=len(coco['images'])+1
            coco['images'].append(dict(id=image_id,file_name=f'../images/{split}/{row["name"]}.jpg',width=row['width'],height=row['height']))
            for b in row['boxes']:
                x,y,right,bottom=b['xyxy'];w,h=right-x,bottom-y
                coco['annotations'].append(dict(id=len(coco['annotations'])+1,image_id=image_id,
                    category_id=CLASSES.index(b['label'])+1,bbox=[x,y,w,h],area=w*h,iscrowd=0))
        save_json(output/'coco'/(split+'.json'),coco)
    save_json(output/'manifest.json',records)
    summary=dict(source_images=len(manifest),images=len(records),boxes=sum(len(r['boxes']) for r in records),
                 splits=dict(Counter(r['split'] for r in records)),train_variants=list(variants),seed=seed,
                 scale_up_fallbacks=fallbacks,source_manifest_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
                 note=f'{sum(r["augmentation"]!="original" for r in records)} derived train views; no increase in independent scenes; original val/test byte-identical')
    save_json(output/'summary.json',summary)
    (output/'data.yaml').write_text('path: '+output.as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'+
                                   ''.join(f'  {i}: {c}\n' for i,c in enumerate(CLASSES)),encoding='utf-8')
    shutil.copyfile(source/'ATTRIBUTION.md',output/'ATTRIBUTION.md')
    with (output/'ATTRIBUTION.md').open('a',encoding='utf-8') as handle:
        handle.write('\nChanges v2: train-only '+', '.join(variants)+
                     '; box/ignore coordinates transformed where geometric; parameters and scale fallbacks recorded in manifest.\n')
    previews=output/'previews';previews.mkdir()
    examples=[r for r in manifest if r['source']=='forte' and r['split']=='train'][:2]
    examples += [next(r for r in manifest if r['source']=='roboflow_cash_counter_theft_v2' and any(b['label']=='cash' for b in r['boxes'])),next(r for r in manifest if r['source']=='openimages')]
    for example in examples:
        rows=[r for r in records if r['parent_name']==example['name']]
        sheet=Image.new('RGB',(464*4,340*3),'white');draw=ImageDraw.Draw(sheet)
        for i,row in enumerate(rows):
            with Image.open(output/'images/train'/(row['name']+'.jpg')) as image:im=image.convert('RGB')
            d=ImageDraw.Draw(im)
            for b in row['boxes']:d.rectangle(b['xyxy'],outline=COLORS[CLASSES.index(b['label'])],width=2)
            im.thumbnail((460,310));x=i%4*464;y=i//4*340
            sheet.paste(im,(x,y+25));draw.text((x+4,y+4),row['augmentation'],fill='black')
        sheet.save(previews/(example['name']+'.jpg'),quality=95)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'datasets/cash_objects_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'datasets/cash_objects_aug_v2')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--variants',nargs='+',choices=VARIANTS,default=VARIANTS)
    args=parser.parse_args();export(args.source.resolve(),args.output.resolve(),args.seed,tuple(args.variants))
