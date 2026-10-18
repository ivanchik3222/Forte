"""Sequential subprocesses free Torch/MPS memory before loading local Qwen."""
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path


def progress(output, stage):
    temp = output/'progress.tmp'
    temp.write_text(json.dumps(dict(stage=stage)), encoding='utf-8')
    temp.replace(output/'progress.json')


def retain_unclassified_signals(result):
    """A failure to identify a rule must not erase a positive trained prediction.

Unclassified signals are explicit, not fabricated normative findings. No claim
is made that their context frames independently prove a particular violation.
"""
    for v in result['violations']:
        v['classification_status']='grounded'
    for event in result['events']:
        if any(v['start_sec'] <= event['timecode_sec'] <= v['end_sec'] for v in result['violations']):
            continue
        refs=[]
        for i in event['evidence_indices'][:3]:
            frame=result['evidence_frames'][i]
            peak=abs(frame['timestamp_sec']-event['timecode_sec'])<1e-4
            refs.append(dict(evidence_index=i,timestamp_sec=frame['timestamp_sec'],
                explanation='Момент максимальной оценки классификатора; действие нужно проверить.' if peak else 'Контекст выделенного моделью эпизода.'))
        if not refs: raise ValueError('Positive classifier event has no evidence')
        key=min(refs,key=lambda f:abs(f['timestamp_sec']-event['timecode_sec']))['timestamp_sec']
        result['violations'].append(dict(type='Признаки нарушения — тип не определён',
            start_sec=min(event['start_sec'],*(f['timestamp_sec'] for f in refs)),
            end_sec=max(event['end_sec'],*(f['timestamp_sec'] for f in refs)),timecode_sec=key,
            description='Банковский классификатор обнаружил признаки возможного нарушения. Конкретное действие и нормативное основание автоматически не установлены.',
            visible_fact='Для проверки выбран интервал исходной записи и кадр максимальной оценки модели.',
            explanation='Вывод основан на обученном бинарном классификаторе. Эти кадры показывают выделенный эпизод; конкретный тип нарушения ими автоматически не подтверждён.',
            classification_status='unclassified',rule_id=None,rule=None,evidence=refs,requires_human_review=True))
    result['violations'].sort(key=lambda v:v['timecode_sec'])
    result['verdict']='violation' if result['violations'] else 'no_violation'
    result['unclassified_count']=sum(v['classification_status']=='unclassified' for v in result['violations'])


def merge_reports(candidate, caption, output, caption_status, elapsed, preserve_candidates=False):
    evidence = []
    result = dict(candidate)
    result.update(engine='reviewed_pipeline', observations=[], caption_status=caption_status,
                  elapsed_seconds=elapsed, verdict='requires_review', violations=[], rule_evaluation='not_performed',
                  assessment_coverage='partial', decision_scope='visible_signs_of_possible_violations')
    for prefix, report in [('candidate', candidate), ('caption', caption)]:
        if report is None:
            continue
        offset = len(evidence)
        for frame in report['evidence_frames']:
            filename = frame['image_file']
            if Path(filename).name != filename:
                raise ValueError('Invalid evidence filename')
            dest = f'{prefix}-{filename}'
            shutil.copyfile(output/prefix/filename, output/dest)
            evidence.append(dict(frame, image_file=dest))
        mapped = [dict(event, evidence_indices=[offset+i for i in event.get('evidence_indices', [])]) for event in report['events']]
        result['events' if prefix == 'candidate' else 'observations'] = mapped
        if prefix == 'caption' and report.get('rule_evaluation') == 'performed':
            result.update(verdict=report['verdict'],rule_evaluation='performed',
                assessment_coverage=report['assessment_coverage'],assessment_version=report['assessment_version'],
                decision_scope=report['decision_scope'])
            result['violations']=[dict(v,evidence=[dict(e,evidence_index=e['evidence_index']+offset)
                for e in v['evidence']]) for v in report['violations']]
    result['evidence_frames'] = evidence
    if caption is not None:
        result.update(coverage_status=caption['coverage_status'], coverage_windows=caption['coverage_windows'],
                      caption_model_sha256=caption['model_sha256'])
        # Each entry represents an inspected/scored time, not every decoded source frame.
        times = sorted({f['timestamp_sec'] for report in (candidate, caption) for f in report['frames']})
        result['frames'] = [dict(timestamp_sec=t, boxes=[]) for t in times]
        result['processed_frames'] = len(times)
    else:
        result.update(coverage_status='partial', coverage_windows=[])
    if result['rule_evaluation']=='performed' or (preserve_candidates and result['events']):
        retain_unclassified_signals(result)
    return result


class ReviewedPipeline:
    def __init__(self, python, root, bundle, backbone, device=None, caption=None, allow_reserved_test=False):
        self.python, self.root = Path(python), Path(root)
        self.bundle, self.backbone = Path(bundle), Path(backbone)
        self.device = 'auto' if device is None else ('cuda:0' if device == '0' else device)
        self.caption = caption
        self.allow_reserved_test = allow_reserved_test

    def analyze(self, source, output, camera_profile='forte_open', timeout=300):
        if camera_profile not in ('forte_open', 'full_frame'):
            raise ValueError('Unknown camera profile')
        started = time.monotonic()
        output = Path(output); output.mkdir(parents=True, exist_ok=True)
        progress(output, 'finding_events')
        directory = output/'candidate'
        command = [str(self.python), str(self.root/'reviewed_inference.py'), str(source),
                   '--output', str(directory), '--bundle', str(self.bundle), '--backbone', str(self.backbone),
                   '--device', self.device, '--timeout', str(max(1, timeout-10))]
        if self.allow_reserved_test: command.append('--allow-reserved-test')
        with (output/'candidate-worker.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)
        candidate = json.loads((directory/'result.json').read_text())
        digest = hashlib.sha256()
        with Path(source).open('rb') as video:
            while chunk := video.read(8*1024*1024):
                digest.update(chunk)
        if candidate['source_sha256'] != digest.hexdigest():
            raise ValueError('Candidate result belongs to another source')
        if self.caption is None:
            for frame in candidate['evidence_frames']:
                shutil.copyfile(directory/frame['image_file'], output/frame['image_file'])
            candidate['camera_profile'] = camera_profile
            progress(output, 'done')
            return candidate
        progress(output, 'assessing_rules' if getattr(self.caption,'assess_rules',False) else 'describing_actions')
        remaining = timeout - (time.monotonic()-started)
        unavailable = getattr(self.caption, 'unavailable_status', None)
        caption, status = None, unavailable or 'time_budget_exceeded'
        if remaining > 25 and not unavailable:
            try:
                caption = self.caption.analyze(source, output/'caption', camera_profile, remaining)
                status = caption['coverage_status']
            except subprocess.TimeoutExpired:
                status = 'time_budget_exceeded'
            except Exception:
                # Raw diagnostics remain local; retain usable candidate results.
                import traceback
                (output/'caption-error.log').write_text(traceback.format_exc(), encoding='utf-8')
                status = 'failed'
        result = merge_reports(candidate, caption, output, status, time.monotonic()-started,
            preserve_candidates=getattr(self.caption,'assess_rules',False))
        result['camera_profile'] = camera_profile
        if getattr(self.caption,'assess_rules',False) and result['rule_evaluation'] != 'performed' and not result['violations']:
            raise RuntimeError('Rule assessment did not complete; no binary verdict is available')
        (output/'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        progress(output, 'done')
        return result
