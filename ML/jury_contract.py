"""Validate a successful case response, including the actual JPEG payload."""
import base64
from io import BytesIO
import math

from PIL import Image


def success_errors(answer, job_id, duration):
    errors=[]
    def number(value):
        return type(value) in (int,float) and math.isfinite(value) and 0 <= value < duration
    if not isinstance(answer,dict): return ['Response is not an object']
    if answer.get('job_id') != job_id: errors.append('Wrong job_id')
    if answer.get('status') != 'done':
        return errors+['No successful case result: '+str(answer.get('error_code') or answer.get('status'))]
    verdict=answer.get('verdict')
    if verdict not in ('violation','no_violation'): errors.append('Missing two-class verdict')
    events=answer.get('violations')
    if not isinstance(events,list): return errors+['violations is not a list']
    if (verdict=='violation' and not events) or (verdict=='no_violation' and events):
        errors.append('Verdict contradicts events')
    for i,event in enumerate(events):
        if not isinstance(event,dict): errors.append(f'Event {i}: not an object'); continue
        for key in ('type','description'):
            if not isinstance(event.get(key),str) or not event[key].strip(): errors.append(f'Event {i}: missing {key}')
        if not number(event.get('timecode_sec')): errors.append(f'Event {i}: invalid timecode')
        frames=event.get('evidence_frames')
        if not isinstance(frames,list) or not 1 <= len(frames) <= 3:
            errors.append(f'Event {i}: requires 1–3 frames'); continue
        points=[]
        for j,frame in enumerate(frames):
            if not isinstance(frame,dict): errors.append(f'Event {i} frame {j}: not an object'); continue
            timestamp=frame.get('timestamp_sec')
            if not number(timestamp): errors.append(f'Event {i} frame {j}: invalid timestamp')
            else: points.append(timestamp)
            try:
                data=base64.b64decode(frame['image_base64'],validate=True)
                with Image.open(BytesIO(data)) as image:
                    if image.format!='JPEG': raise ValueError('Not JPEG')
                    image.verify()
            except (KeyError,TypeError,ValueError,OSError):
                errors.append(f'Event {i} frame {j}: not a valid base64 JPEG')
        if number(event.get('timecode_sec')) and not any(abs(p-event['timecode_sec'])<=.001 for p in points):
            errors.append(f'Event {i}: timecode does not identify an evidence frame')
        # The case requires source grounding in the UI; our API carries it as an extension.
        rule=event.get('rule')
        if not isinstance(rule,dict) or any(not isinstance(rule.get(k),str) or not rule[k].strip()
                                          for k in ('title','section','url','explanation')):
            errors.append(f'Event {i}: no normative grounding')
    return errors
