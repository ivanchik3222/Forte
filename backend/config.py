import os
from pathlib import Path
from datetime import timedelta

# Путь к директории backend
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BACKEND_DIR, 'database')


def _cors_origins():
    """CORS origins из env (через запятую) или дефолт для локальной разработки"""
    raw = os.environ.get('CORS_ORIGINS')
    if raw:
        return [o.strip() for o in raw.split(',') if o.strip()]
    return ['http://localhost:3000', 'http://localhost:5173', 'http://127.0.0.1:3000']


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database — всегда предпочитаем DATABASE_URL из окружения.
    # Без него создаётся ЛОКАЛЬНЫЙ SQLite-файл в database/.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(DATABASE_DIR, "database.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CORS
    CORS_ORIGINS = _cors_origins()

    # JWT
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(hours=12)
    JWT_COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'false').lower() == 'true'
    JWT_COOKIE_SAMESITE = os.environ.get('COOKIE_SAMESITE', 'Lax')
    JWT_REFRESH_COOKIE_PATH = os.environ.get('AUTH_COOKIE_PATH', '/api/auth')
    JWT_REFRESH_CSRF_COOKIE_PATH = JWT_REFRESH_COOKIE_PATH
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = False
    MEDIA_ROOT = os.environ.get('MEDIA_ROOT', os.path.join(BACKEND_DIR, 'media'))
    MAX_FILE_SIZE = 200 * 1024 * 1024
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE + 1024 * 1024
    FFPROBE_PATH = os.environ.get('FFPROBE_PATH', 'ffprobe')
    PLAYBACK_TTL = 900
    UPLOADS_PER_HOUR = 30
    MIN_FREE_BYTES = 256 * 1024 * 1024
    DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true'
    ADMIN_MFA_REQUIRED = False
    AUTH_ACCOUNT_LIMIT = 10
    AUTH_IP_LIMIT = 60
    AUTH_WINDOW_SECONDS = 300
    MIN_PASSWORD_LENGTH = 12
    MAX_PASSWORD_LENGTH = 128
    PUBLIC_REGISTRATION = True
    ALLOW_TEST_EVENTS = False
    REQUIRE_SECURE_CONFIG = False
    ML_ROOT = str(Path(BACKEND_DIR).parent / 'ML')
    ML_WEIGHTS = os.environ.get('ML_WEIGHTS', str(Path(BACKEND_DIR).parent / 'ML/deployment/cash_detector.pt'))
    ML_ENABLED = os.environ.get('ML_ENABLED', 'true').lower() == 'true'
    ML_DEVICE = os.environ.get('ML_DEVICE') or None
    ML_JOB_TIMEOUT = 300
    ML_QUEUE_LIMIT = 20


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    DEMO_MODE = True
    ML_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    PUBLIC_REGISTRATION = False
    REQUIRE_SECURE_CONFIG = True
    ADMIN_MFA_REQUIRED = True
    JWT_COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}


def get_config():
    """Получить текущую конфигурацию по FLASK_ENV"""
    return config.get(os.environ.get('FLASK_ENV') or 'default', DevelopmentConfig)


def validate_config():
    """Проверить критичные настройки (вызывать при деплое)"""
    errors = []
    if os.environ.get('FLASK_ENV') == 'production':
        for var in ('SECRET_KEY', 'JWT_SECRET_KEY', 'DATABASE_URL'):
            if not os.environ.get(var):
                errors.append(f'Переменная окружения {var} обязательна в продакшене')

    if errors:
        print('Ошибки конфигурации:')
        for error in errors:
            print(f'   • {error}')
        return False

    print('Конфигурация корректна')
    return True
