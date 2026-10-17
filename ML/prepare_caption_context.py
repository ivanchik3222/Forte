"""Follow-up input ablation: five higher-resolution frames with temporal context.

Reuses the already locked split/labels. Does not inspect or relabel any caption.
This is exploratory development after v1 evaluation, not an independent test.
"""
import argparse
import json
from pathlib import Path

import av
from PIL import Image

ROOT=Path(__file__).resolve().parent


def contextual_frames(row,folder):
    folder.mkdir(parents=True,exist_ok=True)
    samples=[]
    with av.open(row['source_path']) as container:
        stream=container.streams.video[0]
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else 0.
        duration=float(stream.duration*stream.time_base) if stream.duration else container.duration/1e6
        start=max(0.,row['start_sec']-.5);end=min(duration-.08,row['end_sec']+.5)
        requested=[start+(end-start)*f for f in [0.,.25,.5,.75,1.]]
        container.seek(max(0,int((start+origin)/stream.time_base)),stream=stream,backward=True)
        for frame in container.decode(stream):
            if frame.time is None:raise ValueError('Missing video PTS')
            timestamp=float(frame.time)-origin
            while len(samples)<len(requested) and timestamp+1e-6>=requested[len(samples)]:
                image=frame.to_image().convert('RGB');image.thumbnail((700,700),Image.Resampling.LANCZOS)
                path=folder/f'{len(samples)}.jpg';image.save(path,quality=92)
                samples.append(dict(path=str(path.resolve()),timestamp_sec=timestamp))
            if len(samples)==len(requested):break
    if len(samples)!=5:raise ValueError('Context frame extraction incomplete')
    return samples


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'annotations/caption_training')
    p.add_argument('--output',type=Path,default=ROOT/'annotations/caption_training/detail_v2')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    from training_split import read_split,assert_training_sources
    audit=json.loads((a.source/'audit.json').read_text());split=read_split()
    count=0
    for part in ('train','validation'):
        rows=[json.loads(line) for line in (a.source/f'{part}.jsonl').read_text().splitlines()]
        assert_training_sources([r['source_sha256'] for r in rows if r['source']=='bank_human_review'],split)
        for row in rows:
            if row['source']!='bank_human_review':continue
            row['frames']=contextual_frames(row,a.output/'frames'/row['id'])
            row['prompt']=row['prompt'].replace('three chronological frames','five chronological frames')
            row['prompt']+=(' The first and last frames may provide half a second of context. '
                f'Focus on an action in {row["start_sec"]:.2f}–{row["end_sec"]:.2f} seconds. '
                f'Frame times: {[round(f["timestamp_sec"],2) for f in row["frames"]]}.')
            count+=1
            if count%10==0:print(f'Prepared {count} contextual bank intervals',flush=True)
        (a.output/f'{part}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    audit['input_followup']='5 bank frames, max700px, +/-0.5 sec context; same source splits and labels'
    audit['exploratory_after_v1_evaluation']=True
    (a.output/'audit.json').write_text(json.dumps(audit,indent=2))
    print(f'Prepared {count} intervals; reserved tests unused',flush=True)


if __name__=='__main__':main()
