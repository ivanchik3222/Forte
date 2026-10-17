"""Grounding DINO proposals for human review; not ground-truth annotations."""
import argparse
import json
import hashlib
import os
import time
from pathlib import Path
import cv2
import torch
from PIL import Image,ImageDraw
os.environ.setdefault('HF_HUB_OFFLINE','1')
os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
from pipeline import ROOT,manifest,save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=6)
    p.add_argument('--threshold',type=float,default=.30);p.add_argument('--data',type=Path,default=ROOT/'open/open')
    a=p.parse_args();torch.set_num_threads(4)
    local=ROOT/'models/grounding-dino-tiny'
    expected='1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3'
    if hashlib.sha256((local/'model.safetensors').read_bytes()).hexdigest()!=expected:
        raise ValueError('Grounding DINO weights failed integrity check. Re-run download_models.py --grounding-dino.')
    processor=AutoProcessor.from_pretrained(local,local_files_only=True)
    model=AutoModelForZeroShotObjectDetection.from_pretrained(local,local_files_only=True).eval()
    device='cuda' if torch.cuda.is_available() else 'cpu';model.to(device)
    classes=['person','hand','bag','banknote','safe','door','mobile phone','cup']
    prompt='. '.join(classes)+'.'
    started=time.time()
    records=[r for r in manifest(a.data) if r['label']]
    # Spread the pilot over different visual scenarios rather than only the first videos.
    pilot_ids=[1,13,17,24,40,46]
    records=sorted(records,key=lambda r:(not any(i in pilot_ids for i in r['video_ids']),r['video_ids'][0]))
    proposals=[]
    for r in records[:a.limit]:
        cap=cv2.VideoCapture(r['path']);sec=r['timestamps_sec'][0]
        cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000);ok,f=cap.read();actual=cap.get(cv2.CAP_PROP_POS_MSEC)/1000;cap.release()
        if not ok:raise ValueError(f'Cannot extract {r["path"]}')
        image=Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB));w,h=image.size
        # Crop removes empty foreground and enlarges hands/objects for the detector.
        image=image.crop((0,0,w,int(h*.78)))
        inputs=processor(images=image,text=prompt,return_tensors='pt').to(device)
        with torch.inference_mode():outputs=model(**inputs)
        result=processor.post_process_grounded_object_detection(outputs,inputs.input_ids,threshold=a.threshold,
                         text_threshold=.25,target_sizes=[(image.height,image.width)])[0]
        labels=result['text_labels'] if 'text_labels' in result else result['labels']
        boxes=[dict(label=str(label),score=float(score),xyxy=[float(v) for v in box])
               for label,score,box in zip(labels,result['scores'].cpu(),result['boxes'].cpu())
               if str(label) in classes]
        stem=f'X-{r["video_ids"][0]}_{sec}s'
        image_dir=ROOT/'annotations/images';image_dir.mkdir(parents=True,exist_ok=True)
        image.save(image_dir/(stem+'.jpg'))
        preview=image.copy();draw=ImageDraw.Draw(preview)
        for box in boxes:
            draw.rectangle(box['xyxy'],outline='red',width=2)
            draw.text((box['xyxy'][0],max(0,box['xyxy'][1]-10)),f'{box["label"]} {box["score"]:.2f}',fill='red')
        proposal_dir=ROOT/'annotations/proposals';proposal_dir.mkdir(parents=True,exist_ok=True)
        preview.save(proposal_dir/(stem+'.jpg'))
        proposals.append(dict(video_ids=r['video_ids'],sha256=r['sha256'],timestamp_sec=actual,
                              crop_xyxy=[0,0,w,int(h*.78)],image=str(image_dir/(stem+'.jpg')),
                              review_status='unreviewed',model='IDEA-Research/grounding-dino-tiny',prompt=prompt,boxes=boxes))
        print(stem,[(b['label'],round(b['score'],2)) for b in boxes],flush=True)
    save_json(ROOT/'annotations/proposals/grounding_dino.json',proposals)
    save_json(ROOT/'annotations/proposals/summary.json',dict(images=len(proposals),boxes=sum(len(p['boxes']) for p in proposals),
              elapsed_sec=time.time()-started,threshold=a.threshold,review_status='unreviewed',
              caveat='Mixed/unknown text labels filtered; false positives and missed objects still require manual review.'))

if __name__=='__main__':main()
