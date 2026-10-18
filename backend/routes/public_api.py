"""Public key issuance and isolated async uploads; no user account required."""
import secrets
from datetime import timedelta
from flask import Blueprint, current_app, g, jsonify, request
from filelock import FileLock, Timeout
from models import db, ApiClient, MediaRecord, AnalysisJob, utcnow, _utc_iso, uid
from services.api_keys import authenticate_key, api_key_required, key_digest
from services.security import throttle
from services.media import root, _save_upload
from services.analysis import available, enqueue_job, expire_pending_api_jobs
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


def _jury_analyze():
    from services.jury import authenticate, response
    from services.analysis import available
    from services.media import save_upload
    authenticate(create=True)
    if current_app.config['ML_ENGINE'] != 'reviewed_pipeline' or not available():
        raise ApiError(503,'analysis_unavailable','Для API жюри требуется полный локальный анализ с проверкой правил.')
    expire_pending_api_jobs()
    if AnalysisJob.query.filter(AnalysisJob.status.in_(['queued','processing'])).count():
        raise ApiError(429,'analysis_busy','Модель занята. Повторите после завершения текущего анализа.')
    record,_ = save_upload(request.headers.get('Idempotency-Key') or uid())
    job,status = enqueue_job(record.id,'full_frame',retry_failed=False,require_idle=True)
    return jsonify(response(job)),status


@public_api_bp.post('/analyze')
def analyze():
    # Preserve the registered client-key API and the jury contract on one URL.
    # Database-issued client keys are routed to the legacy isolated-upload flow;
    # all other keys must match the configured jury secret.
    key = request.headers.get('X-API-Key', '')
    client = ApiClient.query.filter_by(key_hash=key_digest(key)).first() if 20 <= len(key) <= 128 else None
    if client is None:
        return _jury_analyze()
    authenticate_key()
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


def public_job(job_id):
    job = AnalysisJob.query.join(MediaRecord, AnalysisJob.media_id == MediaRecord.id).filter(
        AnalysisJob.id == job_id, MediaRecord.api_client_id == g.api_client.id).first()
    if not job:
        raise ApiError(404, 'not_found', 'Анализ не найден.')
    from services.api_result import response
    return response(job, db.session.get(MediaRecord, job.media_id))
