"""Public key issuance and isolated async uploads; no user account required."""
import base64
import math
import secrets
from datetime import timedelta
from flask import Blueprint, current_app, g, jsonify, request
from filelock import FileLock, Timeout
from models import db, ApiClient, MediaRecord, AnalysisJob, utcnow, as_utc, _utc_iso
from services.api_keys import api_key_required, key_digest
from services.security import throttle
from services.media import root, _save_upload
from services.analysis import available, expire_pending_api_jobs
from utils.errors import ApiError

public_api_bp = Blueprint('public_api', __name__)


@public_api_bp.post('/api-keys')
def issue_key():
    # remote_addr is deliberately not taken from an untrusted forwarded header.
    throttle(request.remote_addr or 'unknown', 'key-issue-ip', current_app.config['API_KEY_ISSUE_LIMIT'])
    throttle('all', 'key-issue-global', current_app.config['API_KEY_GLOBAL_ISSUE_LIMIT'])
    key = 'forte_' + secrets.token_urlsafe(32)
    client = ApiClient(key_hash=key_digest(key), expires_at=utcnow() + timedelta(days=current_app.config['API_KEY_DAYS']))
    db.session.add(client)
    db.session.commit()
    return jsonify(api_key=key, expires_at=_utc_iso(client.expires_at)), 201


@public_api_bp.delete('/api-keys/current')
@api_key_required
def revoke_key():
    g.api_client.revoked_at = utcnow()
    db.session.commit()
    return '', 204


@public_api_bp.post('/analyze')
@api_key_required
def analyze():
    if not available():
        raise ApiError(503, 'analysis_unavailable', 'Локальная модель недоступна.')
    throttle(request.remote_addr or 'unknown', 'api-upload-ip', current_app.config['API_UPLOAD_IP_LIMIT'])
    directory = root()
    record = None
    try:
        # Shared with JWT submissions: capacity check and enqueue are serialized.
        with FileLock(str(directory / '.analysis-submit.lock'), timeout=0):
            expire_pending_api_jobs()
            active = AnalysisJob.query.filter(AnalysisJob.status.in_(['queued', 'processing']))
            if active.join(MediaRecord, AnalysisJob.media_id == MediaRecord.id).filter(MediaRecord.api_client_id == g.api_client.id).first():
                raise ApiError(429, 'analysis_busy', 'Дождитесь завершения предыдущего анализа.')
            if active.count() >= current_app.config['ML_QUEUE_LIMIT']:
                raise ApiError(429, 'analysis_busy', 'Очередь заполнена. Повторите позже.')
            record, _ = _save_upload(None, directory, api_client_id=g.api_client.id)
            job = AnalysisJob(media_id=record.id, camera_profile='full_frame')
            db.session.add(job)
            db.session.commit()
            return jsonify(job_id=job.id, status='processing'), 202
    except Timeout:
        raise ApiError(429, 'analysis_busy', 'Другая загрузка ещё выполняется. Повторите позже.')
    except Exception:
        db.session.rollback()
        if record is not None:
            (directory / record.storage_key).unlink(missing_ok=True)
        raise


def failed(job, code, message):
    return dict(job_id=job.id, status='failed', error=dict(code=code, message=message))


def public_job(job_id):
    job = AnalysisJob.query.join(MediaRecord, AnalysisJob.media_id == MediaRecord.id).filter(
        AnalysisJob.id == job_id, MediaRecord.api_client_id == g.api_client.id).first()
    if not job:
        raise ApiError(404, 'not_found', 'Анализ не найден.')
    deadline = current_app.config['API_JOB_DEADLINE']
    elapsed = (as_utc(job.finished_at) if job.finished_at else utcnow()) - as_utc(job.created_at)
    if elapsed.total_seconds() >= deadline:
        return failed(job, 'analysis_timeout', 'Результат не получен за 5 минут.')
    if job.status in ('queued', 'processing'):
        return dict(job_id=job.id, status='processing')
    if job.status == 'failed':
        return failed(job, 'analysis_failed', 'Не удалось обработать видео.')
    result = job.result or {}
    # Observation-only models must never be silently relabelled no_violation.
    if not isinstance(result, dict) or result.get('verdict') not in ('violation', 'no_violation'):
        return failed(job, 'verdict_unavailable', 'Модель сформировала наблюдения, но не определяет нарушения по ТЗ.')
    try:
        violations = serialize_violations(job, result)
    except (ValueError, TypeError, KeyError, OSError):
        return failed(job, 'invalid_result', 'Модель не сформировала полный результат с кадрами-доказательствами.')
    return dict(job_id=job.id, status='done', verdict=result['verdict'], violations=violations)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid timestamp')
    return value


def serialize_violations(job, result):
    source = result['violations']
    if not isinstance(source, list) or (result['verdict'] == 'violation') != bool(source):
        raise ValueError('Inconsistent verdict')
    directory = (root() / 'analysis' / job.id).resolve()
    output = []
    for item in source:
        if not all(isinstance(item[k], str) and item[k].strip() for k in ('type', 'description')):
            raise ValueError('Missing description')
        evidence = item['evidence_frames']
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise ValueError('Expected 1-3 frames')
        frames = []
        for frame in evidence:
            path = (directory / frame['image_file']).resolve()
            if path.parent != directory or path.suffix.lower() not in ('.jpg', '.jpeg'):
                raise ValueError('Invalid evidence path')
            if path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError('Evidence too large')
            data = path.read_bytes()
            if not data.startswith(b'\xff\xd8'):
                raise ValueError('Expected JPEG')
            frames.append(dict(timestamp_sec=number(frame['timestamp_sec']), image_base64=base64.b64encode(data).decode('ascii')))
        output.append(dict(type=item['type'], description=item['description'],
                           timecode_sec=number(item['timecode_sec']), evidence_frames=frames))
    return output
