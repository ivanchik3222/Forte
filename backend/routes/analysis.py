"""Web JWT responses and the API-key-authenticated jury contract."""
from flask import Blueprint, request, jsonify, current_app, g, url_for, send_file
from flask_jwt_extended import get_jwt
import json
from models import db, ApiClient, AnalysisJob, _utc_iso, utcnow, uid
from services.media import get_media, root, sign_file, authorize_file
from services.analysis import enqueue_job
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
        result['violations'] = [dict(v,evidence_frames=[dict(result['evidence_frames'][e['evidence_index']],
            explanation=e['explanation']) for e in v.get('evidence',[])]) for v in result.get('violations',[])]
    stage = None
    if job.status == 'processing':
        try:
            value = json.loads((root()/'analysis'/job.id/'progress.json').read_text()).get('stage')
            if value in ('finding_events', 'describing_actions', 'assessing_rules'):
                stage = value
        except (OSError, ValueError):
            pass
    return dict(job_id=job.id, media_id=job.media_id, status=job.status, stage=stage, camera_profile=job.camera_profile,
        created_at=_utc_iso(job.created_at), started_at=_utc_iso(job.started_at),
        finished_at=_utc_iso(job.finished_at), error=job.error, result=result)


@analysis_bp.post('/media/<record_id>/analyze')
@active_required
def enqueue(record_id):
    get_media(record_id)
    data = request.get_json(silent=True) or {}
    if set(data) - {'camera_profile'} or data.get('camera_profile', 'full_frame') not in ('forte_open', 'full_frame'):
        raise ApiError(422, 'invalid_camera_profile', 'Выберите forte_open или full_frame.')
    profile = data.get('camera_profile', 'full_frame')
    job, status = enqueue_job(record_id, profile)
    return jsonify(job_dto(job)), status


@analysis_bp.get('/media/<record_id>/analysis')
@active_required
def latest(record_id):
    get_media(record_id)
    job = AnalysisJob.query.filter_by(media_id=record_id).first()
    return jsonify(job_dto(job) if job else None)


@analysis_bp.get('/jobs/<job_id>')
def job_status(job_id):
    if request.headers.get('X-API-Key') is not None:
        from services.api_keys import authenticate_key, key_digest
        api_key = request.headers.get('X-API-Key', '')
        api_client = (ApiClient.query.filter_by(key_hash=key_digest(api_key)).first()
                      if 20 <= len(api_key) <= 128 else None)
        if api_client:
            authenticate_key()
            from routes.public_api import public_job
            return jsonify(public_job(job_id))
        from services.jury import authenticate, response
        authenticate()
        job=db.session.get(AnalysisJob,job_id)
        if job is None: raise ApiError(404,'not_found','Анализ не найден.')
        return jsonify(response(job))
    return active_required(lambda: jsonify(job_dto(get_job(job_id))))()


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
