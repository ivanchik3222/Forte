"""One validated case-response format for configured jury and issued API keys.

This adapter preserves model decisions and classifications. It only resolves
local evidence references, validates the result and serializes JPEGs.
"""
import base64
import math
import warnings
from io import BytesIO

from flask import current_app
from PIL import Image

from models import as_utc, utcnow
from services.media import root

TIMEOUT_MESSAGE = 'Результат не получен за 5 минут.'
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


def elapsed_seconds(job, now=None):
    end = job.finished_at if job.finished_at is not None else (now or utcnow())
    return (as_utc(end) - as_utc(job.created_at)).total_seconds()


def failed(job, code, message):
    return dict(job_id=job.id, status='failed', error=dict(code=code, message=message))


def number(value, duration):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid timestamp')
    if duration is not None and value > duration + .001:
        raise ValueError('Timestamp outside video')
    return value


def evidence_frames(item, report):
    if 'evidence' not in item:
        return item['evidence_frames']
    refs, source = item['evidence'], report['evidence_frames']
    if not isinstance(refs, list) or not isinstance(source, list):
        raise ValueError('Invalid evidence references')
    frames = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('Invalid evidence reference')
        index = ref.get('evidence_index')
        if type(index) is not int or not 0 <= index < len(source):
            raise ValueError('Evidence index out of bounds')
        frame = source[index]
        if not isinstance(frame, dict):
            raise ValueError('Invalid evidence frame')
        if 'timestamp_sec' in ref and ref['timestamp_sec'] != frame['timestamp_sec']:
            raise ValueError('Evidence reference timestamp mismatch')
        frames.append(frame)
    return frames


def jpeg_base64(directory, filename):
    if not isinstance(filename, str) or not filename:
        raise ValueError('Invalid evidence filename')
    path = (directory / filename).resolve()
    if path.parent != directory or path.suffix.lower() not in ('.jpg', '.jpeg'):
        raise ValueError('Invalid evidence path')
    with path.open('rb') as image_file:
        data = image_file.read(MAX_EVIDENCE_BYTES + 1)
    if len(data) > MAX_EVIDENCE_BYTES:
        raise ValueError('Evidence too large')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as picture:
            if picture.format != 'JPEG':
                raise ValueError('Evidence must be JPEG')
            picture.verify()
        # verify() alone does not detect a truncated JPEG scan.
        with Image.open(BytesIO(data)) as picture:
            picture.load()
    return base64.b64encode(data).decode('ascii')


def serialize_violations(job, report, duration):
    source = report['violations']
    if not isinstance(source, list) or (report['verdict'] == 'violation') != bool(source):
        raise ValueError('Inconsistent verdict')
    directory = (root() / 'analysis' / job.id).resolve()
    output = []
    for item in source:
        if not isinstance(item, dict) or not all(
                isinstance(item.get(k), str) and item[k].strip() for k in ('type', 'description')):
            raise ValueError('Missing classification or description')
        timecode = number(item['timecode_sec'], duration)
        evidence = evidence_frames(item, report)
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise ValueError('Expected 1-3 frames')
        frames, times = [], set()
        for frame in evidence:
            if not isinstance(frame, dict):
                raise ValueError('Invalid evidence frame')
            timestamp = number(frame['timestamp_sec'], duration)
            if timestamp in times:
                raise ValueError('Repeated evidence frame')
            times.add(timestamp)
            frames.append(dict(timestamp_sec=timestamp,
                image_base64=jpeg_base64(directory, frame['image_file'])))
        if not any(abs(timestamp - timecode) <= .001 for timestamp in times):
            raise ValueError('Event timecode does not match selected evidence')
        if 'start_sec' in item or 'end_sec' in item:
            start, end = number(item['start_sec'], duration), number(item['end_sec'], duration)
            if not all(start <= timestamp <= end for timestamp in times | {timecode}):
                raise ValueError('Evidence outside event')
        event = dict(type=item['type'], timecode_sec=timecode, description=item['description'], evidence_frames=frames)
        # Preserve provenance/uncertainty when provided; never manufacture a rule
        # or turn an unclassified trained prediction into a different decision.
        for key in ('rule', 'classification_status'):
            if key in item:
                event[key] = item[key]
        output.append(event)
    return output


def response(job, media):
    if elapsed_seconds(job) >= current_app.config['API_JOB_DEADLINE']:
        return failed(job, 'analysis_timeout', TIMEOUT_MESSAGE)
    if job.status in ('queued', 'processing'):
        return dict(job_id=job.id, status='processing')
    if job.status == 'failed':
        return failed(job, 'analysis_failed', 'Не удалось обработать видео.')
    report = job.result
    if not isinstance(report, dict) or report.get('verdict') not in ('violation', 'no_violation'):
        return failed(job, 'verdict_unavailable', 'Модель не сформировала бинарный результат анализа.')
    candidate_only = (report.get('candidate_status') == 'candidates_found' and bool(report.get('events'))
        and report['verdict'] == 'violation' and isinstance(report.get('violations'), list)
        and bool(report['violations']) and all(isinstance(v, dict) and v.get('classification_status') == 'unclassified'
            and v.get('rule') is None for v in report['violations']))
    if report.get('engine') == 'reviewed_pipeline' and report.get('rule_evaluation') != 'performed' and not candidate_only:
        return failed(job, 'verdict_unavailable', 'Проверка правил не выполнена.')
    if report['verdict'] == 'no_violation' and report.get('assessment_coverage', 'done') != 'done':
        return failed(job, 'incomplete_analysis', 'Не все интервалы проверены; отсутствие нарушений не установлено.')
    try:
        violations = serialize_violations(job, report, media.duration_sec)
    except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return failed(job, 'invalid_result', 'Модель не сформировала полный результат с кадрами-доказательствами.')
    result = dict(job_id=job.id, status='done', verdict=report['verdict'], violations=violations)
    for source, target in (('assessment_coverage', 'coverage_status'), ('decision_scope', 'decision_scope'),
                           ('rule_evaluation', 'rule_evaluation')):
        if source in report:
            result[target] = report[source]
    return result
