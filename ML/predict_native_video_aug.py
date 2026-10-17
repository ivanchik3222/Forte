"""Offline scan with a saved weak binary video head; no legal/action conclusions."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np

from pipeline import load_encoder
from predict_objects import frames
from train_native_video_aug import encode_samples, pooled


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fps',type=float,default=2.)
    parser.add_argument('--roi',type=int,nargs=4,default=[0,300,464,610])
    args=parser.parse_args()
    if args.fps<=0:raise ValueError('FPS must be positive')
    began=time.perf_counter();encoder,transform,device=load_encoder()
    def samples():
        for t,rgb in frames(args.source,args.fps):
            a,b,c,d=args.roi
            if not (0<=a<c<=rgb.shape[1] and 0<=b<d<=rgb.shape[0]):raise ValueError('ROI outside frame')
            yield t,rgb[b:d,a:c]
    times,features=encode_samples(samples(),encoder,transform,device)
    windows=np.asarray([pooled(times[np.abs(times-t)<=3],features[np.abs(times-t)<=3]) for t in times])
    model=joblib.load(args.model)
    scores=model.predict_proba(windows)[:,1];peak=int(scores.argmax())
    report=dict(source=str(args.source.resolve()),model=str(args.model.resolve()),
        model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
        sampled_fps=args.fps,roi_xyxy=args.roi,frames=len(times),score=float(scores[peak]),
        predicted_time_sec=float(times[peak]),threshold=.5,source_label_1_predicted=bool(scores[peak]>=.5),
        window_scores=[dict(timestamp_sec=float(t),score=float(s)) for t,s in zip(times,scores)],
        elapsed_seconds=round(time.perf_counter()-began,3),
        note='Weak source binary label score; no cash visibility, banking action or confirmed violation conclusion')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='window_scores'},ensure_ascii=False,indent=2))
