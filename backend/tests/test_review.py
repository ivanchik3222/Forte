from datetime import datetime, timedelta, timezone
import pytest
from flask_migrate import upgrade, downgrade
from sqlalchemy import inspect, MetaData, Table
from models import (db, Camera, CameraAlert, CameraHealthReport, CameraHealthInterval,
                    AlertRecording, MediaRecord, User, AuthSession)
from routes.auth import make_tokens

from tests.access_helpers import grant_camera

BASE = datetime(2026, 10, 17, 7, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    state = {'now': BASE}
    monkeypatch.setattr('routes.review.utcnow', lambda: state['now'])
    monkeypatch.setattr('routes.workspace.utcnow', lambda: state['now'])
    monkeypatch.setattr('services.monitoring.utcnow', lambda: state['now'])
    return state


@pytest.fixture
def camera(user1, user2):
    item = Camera(name='Cash 1', location='Astana')
    db.session.add(item)
    db.session.commit()
    grant_camera(item, user1, user2)
    return item


def check(client, headers, camera, clock, second, status='observing', external_id=None):
    clock['now'] = BASE + timedelta(seconds=second)
    return client.post(f'/api/v1/cameras/{camera.id}/health', headers=headers, json={
        'external_id': external_id or f'check-{second}', 'source': 'collector-1',
        'status': status, 'checked_at': clock['now'].isoformat()})


def snapshot(client, headers, **query):
    result = client.get('/api/v1/monitoring', headers=headers, query_string={'date': '2026-10-17', **query})
    assert result.status_code == 200, result.json
    return result.json


def test_unknown_without_checks_and_freshness_without_scheduler(client, auth_headers, admin_headers, camera, clock):
    data = snapshot(client, auth_headers)
    assert data['summary']['unknown'] == 1 and not data['signals'] and data['incidents']['total'] == 0
    assert check(client, admin_headers, camera, clock, 0).status_code == 201
    assert snapshot(client, auth_headers)['signals'][camera.id]['status'] == 'observing'
    clock['now'] = BASE + timedelta(seconds=180)
    data = snapshot(client, auth_headers)
    assert data['signals'][camera.id]['status'] == 'unknown'
    assert data['summary']['unavailable_minutes'] == 0
    assert data['summary']['unknown_minutes'] == 1.5
    assert client.get('/api/v1/cameras', headers=auth_headers).json['items'][0]['status'] == 'unknown'
    # Projection is read-only; restart/read frequency does not change history.
    assert CameraHealthInterval.query.count() == 0


def test_intervals_merge_recover_and_do_not_count_visibility_as_outage(client, auth_headers, admin_headers, camera, clock):
    for sec, state in [(0,'offline'), (60,'offline'), (120,'occluded'), (180,'frozen'), (240,'poor_visibility'), (300,'observing')]:
        assert check(client, admin_headers, camera, clock, sec, state).status_code == 201
    data = snapshot(client, auth_headers)
    assert data['summary']['unavailable_minutes'] == 4
    assert data['summary']['degraded_minutes'] == 1
    assert data['summary']['unknown_minutes'] == 0
    assert data['incidents']['total'] == 4
    assert CameraHealthInterval.query.filter_by(ended_at=None).count() == 0
    assert data['summary']['problems'] == 0


def test_expired_problem_closes_at_ttl_and_gap_is_persisted_on_recovery(client, auth_headers, admin_headers, camera, clock):
    check(client, admin_headers, camera, clock, 0, 'offline')
    clock['now'] = BASE + timedelta(seconds=180)
    before = snapshot(client, auth_headers)
    assert before['summary']['unavailable_minutes'] == 1.5
    assert before['summary']['unknown_minutes'] == 1.5
    assert [i['kind'] for i in before['incidents']['items']] == ['unknown', 'offline']
    assert check(client, admin_headers, camera, clock, 180).status_code == 201
    after = snapshot(client, auth_headers)
    assert after['summary']['unavailable_minutes'] == 1.5
    assert after['summary']['unknown_minutes'] == 1.5
    assert after['summary']['unknown'] == 0
    assert CameraHealthInterval.query.count() == 2


def test_report_arriving_during_snapshot_does_not_double_count_gap(client, auth_headers, admin_headers, camera, clock, monkeypatch):
    from services import monitoring
    check(client, admin_headers, camera, clock, 0, 'offline')
    captured = monitoring.latest_reports()
    check(client, admin_headers, camera, clock, 180)
    clock['now'] = BASE + timedelta(seconds=240)
    # Simulate a read that captured the old report just before recovery committed.
    monkeypatch.setattr(monitoring, 'latest_reports', lambda: captured)
    data = snapshot(client, auth_headers)
    assert data['summary']['unavailable_minutes'] == 1.5
    assert data['summary']['unknown_minutes'] == 2.5
    assert data['incidents']['total'] == 2


def test_concurrent_first_health_report_is_idempotent(app, tmp_path):
    from app import create_app
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    # SQLite needs a file: its in-memory StaticPool shares one connection across threads.
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    isolated = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI':
                          f'sqlite:///{tmp_path / "concurrent.db"}' if uri.startswith('sqlite') else uri})
    with isolated.app_context():
        db.create_all()
        admin = User(email='concurrent@test.test', user_type='admin', is_active=True)
        camera = Camera(name='concurrent', location='Astana')
        db.session.add_all([admin, camera]); db.session.commit()
        token, _ = make_tokens(admin)
        camera_id = camera.id
        db.session.remove()
    barrier = Barrier(2)
    payload = {'external_id':'same-report', 'source':'collector', 'status':'offline',
               'checked_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}

    def send():
        barrier.wait(timeout=10)
        with isolated.test_client() as client:
            return client.post(f'/api/v1/cameras/{camera_id}/health', json=payload,
                               headers={'Authorization':f'Bearer {token}'}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert sorted(results) == [200, 201]
    with isolated.app_context():
        assert CameraHealthReport.query.filter_by(camera_id=camera_id).count() == 1
        assert CameraHealthInterval.query.filter_by(camera_id=camera_id).count() == 1
        db.session.remove(); db.engine.dispose()


def test_health_idempotency_order_and_admin_only(client, auth_headers, admin_headers, camera, clock):
    assert check(client, auth_headers, camera, clock, 0).status_code == 403
    assert check(client, admin_headers, camera, clock, 0, 'offline').status_code == 201
    assert check(client, admin_headers, camera, clock, 30).status_code == 201
    assert check(client, admin_headers, camera, clock, 0, 'offline').status_code == 200
    assert check(client, admin_headers, camera, clock, 0, 'occluded').status_code == 409
    assert check(client, admin_headers, camera, clock, 20).json['error']['code'] == 'out_of_order'
    assert check(client, admin_headers, camera, clock, 30, external_id='same-time').status_code == 409
    assert CameraHealthReport.query.count() == 2
    assert CameraHealthInterval.query.count() == 1
    assert client.get('/api/v1/monitoring').status_code == 401
    assert client.get('/api/v1/shift').status_code == 401


@pytest.mark.parametrize('field,value', [('status','unknown'), ('status',{}), ('checked_at','bad'),
    ('checked_at','2026-10-17T07:00:00'), ('checked_at','2026-10-18T07:00:00Z'),
    ('external_id',''), ('source','x'*81)])
def test_invalid_health_input(client, admin_headers, camera, clock, field, value):
    data = {'external_id':'one', 'source':'collector', 'status':'observing', 'checked_at':BASE.isoformat(), field:value}
    result = client.post(f'/api/v1/cameras/{camera.id}/health', headers=admin_headers, json=data)
    assert result.status_code == 422
    assert CameraHealthReport.query.count() == 0


def test_health_day_clipping_camera_minutes_filters_pagination(client, auth_headers, admin_headers, camera, clock, user1):
    other = Camera(name='Cash 2', location='Astana')
    db.session.add(other); db.session.commit()
    grant_camera(other, user1)
    # 23:59 previous day in Astana; continuous reports cross the day boundary.
    start = datetime(2026, 10, 16, 18, 59, tzinfo=timezone.utc)
    for c in (camera, other):
        for sec, status in [(0,'offline'), (60,'offline'), (120,'observing')]:
            clock['now'] = start + timedelta(seconds=sec)
            assert client.post(f'/api/v1/cameras/{c.id}/health', headers=admin_headers, json={
                'external_id':str(sec), 'source':'collector', 'status':status, 'checked_at':clock['now'].isoformat()}).status_code == 201
    data = snapshot(client, auth_headers, per_page=1)
    assert data['summary']['unavailable_minutes'] == 2  # one minute for each camera
    assert data['incidents']['total'] == 2 and len(data['incidents']['items']) == 1
    assert data['incidents']['items'][0]['startedAt'] == '2026-10-16T19:00:00Z'
    assert snapshot(client, auth_headers, camera_id=camera.id)['summary']['unavailable_minutes'] == 1
    assert snapshot(client, auth_headers, page=99)['incidents']['items'] == []
    assert client.get('/api/v1/monitoring?per_page=101', headers=auth_headers).status_code == 400
    assert client.get('/api/v1/shift?date=not-a-date', headers=auth_headers).status_code == 400


def test_inactive_camera_does_not_confirm_observation(client, auth_headers, admin_headers, camera, clock):
    check(client, admin_headers, camera, clock, 0)
    response = client.patch(f'/api/v1/cameras/{camera.id}', headers=admin_headers, json={'is_active':False})
    assert response.status_code == 200 and response.json['status'] == 'unknown'
    assert snapshot(client, auth_headers)['signals'][camera.id]['status'] == 'unknown'
    assert check(client, admin_headers, camera, clock, 10).status_code == 409


@pytest.fixture
def media(user1, app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    (tmp_path/'record.mp4').write_bytes(b'0123456789')
    record = MediaRecord(owner_id=user1.id, original_name='shift.mp4', storage_key='record.mp4',
                        size_bytes=10, content_type='video/mp4', duration_sec=100)
    db.session.add(record); db.session.commit()
    return record


def event_payload(camera, media=None, index=0):
    data = dict(camera_id=camera.id, source='manual', external_event_id=f'event-{index}',
        detected_at=(BASE-timedelta(minutes=20-index)).isoformat(), type=f'Episode {index}',
        description='Operator supplied description', timecode_sec=10+index)
    if media:
        data['media_id'] = media.id
    return data


def test_event_ingestion_selection_filters_and_read_persistence(client, auth_headers, admin_headers, camera, clock, media):
    assert client.post('/api/v1/events', headers=auth_headers, json=event_payload(camera)).status_code == 403
    for i in range(9):
        result = client.post('/api/v1/events', headers=admin_headers, json=event_payload(camera, media, i))
        assert result.status_code == 201, result.json
    assert client.post('/api/v1/events', headers=admin_headers, json=event_payload(camera, media, 0)).status_code == 200
    assert client.post('/api/v1/events', headers=admin_headers, json={**event_payload(camera, media), 'type':'changed'}).status_code == 409
    result = client.get('/api/v1/shift?date=2026-10-17', headers=auth_headers)
    assert result.status_code == 200, result.json
    data = result.json
    assert data['total'] == 9 and data['max_duration_sec'] == 60
    assert [a['event']['type'] for a in data['episodes']] == [f'Episode {i}' for i in range(3,9)]
    assert data['episodes'][0]['recording'] == {'media_id':media.id, 'duration_sec':100}
    assert all(a['read_at'] is None for a in data['episodes'])
    assert client.get('/api/v1/shift?date=2026-10-16', headers=auth_headers).json['total'] == 0
    assert client.get('/api/v1/shift?date=2026-10-17&camera_id=other', headers=auth_headers).json['total'] == 0
    first = data['episodes'][0]['id']
    client.post('/api/v1/notifications/read', headers=auth_headers, json={'ids':[first]})
    db.session.expire_all()
    assert client.get('/api/v1/shift?date=2026-10-17', headers=auth_headers).json['episodes'][0]['read_at']
    assert CameraAlert.query.count() == 9 and AlertRecording.query.count() == 9


def test_shift_media_owner_scope_range_and_revocation(client, auth_headers, admin_headers, user2, camera, clock, media):
    created = client.post('/api/v1/events', headers=admin_headers, json=event_payload(camera, media)).json
    token, _ = make_tokens(user2)
    other_headers = {'Authorization':f'Bearer {token}'}
    other = client.get('/api/v1/shift?date=2026-10-17', headers=other_headers).json['episodes'][0]
    assert other['recording'] is None  # Shared event never grants access to a private upload.
    assert client.post(f'/api/v1/media/{media.id}/playback-url', headers=other_headers).status_code == 404
    assert client.get(f'/api/v1/notifications/{created["id"]}', headers=auth_headers).json['recording']['media_id'] == media.id
    link = client.post(f'/api/v1/media/{media.id}/playback-url', headers=auth_headers).json['url']
    response = client.get(link, headers={'Range':'bytes=2-5'})
    assert response.status_code == 206 and response.data == b'2345'
    for session in AuthSession.query.filter_by(user_id=media.owner_id):
        session.revoked_at = BASE
    db.session.commit()
    assert client.get(link).status_code == 401


@pytest.mark.parametrize('offset', [-1, 100, True, '10', float('nan'), float('inf')])
def test_event_rejects_bad_offsets_without_partial_writes(client, admin_headers, camera, clock, media, offset):
    result = client.post('/api/v1/events', headers=admin_headers, json={**event_payload(camera, media), 'timecode_sec':offset})
    assert result.status_code == 422
    assert CameraAlert.query.count() == 0 and AlertRecording.query.count() == 0


def test_attach_existing_event_and_preserve_no_media_fallback(client, auth_headers, admin_headers, camera, clock, media):
    result = client.post('/api/v1/events', headers=admin_headers, json=event_payload(camera))
    alert_id = result.json['id']
    assert result.json['recording'] is None
    path = f'/api/v1/notifications/{alert_id}/recording'
    assert client.put(path, headers=auth_headers, json={'media_id':media.id}).status_code == 403
    assert client.put(path, headers=admin_headers, json={'media_id':'missing'}).status_code == 404
    for _ in range(2):
        assert client.put(path, headers=admin_headers, json={'media_id':media.id}).status_code == 200
    assert AlertRecording.query.count() == 1


def test_new_migration_preserves_existing_video_event_and_readiness(tmp_path):
    from app import create_app
    app = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "upgrade.db"}'})
    with app.app_context():
        upgrade(revision='0002')
        user = User(email='old@test.test'); db.session.add(user); db.session.flush()
        # Seed the historical schema without using fields added by later models.
        legacy_media = Table('media_records', MetaData(), autoload_with=db.session.connection())
        media_id = 'legacy-media'
        db.session.execute(legacy_media.insert().values(
            id=media_id, owner_id=user.id, original_name='old.mp4', search_name='old.mp4',
            storage_key='old.mp4', size_bytes=10, content_type='video/mp4', created_at=BASE))
        camera = Camera(name='old', location='Astana'); db.session.add(camera); db.session.flush()
        alert = CameraAlert(camera_id=camera.id, source='old', type='old', description='old')
        db.session.add(alert); db.session.commit()
        ids = user.id, media_id, alert.id
        upgrade()
        assert db.session.get(User, ids[0]) and db.session.get(MediaRecord, ids[1]) and db.session.get(CameraAlert, ids[2])
        assert app.test_client().get('/api/ready').status_code == 200
        db.session.remove()
        downgrade(revision='0002')
        assert 'alert_recordings' not in inspect(db.engine).get_table_names()
        upgrade()
        assert CameraAlert.query.count() == 1
        db.session.remove(); db.engine.dispose()
