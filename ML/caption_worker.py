"""Optional isolated MLX caption engine for the existing authenticated worker.

No fabricated detector confidence, bounding boxes, binary verdict or legal rule.
The subprocess has an actual wall-clock timeout; partial coverage stays explicit.
"""
import base64
import hashlib
import json
import subprocess
from pathlib import Path


def convert_report(report,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    assessed = report.get('rule_evaluation') == 'performed'
    if report.get('automatic_violation_detection') is not assessed or report.get('status') not in ('done','partial'):
        raise ValueError('Unexpected local observation report')
    evidence=[];events=[];seen={}
    for row in report['observations']:
        indices=[]
        if not 0<=row['start_sec']<=row['end_sec']<=report['duration_sec']:
            raise ValueError('Observation outside video')
        for frame in row['evidence_frames']:
            timestamp=frame['timestamp_sec']
            if not row['start_sec']-1e-6<=timestamp<=row['end_sec']+1e-6:
                raise ValueError('Evidence outside observation')
            data=base64.b64decode(frame['image_base64'],validate=True)
            if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                raise ValueError('Evidence is not JPEG')
            key=(timestamp,hashlib.sha256(data).hexdigest())
            if key not in seen:
                index=len(evidence);name=f'evidence-{index:03d}.jpg'
                (output/name).write_bytes(data);seen[key]=index
                evidence.append(dict(timestamp_sec=timestamp,image_file=name,boxes=[]))
            indices.append(seen[key])
        events.append(dict(kind=row['kind'],description=row['description'],start_sec=row['start_sec'],end_sec=row['end_sec'],
            mean_detector_confidence=None,evidence_indices=indices,requires_human_review=True))
    completed={i for i,w in enumerate(report['windows']) if w['status']=='done'}
    times=sorted({f['timestamp_sec'] for f in report['sampled_frames'] if f['window_index'] in completed})
    converted = dict(engine='dense_vlm',verdict='requires_review',violations=[],rule_evaluation='not_performed',
        processed_frames=len(times),sampled_fps=len(report['sampled_frames'])/report['duration_sec'],
        elapsed_seconds=report['elapsed_sec'],model_sha256=report['model_sha256'],
        adapter_sha256=report.get('adapter_sha256'),
        frames=[dict(timestamp_sec=t,boxes=[]) for t in times],events=events,evidence_frames=evidence,
        coverage_status=report['status'],coverage_windows=report['windows'],
        sampling_max_gap_sec=report['sampling_max_gap_sec'],limitations=report['limitations'])
    if assessed:
        for finding in report['violations']:
            refs=[]
            for frame in finding['evidence_frames']:
                timestamp=frame['timestamp_sec']
                if not finding['start_sec'] <= timestamp <= finding['end_sec']:
                    raise ValueError('Finding evidence outside event')
                data=base64.b64decode(frame['image_base64'],validate=True)
                if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'): raise ValueError('Invalid finding JPEG')
                key=(timestamp,hashlib.sha256(data).hexdigest())
                if key not in seen:
                    index=len(evidence);name=f'evidence-{index:03d}.jpg'
                    (output/name).write_bytes(data);seen[key]=index
                    evidence.append(dict(timestamp_sec=timestamp,image_file=name,boxes=[]))
                refs.append(dict(evidence_index=seen[key],timestamp_sec=timestamp,explanation=frame['explanation']))
            converted['violations'].append({**{k:v for k,v in finding.items() if k!='evidence_frames'},'evidence':refs})
        converted.update(verdict=report['verdict'],rule_evaluation='performed',
            assessment_coverage=report['assessment_coverage'],assessment_version=report['assessment_version'],
            decision_scope=report['decision_scope'])
    return converted


class CaptionAnalyzer:
    def __init__(self,python,ml_root,adapter=None,model_size='4b',input_mode='images',assess_rules=False):
        self.python=Path(python);self.root=Path(ml_root);self.adapter=Path(adapter) if adapter else None
        if model_size not in ('4b','8b') or input_mode not in ('images','native_video'):raise ValueError('Unknown VLM configuration')
        self.model_size=model_size;self.input_mode=input_mode
        self.assess_rules=assess_rules

    def analyze(self,source,output,camera_profile='full_frame',timeout=300):
        if camera_profile not in ('full_frame','forte_open'):raise ValueError('Unknown camera profile')
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        destination=output/'caption-report.json'
        command=[str(self.python),str(self.root/'dense_observations.py'),str(source),
            '--output',str(destination),'--budget-sec',str(max(1,timeout-20)),
            '--model-size',self.model_size,'--input-mode',self.input_mode]
        if self.adapter:command.extend(['--adapter',str(self.adapter)])
        if self.assess_rules:command.extend(['--assess-rules','--max-tokens','1400'])
        # argv rather than a shell; paths never become executable shell fragments.
        with (output/'caption-worker.log').open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=False)
        if result.returncode:raise RuntimeError('Local caption worker failed; see its local log')
        report=json.loads(destination.read_text())
        digest=hashlib.sha256()
        with Path(source).open('rb') as video:
            while chunk:=video.read(8*1024*1024):digest.update(chunk)
        if report['source_sha256']!=digest.hexdigest():
            raise ValueError('Caption result belongs to another source')
        converted=convert_report(report,output);converted['camera_profile']=camera_profile
        (output/'result.json').write_text(json.dumps(converted,ensure_ascii=False))
        return converted
