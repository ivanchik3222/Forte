"""
Общие фикстуры для тестирования backend.
"""
import sys
import os
import pytest
from datetime import timedelta

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
from models import db as _db
from models import User


def create_test_app():
    """Создать Flask-приложение для тестов."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['JWT_SECRET_KEY'] = 'test-jwt-secret'
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=1)

    _db.init_app(app)
    JWTManager(app)

    from routes.auth import auth_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    return app


@pytest.fixture(scope='session')
def app():
    """Приложение Flask для всей сессии тестов."""
    app = create_test_app()
    yield app


@pytest.fixture(autouse=True)
def setup_db(app):
    """Создаёт и очищает БД перед каждым тестом."""
    with app.app_context():
        _db.create_all()
        yield
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def create_user():
    """Фабрика для создания пользователей."""
    def _create(email=None, nickname=None, password='test1234',
                full_name='Test User', **kwargs):
        user = User(
            email=email,
            nickname=nickname,
            full_name=full_name,
            is_active=True,
            is_verified=False,
            **kwargs
        )
        user.set_password(password)
        _db.session.add(user)
        _db.session.commit()
        return user

    return _create


@pytest.fixture
def user1(create_user):
    """Первый тестовый пользователь."""
    return create_user(email='user1@test.com', nickname='user1', full_name='User One')


@pytest.fixture
def user2(create_user):
    """Второй тестовый пользователь."""
    return create_user(email='user2@test.com', nickname='user2', full_name='User Two')


@pytest.fixture
def admin_user(create_user):
    """Администратор."""
    return create_user(email='admin@test.com', nickname='admin1',
                       full_name='Admin', user_type='admin')


@pytest.fixture
def auth_headers(user1):
    """Заголовки авторизации для user1."""
    token = create_access_token(identity=str(user1.id))
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def admin_headers(admin_user):
    """Заголовки авторизации для администратора (с claim user_type)."""
    token = create_access_token(
        identity=str(admin_user.id),
        additional_claims={'user_type': 'admin'}
    )
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def refresh_headers(user1):
    """Заголовки с refresh-токеном для user1."""
    token = create_refresh_token(identity=str(user1.id))
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
