"""API-key-only jury identity and the exact flat case response (no JWT needed)."""
import hashlib
import secrets
from pathlib import Path
from flask import current_app, request, g
from filelock import FileLock
from models import db, User, MediaRecord
from services.media import root
from utils.errors import ApiError


def authenticate(create=False):
    if 'Authorization' in request.headers and request.headers.get('X-API-Key'):
        raise ApiError(400,'ambiguous_auth','Передайте только X-API-Key.')
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
    from services.api_result import response as api_response
    return api_response(job, media)
