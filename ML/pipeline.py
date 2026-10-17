"""Local point-supervised baseline. No legal/type labels are inferred from binary labels."""
import argparse
import hashlib
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torchvision.models import resnet18, ResNet18_Weights

ROOT = Path(__file__).resolve().parent
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def manifest(data):
    with zipfile.ZipFile(data/'open_labels.xlsx') as z:
        xml = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        records = []
        for row in xml.findall('.//s:row', NS)[1:]:
            cells = {}
            for c in row.findall('s:c', NS):
                value = ''.join(c.itertext())
                cells[re.sub(r'\d+', '', c.attrib['r'])] = shared[int(value)] if c.attrib.get('t') == 's' else value
            if not cells.get('A'): continue
            vid = int(re.search(r'\d+', cells['A']).group())
            label = cells.get('C', '').strip()
            if label not in ('нарушение', 'без нарушения'):
                raise ValueError(f'Unknown label: {cells}')
            parts = [int(v) for v in re.findall(r'\d+', cells.get('B',''))]
            timestamp = (parts[0]*60+parts[1] if len(parts)==2 else parts[0]) if parts else None
            if label == 'нарушение' and timestamp is None: raise ValueError(f'Missing timestamp: {vid}')
            records.append(dict(video_id=vid,label=int(label=='нарушение'),timestamp_sec=timestamp))
    files = {int(re.search(r'\d+',p.stem).group()):p for p in (data/'videos').glob('*.mov')}
    grouped = {}
    for row in records:
        path=files.pop(row['video_id'])
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in grouped:
            grouped[digest]=dict(sha256=digest,path=str(path.resolve()),label=row['label'],video_ids=[],timestamps_sec=[],
                                 appearance_group='pink' if row['video_id']<=32 or row['video_id']>=47 else 'white')
        record=grouped[digest]
        if row['label'] != record['label']: raise ValueError('Conflicting labels for duplicate video')
        record['video_ids'].append(row['video_id'])
        if row['timestamp_sec'] is not None: record['timestamps_sec'].append(row['timestamp_sec'])
    if files: raise ValueError(f'Unlabelled files: {files}')
    result=list(grouped.values())
    for r in result:r['timestamps_sec']=sorted(set(r['timestamps_sec']))
    return result


def load_encoder():
    torch.set_num_threads(4)
    weights_path=ROOT/'models/resnet18-f37072fd.pth'
    if not weights_path.exists():
        raise FileNotFoundError('Run download_models.py --resnet first; inference never downloads weights.')
    model=resnet18(weights=None)
    model.load_state_dict(torch.load(weights_path,map_location='cpu',weights_only=True))
    model.fc=torch.nn.Identity()
    device='cuda' if torch.cuda.is_available() else 'cpu'
    return model.eval().to(device),ResNet18_Weights.IMAGENET1K_V1.transforms(),device


def extract(path, model, transform, device, fps=2.0):
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened(): raise ValueError(f'Cannot decode {path}')
    duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS)
    times=[];features=[];batch=[];batch_times=[]
    def flush():
        if not batch:return
        with torch.inference_mode():
            vectors=model(torch.stack(batch).to(device)).cpu().numpy().reshape(-1,1024)
        features.extend(vectors);times.extend(batch_times);batch.clear();batch_times.clear()
    for sec in np.arange(0,duration,1/fps):
        cap.set(cv2.CAP_PROP_POS_MSEC,float(sec*1000))
        ok,frame=cap.read()
        if not ok: continue
        # Record decoder position rather than estimating timestamp from a rounded FPS.
        actual=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
        image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        w,h=image.size
        # General upper-scene crop; cash desk moves with camera so this is only a baseline.
        crop=image.crop((0,0,w,int(h*.78)))
        batch.extend([transform(image),transform(crop)])
        batch_times.append(actual)
        if len(batch)>=32:flush()
    flush();cap.release()
    if not times:raise ValueError('No frames extracted')
    return np.asarray(times,dtype=np.float32),np.asarray(features,dtype=np.float32)


def contextual(times, features, centers):
    result=[]
    for t in centers:
        f=features[np.abs(times-t)<=2.0]
        if not len(f):f=features[[np.argmin(np.abs(times-t))]]
        motion=np.abs(np.diff(f,axis=0)).mean(0) if len(f)>1 else np.zeros(f.shape[1])
        result.append(np.concatenate([f.mean(0),f.std(0),f.max(0),motion]))
    return np.asarray(result,dtype=np.float32)


def train_samples(records, cache):
    xs=[];ys=[];ws=[]
    for r in records:
        times,features=cache[r['sha256']]
        # Unmarked parts of positive videos are UNKNOWN, never used as negatives.
        centers=np.asarray([t+d for t in r['timestamps_sec'] for d in [-.5,0,.5]]) if r['label'] else times[::4]
        x=contextual(times,features,centers)
        xs.extend(x);ys.extend([r['label']]*len(x));ws.extend([1/len(x)]*len(x))
    # Balance total weight by class, while giving equal weight to each source video.
    y=np.asarray(ys);w=np.asarray(ws)
    for k in [0,1]:w[y==k]/=w[y==k].sum()
    w*=len(w)/2
    return np.asarray(xs),y,w


def fit(records,cache):
    x,y,w=train_samples(records,cache)
    model=make_pipeline(StandardScaler(),LogisticRegression(C=.01,max_iter=2000,random_state=42))
    model.fit(x,y,logisticregression__sample_weight=w)
    return model


def predict_record(model,r,cache):
    times,features=cache[r['sha256']]
    scores=model.predict_proba(contextual(times,features,times))[:,1]
    idx=int(scores.argmax())
    return dict(video_ids=r['video_ids'],label=r['label'],score=float(scores[idx]),predicted_time_sec=float(times[idx]),
                annotated_times_sec=r['timestamps_sec'],appearance_group=r['appearance_group'])


def metrics(predictions):
    y=[r['label'] for r in predictions];yp=[int(r['score']>=.5) for r in predictions]
    p,r,f,_=precision_recall_fscore_support(y,yp,average='binary',zero_division=0)
    errors=[min(abs(v['predicted_time_sec']-t) for t in v['annotated_times_sec']) for v in predictions if v['label']]
    return dict(n_videos=len(y),threshold=.5,accuracy=float(accuracy_score(y,yp)),precision=float(p),recall=float(r),f1=float(f),
                confusion_matrix_labels_0_1=confusion_matrix(y,yp,labels=[0,1]).tolist(),
                localization_mae_positive_videos_sec=float(np.mean(errors)),
                localization_within_2s=float(np.mean(np.asarray(errors)<=2)))


def run(args):
    started=time.time();records=manifest(args.data)
    save_json(ROOT/'annotations/manifest.json',records)
    cache_dir=ROOT/'cache/resnet18_2fps_v1';cache_dir.mkdir(parents=True,exist_ok=True)
    encoder=transform=device=None;cache={}
    for i,r in enumerate(records):
        dest=cache_dir/(r['sha256']+'.npz')
        if not dest.exists():
            if encoder is None:encoder,transform,device=load_encoder()
            times,features=extract(r['path'],encoder,transform,device)
            np.savez_compressed(dest,times=times,features=features)
        with np.load(dest) as z:cache[r['sha256']]=(z['times'],z['features'])
        if any(t>cache[r['sha256']][0][-1]+1 for t in r['timestamps_sec']):raise ValueError('Timestamp exceeds decoded video')
        print(f'features {i+1}/{len(records)} ids={r["video_ids"]}',flush=True)
    # Deduplication happens BEFORE splitting. This evaluation still shares the camera/background.
    splitter=StratifiedKFold(n_splits=5,shuffle=True,random_state=42)
    oof=[]
    for fold,(tr,va) in enumerate(splitter.split(records,[r['label'] for r in records])):
        model=fit([records[i] for i in tr],cache)
        oof.extend([dict(predict_record(model,records[i],cache),fold=fold) for i in va])
        print(f'fold {fold+1}/5 complete',flush=True)
    # Harder split by visible attire/session, not face identity. No threshold tuning on this holdout.
    tr=[r for r in records if r['appearance_group']=='pink'];va=[r for r in records if r['appearance_group']=='white']
    cross_model=fit(tr,cache)
    cross=[predict_record(cross_model,r,cache) for r in va]
    final=fit(records,cache)
    import pickle
    run_dir=ROOT/'runs/baseline';run_dir.mkdir(parents=True,exist_ok=True)
    with (run_dir/'classifier.pkl').open('wb') as f:pickle.dump(final,f)
    report=dict(backbone='ResNet18 ImageNet1K V1 frozen',head='StandardScaler + LogisticRegression C=0.01',
                unique_videos=len(records),point_supervision_radius_sec=.5,context_radius_sec=2,sample_fps=2,
                oof_same_scene=metrics(oof),appearance_holdout_pink_to_white=metrics(cross),
                elapsed_sec=time.time()-started,
                limitations=['Binary candidate detector, no legal/type classification','Point supervision is incomplete',
                             'Same camera; OOF score is optimistic for unseen cameras','Threshold fixed at 0.5, not calibrated',
                             'Final model trained on all unique videos; evaluate using OOF/holdout predictions only'])
    save_json(run_dir/'metrics.json',report);save_json(run_dir/'oof_predictions.json',oof);save_json(run_dir/'appearance_holdout_predictions.json',cross)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=ROOT/'open/open')
    run(parser.parse_args())
