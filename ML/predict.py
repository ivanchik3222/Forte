"""Offline binary candidate inference; does not fabricate a legal rule or event type."""
import argparse
import pickle
import time
from pathlib import Path
import numpy as np
from pipeline import ROOT,load_encoder,extract,contextual,save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('video',type=Path);p.add_argument('--output',type=Path,default=ROOT/'runs/prediction.json')
    p.add_argument('--threshold',type=float,default=.5);a=p.parse_args();started=time.time()
    # Only load this project's locally trained artifact; never load untrusted pickle files.
    with (ROOT/'runs/baseline/classifier.pkl').open('rb') as f:head=pickle.load(f)
    model,transform,device=load_encoder();times,features=extract(a.video,model,transform,device)
    scores=head.predict_proba(contextual(times,features,times))[:,1]
    hits=np.flatnonzero(scores>=a.threshold);groups=[]
    for i in hits:
        if not groups or times[i]-times[groups[-1][-1]]>1.5:groups.append([])
        groups[-1].append(int(i))
    events=[]
    for group in groups:
        idx=max(group,key=lambda i:scores[i])
        events.append(dict(timecode_sec=float(times[idx]),score=float(scores[idx]),
                           start_sec=float(times[group[0]]),end_sec=float(times[group[-1]]),
                           type=None,rule_id=None,requires_review=True))
    save_json(a.output,dict(video=str(a.video.resolve()),candidate_verdict='violation' if events else 'no_violation',
                           events=events,elapsed_sec=time.time()-started,
                           warning='Experimental binary candidates, not final API output or confirmed legal violations.'))
    print(a.output)

if __name__=='__main__':main()
