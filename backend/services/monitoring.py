"""Health is supplied by a collector; a missing collector never proves an outage.

Intervals are closed transactionally on incoming checks. Reads project expiration
without a scheduler, and the next report persists that same unknown interval.
"""
from datetime import timedelta
from sqlalchemy import select, update, or_
from models import db, Camera, CameraHealthReport, CameraHealthInterval, as_utc, _utc_iso, utcnow
from utils.errors import ApiError

HEALTH_TTL = timedelta(seconds=90)
HEALTH_STATUSES = ('observing', 'offline', 'occluded', 'frozen', 'poor_visibility')


def latest_reports():
    latest_id = (select(CameraHealthReport.id)
                 .where(CameraHealthReport.camera_id == Camera.id)
                 .order_by(CameraHealthReport.checked_at.desc()).limit(1).correlate(Camera).scalar_subquery())
    return {camera.id: report for camera, report in db.session.query(Camera, CameraHealthReport)
            .outerjoin(CameraHealthReport, CameraHealthReport.id == latest_id)}


def health_status(camera, report, now):
    if not camera.is_active or not report or not timedelta(0) <= now - as_utc(report.checked_at) <= HEALTH_TTL:
        return 'unknown'
    return report.status


def camera_dto(camera, report, now):
    data = camera.to_dict()
    status = health_status(camera, report, now)
    data['status'] = 'unknown' if status == 'unknown' else 'offline' if status == 'offline' else 'online'
    data['health_status'] = status
    return data


def ingest_health(camera_id, external_id, source, status, checked_at):
    # A write lock works on both SQLite and PostgreSQL, serializing even the first
    # check and preventing two workers from creating overlapping open intervals.
    result = db.session.execute(update(Camera).where(Camera.id == camera_id).values(is_active=Camera.is_active))
    if not result.rowcount:
        raise ApiError(404, 'not_found', 'Камера не найдена.')
    camera = db.session.get(Camera, camera_id, populate_existing=True)
    previous = CameraHealthReport.query.filter_by(camera_id=camera_id, external_id=external_id).first()
    if previous:
        if (previous.source, previous.status, as_utc(previous.checked_at)) != (source, status, checked_at):
            raise ApiError(409, 'idempotency_conflict', 'ID проверки уже использован с другими данными.')
        db.session.commit()
        return previous, 200
    if not camera.is_active:
        raise ApiError(409, 'camera_inactive', 'Камера отключена в справочнике.')
    latest = CameraHealthReport.query.filter_by(camera_id=camera_id).order_by(CameraHealthReport.checked_at.desc()).first()
    if latest and checked_at <= as_utc(latest.checked_at):
        raise ApiError(409, 'out_of_order', 'Проверки должны поступать по возрастанию checked_at.')
    opened = CameraHealthInterval.query.filter_by(camera_id=camera_id, ended_at=None).first()
    gap = bool(latest and checked_at > as_utc(latest.checked_at) + HEALTH_TTL)
    if opened and (gap or opened.kind != status):
        opened.ended_at = as_utc(latest.checked_at) + HEALTH_TTL if gap else checked_at
    if gap:
        db.session.add(CameraHealthInterval(camera_id=camera_id, kind='unknown',
            started_at=as_utc(latest.checked_at) + HEALTH_TTL, ended_at=checked_at))
    if status != 'observing' and (not opened or gap or opened.kind != status):
        db.session.add(CameraHealthInterval(camera_id=camera_id, kind=status, started_at=checked_at))
    report = CameraHealthReport(camera_id=camera_id, external_id=external_id, source=source,
                                status=status, checked_at=checked_at)
    camera.status = 'offline' if status == 'offline' else 'online'
    camera.last_seen_at = checked_at
    db.session.add(report)
    db.session.commit()
    return report, 201


def monitoring_snapshot(start, end, camera_id=None, now=None):
    now = now or utcnow()
    cameras = Camera.query.order_by(Camera.name, Camera.id).all()
    reports = latest_reports()
    scope = [c for c in cameras if not camera_id or c.id == camera_id]
    query = CameraHealthInterval.query.filter(CameraHealthInterval.started_at < min(end, now),
        or_(CameraHealthInterval.ended_at.is_(None), CameraHealthInterval.ended_at > start))
    if camera_id:
        query = query.filter_by(camera_id=camera_id)
    intervals = []

    def add(identifier, cid, kind, began, finished):
        left, right = max(start, began), min(end, now, finished or now)
        if right > left:
            intervals.append(dict(id=identifier, cameraId=cid, mode='api', kind=kind,
                startedAt=_utc_iso(left), endedAt=_utc_iso(right) if finished or right < now else None,
                duration_sec=(right-left).total_seconds()))

    for item in query:
        report = reports.get(item.camera_id)
        # A check can commit between the report query and this query. Project
        # history only through the captured report, so the newly persisted gap
        # cannot be counted a second time alongside its virtual counterpart.
        if not report or as_utc(item.started_at) > as_utc(report.checked_at):
            continue
        finished = as_utc(item.ended_at) if item.ended_at else None
        if finished and finished > as_utc(report.checked_at):
            finished = None
        if not finished and report and now > as_utc(report.checked_at) + HEALTH_TTL:
            finished = as_utc(report.checked_at) + HEALTH_TTL
        add(item.id, item.camera_id, item.kind, as_utc(item.started_at), finished)
    signals = {}
    for camera in scope:
        report = reports.get(camera.id)
        if report:
            signals[camera.id] = dict(cameraId=camera.id, mode='api', status=health_status(camera, report, now),
                checkedAt=_utc_iso(report.checked_at), source=report.source)
            expiry = as_utc(report.checked_at) + HEALTH_TTL
            if now > expiry:
                add(f'expired-{report.id}', camera.id, 'unknown', expiry, None)
    intervals.sort(key=lambda x: (x['startedAt'], x['id']), reverse=True)
    statuses = [health_status(c, reports.get(c.id), now) for c in scope]
    return dict(as_of=_utc_iso(now), ttl_seconds=int(HEALTH_TTL.total_seconds()),
        cameras=[camera_dto(c, reports.get(c.id), now) for c in cameras], signals=signals,
        incidents=intervals, summary=dict(
            problems=sum(s not in ('observing', 'unknown') for s in statuses),
            unknown=statuses.count('unknown'),
            unavailable_minutes=sum(i['duration_sec'] for i in intervals if i['kind'] in ('offline','occluded','frozen')) / 60,
            unknown_minutes=sum(i['duration_sec'] for i in intervals if i['kind'] == 'unknown') / 60,
            degraded_minutes=sum(i['duration_sec'] for i in intervals if i['kind'] == 'poor_visibility') / 60))
