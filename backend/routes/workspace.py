from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, request, jsonify, g, send_file, url_for, current_app
from flask_jwt_extended import get_jwt
from models import db, MediaRecord, Camera, CameraAlert, AlertRead, AlertRecording, EvidenceFrame, RegulatorySource, _utc_iso, utcnow
from utils.decorators import active_required, admin_required
from utils.errors import ApiError
from services.media import save_upload, media_query, get_media, sign_file, authorize_file, file_path
from services.monitoring import latest_reports, camera_dto, monitoring_snapshot

workspace_bp = Blueprint('workspace', __name__)


def pagination(query, serialize):
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        if page < 1 or not 1 <= per_page <= 100:
            raise ValueError()
    except ValueError:
        raise ApiError(400, 'invalid_pagination', 'page >= 1, per_page от 1 до 100.')
    result = query.paginate(page=page, per_page=per_page, error_out=False)
    return dict(items=[serialize(x) for x in result.items], page=page, per_page=per_page, total=result.total)


def day_bounds():
    zone = ZoneInfo('Asia/Almaty')
    day = request.args.get('date', datetime.now(zone).date().isoformat())
    try:
        parsed = datetime.strptime(day, '%Y-%m-%d')
        if parsed.strftime('%Y-%m-%d') != day:
            raise ValueError()
        start = parsed.replace(tzinfo=zone)
    except ValueError:
        raise ApiError(400, 'invalid_date', 'Дата должна быть YYYY-MM-DD.')
    return day, start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def alerts_for_day():
    _, start, end = day_bounds()
    query = CameraAlert.query.filter(CameraAlert.detected_at >= start, CameraAlert.detected_at < end)
    camera = request.args.get('camera_id')
    if camera:
        query = query.filter_by(camera_id=camera)
    return query


def is_read():
    return db.exists().where(AlertRead.alert_id == CameraAlert.id, AlertRead.user_id == g.user.id)


def alert_dto(alert, detail=False):
    read = db.session.get(AlertRead, (g.user.id, alert.id))
    frames = []
    if detail:
        for frame in EvidenceFrame.query.filter_by(alert_id=alert.id).order_by(EvidenceFrame.timestamp_sec, EvidenceFrame.id):
            token = sign_file('frame', frame.id, g.user.id, get_jwt()['sid'])
            frames.append(dict(timestamp_sec=frame.timestamp_sec, image_url=url_for('workspace.frame_content', frame_id=frame.id, token=token)))
    link = db.session.get(AlertRecording, alert.id)
    media = media_query().filter_by(id=link.media_id).first() if link else None
    recording = dict(media_id=media.id, duration_sec=media.duration_sec) if media else None
    return dict(id=alert.id, camera_id=alert.camera_id, camera_name=alert.camera.name,
                location=alert.camera.location, detected_at=_utc_iso(alert.detected_at), source=alert.source,
                read_at=_utc_iso(read.read_at) if read else None, recording=recording,
                event=dict(type=alert.type, description=alert.description, timecode_sec=alert.timecode_sec,
                           evidence_frames=frames, rule=alert.rule))


@workspace_bp.get('/capabilities')
@active_required
def capabilities():
    from services.analysis import available
    return jsonify(uploads=True, analysis=available(), analysis_kind='object_observations',
                   automatic_violation_detection=False, camera_stream=False, monitoring=True, shift_review=True,
                   automatic_quality_checks=False, formats=['mov', 'mp4', 'webm'], max_file_size=current_app.config['MAX_FILE_SIZE'])


@workspace_bp.post('/analyze')
@active_required
def analyze_unavailable():
    raise ApiError(503, 'analysis_unavailable', 'ИИ-анализ пока не подключён.')


@workspace_bp.post('/media')
@active_required
def upload_media():
    record, status = save_upload()
    return jsonify(record.to_dict()), status


@workspace_bp.get('/media')
@active_required
def list_media():
    query = media_query()
    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(MediaRecord.search_name.contains(search.casefold(), autoescape=True))
    status = request.args.get('status', 'all')
    if status not in ('all', 'stored'):
        raise ApiError(400, 'invalid_status', 'Допустимы all и stored.')
    sort = request.args.get('sort', 'newest')
    if sort not in ('newest', 'oldest'):
        raise ApiError(400, 'invalid_sort', 'Допустимы newest и oldest.')
    query = query.order_by(MediaRecord.created_at.desc(), MediaRecord.id.desc()) if sort == 'newest' else query.order_by(MediaRecord.created_at, MediaRecord.id)
    return jsonify(pagination(query, lambda x: x.to_dict()))


@workspace_bp.get('/media/<record_id>')
@active_required
def media_detail(record_id):
    return jsonify(get_media(record_id).to_dict())


@workspace_bp.post('/media/<record_id>/playback-url')
@active_required
def playback(record_id):
    get_media(record_id)
    token = sign_file('media', record_id, g.user.id, get_jwt()['sid'])
    return jsonify(url=url_for('workspace.media_content', record_id=record_id, token=token), expires_in=current_app.config['PLAYBACK_TTL'])


@workspace_bp.get('/media/<record_id>/content')
def media_content(record_id):
    authorize_file('media', record_id, request.args.get('token', ''))
    record = get_media(record_id)
    return send_file(file_path(record.storage_key), mimetype=record.content_type, conditional=True,
                     download_name=record.original_name, as_attachment=request.args.get('download') == '1')


@workspace_bp.get('/media/<record_id>/report')
@active_required
def report(record_id):
    payload = get_media(record_id).to_dict()
    from models import AnalysisJob
    job = AnalysisJob.query.filter_by(media_id=record_id).first()
    payload['analysis_status'] = job.status if job else 'not_requested'
    payload['analysis'] = job.result if job and job.status == 'done' else None
    payload['notice'] = 'Наблюдения модели требуют проверки специалистом. Оценка нарушений не выполнялась.' if job else 'Видео сохранено. Анализ не выполнялся.'
    response = jsonify(payload)
    response.headers['Content-Disposition'] = f'attachment; filename="forte-report-{payload["id"]}.json"'
    return response


@workspace_bp.get('/cameras')
@active_required
def cameras():
    reports, now = latest_reports(), utcnow()
    return jsonify(pagination(Camera.query.order_by(Camera.name, Camera.id), lambda c: camera_dto(c, reports.get(c.id), now)))


@workspace_bp.post('/cameras')
@workspace_bp.patch('/cameras/<camera_id>')
@admin_required
def edit_camera(camera_id=None):
    camera = db.session.get(Camera, camera_id) if camera_id else Camera()
    if camera is None:
        raise ApiError(404, 'not_found', 'Камера не найдена.')
    data = request.get_json()
    if set(data) - {'name', 'location', 'is_active'}:
        raise ApiError(422, 'invalid_fields', 'Разрешены name, location, is_active. Статус требует источника heartbeat.')
    for field, limit in [('name', 120), ('location', 255)]:
        if field in data or camera_id is None:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ApiError(422, 'invalid_field', f'Некорректное поле {field}.')
            setattr(camera, field, value.strip())
    if 'is_active' in data:
        if not isinstance(data['is_active'], bool):
            raise ApiError(422, 'invalid_field', 'is_active должен быть boolean.')
        camera.is_active = data['is_active']
    db.session.add(camera)
    db.session.commit()
    return jsonify(camera_dto(camera, latest_reports().get(camera.id), utcnow())), 200 if camera_id else 201


@workspace_bp.get('/notifications')
@active_required
def notifications():
    query = alerts_for_day()
    total, read_count = query.count(), query.filter(is_read()).count()
    state = request.args.get('read', 'all')
    if state not in ('all', 'new', 'read'):
        raise ApiError(400, 'invalid_filter', 'Допустимы all, new, read.')
    if state != 'all':
        query = query.filter(is_read() if state == 'read' else ~is_read())
    data = pagination(query.order_by(CameraAlert.detected_at.desc(), CameraAlert.id.desc()), alert_dto)
    data['counts'] = dict(all=total, read=read_count, new=total-read_count)
    return jsonify(data)


@workspace_bp.get('/notifications/<alert_id>')
@active_required
def notification_detail(alert_id):
    alert = db.session.get(CameraAlert, alert_id)
    if not alert:
        raise ApiError(404, 'not_found', 'Событие не найдено.')
    return jsonify(alert_dto(alert, detail=True))


@workspace_bp.post('/notifications/read')
@active_required
def mark_read():
    ids = request.get_json().get('ids')
    if not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(i, str) for i in ids):
        raise ApiError(422, 'invalid_ids', 'Передайте до 100 ID событий.')
    ids = list(set(ids))
    if CameraAlert.query.filter(CameraAlert.id.in_(ids)).count() != len(ids):
        raise ApiError(404, 'not_found', 'Событие не найдено.')
    # Database upsert prevents races between tabs and preserves the first read time.
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    insert = postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    for alert_id in ids:
        stmt = insert(AlertRead).values(user_id=g.user.id, alert_id=alert_id).on_conflict_do_nothing(index_elements=['user_id', 'alert_id'])
        db.session.execute(stmt)
    db.session.commit()
    return jsonify(items=[dict(id=i, read_at=_utc_iso(db.session.get(AlertRead, (g.user.id, i)).read_at)) for i in ids])


@workspace_bp.get('/frames/<frame_id>/content')
def frame_content(frame_id):
    authorize_file('frame', frame_id, request.args.get('token', ''))
    frame = db.session.get(EvidenceFrame, frame_id)
    if not frame:
        raise ApiError(404, 'not_found', 'Кадр не найден.')
    return send_file(file_path(frame.storage_key), mimetype='image/jpeg', conditional=True)


@workspace_bp.get('/overview')
@active_required
def overview():
    query = alerts_for_day()
    total = query.count()
    read = query.filter(is_read()).count()
    day, start, end = day_bounds()
    health = monitoring_snapshot(start, end)
    return jsonify(date=day, monitoring_summary=health['summary'], today_total=total, today_read=read, today_unread=total-read,
                   unread_total=CameraAlert.query.filter(~is_read()).count(),
                   camera_total=Camera.query.count(), media_total=media_query().count(),
                   recent_alerts=[alert_dto(a) for a in query.order_by(CameraAlert.detected_at.desc(), CameraAlert.id.desc()).limit(5)],
                   recent_media=[m.to_dict() for m in media_query().order_by(MediaRecord.created_at.desc(), MediaRecord.id.desc()).limit(3)])


@workspace_bp.get('/sources')
@active_required
def sources():
    return jsonify(pagination(RegulatorySource.query.filter_by(is_active=True).order_by(RegulatorySource.id), lambda s: s.to_dict()))
