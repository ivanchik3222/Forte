"""Offline image/video object detection with original-pixel boxes and video PTS."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from train_detector import ROOT,local_yolo

COLORS=['cyan','red','lime','orange','magenta']


def frames(path,fps):
    if path.suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp'}:
        with Image.open(path) as image:
            yield 0.,np.asarray(image.convert('RGB'))
        return
    import av
    with av.open(str(path)) as video:
        stream=video.streams.video[0]
        next_time=0.
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else None
        for frame in video.decode(stream):
            if frame.time is None:
                raise ValueError('Video frame has no PTS timestamp')
            if origin is None:origin=float(frame.time)
            timestamp=float(frame.time)-origin
            if timestamp+1e-6>=next_time:
                yield timestamp,frame.to_ndarray(format='rgb24')
                next_time=(int(timestamp*fps)+1)/fps


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--weights',type=Path,default=ROOT/'models/cash_detector/best.pt')
    parser.add_argument('--output',type=Path,default=ROOT/'runs/object_prediction')
    parser.add_argument('--roi',type=int,nargs=4,default=None,metavar=('X1','Y1','X2','Y2'))
    parser.add_argument('--fps',type=float,default=2.)
    parser.add_argument('--confidence',type=float,default=.25)
    parser.add_argument('--nms-iou',type=float,default=.7)
    parser.add_argument('--device',default=None)
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--max-frames',type=int,default=0)
    args=parser.parse_args()
    if args.fps<=0 or not 0<args.confidence<=1 or not 0<args.nms_iou<=1:raise ValueError('Invalid FPS/confidence/NMS IoU')
    device=args.device or ('0' if torch.cuda.is_available() else 'cpu')
    began=time.perf_counter();YOLO=local_yolo();model=YOLO(str(args.weights))
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[];preview_count=0
    for timestamp,rgb in frames(args.source,args.fps):
        height,width=rgb.shape[:2];roi=args.roi or [0,0,width,height]
        x1,y1,x2,y2=roi
        if not (0<=x1<x2<=width and 0<=y1<y2<=height):raise ValueError('ROI outside source frame')
        # Ultralytics accepts PIL RGB; ndarray inputs would be interpreted as BGR.
        crop=Image.fromarray(rgb[y1:y2,x1:x2])
        prediction=model.predict(crop,imgsz=args.imgsz,device=device,conf=args.confidence,iou=args.nms_iou,verbose=False)[0]
        boxes=[]
        for b,score,cls in zip(prediction.boxes.xyxy.cpu(),prediction.boxes.conf.cpu(),prediction.boxes.cls.cpu()):
            left,top,right,bottom=b.tolist();class_id=int(cls)
            boxes.append(dict(class_id=class_id,label=model.names[class_id],confidence=round(float(score),5),
                              xyxy=[round(left+x1,2),round(top+y1,2),round(right+x1,2),round(bottom+y1,2)]))
        rows.append(dict(timestamp_sec=timestamp,boxes=boxes))
        # A few local evidence images; JSON retains every sampled frame.
        if preview_count<8 and timestamp>=preview_count*20:
            preview=Image.fromarray(rgb);draw=ImageDraw.Draw(preview)
            draw.rectangle(roi,outline='white',width=1)
            for b in boxes:
                color=COLORS[b['class_id']];draw.rectangle(b['xyxy'],outline=color,width=2)
                left,top,_,_=b['xyxy'];draw.text((left,max(0,top-10)),f'{b["label"]} {b["confidence"]:.2f}',fill=color)
            preview.save(args.output/f'frame_{timestamp:07.2f}.jpg',quality=95);preview_count+=1
        if args.max_frames and len(rows)>=args.max_frames:break
    report=dict(source=str(args.source.resolve()),weights=str(args.weights.resolve()),device=device,
                roi_xyxy=args.roi,sampled_fps=args.fps,confidence=args.confidence,nms_iou=args.nms_iou,
                coordinate_system='original image pixels',timestamp_source='PyAV frame PTS minus stream start for video',
                processed_frames=len(rows),elapsed_seconds=round(time.perf_counter()-began,3),frames=rows,
                note='Object detections only; no violation labels or legal conclusions')
    (args.output/'predictions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='frames'},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
