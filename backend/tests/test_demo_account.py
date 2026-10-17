from datetime import timedelta
import pytest
from sqlalchemy import text
from models import db, User, MediaRecord, AuthSession, utcnow
from services.demo_account import DEMO_EMAIL, DEMO_PASSWORD, seed_demo_user


def demo_login(client):
    return client.post('/api/auth/login', json={'identifier': DEMO_EMAIL, 'password': DEMO_PASSWORD})


def test_seed_preserves_user_data_and_sessions(app, client, user1):
    runner = app.test_cli_runner()
    assert runner.invoke(args=['seed-demo-user']).exit_code == 0
    demo = User.query.filter_by(email=DEMO_EMAIL).one()
    demo_id, password_hash = demo.id, demo.password_hash
    db.session.add(MediaRecord(owner_id=demo.id, original_name='test.mp4', storage_key='test.mp4',
                               size_bytes=10, content_type='video/mp4'))
    db.session.commit()
    response = demo_login(client)
    assert response.status_code == 200
    assert runner.invoke(args=['seed-demo-user']).exit_code == 0
    assert User.query.filter_by(email=DEMO_EMAIL).one().id == demo_id
    assert demo.password_hash == password_hash
    assert User.query.count() == 2
    assert MediaRecord.query.filter_by(owner_id=demo_id).count() == 1
    assert AuthSession.query.filter_by(user_id=demo_id, revoked_at=None).count() == 1
    headers = {'Authorization': f'Bearer {response.json["access_token"]}'}
    assert client.get('/api/auth/me', headers=headers).status_code == 200


def test_demo_session_refresh_logout_and_permissions(client):
    seed_demo_user()
    response = demo_login(client)
    assert response.status_code == 200
    assert response.json['user']['user_type'] == 'user'
    assert 'HttpOnly' in response.headers['Set-Cookie']
    headers = {'Authorization': f'Bearer {response.json["access_token"]}'}
    assert client.get('/api/v1/overview', headers=headers).status_code == 200
    assert client.get('/api/admin/users', headers=headers).status_code == 403
    assert client.post('/api/v1/cameras', headers=headers, json={'name': 'Demo', 'location': 'Test'}).status_code == 403
    csrf = {'X-CSRF-TOKEN': response.json['csrf_token']}
    assert client.post('/api/auth/refresh', headers=csrf).status_code == 200
    assert client.post('/api/auth/logout', headers=csrf).status_code == 200
    assert client.get('/api/auth/me', headers=headers).status_code == 401


@pytest.mark.parametrize('method,path,payload', [
    ('put', '/api/auth/profile', {'full_name': 'Changed', 'nickname': 'changed'}),
    ('post', '/api/auth/change-password', {'current_password': DEMO_PASSWORD, 'new_password': 'changed123'}),
    ('post', '/api/auth/deactivate', {'password': DEMO_PASSWORD}),
    ('delete', '/api/auth/deactivate', {}),
])
def test_shared_account_cannot_be_changed_by_visitors(client, method, path, payload):
    seed_demo_user()
    login = demo_login(client)
    response = getattr(client, method)(path, json=payload,
                                      headers={'Authorization': f'Bearer {login.json["access_token"]}'})
    assert response.status_code == 403
    assert response.json['error']['code'] == 'demo_account_shared'
    assert demo_login(client).status_code == 200


def test_shared_password_cannot_be_reset(client):
    demo = seed_demo_user()
    assert client.post('/api/auth/forgot-password', json={'email': DEMO_EMAIL}).status_code == 200
    assert demo.reset_token is None
    demo.reset_token = 'old-reset-token'
    demo.reset_token_expires = utcnow() + timedelta(hours=1)
    db.session.commit()
    assert client.post('/api/auth/reset-password', json={'token': demo.reset_token, 'password': 'changed123'}).status_code == 403
    assert demo_login(client).status_code == 200


def test_demo_cannot_be_promoted(client, admin_headers):
    demo = seed_demo_user()
    response = client.patch(f'/api/admin/users/{demo.id}', json={'user_type': 'admin'}, headers=admin_headers)
    assert response.status_code == 403
    assert db.session.get(User, demo.id).user_type == 'user'


def test_reserved_email_cannot_be_registered_or_created_as_admin(app, client):
    assert client.post('/api/auth/register', json={'identifier': DEMO_EMAIL.upper(), 'password': 'other1234'}).status_code == 409
    result = app.test_cli_runner().invoke(args=['create-user', '--email', DEMO_EMAIL, '--password', 'other1234', '--admin'])
    assert result.exit_code != 0
    assert User.query.count() == 0


def test_existing_conflicting_account_is_not_overwritten(app, create_user):
    existing = create_user(email=DEMO_EMAIL, password='private1234', user_type='admin')
    old_hash = existing.password_hash
    result = app.test_cli_runner().invoke(args=['seed-demo-user'])
    assert result.exit_code != 0
    assert existing.user_type == 'admin' and existing.password_hash == old_hash
    assert User.query.count() == 1


def test_init_db_recreates_demo_after_database_reset(tmp_path):
    from app import create_app
    fresh = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "demo.db"}'})
    with fresh.app_context():
        runner = fresh.test_cli_runner()
        for _ in range(2):
            result = runner.invoke(args=['init-db'])
            assert result.exit_code == 0, result.output
            assert User.query.filter_by(email=DEMO_EMAIL).count() == 1
            assert demo_login(fresh.test_client()).status_code == 200
            db.session.remove()
            db.drop_all()
            db.session.execute(text('DROP TABLE alembic_version'))
            db.session.commit()
        db.session.remove()
        db.engine.dispose()
