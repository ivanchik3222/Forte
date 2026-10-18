"""Executable proof of the security boundaries shown to the jury."""
import time
from types import SimpleNamespace
import pytest
import pyotp
from flask_jwt_extended import decode_token
from models import (db, Branch, BranchAccess, Camera, CameraScope, CameraAccess,
                    CameraAlert, EvidenceFrame, MediaRecord, AlertRecording,
                    UserMFA, AuthSession, SessionSecurity, CameraHealthInterval, utcnow)
from routes.auth import make_tokens
from services.demo_account import seed_demo_user, DEMO_EMAIL, DEMO_PASSWORD
from services.security import mfa_cipher


def headers(user):
    token, _ = make_tokens(user)
    return {'Authorization': f'Bearer {token}'}


def login(client, identifier='user1', password='test1234', **extra):
    return client.post('/api/auth/login', json=dict(identifier=identifier, password=password, **extra))


@pytest.fixture
def throttle_clock(app, monkeypatch):
    # Keep requests in one fixed window regardless of CI timing. Replace only
    # the security module's clock, leaving JWT/session timestamps untouched.
    clock = SimpleNamespace(now=100 * app.config['AUTH_WINDOW_SECONDS'])
    monkeypatch.setattr('services.security.time', SimpleNamespace(time=lambda: clock.now))
    return clock


@pytest.fixture
def scoped(user1, user2, app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    branches = [Branch(id='a', name='A'), Branch(id='b', name='B')]
    cameras = [Camera(id='a', name='A', location='A'), Camera(id='b', name='B', location='B')]
    db.session.add_all(branches + cameras); db.session.flush()
    db.session.add_all([CameraScope(camera_id=c.id, branch_id=c.id) for c in cameras])
    db.session.add_all([BranchAccess(user_id=user1.id, branch_id='a'), BranchAccess(user_id=user2.id, branch_id='b')])
    for c in cameras:
        event = CameraAlert(id=c.id, camera_id=c.id, source='manual', type=c.name, description=c.name)
        db.session.add(event); db.session.flush()
        db.session.add(EvidenceFrame(id=c.id, alert_id=c.id, timestamp_sec=0, storage_key=c.id+'.jpg'))
        (tmp_path/(c.id+'.jpg')).write_bytes(b'jpeg')
    db.session.commit()
    return tmp_path


def test_branch_isolation_covers_lists_details_frames_and_aggregates(client, user1, scoped):
    h = headers(user1)
    assert [c['id'] for c in client.get('/api/v1/cameras', headers=h).json['items']] == ['a']
    assert client.get('/api/v1/notifications/b', headers=h).status_code == 404
    assert client.post('/api/v1/notifications/read', headers=h, json={'ids':['a','b']}).status_code == 404
    assert client.get('/api/v1/notifications', headers=h).json['total'] == 1
    overview = client.get('/api/v1/overview', headers=h).json
    assert overview['camera_total'] == 1 and overview['unread_total'] == 1
    assert client.get('/api/v1/shift', headers=h).json['total'] == 1
    assert client.get('/api/v1/shift?camera_id=b', headers=h).json['episodes'] == []
    assert [c['id'] for c in client.get('/api/v1/monitoring', headers=h).json['cameras']] == ['a']
    detail = client.get('/api/v1/notifications/a', headers=h).json
    url = detail['event']['evidence_frames'][0]['image_url']
    assert client.get(url).data == b'jpeg'
    assert client.get(url.replace('/frames/a/', '/frames/b/')).status_code == 401
    BranchAccess.query.filter_by(user_id=user1.id).delete(); db.session.commit()
    assert client.get(url).status_code == 404  # Already-issued link loses access immediately.
    assert client.get('/api/v1/cameras', headers=h).json['items'] == []


def test_camera_grant_and_linked_media_do_not_bypass_branch(client, user1, user2, scoped):
    record = MediaRecord(id='video', owner_id=user1.id, original_name='v.mp4', storage_key='v.mp4', size_bytes=5, content_type='video/mp4')
    db.session.add(record); db.session.commit()
    (scoped/'v.mp4').write_bytes(b'video')
    h = headers(user1)
    url = client.post('/api/v1/media/video/playback-url', headers=h).json['url']
    db.session.add(AlertRecording(alert_id='b', media_id='video')); db.session.commit()
    for path in ('/media/video', '/media/video/report', '/media/video/analysis'):
        assert client.get('/api/v1'+path, headers=h).status_code == 404
    assert client.get(url).status_code == 404
    db.session.add(CameraAccess(user_id=user1.id, camera_id='b')); db.session.commit()
    assert client.get(url).data == b'video'
    assert client.get('/api/v1/media/video', headers=headers(user2)).status_code == 404


def test_demo_cannot_read_real_data_or_reuse_old_session_when_disabled(client, app, monkeypatch, scoped):
    demo = seed_demo_user()
    h = headers(demo)
    assert client.get('/api/v1/cameras', headers=h).json['items'] == []
    assert client.get('/api/v1/notifications/a', headers=h).status_code == 404
    assert client.get('/api/v1/overview', headers=h).json['today_total'] == 0
    monkeypatch.setitem(app.config, 'DEMO_MODE', False)
    assert login(client, DEMO_EMAIL, DEMO_PASSWORD).status_code == 401
    assert client.get('/api/v1/overview', headers=h).status_code == 401
    assert app.test_cli_runner().invoke(args=['seed-demo-user']).exit_code != 0


def test_admin_access_management_and_non_admin_denial(client, admin_headers, user1, scoped):
    h = headers(user1)
    path = f'/api/admin/users/{user1.id}/access'
    payload = {'branch_ids': [], 'camera_ids': ['b']}
    assert client.put(path, headers=h, json=payload).status_code == 403
    assert client.put(path, headers=admin_headers, json=payload).status_code == 200
    assert [c['id'] for c in client.get('/api/v1/cameras', headers=h).json['items']] == ['b']
    assert client.put('/api/admin/cameras/a/scope', headers=admin_headers, json={'branch_id':'a', 'is_demo':True}).status_code == 403


def test_login_limit_shared_across_aliases_and_client_addresses(client, app, monkeypatch, user1, throttle_clock):
    monkeypatch.setitem(app.config, 'AUTH_ACCOUNT_LIMIT', 2)
    assert login(client, 'user1', 'wrong').status_code == 401
    assert login(client, 'user1@test.com', 'wrong').status_code == 401
    result = client.post('/api/auth/login', json={'identifier':'user1', 'password':'test1234'}, environ_base={'REMOTE_ADDR':'10.0.0.2'})
    assert result.status_code == 429 and result.headers['Retry-After'] == '300'


def test_ip_limit_cannot_be_bypassed_with_forged_forwarded_header(client, app, monkeypatch, throttle_clock):
    monkeypatch.setitem(app.config, 'AUTH_IP_LIMIT', 2)
    for n in range(2):
        assert client.post('/api/auth/login', json={'identifier':str(n), 'password':'wrong'}, headers={'X-Forwarded-For':f'10.1.1.{n}'}).status_code == 401
    assert login(client, 'another', 'wrong').status_code == 429


@pytest.mark.parametrize('limit_setting', ['AUTH_ACCOUNT_LIMIT', 'AUTH_IP_LIMIT'])
def test_login_limit_resets_at_fixed_window_boundary(client, app, monkeypatch, user1, throttle_clock, limit_setting):
    monkeypatch.setitem(app.config, limit_setting, 2)
    next_window = throttle_clock.now + app.config['AUTH_WINDOW_SECONDS']
    throttle_clock.now = next_window - 0.001
    assert login(client, password='wrong').status_code == 401
    assert login(client, 'user1@test.com', 'wrong').status_code == 401
    assert login(client).status_code == 429

    throttle_clock.now = next_window
    assert login(client).status_code == 200
    assert login(client, 'user1@test.com').status_code == 200
    assert login(client).status_code == 429


def test_refresh_rotation_replay_revokes_session_and_signed_urls(client, user1, scoped):
    result = login(client)
    old_cookie = client.get_cookie('refresh_token_cookie', path='/api/auth').value
    old_csrf = result.json['csrf_token']
    h = {'Authorization':'Bearer '+result.json['access_token']}
    url = client.get('/api/v1/notifications/a', headers=h).json['event']['evidence_frames'][0]['image_url']
    refreshed = client.post('/api/auth/refresh', headers={'X-CSRF-TOKEN':old_csrf})
    assert refreshed.status_code == 200 and refreshed.json['csrf_token'] != old_csrf
    assert client.get_cookie('refresh_token_cookie', path='/api/auth').value != old_cookie
    assert client.get(url).status_code == 200
    client.set_cookie('refresh_token_cookie', old_cookie, path='/api/auth')
    assert client.post('/api/auth/refresh', headers={'X-CSRF-TOKEN':old_csrf}).json['error']['code'] == 'refresh_reused'
    assert client.get(url).status_code == 401
    assert client.get('/api/auth/me', headers=h).status_code == 401


def test_admin_requires_mfa_and_used_code_is_rejected(client, app, monkeypatch, admin_user):
    monkeypatch.setitem(app.config, 'ADMIN_MFA_REQUIRED', True)
    assert login(client, 'admin1').json['error']['code'] == 'mfa_setup_required'
    secret = pyotp.random_base32()
    db.session.add(UserMFA(user_id=admin_user.id, secret=mfa_cipher().encrypt(secret.encode()).decode()))
    db.session.commit()
    assert login(client, 'admin1').json['error']['code'] == 'mfa_required'
    assert login(client, 'admin1', otp='not-a-code').status_code == 401
    code = pyotp.TOTP(secret).now()
    result = login(client, 'admin1', otp=code)
    assert result.status_code == 200
    assert client.get('/api/admin/users', headers={'Authorization':'Bearer '+result.json['access_token']}).status_code == 200
    assert login(client, 'admin1', otp=code).json['error']['code'] == 'mfa_invalid'
    assert client.get('/api/admin/users', headers=headers(admin_user)).status_code == 401


@pytest.mark.parametrize('password', ['short', 'x'*129])
def test_password_policy_on_register_change_reset(client, user1, password):
    assert client.post('/api/auth/register', json={'identifier':'new-user', 'password':password}).status_code == 400
    assert client.post('/api/auth/change-password', headers=headers(user1), json={'current_password':'test1234', 'new_password':password}).status_code == 400
    from datetime import timedelta
    user1.reset_token = 'test-reset'; user1.reset_token_expires = utcnow()+timedelta(minutes=1)
    db.session.commit()
    assert client.post('/api/auth/reset-password', json={'token':'test-reset', 'password':password}).status_code == 400

