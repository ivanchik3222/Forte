"""Train-only 6-second video variants; FPS preserves real time and source PTS mapping."""
import argparse
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image,ImageDraw

from augment_detection_v2 import ROOT, apply_view, variant_seed
from pipeline import manifest as bank_manifest

VARIANTS = [('original_2fps','original',2),('original_12fps','original',12),
            ('mirror_12fps','mirror',12),('grayscale_6fps','grayscale',6),
            ('scale_down_6fps','scale_down',6),('scale_up_12fps','scale_up',12)]


def resample_indices(source_times, desired_times):
    source_times=np.asarray(source_times)
    if not len(source_times) or np.any(np.diff(source_times)<=0):
        raise ValueError('Decoded source PTS must increase')
    indices=[]
    for t in desired_times:
        right=int(np.searchsorted(source_times,t))
        options=[i for i in (right-1,right) if 0<=i<len(source_times)]
        indices.append(min(options,key=lambda i:abs(source_times[i]-t)))
    return np.asarray(indices,dtype=int)


def decode_window(path, anchor, roi, length=6.):
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        if stream.duration is not None:duration=float(stream.duration*stream.time_base)
        elif container.duration is not None:duration=container.duration/av.time_base
        else:raise ValueError('Source duration unavailable')
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else float(next(container.decode(stream)).time)
        start=max(0.,min(anchor-length/2,max(0.,duration-length)))
        end=min(duration,start+length)
        container.seek(int((origin+start)/stream.time_base),stream=stream,backward=True)
        times=[];pixels=[]
        for frame in container.decode(stream):
            if frame.time is None:raise ValueError('Missing source PTS')
            sec=float(frame.time)-origin
            if sec<start-.05:continue
            if sec>end+.05:break
            rgb=frame.to_ndarray(format='rgb24');x1,y1,x2,y2=roi
            if not (0<=x1<x2<=rgb.shape[1] and 0<=y1<y2<=rgb.shape[0]):raise ValueError('ROI out of source image')
            times.append(sec);pixels.append(rgb[y1:y2,x1:x2].copy())
    if not times or not start<=anchor<=end:raise ValueError('Anchor outside clip')
    return np.asarray(times),pixels,start,end


def write_video(path, source_times, pixels, start, end, fps, variant, boxes, seed):
    target_times=np.arange(0,end-start-1e-7,1/fps)
    selected=resample_indices(source_times,start+target_times)
    mapping=[]
    with av.open(str(path),mode='w') as output:
        stream=output.add_stream('libx264',rate=fps)
        stream.width=pixels[0].shape[1];stream.height=pixels[0].shape[0]
        stream.pix_fmt='yuv420p';stream.options={'preset':'veryfast','crf':'23'}
        stream.codec_context.thread_count=2
        for index,(t,source_index) in enumerate(zip(target_times,selected)):
            # Reset the seed so geometry and photometric settings are coherent across the clip.
            image,_,matrix,params=apply_view(pixels[source_index],boxes,variant,np.random.default_rng(seed))
            frame=av.VideoFrame.from_ndarray(np.asarray(image),format='rgb24')
            frame.pts=index;frame.time_base=Fraction(1,fps)
            for packet in stream.encode(frame):output.mux(packet)
            mapping.append(dict(output_sec=float(t),source_sec=float(source_times[source_index])))
        for packet in stream.encode():output.mux(packet)
    return mapping,matrix,params


def export(source,output):
    if output.exists():raise FileExistsError(f'Choose a new output: {output}')
    source_rows=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    heldout={r['source_group'] for r in source_rows if r['split']!='train'}
    parents=[r for r in source_rows if r['split']=='train' and r['source']=='forte']
    sources={r['sha256']:r for r in bank_manifest(ROOT/'open/open')}
    output.mkdir(parents=True);(output/'train').mkdir();(output/'previews').mkdir()
    records=[]
    for parent in parents:
        if parent['source_group'] in heldout:raise ValueError('Source leakage')
        raw=sources[parent['source_sha256']]
        times,pixels,start,end=decode_window(Path(raw['path']),parent['timestamp_sec'],parent['roi_xyxy'])
        sheets=[]
        for name,variant,fps in VARIANTS:
            path=output/'train'/(parent['name']+'__'+name+'.mp4')
            seed=variant_seed(parent['name'],variant)
            mapping,matrix,params=write_video(path,times,pixels,start,end,fps,variant,parent['boxes'],seed)
            records.append(dict(name=path.stem,file_name=str(path.relative_to(output)),split='train',
                source_group=parent['source_group'],video_ids=parent['video_ids'],
                source_video_sha256=parent['source_sha256'],parent_frame=parent['name'],
                roi_xyxy=parent['roi_xyxy'],variant=name,transform=variant,augmentation_parameters=params,
                affine_from_source_roi=matrix,fps=fps,frames=len(mapping),
                clip_start_source_sec=start,source_duration_sec=end-start,
                anchor_source_sec=parent['timestamp_sec'],anchor_clip_sec=parent['timestamp_sec']-start,
                source_binary_label=raw['label'],
                source_frame_mapping=mapping,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                label_scope='Source binary point/video label only; no dense boxes or action intervals',
                training_use='Temporal assets; not passed to the frame YOLO trainer'))
            if len(sheets)<len(VARIANTS):
                with av.open(str(path)) as video:
                    target=(parent['timestamp_sec']-start)
                    for frame in video.decode(video.streams.video[0]):
                        if float(frame.time)+1e-5>=target:
                            sheets.append((name,frame.to_image()));break
        if len(records)<=len(VARIANTS)*2:
            sheet=Image.new('RGB',(464*3,340*2),'white');draw=ImageDraw.Draw(sheet)
            for i,(name,image) in enumerate(sheets):
                x=i%3*464;y=i//3*340;sheet.paste(image,(x,y+25));draw.text((x+4,y+4),name,fill='black')
            sheet.save(output/'previews'/(parent['name']+'.jpg'),quality=95)
        print('Video variants',parent['name'],len(VARIANTS),flush=True)
    summary=dict(clips=len(records),source_anchor_frames=len(parents),
        independent_source_videos=len({r['source_group'] for r in records}),
        variants=[r[0] for r in VARIANTS],fps_counts=dict(Counter(r['fps'] for r in records)),
        frames=sum(r['frames'] for r in records),val_test_processed=False,
        note='FPS resampling preserves event time; no dense labels invented; YOLO training uses reviewed image augmentations')
    (output/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'README.md').write_text('# Train-only video augmentation assets\n\n'
        'Six-second source-anchored MP4 clips at 2, 6 and 12 FPS. Original PTS mapping, source groups and fixed per-clip geometry are preserved. '
        'No val/test video is processed. Source binary labels are weak labels; there are no dense frame boxes or banking action intervals. '
        'Frame detector training uses cash_objects_aug_v2, not arbitrary frames of these clips.\n',encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'datasets/cash_objects_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'datasets/cash_video_aug_v2')
    args=parser.parse_args();export(args.source,args.output)
