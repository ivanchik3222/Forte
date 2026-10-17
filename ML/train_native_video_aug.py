"""Weak binary video-label pilot: train on augmented native clips, scan original VAL videos."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import av
import joblib
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipeline import ROOT, load_encoder, manifest as bank_manifest
from predict_objects import frames


def pooled(times,features):
    if len(times)==0:raise ValueError('No video features')
    dt=np.diff(times)
    if np.any(dt<=0):raise ValueError('Non-increasing feature timestamps')
    rate=np.mean(np.abs(np.diff(features,axis=0))/dt[:,None],axis=0) if len(dt) else np.zeros(features.shape[1])
    return np.concatenate([features.mean(0),features.std(0),features.max(0),rate]).astype(np.float32)


def encode_samples(samples,encoder,transform,device):
    times=[];features=[];batch=[]
    def flush():
        if batch:
            with torch.inference_mode():features.extend(encoder(torch.stack(batch).to(device)).cpu().numpy())
            batch.clear()
    for sec,rgb in samples:
        times.append(sec);batch.append(transform(Image.fromarray(rgb)))
        if len(batch)==32:flush()
    flush()
    return np.asarray(times,dtype=np.float32),np.asarray(features,dtype=np.float32)


def all_clip_frames(path):
    with av.open(str(path)) as video:
        stream=video.streams.video[0]
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else None
        for frame in video.decode(stream):
            if frame.time is None:raise ValueError('Missing clip PTS')
            if origin is None:origin=float(frame.time)
            yield float(frame.time)-origin,frame.to_ndarray(format='rgb24')


def balanced_group_weights(rows):
    counts=Counter(r['source_group'] for r in rows)
    weights=np.asarray([1/counts[r['source_group']] for r in rows],dtype=np.float64)
    labels=np.asarray([r['source_binary_label'] for r in rows])
    total=len(counts)
    for cls in (0,1):
        if not np.any(labels==cls):raise ValueError('Both binary labels required')
        weights[labels==cls]*=(total/2)/weights[labels==cls].sum()
    return weights


def metrics(rows):
    truth=[r['label'] for r in rows];pred=[int(r['score']>=.5) for r in rows]
    p,r,f,_=precision_recall_fscore_support(truth,pred,average='binary',zero_division=0)
    return dict(videos=len(rows),threshold=.5,precision=float(p),recall=float(r),f1=float(f),
                accuracy=float(accuracy_score(truth,pred)),tp=sum(a==b==1 for a,b in zip(truth,pred)),
                fp=sum(a==0 and b==1 for a,b in zip(truth,pred)),fn=sum(a==1 and b==0 for a,b in zip(truth,pred)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips',type=Path,default=ROOT/'datasets/cash_video_aug_v2')
    parser.add_argument('--out',type=Path,default=ROOT/'runs/native_video_aug_v2')
    parser.add_argument('--model-dir',type=Path,default=ROOT/'models/native_video_aug_v2')
    args=parser.parse_args()
    if args.out.exists() or args.model_dir.exists():raise FileExistsError('Choose new output/model directories')
    rows=json.loads((args.clips/'manifest.json').read_text(encoding='utf-8'))
    if any(r['split']!='train' for r in rows):raise ValueError('Only train clips accepted')
    bank=bank_manifest(ROOT/'open/open');by_sha={r['sha256']:r for r in bank}
    for row in rows:
        source=by_sha[row['source_video_sha256']]
        if row['source_binary_label']!=source['label']:
            raise ValueError('Clip binary label differs from source annotation')
        if source['label'] and not any(row['clip_start_source_sec']<=t<=row['clip_start_source_sec']+row['source_duration_sec']
                                       for t in source['timestamps_sec']):
            raise ValueError('Positive source clip lacks an annotated positive point; its label is unknown')
    native=json.loads((ROOT/'datasets/cash_objects_v1/manifest.json').read_text(encoding='utf-8'))
    val_rows=[r for r in native if r['split']=='val' and r['source']=='forte']
    heldout={r['source_group'] for r in native if r['split']!='train'}
    if any(r['source_group'] in heldout for r in rows):raise ValueError('Source-video leakage')
    encoder,transform,device=load_encoder();torch.set_num_threads(4)
    cache=ROOT/'cache/native_video_aug_v2';cache.mkdir(parents=True,exist_ok=True)
    vectors=[]
    for index,row in enumerate(rows):
        target=cache/(row['sha256']+'.npz')
        if target.exists():
            with np.load(target) as z:times=z['times'];features=z['features']
        else:
            times,features=encode_samples(all_clip_frames(args.clips/row['file_name']),encoder,transform,device)
            np.savez_compressed(target,times=times,features=features)
        vectors.append(pooled(times,features))
        if (index+1)%30==0:print('Encoded train clips',index+1,'/',len(rows),flush=True)
    x=np.asarray(vectors);y=np.asarray([r['source_binary_label'] for r in rows])
    val_cache={}
    for row in val_rows:
        raw=by_sha[row['source_sha256']];key=row['source_sha256'];roi=row['roi_xyxy']
        cached=cache/('val_'+key+'.npz')
        if cached.exists():
            with np.load(cached) as z:times=z['times'];features=z['features']
        else:
            def cropped_samples():
                for t,rgb in frames(Path(raw['path']),2.):
                    a,b,c,d=roi;yield t,rgb[b:d,a:c]
            times,features=encode_samples(cropped_samples(),encoder,transform,device)
            np.savez_compressed(cached,times=times,features=features)
        # Scan the entire VAL recording; annotated positive times do not choose evaluation windows.
        windows=np.asarray([pooled(times[np.abs(times-t)<=3],features[np.abs(times-t)<=3]) for t in times])
        val_cache[key]=(times,windows,raw)
        print('Encoded full VAL video',raw['video_ids'],len(times),flush=True)
    args.out.mkdir(parents=True);args.model_dir.mkdir(parents=True)
    report=dict(task='Source-provided binary video labels, not banking action classes',
                train_source_videos=len({r['source_group'] for r in rows}),val_source_videos=len(val_cache),
                encoder='Frozen ImageNet ResNet18',features='mean/std/max and absolute representation change per second',
                feature_dimensions=2048,validation='Full original VAL videos scanned at 2 FPS in +/-3 second windows; max score',
                results={},production_model_replaced=False,
                limitations=['Weak source binary labels; no action types, dense boxes or verified legal rules',
                             '10 validation recordings on the same camera; single seed, no fresh test',
                             'Max score over windows may increase false alarms on longer recordings',
                             'Frozen features + logistic head, not a fully trained video action network',
                             'No direct claim about cash detection precision or money concealment'])
    for name,selected in (('control',np.asarray([r['variant']=='original_12fps' for r in rows])),
                          ('augmented',np.ones(len(rows),dtype=bool))):
        train_rows=[r for r,keep in zip(rows,selected) if keep]
        weights=balanced_group_weights(train_rows)
        model=make_pipeline(StandardScaler(),LogisticRegression(C=.01,max_iter=2000,random_state=42))
        model.fit(x[selected],y[selected],standardscaler__sample_weight=weights,logisticregression__sample_weight=weights)
        prediction=[]
        for times,windows,raw in val_cache.values():
            scores=model.predict_proba(windows)[:,1];peak=int(scores.argmax())
            prediction.append(dict(video_ids=raw['video_ids'],label=raw['label'],score=float(scores[peak]),
                predicted_time_sec=float(times[peak]),annotated_points_sec=raw['timestamps_sec']))
        joblib.dump(model,args.model_dir/(name+'.joblib'))
        stats=metrics(prediction)
        report['results'][name]=dict(train_clips=len(train_rows),total_sample_weight=float(weights.sum()),metrics=stats,
            weights_sha256=hashlib.sha256((args.model_dir/(name+'.joblib')).read_bytes()).hexdigest())
        (args.out/(name+'_predictions.json')).write_text(json.dumps(prediction,indent=2),encoding='utf-8')
        print(name,json.dumps(stats),flush=True)
    report['source_manifest_sha256']=hashlib.sha256((args.clips/'manifest.json').read_bytes()).hexdigest()
    report['selected_by_val']=max(report['results'],key=lambda k:report['results'][k]['metrics']['f1'])
    (args.out/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (args.model_dir/'model_card.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
