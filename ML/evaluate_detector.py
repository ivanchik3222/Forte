"""Evaluate on original holdouts; save metrics and per-image evidence locally."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image,ImageDraw
from train_detector import ROOT,local_yolo

COLORS=['cyan','red','lime','orange','magenta']


def overlap(a,b):
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    intersection=max(0.,x2-x1)*max(0.,y2-y1)
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0.


def fixed_counts(ground_truth,predictions,classes):
    counts={c:dict(tp=0,fp=0,fn=0) for c in classes}
    used=set()
    for p in sorted(predictions,key=lambda p:p['confidence'],reverse=True):
        candidates=[(overlap(p['xyxy'],g['xyxy']),i) for i,g in enumerate(ground_truth)
                    if i not in used and p['label']==g['label']]
        best=max(candidates,default=(0.,-1))
        if best[0]>=.5:
            counts[p['label']]['tp']+=1;used.add(best[1])
        else:
            counts[p['label']]['fp']+=1
    for i,g in enumerate(ground_truth):
        if i not in used:counts[g['label']]['fn']+=1
    return counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('weights',type=Path)
    parser.add_argument('--data',type=Path,default=ROOT/'datasets/cash_objects_v1')
    parser.add_argument('--split',choices=['train','val','test'],default='val')
    parser.add_argument('--name',default='detector_evaluation')
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--device',default=None)
    parser.add_argument('--confidence',type=float,default=.25)
    args=parser.parse_args()
    if args.device is None:
        args.device='0' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(4)
    YOLO=local_yolo();model=YOLO(str(args.weights))
    out=ROOT/'runs'/args.name
    if out.exists():raise FileExistsError(f'Choose new --name: {out}')
    metrics=model.val(data=str(args.data/'data.yaml'),split=args.split,imgsz=args.imgsz,
                      batch=5,device=args.device,workers=0,conf=.001,iou=.7,plots=True,
                      project=str(ROOT/'runs'),name=args.name,exist_ok=False,verbose=False)
    out=Path(metrics.save_dir)
    classes=[model.names[i] for i in sorted(model.names)]
    per_class={}
    for j,idx in enumerate(metrics.box.ap_class_index):
        per_class[classes[int(idx)]]=dict(map50=float(metrics.box.ap50[j]),map50_95=float(metrics.box.ap[j]))
    records=json.loads((args.data/'manifest.json').read_text(encoding='utf-8'))
    records=[r for r in records if r['split']==args.split]
    totals={c:dict(tp=0,fp=0,fn=0) for c in classes};evidence=[]
    previews=out/'predictions';previews.mkdir(exist_ok=True)
    for r in records:
        path=args.data/'images'/args.split/(r['name']+'.jpg')
        result=model.predict(str(path),imgsz=args.imgsz,device=args.device,conf=args.confidence,
                             iou=.7,verbose=False)[0]
        predictions=[dict(label=classes[int(c)],confidence=float(s),xyxy=b.tolist())
                     for b,s,c in zip(result.boxes.xyxy.cpu(),result.boxes.conf.cpu(),result.boxes.cls.cpu())]
        count=fixed_counts(r['boxes'],predictions,classes)
        for c in classes:
            for k in totals[c]:totals[c][k]+=count[c][k]
        evidence.append(dict(name=r['name'],predictions=predictions,ground_truth=r['boxes'],counts=count))
        with Image.open(path) as im:preview=im.convert('RGB')
        draw=ImageDraw.Draw(preview)
        for p in predictions:
            color=COLORS[classes.index(p['label'])];draw.rectangle(p['xyxy'],outline=color,width=2)
            x,y,_,_=p['xyxy'];draw.text((x,max(0,y-10)),f'{p["label"]} {p["confidence"]:.2f}',fill=color)
        preview.save(previews/(r['name']+'.jpg'),quality=95)
    for c,counts in totals.items():
        tp,fp,fn=counts['tp'],counts['fp'],counts['fn']
        counts['precision']=tp/(tp+fp) if tp+fp else 0.
        counts['recall']=tp/(tp+fn) if tp+fn else 0.
    tp=sum(v['tp'] for v in totals.values());fp=sum(v['fp'] for v in totals.values());fn=sum(v['fn'] for v in totals.values())
    summary=dict(split=args.split,images=len(records),weights=str(args.weights.resolve()),
                 weights_sha256=hashlib.sha256(args.weights.read_bytes()).hexdigest(),
                 map50=float(metrics.box.map50),map50_95=float(metrics.box.map),per_class_ap=per_class,
                 fixed_threshold=dict(confidence=args.confidence,iou=.5,per_class=totals,
                                      tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else 0.,
                                      recall=tp/(tp+fn) if tp+fn else 0.),
                 limitations=['Small holdout on the same camera','Object detection, not violation detection',
                              'Ground truth reviewed by Codex, not expert adjudication'])
    (out/'metrics.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (out/'predictions.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    # Compact sheets for comparing predictions with the already exported GT previews.
    for start in range(0,len(records),8):
        group=records[start:start+8];sheet=Image.new('RGB',(928,350*((len(group)+1)//2)),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(group):
            with Image.open(previews/(r['name']+'.jpg')) as src:im=src.convert('RGB')
            im.thumbnail((464,310));x=j%2*464;y=j//2*350;sheet.paste(im,(x,y+25));d.text((x+3,y+3),r['name'],fill='black')
        sheet.save(out/f'predictions_{start//8+1:02d}.jpg',quality=95)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
