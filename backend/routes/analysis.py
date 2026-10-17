"""Authenticated object observations; automatic violation evaluation is disabled."""
from flask import Blueprint, request, jsonify, current_app, g, url_for, send_file
from flask_jwt_extended import get_jwt
from filelock import FileLock, Timeout
from models import db, AnalysisJob, _utc_iso, utcnow
from services.media import get_media, root, sign_file, authorize_file
from services.analysis import available
from utils.decorators import active_required
from utils.errors import ApiError

analysis_bp = Blueprint('analysis', __name__)


def get_job(job_id):
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        raise ApiError(404, 'not_found', 'Анализ не найден.')
    get_media(job.media_id)
    return job


def job_dto(job):
    result = dict(job.result) if job.result else None
    if result:
        signed = sign_file('analysis', job.id, g.user.id, get_jwt()['sid'])
        result['evidence_frames'] = [dict(timestamp_sec=e['timestamp_sec'], boxes=e['boxes'],
            image_url=url_for('analysis.evidence', job_id=job.id, index=i, token=signed))
            for i, e in enumerate(result['evidence_frames'])]
    return dict(job_id=job.id, media_id=job.media_id, status=job.status, camera_profile=job.camera_profile,
        created_at=_utc_iso(job.created_at), started_at=_utc_iso(job.started_at),
        finished_at=_utc_iso(job.finished_at), error=job.error, result=result)


@analysis_bp.post('/media/<record_id>/analyze')
@active_required
def enqueue(record_id):
    get_media(record_id)
    if not available():
        raise ApiError(503, 'analysis_unavailable', 'Локальная модель не установлена или отключена.')
    data = request.get_json(silent=True) or {}
    if set(data) - {'camera_profile'} or data.get('camera_profile', 'full_frame') not in ('forte_open', 'full_frame'):
        raise ApiError(422, 'invalid_camera_profile', 'Выберите forte_open или full_frame.')
    profile = data.get('camera_profile', 'full_frame')
    try:
        # Serialize submissions as well as retries; one durable job per media.
        with FileLock(str(root()/'.analysis-submit.lock'), timeout=0):
            job = AnalysisJob.query.filter_by(media_id=record_id).first()
            if job and job.status != 'failed':
                if job.camera_profile != profile:
                    raise ApiError(409, 'profile_conflict', 'Для записи уже выполнялся анализ с другим профилем.')
                return jsonify(job_dto(job)), 200
            if AnalysisJob.query.filter(AnalysisJob.status.in_(['queued', 'processing'])).count() >= current_app.config['ML_QUEUE_LIMIT']:
                raise ApiError(429, 'analysis_busy', 'Очередь заполнена. Повторите позже.')
            if job:
                job.status, job.camera_profile, job.result, job.error = 'queued', profile, None, None
                job.created_at, job.started_at, job.finished_at = utcnow(), None, None
            else:
                job = AnalysisJob(media_id=record_id, camera_profile=profile)
                db.session.add(job)
            db.session.commit()
            return jsonify(job_dto(job)), 202
    except Timeout:
        raise ApiError(429, 'analysis_busy', 'Повторите запрос через несколько секунд.')


@analysis_bp.get('/media/<record_id>/analysis')
@active_required
def latest(record_id):
    get_media(record_id)
    job = AnalysisJob.query.filter_by(media_id=record_id).first()
    return jsonify(job_dto(job) if job else None)


@analysis_bp.get('/jobs/<job_id>')
@active_required
def job_status(job_id):
    return jsonify(job_dto(get_job(job_id)))


@analysis_bp.get('/jobs/<job_id>/evidence/<int:index>')
def evidence(job_id, index):
    authorize_file('analysis', job_id, request.args.get('token', ''))
    job = get_job(job_id)
    evidence_frames = (job.result or {}).get('evidence_frames', [])
    if job.status != 'done' or not 0 <= index < len(evidence_frames):
        raise ApiError(404, 'not_found', 'Кадр не найден.')
    directory = (root()/'analysis'/job.id).resolve()
    path = (directory/evidence_frames[index]['image_file']).resolve()
    if path.parent != directory or not path.is_file():
        raise ApiError(404, 'not_found', 'Кадр недоступен.')
    return send_file(path, mimetype='image/jpeg', conditional=True)
