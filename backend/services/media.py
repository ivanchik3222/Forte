import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from filelock import FileLock, Timeout
from flask import current_app, request, g
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from models import db, MediaRecord, UploadRequest, AuthSession, User, uid, utcnow, as_utc
from utils.errors import ApiError

TYPES = {'.mov': 'video/quicktime', '.mp4': 'video/mp4', '.webm': 'video/webm'}


def root():
    path = Path(current_app.config['MEDIA_ROOT']).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_query():
    query = MediaRecord.query.filter(MediaRecord.api_client_id.is_(None))
    from models import AlertRecording, CameraAlert
    from services.access import camera_ids
    # A private upload linked to an out-of-scope camera is no longer visible,
    # even to its uploader; one accessible association must not bypass another.
    forbidden = db.select(AlertRecording.media_id).join(CameraAlert, CameraAlert.id == AlertRecording.alert_id).where(~CameraAlert.camera_id.in_(camera_ids()))
    query = query.filter(~MediaRecord.id.in_(forbidden))
    return query if g.user.user_type == 'admin' else query.filter_by(owner_id=g.user.id)


def get_media(record_id):
    record = media_query().filter_by(id=record_id).first()
    if not record:
        raise ApiError(404, 'not_found', 'Запись не найдена.')
    return record


def probe(path, extension):
    try:
        result = subprocess.run([
            current_app.config['FFPROBE_PATH'], '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-format_whitelist', 'mov,matroska,webm', '-show_entries',
            'format=format_name,duration:stream=codec_type', '-of', 'json', str(path),
        ], capture_output=True, timeout=20, check=True)
        data = json.loads(result.stdout)
        formats = data.get('format', {}).get('format_name', '').split(',')
        expected = 'webm' if extension == '.webm' else 'mov'
        if expected not in formats or not any(s.get('codec_type') == 'video' for s in data.get('streams', [])):
            raise ValueError('Not a supported video')
        value = data.get('format', {}).get('duration')
        duration = float(value) if value is not None else None
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            raise ValueError('Invalid duration')
        return duration
    except FileNotFoundError:
        raise ApiError(503, 'probe_unavailable', 'Проверка видео недоступна: ffprobe не установлен на сервере.')
    except (subprocess.SubprocessError, ValueError, KeyError):
        raise ApiError(415, 'invalid_video', 'Файл не содержит поддерживаемое видео MOV, MP4 или WebM.')


def save_upload(idempotency_key=None):
    key = idempotency_key or request.headers.get('Idempotency-Key', '')
    if not key or len(key) > 80 or not all(c.isalnum() or c in '-_' for c in key):
        raise ApiError(400, 'idempotency_key_required', 'Передайте корректный Idempotency-Key (до 80 символов).')
    try:
        directory = root()
        with FileLock(str(directory / f'.upload-{g.user.id}.lock'), timeout=0):
            return _save_upload(key, directory)
    except Timeout:
        raise ApiError(429, 'upload_busy', 'Другая загрузка ещё выполняется. Повторите позже с тем же ключом.')
    except OSError:
        raise ApiError(503, 'storage_unavailable', 'Хранилище временно недоступно.')


def _save_upload(key, directory, api_client_id=None):
    if shutil.disk_usage(directory).free < current_app.config['MAX_FILE_SIZE'] + current_app.config['MIN_FREE_BYTES']:
        raise ApiError(503, 'storage_full', 'Недостаточно места для загрузки.')
    files = request.files.getlist('file')
    if len(files) != 1 or len(request.files) != 1:
        raise ApiError(400, 'file_required', 'Передайте один файл в поле file.')
    upload = files[0]
    name = (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    extension = Path(name).suffix.lower()
    if not name or len(name) > 255 or extension not in TYPES:
        raise ApiError(415, 'unsupported_format', 'Допустимы MOV, MP4, WebM; имя до 255 символов.')
    fd, tmp = tempfile.mkstemp(prefix='.pending-', dir=directory)
    temporary, destination = Path(tmp), None
    try:
        digest = hashlib.sha256(name.encode('utf-8') + b'\0')
        size = 0
        with os.fdopen(fd, 'wb') as output:
            while chunk := upload.stream.read(1024 * 1024):
                size += len(chunk)
                if size > current_app.config['MAX_FILE_SIZE']:
                    raise ApiError(413, 'file_too_large',
                                   f"Размер файла превышает лимит {current_app.config['MAX_FILE_SIZE']} байт.")
                output.write(chunk)
                digest.update(chunk)
        if not size:
            raise ApiError(422, 'empty_file', 'Файл пустой.')
        fingerprint = digest.hexdigest()
        existing = UploadRequest.query.filter_by(owner_id=g.user.id, key=key).first() if api_client_id is None else None
        if existing:
            if existing.fingerprint != fingerprint:
                raise ApiError(409, 'idempotency_conflict', 'Этот ключ уже использован для другого файла.')
            return db.session.get(MediaRecord, existing.media_id), 200
        count = (UploadRequest.query.filter(UploadRequest.owner_id == g.user.id,
                                          UploadRequest.created_at >= utcnow() - timedelta(hours=1)).count()
                 if api_client_id is None else MediaRecord.query.filter(
                     MediaRecord.api_client_id == api_client_id,
                     MediaRecord.created_at >= utcnow() - timedelta(hours=1)).count())
        if count >= current_app.config['UPLOADS_PER_HOUR']:
            raise ApiError(429, 'upload_rate_limit', 'Лимит загрузок за час исчерпан.')
        duration = probe(temporary, extension)
        record = MediaRecord(id=uid(), owner_id=g.user.id if api_client_id is None else None,
                             api_client_id=api_client_id, original_name=name,
                             storage_key=uid() + extension, size_bytes=size,
                             content_type=TYPES[extension], duration_sec=duration)
        destination = directory / record.storage_key
        temporary.replace(destination)
        db.session.add(record)
        db.session.flush()
        if api_client_id is None:
            db.session.add(UploadRequest(owner_id=g.user.id, key=key, fingerprint=fingerprint, media_id=record.id))
            db.session.commit()
        destination = None  # The committed record owns the file.
        return record, 201
    finally:
        temporary.unlink(missing_ok=True)
        if destination is not None:
            db.session.rollback()
            destination.unlink(missing_ok=True)


def signer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='forte-media-v1')


def sign_file(kind, object_id, user_id, sid):
    return signer().dumps(dict(kind=kind, id=object_id, user=user_id, sid=sid))


def authorize_file(kind, object_id, token):
    try:
        data = signer().loads(token, max_age=current_app.config['PLAYBACK_TTL'])
    except (BadSignature, SignatureExpired):
        raise ApiError(401, 'link_expired', 'Ссылка истекла. Обновите её в карточке.')
    session = db.session.get(AuthSession, data.get('sid'))
    user = db.session.get(User, data.get('user'))
    if data.get('kind') != kind or data.get('id') != object_id or not user or not user.is_active or not session or session.user_id != user.id or session.revoked_at or as_utc(session.expires_at) <= utcnow():
        raise ApiError(401, 'link_invalid', 'Ссылка недействительна.')
    from utils.decorators import validate_user_security
    validate_user_security(user, session.id)
    g.user = user
    return user


def file_path(storage_key):
    directory = root()
    path = (directory / storage_key).resolve()
    if path.parent != directory or not path.is_file():
        raise ApiError(404, 'file_not_found', 'Файл недоступен.')
    return path
