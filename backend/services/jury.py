"""API-key-only jury identity and the exact flat case response (no JWT needed)."""
import base64
import hashlib
import secrets
from pathlib import Path
from flask import current_app, request, g
from filelock import FileLock
from models import db, User, AnalysisJob, MediaRecord
from services.media import root
from utils.errors import ApiError


def authenticate(create=False):
    configured = current_app.config.get('JURY_API_KEY', '')
    if not configured:
        try: configured = Path(current_app.config['JURY_API_KEY_FILE']).read_text().strip()
        except OSError: configured = ''
    provided = request.headers.get('X-API-Key', '')
    if not configured or not provided or not secrets.compare_digest(provided.encode(), configured.encode()):
        raise ApiError(401, 'invalid_api_key', 'Передайте действующий X-API-Key.')
    # A separate non-login account per key. A key cannot read web uploads.
    nickname = 'jury-'+hashlib.sha256(configured.encode()).hexdigest()[:32]
    with FileLock(str(root()/'.jury-identity.lock'), timeout=5):
        user = User.query.filter_by(nickname=nickname).first()
        if user is None and create:
            user = User(nickname=nickname,full_name='API жюри',is_active=True,user_type='user')
            db.session.add(user); db.session.commit()
    if user is None or not user.is_active:
        raise ApiError(404,'not_found','Анализ не найден.')
    g.user = user
    return user


def response(job):
    media = db.session.get(MediaRecord, job.media_id)
    if media is None or media.owner_id != g.user.id:
        raise ApiError(404,'not_found','Анализ не найден.')
    dto = dict(job_id=job.id,status='processing' if job.status=='queued' else job.status)
    if job.status == 'failed': dto['error'] = job.error
    if job.status != 'done': return dto
    result = job.result or {}
    if result.get('verdict') not in ('violation','no_violation') or result.get('rule_evaluation') != 'performed':
        return dict(job_id=job.id,status='failed',error='Бинарная оценка правил не выполнена.')
    directory = (root()/'analysis'/job.id).resolve()
    violations=[]
    for v in result['violations']:
        frames=[]
        for ref in v['evidence']:
            frame = result['evidence_frames'][ref['evidence_index']]
            path = (directory/frame['image_file']).resolve()
            if path.parent != directory or not path.is_file():
                raise ApiError(503,'evidence_unavailable','Кадр-доказательство недоступен.')
            frames.append(dict(timestamp_sec=frame['timestamp_sec'],image_base64=base64.b64encode(path.read_bytes()).decode(),
                explanation=ref['explanation']))
        violations.append(dict(type=v['type'],timecode_sec=v['timecode_sec'],description=v['description'],
            evidence_frames=frames,rule=v['rule'],classification_status=v.get('classification_status','grounded')))
    dto.update(verdict=result['verdict'],violations=violations,
        coverage_status=result.get('assessment_coverage','partial'),decision_scope=result.get('decision_scope'))
    return dto
