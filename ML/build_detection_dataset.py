"""Export visually corrected annotations to COCO + YOLO, preserving source groups."""
import json,hashlib,collections
from pathlib import Path
from PIL import Image,ImageDraw
from pipeline import ROOT,save_json

CLASSES=['person','hand','cash','bag','storage_cabinet']
DATA=ROOT/'datasets/cash_objects_v1'
REVIEW=ROOT/'annotations/corrected'
COLORS={'person':'cyan','hand':'red','cash':'lime','bag':'orange','storage_cabinet':'magenta'}
VAL={16,17,30,31,32,34,35,37,38,39}
TEST={33,40,43,44,45,46}

def clip(box,roi):
    x1,y1,x2,y2=box;l,t,r,b=roi
    return [max(x1,l)-l,max(y1,t)-t,min(x2,r)-l,min(y2,b)-t]

def pack(image,manual,roi):
    image=image.crop(roi);draw=ImageDraw.Draw(image)
    ignores=[]
    for box in manual.get('ignore',[]):
        c=clip(box,roi)
        if c[2]>c[0] and c[3]>c[1]:draw.rectangle(c,fill=(114,114,114));ignores.append(c)
    boxes=[]
    for label in CLASSES:
        for box in manual.get(label,[]):
            c=clip(box,roi)
            if c[2]-c[0]>=4 and c[3]-c[1]>=4:boxes.append(dict(label=label,xyxy=c))
    return image,boxes,ignores

def main():
    frames=json.loads((REVIEW/'frames.json').read_text(encoding='utf-8'))
    manual=json.loads((REVIEW/'manual_boxes.json').read_text(encoding='utf-8'))
    if {Path(r['file_name']).stem for r in frames}!=set(manual):raise ValueError('Manual annotation coverage mismatch')
    records=[];images={}
    for r in frames:
        stem=Path(r['file_name']).stem;labels=manual[stem]
        # Only the inspected cashier work area is exhaustive. Reflections in upper glass are outside the exported ROI.
        roi=[0,300,464,610]
        image,boxes,ignores=pack(Image.open(REVIEW/'images'/r['file_name']).convert('RGB'),labels,roi)
        vid=r['video_ids'][0];split='val' if vid in VAL else 'test' if vid in TEST else 'train'
        group='forte_' + r['source_sha256']
        records.append(dict(name=stem,source='forte',source_group=group,source_sha256=r['source_sha256'],
                            video_ids=r['video_ids'],timestamp_sec=r['timestamp_sec'],split=split,roi_xyxy=roi,
                            width=image.width,height=image.height,boxes=boxes,ignore_regions_masked=ignores,
                            review_status='codex_visual_review',scope='exhaustive for listed classes within exported ROI'))
        images[stem]=image
    external=json.loads((REVIEW/'external_candidates.json').read_text(encoding='utf-8'))
    em=json.loads((REVIEW/'external_manual.json').read_text(encoding='utf-8'))
    for index,labels in em.items():
        r=external[int(index)];stem='roboflow_'+index.zfill(2)
        image,boxes,ignores=pack(Image.open(r['path']).convert('RGB'),labels,labels['crop'])
        records.append(dict(name=stem,source='roboflow_cash_counter_theft_v2',source_group=labels['group'],split='train',
                            original_file=r['file_name'],original_split=r['original_split'],
                            source_sha256=hashlib.sha256(Path(r['path']).read_bytes()).hexdigest(),
                            roi_xyxy=labels['crop'],width=image.width,height=image.height,boxes=boxes,
                            ignore_regions_masked=ignores,review_status='codex_visual_review',
                            scope='original labels replaced; Cash is visible notes/stacks, Hand excludes forearm',
                            source_url='https://universe.roboflow.com/ayaan-falfl/cash-counter-theft/dataset/2',
                            author='Ayaan',license='CC BY 4.0'))
        images[stem]=image
    oi=json.loads((ROOT/'external/openimages_bags/candidates.json').read_text(encoding='utf-8'))
    oi_review=json.loads((REVIEW/'openimages_review.json').read_text(encoding='utf-8'))
    for index in oi_review['accepted_indices']:
        r=oi[index];stem='openimages_'+r['image_id'];image=Image.open(r['path']).convert('RGB')
        original_w,original_h=image.size;image.thumbnail((768,768))
        sx,sy=image.width/original_w,image.height/original_h
        boxes=[dict(label='bag',xyxy=[round(x1*sx),round(y1*sy),round(x2*sx),round(y2*sy)]) for x1,y1,x2,y2 in r['bag_boxes']]
        meta=r['metadata']
        records.append(dict(name=stem,source='openimages',source_group=stem,split='train',source_sha256=hashlib.sha256(Path(r['path']).read_bytes()).hexdigest(),
                            width=image.width,height=image.height,boxes=boxes,ignore_regions_masked=[],review_status='codex_visual_review',
                            scope='bag-only scene visually checked for other target classes',image_id=r['image_id'],
                            original_size=[original_w,original_h],author=meta.get('Author'),title=meta.get('Title'),
                            original_url=meta.get('OriginalURL'),original_landing_url=meta.get('OriginalLandingURL'),
                            license=meta.get('License'),annotations_license='CC BY 4.0',annotation_author='Google LLC',
                            source_url='https://storage.googleapis.com/openimages/web/download_v7.html',
                            modifications='Image resized if needed; labels mapped from Handbag to bag'))
        images[stem]=image
    # Preserve all related native recordings in the same split, including exact copies.
    for r in records:
        if r['source']=='forte':
            vid=r['video_ids'][0]
            r['scene_group']=('green_bag' if vid in {16,17} else 'intrusion_pink' if vid in {30,31,32} else
                              'transactions_white' if vid in {34,35,37,38,39} else 'solo_white' if vid in {40,43,44,45,46} else
                              'entry_white' if vid==33 else 'transactions_pink' if vid in {1,2,3,4,5,18,19} else 'solo_pink')
        else:r['scene_group']=r['source_group']
        # Delete only known generated copies when a record has moved between splits.
        for old_split in ['train','val','test']:
            if old_split==r['split']:continue
            for old in [DATA/'images'/old_split/(r['name']+'.jpg'),DATA/'labels'/old_split/(r['name']+'.txt')]:
                if not old.resolve().is_relative_to(DATA.resolve()):raise ValueError('Unsafe generated path')
                if old.exists():old.unlink()
    for split in ['train','val','test']:
        (DATA/'images'/split).mkdir(parents=True,exist_ok=True);(DATA/'labels'/split).mkdir(parents=True,exist_ok=True)
        coco=dict(images=[],annotations=[],categories=[dict(id=i+1,name=c) for i,c in enumerate(CLASSES)],
                  info=dict(description='Cash object detection starter set; visually reviewed by Codex, no expert sign-off',date_created='2026-10-17'))
        for r in [v for v in records if v['split']==split]:
            name=r['name'];image=images[name];image_path=DATA/'images'/split/(name+'.jpg');image.save(image_path,quality=95)
            image_id=len(coco['images'])+1
            coco['images'].append(dict(id=image_id,file_name=f'../images/{split}/{name}.jpg',width=image.width,height=image.height))
            yolo=[]
            for box in r['boxes']:
                cls=CLASSES.index(box['label']);x1,y1,x2,y2=box['xyxy'];w=x2-x1;h=y2-y1
                coco['annotations'].append(dict(id=len(coco['annotations'])+1,image_id=image_id,category_id=cls+1,
                                               bbox=[x1,y1,w,h],area=w*h,iscrowd=0))
                yolo.append(f'{cls} {(x1+x2)/2/image.width:.8f} {(y1+y2)/2/image.height:.8f} {w/image.width:.8f} {h/image.height:.8f}')
            (DATA/'labels'/split/(name+'.txt')).write_text('\n'.join(yolo)+'\n',encoding='utf-8')
            preview=image.copy();d=ImageDraw.Draw(preview)
            for box in r['boxes']:
                d.rectangle(box['xyxy'],outline=COLORS[box['label']],width=2)
                x,y,_,_=box['xyxy'];d.text((x,max(0,y-10)),box['label'],fill=COLORS[box['label']])
            (DATA/'previews').mkdir(exist_ok=True);preview.save(DATA/'previews'/(name+'.jpg'),quality=95)
        save_json(DATA/'coco'/(split+'.json'),coco)
    yaml='path: '+DATA.resolve().as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'
    yaml+=''.join(f'  {i}: {name}\n' for i,name in enumerate(CLASSES))
    (DATA/'data.yaml').write_text(yaml,encoding='utf-8')
    save_json(DATA/'manifest.json',records)
    summary=dict(classes=CLASSES,images=len(records),boxes=sum(len(r['boxes']) for r in records),
                 splits={s:dict(images=sum(r['split']==s for r in records),class_counts=dict(collections.Counter(b['label'] for r in records if r['split']==s for b in r['boxes']))) for s in ['train','val','test']},
                 source_counts=dict(collections.Counter(r['source'] for r in records)),
                 review='Codex visual review, not expert adjudication',
                 limitations=['Small starter set','Most native objects are small','Metal storage cabinet labels do not imply safe certification',
                              'Bag has very few native examples','External sources are auxiliary train only','Evaluation still shares the same camera'])
    save_json(DATA/'summary.json',summary)
    attribution=['# Attribution and data sources','',
                 'ForteBank: supplied hackathon training videos; local use under the case terms. Do not redistribute video frames.',
                 '', 'Roboflow Cash Counter Theft v2 by Ayaan: https://universe.roboflow.com/ayaan-falfl/cash-counter-theft/dataset/2',
                 'Declared license: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/',
                 'Changes: selected images cropped, labels manually replaced, Cashier/Customer merged into person; uncertain regions masked.',
                 '', 'Open Images: https://storage.googleapis.com/openimages/web/download_v7.html',
                 'Annotations by Google LLC, CC BY 4.0. Image authors, original links and individual licenses below.',
                 'Changes: selected images resized if necessary; Handbag mapped to bag.','']
    for r in records:
        if r['source']=='openimages':
            attribution.append(f'- {r["image_id"]}: {r.get("title") or "Untitled"}; author {r.get("author")}; {r.get("original_landing_url") or r.get("original_url")}; {r.get("license")}')
    (DATA/'ATTRIBUTION.md').write_text('\n'.join(attribution)+'\n',encoding='utf-8')
    # Contact sheets of actual exported pixels and labels are the final visual gate.
    for start in range(0,len(records),8):
        group=records[start:start+8];sheet=Image.new('RGB',(928,350*((len(group)+1)//2)),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(group):
            im=Image.open(DATA/'previews'/(r['name']+'.jpg'));im.thumbnail((464,310))
            x=(j%2)*464;y=(j//2)*350;sheet.paste(im,(x,y+25));d.text((x+3,y+3),r['name']+' '+r['split'],fill='black')
        sheet.save(DATA/'previews'/f'sheet_{start//8+1:02d}.jpg',quality=95)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
