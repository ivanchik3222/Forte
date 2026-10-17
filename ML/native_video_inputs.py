"""Qwen3-VL native video tokens, paired temporal patches, and explicit timestamps.

Uses local PyAV video frames only; never audio or an external inference service.
"""
import math
from pathlib import Path

import av
import numpy as np
from PIL import Image


def sample_video_interval(source,start_sec,end_sec,fps=4.,max_frames=24,max_side=560):
    with av.open(str(source)) as container:
        stream=container.streams.video[0]
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else 0.
        duration=float(stream.duration*stream.time_base) if stream.duration else container.duration/1e6
        source_fps=float(stream.average_rate)
        start=max(0.,start_sec-.5);end=min(duration-.08,end_sec+.5)
        if end<start or source_fps<=0:raise ValueError('Invalid video interval')
        count=min(max_frames,max(4,2*math.ceil(((end-start)*fps+1)/2)))
        requested=np.linspace(start,end,count);images=[];timestamps=[]
        container.seek(max(0,int((start+origin)/stream.time_base)),stream=stream,backward=True)
        for frame in container.decode(stream):
            if frame.time is None:raise ValueError('Missing frame PTS')
            timestamp=float(frame.time)-origin
            while len(images)<count and timestamp+1e-6>=requested[len(images)]:
                image=frame.to_image().convert('RGB');image.thumbnail((max_side,max_side),Image.Resampling.LANCZOS)
                images.append(np.asarray(image));timestamps.append(timestamp)
            if len(images)==count:break
        if len(images)!=count:raise ValueError('Missing native-video samples')
        metadata=dict(total_num_frames=stream.frames or round(duration*source_fps),fps=source_fps,duration=duration,
            frames_indices=[round(t*source_fps) for t in timestamps],video_backend='pyav')
    # Processor timestamps quantize PTS to the source frame grid (<= half a frame).
    # Exact decoded PTS remain separately available for evidence and reporting.
    return np.stack(images),metadata,timestamps


def prepare_video_prompt(processor,source,start_sec,end_sec,prompt,response=None):
    video,metadata,timestamps=sample_video_interval(source,start_sec,end_sec)
    formatted,batch=encode_video_frames(processor,video,metadata,prompt,response)
    return formatted,batch,timestamps


def encode_video_frames(processor,video,metadata,prompt,response=None):
    import mlx.core as mx
    messages=[dict(role='user',content=[dict(type='video'),dict(type='text',text=prompt)])]
    formatted=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    if response is not None:formatted+=response+processor.tokenizer.eos_token
    inputs=processor(text=[formatted],videos=[video],video_metadata=[metadata],
        do_sample_frames=False,cap_pixels_per_frame=False,padding=True,return_tensors='np')
    batch=dict(input_ids=mx.array(inputs['input_ids']),pixel_values=mx.array(inputs['pixel_values_videos']),
        mask=mx.array(inputs['attention_mask']),video_grid_thw=mx.array(inputs['video_grid_thw']))
    return formatted,batch
