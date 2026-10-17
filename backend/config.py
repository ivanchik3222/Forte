import os
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
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False


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
