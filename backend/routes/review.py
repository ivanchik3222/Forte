"""Collector ingestion and the non-ML shift review API."""
import math
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.exc import IntegrityError
from models import db, Camera, CameraAlert, AlertRecording, as_utc, utcnow, _utc_iso
from utils.decorators import active_required, admin_required
from utils.errors import ApiError
from services.media import get_media
from services.monitoring import HEALTH_STATUSES, ingest_health, monitoring_snapshot
from routes.workspace import day_bounds, alerts_for_day, alert_dto

review_bp = Blueprint('review', __name__)


def fields(data, allowed):
    if set(data) - set(allowed):
        raise ApiError(422, 'invalid_fields', 'Переданы неизвестные поля.')


def string(data, key, limit):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ApiError(422, 'invalid_field', f'Некорректное поле {key}.')
    return value.strip()


def timestamp(data, key):
    value = data.get(key)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        parsed = as_utc(parsed)
        if parsed > utcnow():
            raise ValueError()
        return parsed
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ApiError(422, 'invalid_timestamp', f'{key}: нужна дата ISO 8601 с часовым поясом, не в будущем.')


def recording(media_id, offset):
    if not isinstance(media_id, str):
        raise ApiError(422, 'invalid_field', 'media_id должен быть строкой.')
    media = get_media(media_id)
    if not media.duration_sec or not math.isfinite(media.duration_sec) or offset >= media.duration_sec:
        raise ApiError(422, 'invalid_timecode', 'Таймкод должен находиться внутри записи с известной длительностью.')
    return media


@review_bp.post('/cameras/<camera_id>/health')
@admin_required
def health_check(camera_id):
    data = request.get_json()
    fields(data, ('external_id', 'source', 'status', 'checked_at'))
    status = data.get('status')
    if status not in HEALTH_STATUSES:
        raise ApiError(422, 'invalid_status', 'Неизвестный результат проверки камеры.')
    report, code = ingest_health(camera_id, string(data, 'external_id', 120), string(data, 'source', 80),
                                  status, timestamp(data, 'checked_at'))
    return jsonify(id=report.id, camera_id=report.camera_id, status=report.status, checked_at=_utc_iso(report.checked_at)), code


@review_bp.get('/monitoring')
@active_required
def monitoring():
    day, start, end = day_bounds()
    data = monitoring_snapshot(start, end, request.args.get('camera_id'))
    # Interval pagination does not change the summary's scope.
    try:
        page, per_page = int(request.args.get('page', 1)), int(request.args.get('per_page', 50))
        if page < 1 or not 1 <= per_page <= 100:
            raise ValueError()
    except ValueError:
        raise ApiError(400, 'invalid_pagination', 'page >= 1, per_page от 1 до 100.')
    items = data['incidents']
    data['incidents'] = dict(items=items[(page-1)*per_page:page*per_page], total=len(items), page=page, per_page=per_page)
    return jsonify(date=day, **data)


@review_bp.post('/events')
@admin_required
def create_event():
    data = request.get_json()
    fields(data, ('camera_id', 'source', 'external_event_id', 'detected_at', 'type', 'description', 'timecode_sec', 'media_id'))
    camera_id = string(data, 'camera_id', 36)
    if not db.session.get(Camera, camera_id):
        raise ApiError(404, 'not_found', 'Камера не найдена.')
    source = string(data, 'source', 80)
    if source == 'test' and not (current_app.debug or current_app.testing or current_app.config['ALLOW_TEST_EVENTS']):
        raise ApiError(403, 'test_events_disabled', 'Тестовые события отключены.')
    offset = data.get('timecode_sec', 0)
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0:
        raise ApiError(422, 'invalid_timecode', 'timecode_sec должен быть конечным неотрицательным числом.')
    values = dict(camera_id=camera_id, source=source, external_event_id=string(data, 'external_event_id', 120),
        detected_at=timestamp(data, 'detected_at'), type=string(data, 'type', 255),
        description=string(data, 'description', 10000), timecode_sec=offset)
    media_id = data.get('media_id')
    if media_id is not None:
        recording(media_id, offset)

    def replay(existing):
        link = db.session.get(AlertRecording, existing.id)
        matches = all((as_utc(getattr(existing, k)) if k == 'detected_at' else getattr(existing, k)) == v for k, v in values.items())
        if not matches or (link.media_id if link else None) != media_id:
            raise ApiError(409, 'idempotency_conflict', 'ID события уже использован с другими данными.')
        return jsonify(alert_dto(existing, detail=True)), 200

    previous = CameraAlert.query.filter_by(source=source, external_event_id=values['external_event_id']).first()
    if previous:
        return replay(previous)
    alert = CameraAlert(**values)
    try:
        db.session.add(alert)
        db.session.flush()
        if media_id:
            db.session.add(AlertRecording(alert_id=alert.id, media_id=media_id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        previous = CameraAlert.query.filter_by(source=source, external_event_id=values['external_event_id']).first()
        if previous:
            return replay(previous)
        raise
    return jsonify(alert_dto(alert, detail=True)), 201


@review_bp.put('/notifications/<alert_id>/recording')
@admin_required
def attach_recording(alert_id):
    data = request.get_json()
    fields(data, ('media_id',))
    alert = db.session.get(CameraAlert, alert_id)
    if not alert:
        raise ApiError(404, 'not_found', 'Событие не найдено.')
    media = recording(data.get('media_id'), alert.timecode_sec)
    # One association per event, atomically replaceable by an administrator.
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    insert = postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    db.session.execute(insert(AlertRecording).values(alert_id=alert.id, media_id=media.id)
        .on_conflict_do_update(index_elements=['alert_id'], set_={'media_id': media.id}))
    db.session.commit()
    return jsonify(alert_dto(alert, detail=True))


@review_bp.get('/shift')
@active_required
def shift():
    day, start, end = day_bounds()
    query = alerts_for_day()
    # Same deterministic order as the demo: six latest, played chronologically.
    episodes = query.order_by(CameraAlert.detected_at.desc(), CameraAlert.id.desc()).limit(6).all()[::-1]
    health = monitoring_snapshot(start, end, request.args.get('camera_id'))
    return jsonify(date=day, total=query.count(), episodes=[alert_dto(a, detail=True) for a in episodes],
        cameras=health['cameras'], incidents=health['incidents'], monitoring_summary=health['summary'],
        as_of=health['as_of'], selection='latest_six', max_duration_sec=len(episodes)*10)
