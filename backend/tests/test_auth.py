"""Тесты авторизации и администрирования."""
import json


def post_json(client, url, data, headers=None):
    return client.post(url, data=json.dumps(data),
                       content_type='application/json', headers=headers or {})


class TestRegister:
    def test_register_with_email(self, client):
        resp = post_json(client, '/api/auth/register', {
            'email': 'new@test.com', 'password': 'secret123', 'full_name': 'New User',
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['user']['email'] == 'new@test.com'
        assert 'access_token' in body
        assert 'refresh_token' in body

    def test_register_with_nickname(self, client):
        resp = post_json(client, '/api/auth/register', {
            'nickname': 'cool_nick', 'password': 'secret123',
        })
        assert resp.status_code == 201
        assert resp.get_json()['user']['nickname'] == 'cool_nick'

    def test_register_with_identifier(self, client):
        resp = post_json(client, '/api/auth/register', {
            'identifier': 'ident@test.com', 'password': 'secret123',
        })
        assert resp.status_code == 201
        assert resp.get_json()['user']['email'] == 'ident@test.com'

    def test_register_duplicate_email(self, client, user1):
        resp = post_json(client, '/api/auth/register', {
            'email': 'user1@test.com', 'password': 'secret123',
        })
        assert resp.status_code == 400

    def test_register_short_password(self, client):
        resp = post_json(client, '/api/auth/register', {
            'email': 'x@test.com', 'password': '123',
        })
        assert resp.status_code == 400

    def test_register_invalid_email(self, client):
        resp = post_json(client, '/api/auth/register', {
            'email': 'not-an-email', 'password': 'secret123',
        })
        assert resp.status_code == 400

    def test_register_no_identifier(self, client):
        resp = post_json(client, '/api/auth/register', {'password': 'secret123'})
        assert resp.status_code == 400


class TestLogin:
    def test_login_with_email(self, client, user1):
        resp = post_json(client, '/api/auth/login', {
            'email': 'user1@test.com', 'password': 'test1234',
        })
        assert resp.status_code == 200
        assert 'access_token' in resp.get_json()

    def test_login_with_identifier_nickname(self, client, user1):
        resp = post_json(client, '/api/auth/login', {
            'identifier': 'user1', 'password': 'test1234',
        })
        assert resp.status_code == 200

    def test_login_wrong_password(self, client, user1):
        resp = post_json(client, '/api/auth/login', {
            'email': 'user1@test.com', 'password': 'wrong',
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = post_json(client, '/api/auth/login', {
            'email': 'ghost@test.com', 'password': 'test1234',
        })
        assert resp.status_code == 401


class TestTokens:
    def test_refresh(self, client, refresh_headers):
        resp = client.post('/api/auth/refresh', headers=refresh_headers)
        assert resp.status_code == 200
        assert 'access_token' in resp.get_json()

    def test_me(self, client, auth_headers):
        resp = client.get('/api/auth/me', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['data']['user']['email'] == 'user1@test.com'

    def test_me_without_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401


class TestProfile:
    def test_update_full_name(self, client, auth_headers):
        resp = client.put('/api/auth/profile', data=json.dumps({'full_name': 'Updated'}),
                          content_type='application/json', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['data']['user']['full_name'] == 'Updated'

    def test_update_nickname_taken(self, client, auth_headers, user2):
        resp = client.put('/api/auth/profile', data=json.dumps({'nickname': 'user2'}),
                          content_type='application/json', headers=auth_headers)
        assert resp.status_code == 400


class TestPassword:
    def test_change_password(self, client, auth_headers):
        resp = post_json(client, '/api/auth/change-password', {
            'current_password': 'test1234', 'new_password': 'newpass123',
        }, headers=auth_headers)
        assert resp.status_code == 200

        # Логин с новым паролем работает
        resp = post_json(client, '/api/auth/login', {
            'email': 'user1@test.com', 'password': 'newpass123',
        })
        assert resp.status_code == 200

    def test_change_password_wrong_current(self, client, auth_headers):
        resp = post_json(client, '/api/auth/change-password', {
            'current_password': 'wrong', 'new_password': 'newpass123',
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_forgot_password_unknown_email_is_silent(self, client):
        resp = post_json(client, '/api/auth/forgot-password', {'email': 'ghost@test.com'})
        assert resp.status_code == 200


class TestDeactivate:
    def test_deactivate(self, client, auth_headers):
        resp = post_json(client, '/api/auth/deactivate', {'password': 'test1234'},
                         headers=auth_headers)
        assert resp.status_code == 200

        # После деактивации логин не работает
        resp = post_json(client, '/api/auth/login', {
            'email': 'user1@test.com', 'password': 'test1234',
        })
        assert resp.status_code == 401


class TestAdmin:
    def test_list_users_as_admin(self, client, admin_headers, user1, user2):
        resp = client.get('/api/admin/users', headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()['total'] >= 3

    def test_list_users_as_regular_user(self, client, auth_headers):
        resp = client.get('/api/admin/users', headers=auth_headers)
        assert resp.status_code == 403

    def test_update_user(self, client, admin_headers, user1):
        resp = client.patch(f'/api/admin/users/{user1.id}',
                            data=json.dumps({'is_active': False}),
                            content_type='application/json', headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()['user']['is_active'] is False
