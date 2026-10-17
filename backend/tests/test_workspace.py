from tests.access_helpers import grant_camera
import io
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import inspect, text
from flask_migrate import upgrade
from models import db, MediaRecord, Camera, CameraAlert, AlertRead, AuthSession, User, EvidenceFrame
from routes.auth import make_tokens


@pytest.fixture
def storage(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    monkeypatch.setitem(app.config, 'MIN_FREE_BYTES', 0)
    monkeypatch.setattr('services.media.probe', lambda path, ext: 1.0)
    return tmp_path


def upload(client, headers, content=b'video-data', name='cash.mov', key='upload-1'):
    return client.post('/api/v1/media', headers={**headers, 'Idempotency-Key': key},
                       data={'file': (io.BytesIO(content), name)}, content_type='multipart/form-data')


def test_upload_history_detail_export_and_range(client, auth_headers, storage):
    response = upload(client, auth_headers)
    assert response.status_code == 201
    item = response.json
    assert item['status'] == 'stored' and item['verdict'] is None and item['violations'] == []
    assert len(list(storage.glob('*.mov'))) == 1
    record_id = item['id']
    assert client.get('/api/v1/media', headers=auth_headers).json['total'] == 1
    assert client.get(f'/api/v1/media/{record_id}', headers=auth_headers).json == item
    assert client.get(f'/api/v1/media/{record_id}/report', headers=auth_headers).json['analysis_status'] == 'not_requested'
    url = client.post(f'/api/v1/media/{record_id}/playback-url', headers=auth_headers).json['url']
    content = client.get(url, headers={'Range': 'bytes=0-4'})
    assert content.status_code == 206 and content.data == b'video'
    assert client.get(url, headers={'Range': 'bytes=1000-2000'}).status_code == 416
    assert client.get(f'/api/v1/media/{record_id}/content').status_code == 401
    assert client.get('/api/v1/media?search=missing', headers=auth_headers).json['total'] == 0


def test_idempotency_and_conflict(client, auth_headers, storage):
    first = upload(client, auth_headers)
    repeat = upload(client, auth_headers)
    assert repeat.status_code == 200 and first.json['id'] == repeat.json['id']
    assert upload(client, auth_headers, content=b'different').status_code == 409
    assert MediaRecord.query.count() == 1
    assert len(list(storage.glob('*.mov'))) == 1


def test_unicode_filename_search(client, auth_headers, storage):
    assert upload(client, auth_headers, name='КАССА_Астана.mov').status_code == 201
    result=client.get('/api/v1/media', query_string={'search':'касса_астана'}, headers=auth_headers)
    assert result.json['total'] == 1
    assert client.get('/api/v1/media', query_string={'search':'%'}, headers=auth_headers).json['total'] == 0


def test_media_scope_and_role_change(client, auth_headers, user2, admin_headers, admin_user, storage):
    item = upload(client, auth_headers).json
    other, _ = make_tokens(user2)
    other_headers = {'Authorization': f'Bearer {other}'}
    assert client.get('/api/v1/media', headers=other_headers).json['total'] == 0
    assert client.get(f'/api/v1/media/{item["id"]}', headers=other_headers).status_code == 404
    assert client.post(f'/api/v1/media/{item["id"]}/playback-url', headers=other_headers).status_code == 404
    assert client.get(f'/api/v1/media/{item["id"]}', headers=admin_headers).status_code == 200
    admin_user.user_type = 'user'; db.session.commit()
    assert client.get('/api/admin/users', headers=admin_headers).status_code == 403


@pytest.mark.parametrize('name,content,status', [('empty.mp4', b'', 422), ('bad.exe', b'123', 415)])
def test_bad_uploads(client, auth_headers, storage, name, content, status):
    assert upload(client, auth_headers, content, name).status_code == status
    assert not list(storage.glob('.pending-*')) and MediaRecord.query.count() == 0


def test_upload_size_and_rate_limits(client, auth_headers, storage, app, monkeypatch):
    monkeypatch.setitem(app.config, 'MAX_FILE_SIZE', 3)
    assert upload(client, auth_headers).status_code == 413
    monkeypatch.setitem(app.config, 'MAX_FILE_SIZE', 100)
    monkeypatch.setitem(app.config, 'UPLOADS_PER_HOUR', 1)
    assert upload(client, auth_headers).status_code == 201
    assert upload(client, auth_headers).status_code == 200
    assert upload(client, auth_headers, key='another').status_code == 429


def test_upload_capabilities_limit(client, auth_headers, app):
    response = client.get('/api/v1/capabilities', headers=auth_headers)
    assert response.status_code == 200
    assert response.json['max_file_size'] == 1024 ** 3
    assert app.config['MAX_CONTENT_LENGTH'] == 1024 ** 3 + 1024 ** 2


def test_upload_exact_limit_and_overflow(client, auth_headers, storage, app, monkeypatch):
    # Exercise multipart and the chunk boundary without a GiB allocation per test.
    limit = 1024 * 1024
    monkeypatch.setitem(app.config, 'MAX_FILE_SIZE', limit)
    monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH', limit + 1024 * 1024)
    content = b'x' * limit
    first = upload(client, auth_headers, content)
    assert first.status_code == 201
    assert MediaRecord.query.one().size_bytes == limit
    assert next(storage.glob('*.mov')).read_bytes() == content
    repeat = upload(client, auth_headers, content)
    assert repeat.status_code == 200 and repeat.json['id'] == first.json['id']
    rejected = upload(client, auth_headers, content + b'x', key='oversized')
    assert rejected.status_code == 413
    assert rejected.json['error']['code'] == 'file_too_large'
    assert str(limit) in rejected.json['error']['message']
    assert MediaRecord.query.count() == 1
    assert len(list(storage.glob('*.mov'))) == 1
    assert not list(storage.glob('.pending-*'))


def test_upload_body_limit(client, auth_headers, storage, app, monkeypatch):
    monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH', 1024)
    response = upload(client, auth_headers, b'x' * 1024)
    assert response.status_code == 413
    assert response.json['error']['code'] == 'http_413'
    assert MediaRecord.query.count() == 0
    assert not list(storage.glob('.pending-*'))
    assert not list(storage.glob('*.mov'))


def test_upload_xhr_cors_preflight(client, app):
    origin = app.config['CORS_ORIGINS'][0]
    response = client.options('/api/v1/media', headers={
        'Origin': origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,idempotency-key',
    })
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == origin
    assert response.headers['Access-Control-Allow-Credentials'] == 'true'
    allowed = response.headers['Access-Control-Allow-Headers'].lower()
    assert 'authorization' in allowed and 'idempotency-key' in allowed


def test_commit_failure_removes_file(client, auth_headers, storage, monkeypatch):
    def fail():
        raise RuntimeError('Database write failed')
    monkeypatch.setattr(db.session, 'commit', fail)
    assert upload(client, auth_headers).status_code == 500
    assert not list(storage.glob('*.mov')) and not list(storage.glob('.pending-*'))
    assert MediaRecord.query.count() == 0


def test_disk_full(client, auth_headers, storage, monkeypatch):
    from collections import namedtuple
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr('services.media.shutil.disk_usage', lambda _: usage(10,10,0))
    assert upload(client, auth_headers).json['error']['code'] == 'storage_full'


def test_session_csrf_restore_logout_revokes_media(client, user1, storage):
    login = client.post('/api/auth/login', json={'identifier': 'user1', 'password': 'test1234'})
    token = login.json['access_token']; headers = {'Authorization': f'Bearer {token}'}
    item = upload(client, headers).json
    url = client.post(f'/api/v1/media/{item["id"]}/playback-url', headers=headers).json['url']
    assert client.post('/api/auth/refresh').status_code == 401
    csrf = client.get('/api/auth/session-csrf').json['csrf_token']
    assert client.post('/api/auth/refresh', headers={'X-CSRF-TOKEN': csrf}).status_code == 200
    assert client.post('/api/auth/refresh', headers={'X-CSRF-TOKEN': csrf, 'Origin': 'https://evil.invalid'}).status_code == 403
    csrf = client.get('/api/auth/session-csrf').json['csrf_token']
    assert client.post('/api/auth/logout', headers={'X-CSRF-TOKEN': csrf}).status_code == 200
    assert client.get('/api/v1/media', headers=headers).status_code == 401
    assert client.get(url).status_code == 401
    assert client.get('/api/auth/session-csrf').status_code == 401


def test_inactive_account_denied(client, user1, auth_headers):
    user1.is_active = False; db.session.commit()
    assert client.get('/api/v1/capabilities', headers=auth_headers).status_code == 401


def test_production_rejects_placeholder_secrets():
    from app import create_app
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app({'REQUIRE_SECURE_CONFIG': True, 'TESTING': False, 'SECRET_KEY': 'short'})


def test_registration_can_be_disabled(client, app, monkeypatch):
    monkeypatch.setitem(app.config, 'PUBLIC_REGISTRATION', False)
    result = client.post('/api/auth/register', json={'identifier':'new-user','password':'secret123'})
    assert result.status_code == 403


def test_notifications_date_read_scope_and_counts(client, auth_headers, user1, user2):
    camera = Camera(id='cam1', name='Cash 1', location='Office')
    db.session.add(camera); db.session.flush()
    grant_camera(camera, user1, user2)
    for i, hour in enumerate([18, 19, 20]):
        db.session.add(CameraAlert(id=f'event{i}', camera_id=camera.id, source='test', type='Test', description='Test only', detected_at=datetime(2026,10,16,hour,tzinfo=timezone.utc)))
    db.session.commit()
    result = client.get('/api/v1/notifications?date=2026-10-17&per_page=1', headers=auth_headers)
    assert result.json['total'] == 2 and len(result.json['items']) == 1
    assert result.json['counts']['new'] == 2
    first = client.post('/api/v1/notifications/read', headers=auth_headers, json={'ids':['event1']}).json
    again = client.post('/api/v1/notifications/read', headers=auth_headers, json={'ids':['event1']}).json
    assert first == again and AlertRead.query.count() == 1
    summary = client.get('/api/v1/overview?date=2026-10-17', headers=auth_headers).json
    assert summary['today_read'] == 1 and summary['today_unread'] == 1 and summary['unread_total'] == 2
    token, _ = make_tokens(user2)
    other = client.get('/api/v1/overview?date=2026-10-17', headers={'Authorization':f'Bearer {token}'}).json
    assert other['today_read'] == 0 and other['unread_total'] == 3
    assert client.post('/api/v1/notifications/read', headers=auth_headers, json={'ids':['event2','missing']}).status_code == 404
    assert AlertRead.query.count() == 1


def test_camera_admin_and_unavailable_analysis(client, auth_headers, admin_headers):
    assert client.post('/api/v1/cameras', json={'name':'C','location':'L'}, headers=auth_headers).status_code == 403
    created = client.post('/api/v1/cameras', json={'name':'C','location':'L'}, headers=admin_headers)
    assert created.status_code == 201 and created.json['status'] == 'unknown'
    assert client.patch('/api/v1/cameras/'+created.json['id'], json={'status':'online'}, headers=admin_headers).status_code == 422
    # The jury endpoint now has its own API-key authentication, independent of JWT.
    assert client.post('/api/v1/analyze', headers=auth_headers).json['error']['code'] == 'invalid_api_key'


@pytest.mark.parametrize('path', ['/media?page=0','/media?per_page=101','/media?sort=no','/notifications?date=bad','/notifications?read=wrong'])
def test_query_validation(client, auth_headers, path):
    result = client.get('/api/v1'+path, headers=auth_headers)
    assert result.status_code == 400 and isinstance(result.json['error']['message'], str)


def test_empty_factory_migrations_and_restart(tmp_path):
    from app import create_app
    config = {'TESTING':True, 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "fresh.db"}'}
    fresh = create_app(config)
    with fresh.app_context():
        assert not inspect(db.engine).get_table_names()
        upgrade()
        db.session.add(User(email='persist@test.com', is_active=True)); db.session.commit()
        db.session.remove(); db.engine.dispose()
    restarted = create_app(config)
    with restarted.app_context():
        assert User.query.filter_by(email='persist@test.com').one()
        assert 'media_records' in inspect(db.engine).get_table_names()
        assert restarted.test_client().get('/missing').json['error']['code'] == 'http_404'
        db.session.remove(); db.engine.dispose()


def test_legacy_adoption_preserves_users(tmp_path):
    from app import create_app
    fresh = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "legacy.db"}'})
    with fresh.app_context():
        User.__table__.create(db.engine)
        db.session.add(User(email='legacy@test.com')); db.session.commit()
        result = fresh.test_cli_runner().invoke(args=['adopt-legacy-db','--backup-confirmed'])
        assert result.exit_code == 0, result.output
        assert User.query.filter_by(email='legacy@test.com').one()
        assert db.session.execute(text('select version_num from alembic_version')).scalar() == '0006'
        db.session.remove(); db.engine.dispose()


@pytest.mark.parametrize('extension,codec', [('mp4','libx264'), ('mov','libx264'), ('webm','libvpx')])
def test_real_video_validation(client, auth_headers, app, tmp_path, monkeypatch, extension, codec):
    ffmpeg = os.environ.get('TEST_FFMPEG') or shutil.which('ffmpeg')
    ffprobe = os.environ.get('FFPROBE_PATH') or shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        pytest.skip('Install ffmpeg/ffprobe to run real container validation')
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path/'media'))
    monkeypatch.setitem(app.config, 'FFPROBE_PATH', ffprobe)
    source = tmp_path/f'sample.{extension}'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=black:s=32x32:d=0.2','-c:v',codec,'-y',str(source)],check=True,timeout=30)
    result = upload(client, auth_headers, source.read_bytes(), f'real.{extension}')
    assert result.status_code == 201, result.json
    assert result.json['duration_sec'] > 0
    assert upload(client, auth_headers, b'not video', 'fake.mov', key='invalid').status_code == 415


def test_legacy_adoption_rejects_schema_drift(tmp_path):
    from app import create_app
    fresh = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path / "changed.db"}'})
    with fresh.app_context():
        User.__table__.create(db.engine)
        db.session.execute(text('ALTER TABLE users ADD COLUMN unexpected TEXT')); db.session.commit()
        result = fresh.test_cli_runner().invoke(args=['adopt-legacy-db','--backup-confirmed'])
        assert result.exit_code != 0
        assert 'alembic_version' not in inspect(db.engine).get_table_names()
        db.session.remove(); db.engine.dispose()


def test_import_test_events_is_idempotent_and_blocked_in_production(app, client, auth_headers, tmp_path, monkeypatch):
    fixture = Path(__file__).parent/'fixtures'/'events.json'
    runner = app.test_cli_runner()
    assert runner.invoke(args=['import-test-events',str(fixture)]).exit_code == 0
    assert runner.invoke(args=['import-test-events',str(fixture)]).exit_code == 0
    assert CameraAlert.query.count() == 1
    assert CameraAlert.query.first().source == 'test'
    monkeypatch.setitem(app.config,'TESTING',False)
    monkeypatch.setitem(app.config,'DEBUG',False)
    assert runner.invoke(args=['import-test-events',str(fixture)]).exit_code != 0


def test_signed_url_expiration_and_frame_access(client, auth_headers, storage, app, monkeypatch, user1):
    record=upload(client,auth_headers).json
    url=client.post(f'/api/v1/media/{record["id"]}/playback-url',headers=auth_headers).json['url']
    monkeypatch.setitem(app.config,'PLAYBACK_TTL',-1)
    assert client.get(url).status_code == 401
    monkeypatch.setitem(app.config,'PLAYBACK_TTL',900)
    camera=Camera(id='camera-frame',name='C',location='L'); db.session.add(camera); db.session.flush()
    grant_camera(camera, user1)
    alert=CameraAlert(id='alert-frame',camera_id=camera.id,source='test',type='Frame',description='Fixture')
    db.session.add(alert); db.session.flush()
    frame=EvidenceFrame(id='frame1',alert_id=alert.id,timestamp_sec=0,storage_key='fixture.jpg')
    db.session.add(frame); db.session.commit()
    (storage/'fixture.jpg').write_bytes(b'\xff\xd8\xfffixture')
    detail=client.get('/api/v1/notifications/alert-frame',headers=auth_headers).json
    frame_url=detail['event']['evidence_frames'][0]['image_url']
    assert client.get(frame_url).data == b'\xff\xd8\xfffixture'
    assert client.get('/api/v1/frames/frame1/content').status_code == 401


def test_sqlite_and_media_backup_restore(tmp_path):
    import sqlite3
    from app import create_app
    source_db=tmp_path/'source.db'; restored_db=tmp_path/'restored.db'
    source_media=tmp_path/'source-media'; source_media.mkdir()
    source_app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{source_db}','MEDIA_ROOT':str(source_media)})
    with source_app.app_context():
        upgrade()
        user=User(email='backup@test.com',is_active=True);user.set_password('backup-test-password')
        db.session.add(user);db.session.flush()
        db.session.add(MediaRecord(id='backed-up',owner_id=user.id,original_name='source.mp4',storage_key='source.mp4',size_bytes=5,content_type='video/mp4'))
        db.session.commit()
        (source_media/'source.mp4').write_bytes(b'video')
        db.session.remove();db.engine.dispose()
    with sqlite3.connect(source_db) as source, sqlite3.connect(restored_db) as destination:
        source.backup(destination)
    restored_media=tmp_path/'restored-media';shutil.copytree(source_media,restored_media)
    restored=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{restored_db}','MEDIA_ROOT':str(restored_media)})
    with restored.app_context():
        upgrade()
        token,_=make_tokens(User.query.filter_by(email='backup@test.com').one())
        headers={'Authorization':f'Bearer {token}'}; browser=restored.test_client()
        assert browser.get('/api/v1/media',headers=headers).json['total']==1
        url=browser.post('/api/v1/media/backed-up/playback-url',headers=headers).json['url']
        assert browser.get(url).data==b'video'
        db.session.remove();db.engine.dispose()
