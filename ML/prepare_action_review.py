"""Prepare unreviewed action tasks; binary video labels never label ID/tremor."""
import argparse
from collections import Counter
import json
from pathlib import Path

import av
from pipeline import ROOT, manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'annotations/action_review/tasks.json')
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Will not overwrite action annotations')
    records=manifest(ROOT/'open/open')
    native=json.loads((ROOT/'datasets/cash_objects_v1/manifest.json').read_text(encoding='utf-8'))
    splits={r['source_sha256']:r['split'] for r in native if r['source']=='forte'}
    tasks=[]
    for row in records:
        with av.open(row['path']) as video:
            stream=video.streams.video[0]
            fps=float(stream.average_rate) if stream.average_rate else None
            duration=float(video.duration/av.time_base) if video.duration else None
        checks={}
        for kind in ('identity_document_presentation','customer_hand_oscillation'):
            checks[kind]=dict(status='unreviewed',intervals=[],evidence_frames=[],
                customer_role_verified=False,visibility='unreviewed',notes='')
        tasks.append(dict(video_ids=row['video_ids'],source_sha256=row['sha256'],
            source_file=Path(row['path']).name,split=splits[row['sha256']],duration_sec=duration,original_fps=fps,
            source_binary_label=row['label'],source_positive_points_sec=row['timestamps_sec'],
            source_label_does_not_label_additional_checks=True,
            transaction_intervals=[],checks=checks,review_status='unreviewed'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(tasks,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(unique_video_tasks=len(tasks),original_video_ids=sum(len(t['video_ids']) for t in tasks),
        splits=dict(Counter(t['split'] for t in tasks)),checks_per_task=2,
        labelled_action_intervals=0,status='unreviewed; no generated ground truth',
        source_binary_labels_are_not_identity_or_hand_oscillation_labels=True)
    args.output.with_name('summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
