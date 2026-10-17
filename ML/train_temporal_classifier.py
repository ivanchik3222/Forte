"""Train point-supervised binary heads on frozen pretrained 3D motion features."""
import argparse
from collections import Counter
import copy
import hashlib
from html import escape
import json
from pathlib import Path
import random
import time

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,average_precision_score,precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import torch

from pipeline import manifest
from temporal_classifier import ROOT,CONFIG,VARIANTS,R3DEncoder,positive_mask,scores


def stats(rows,threshold=.5):
    y=np.asarray([r['label'] for r in rows]);pred=np.asarray([r['score']>=threshold for r in rows])
    p,r,f,_=precision_recall_fscore_support(y,pred,average='binary',zero_division=0)
    errors=[min(abs(row['predicted_time_sec']-t) for t in row['annotated_points_sec']) for row in rows if row['label']]
    return dict(videos=len(rows),threshold=threshold,accuracy=float(accuracy_score(y,pred)),precision=float(p),recall=float(r),f1=float(f),
        average_precision=float(average_precision_score(y,[r['score'] for r in rows])),
        tp=int(sum((y==1)&pred)),fp=int(sum((y==0)&pred)),fn=int(sum((y==1)&~pred)),tn=int(sum((y==0)&~pred)),
        localization_mae_positive_sec=float(np.mean(errors)) if errors else None,
        localization_within_2sec=float(np.mean(np.asarray(errors)<=2)) if errors else None)


def predictions(head,rows,cache):
    result=[]
    for row in rows:
        times,features=cache[row['sha256']]
        values=scores(head,features);peak=int(values.argmax())
        result.append(dict(video_ids=row['video_ids'],sha256=row['sha256'],split=row['split'],label=row['label'],
            score=float(values[peak]),predicted_time_sec=float(times[peak]),annotated_points_sec=row['timestamps_sec']))
    return result


def rank(metrics):
    return metrics['f1'],metrics['precision'],metrics['average_precision']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'runs/temporal_classifier_v1')
    parser.add_argument('--models',type=Path,default=ROOT/'models/temporal_classifier_v1')
    parser.add_argument('--epochs',type=int,default=200)
    args=parser.parse_args()
    if args.output.exists() or args.models.exists(): raise FileExistsError('Choose fresh run/model paths')
    args.output.mkdir(parents=True);args.models.mkdir(parents=True)
    random.seed(42);np.random.seed(42);torch.manual_seed(42)
    started=time.perf_counter()
    records=manifest(ROOT/'open/open')
    native=json.loads((ROOT/'datasets/cash_objects_v1/manifest.json').read_text(encoding='utf-8'))
    split={r['source_sha256']:r['split'] for r in native if r['source']=='forte'}
    for row in records: row['split']=split[row['sha256']]
    train=[r for r in records if r['split']=='train'];val=[r for r in records if r['split']=='val'];test=[r for r in records if r['split']=='test']
    assert len(train)==24 and len(val)==10 and len(test)==6
    assert len({r['sha256'] for r in records})==len(records)
    encoder=R3DEncoder();cache_dir=ROOT/'cache/r3d_native_v1';cache_dir.mkdir(parents=True,exist_ok=True)
    cache={};bags=[]
    def extract(row,variant='original',centers=None):
        identity=dict(source_sha256=row['sha256'],config=CONFIG,encoder_sha256=encoder.sha256,
            variant=variant,selected_centers=centers.tolist() if centers is not None else None)
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        path=cache_dir/(key+'.npz')
        if path.exists():
            with np.load(path) as saved: times=saved['times'];features=saved['features']
        else:
            times,features=encoder.encode(Path(row['path']),variant,centers)
            np.savez_compressed(path,times=times,features=features)
            path.with_suffix('.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
        return times,features
    for i,row in enumerate(train+val,1):
        times,features=extract(row);cache[row['sha256']]=(times,features)
        if row['split']=='train':
            selected=positive_mask(times,row['timestamps_sec']) if row['label'] else np.ones(len(times),dtype=bool)
            bags.append(dict(source_group=row['sha256'],label=row['label'],variant='original',features=features[selected]))
            for variant in VARIANTS[1:]:
                _,augmented=extract(row,variant,times[selected])
                bags.append(dict(source_group=row['sha256'],label=row['label'],variant=variant,features=augmented))
        print(f'Encoded train/val {i}/{len(train+val)} ids={row["video_ids"]} clips={len(times)}',flush=True)
    # Each original source gets the same weight; positive unknown intervals are excluded.
    source_counts=Counter(b['source_group'] for b in bags)
    x=np.concatenate([b['features'] for b in bags]);y=np.concatenate([np.full(len(b['features']),b['label']) for b in bags])
    sample_weights=np.concatenate([np.full(len(b['features']),1/(source_counts[b['source_group']]*len(b['features']))) for b in bags])
    assert abs(sample_weights.sum()-len(train))<1e-6
    baseline=make_pipeline(StandardScaler(),LogisticRegression(C=.01,max_iter=2000,random_state=42))
    baseline.fit(x,y,standardscaler__sample_weight=sample_weights,logisticregression__sample_weight=sample_weights)
    common=dict(config=CONFIG,encoder_sha256=encoder.sha256,threshold=.5,seed=42,
        task='Source binary labels only; action type/cause/rule are not annotated')
    logistic=dict(common,kind='logistic',model=baseline)
    joblib.dump(logistic,args.models/'logistic.joblib')
    scaler=StandardScaler().fit(x,sample_weight=sample_weights)
    tensor_bags=[(torch.tensor(scaler.transform(b['features']),dtype=torch.float32),torch.tensor(float(b['label']))) for b in bags]
    head=torch.nn.Linear(512,1);torch.nn.init.zeros_(head.weight);torch.nn.init.zeros_(head.bias)
    optimizer=torch.optim.AdamW(head.parameters(),lr=.001,weight_decay=.01)
    criterion=torch.nn.BCEWithLogitsLoss();history=[];best=None;best_key=None
    def pack(epoch):
        return dict(common,kind='point_mil_linear',mean=scaler.mean_.astype(np.float32),std=scaler.scale_.astype(np.float32),
            weight=head.weight.detach().numpy()[0].copy(),bias=float(head.bias.detach()[0]),epoch=epoch)
    for epoch in range(1,args.epochs+1):
        optimizer.zero_grad();losses=[]
        for features,label in tensor_bags:
            logits=head(features).flatten()
            loss=criterion(logits.max(),label)
            if label.item()==1: loss=loss+.25*criterion(logits,torch.ones_like(logits))
            losses.append(loss)
        loss=torch.stack(losses).mean();loss.backward();optimizer.step()
        if epoch==1 or epoch%5==0 or epoch==args.epochs:
            candidate=pack(epoch);pred=predictions(candidate,val,cache);metric=stats(pred)
            history.append(dict(epoch=epoch,loss=float(loss.detach()),validation=metric))
            if best_key is None or rank(metric)>best_key:
                best_key=rank(metric);best=copy.deepcopy(candidate)
            if epoch%25==0: print('MIL epoch',epoch,'loss',round(float(loss.detach()),5),'val',json.dumps(metric),flush=True)
    joblib.dump(pack(args.epochs),args.models/'mil_last.joblib')
    joblib.dump(best,args.models/'mil_best.joblib')
    candidates={'logistic':logistic,'point_mil':best};validation={}
    for name,candidate in candidates.items():
        rows=predictions(candidate,val,cache);validation[name]=stats(rows)
        (args.output/(name+'_val_predictions.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
    selected=max(candidates,key=lambda name:rank(validation[name]));final=candidates[selected]
    joblib.dump(final,args.models/'best.joblib')
    print('Selected on VAL:',selected,json.dumps(validation),flush=True)
    # TEST is decoded/scored only after selection; no threshold adjustment on test.
    for row in test:
        cache[row['sha256']]=extract(row)
        print('Encoded final TEST',row['video_ids'],flush=True)
    all_predictions=predictions(final,records,cache)
    metrics={s:stats([r for r in all_predictions if r['split']==s]) for s in ('train','val','test')}
    card=dict(task=common['task'],architecture='Frozen torchvision R3D-18 Kinetics-400 + '+final['kind'],
        selected_by='VAL video F1, then precision, then average precision; threshold fixed 0.5',
        selected=selected,selected_epoch=final.get('epoch'),config=CONFIG,variants_train_only=list(VARIANTS),
        encoder_sha256=encoder.sha256,head_sha256=hashlib.sha256((args.models/'best.joblib').read_bytes()).hexdigest(),
        pretrained_url='https://download.pytorch.org/models/r3d_18-b3b3357e.pth',
        training_sources=len(train),validation_sources=len(val),test_sources=len(test),
        training_feature_windows=len(x),training_effective_source_weight=float(sample_weights.sum()),
        validation_candidates=validation,metrics=metrics,elapsed_seconds=round(time.perf_counter()-started,3),
        source_label_counts={s:dict(Counter(r['label'] for r in records if r['split']==s)) for s in ('train','val','test')},
        classifier_trained=True,event_type_trained=False,reason_trained=False,rule_trained=False,case_ready=False,
        limitations=['Only 40 unique staged videos, same camera, one seed; six-video test is very small',
            'Existing val/test were examined in prior experiments; this is not a fresh hidden holdout',
            'No event types or normative applicability labels; binary score cannot supply legal grounding',
            'Max pooling can cause false alarms; output score is not calibrated',
            'Native ROI only; unknown camera angles unsupported',
            'No face recognition, no identity document or hand-oscillation supervision'])
    (args.models/'model_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'metrics.json').write_text(json.dumps(card,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'all_unique_predictions.json').write_text(json.dumps(all_predictions,indent=2),encoding='utf-8')
    (args.output/'learning_history.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
    print(json.dumps(card,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
