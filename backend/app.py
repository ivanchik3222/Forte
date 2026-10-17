import os
import logging
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlite3 import Connection
from config import get_config
from models import db
from utils.errors import ApiError, error_response
from utils.logging import RedactMediaSignature

logging.getLogger('werkzeug').addFilter(RedactMediaSignature())

migrate = Migrate()
jwt = JWTManager()


@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, _):
    if isinstance(connection, Connection):
        connection.execute('PRAGMA foreign_keys=ON')


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(get_config())
    if isinstance(config_object, dict):
        app.config.update(config_object)
    elif config_object:
        app.config.from_object(config_object)
    if app.config['REQUIRE_SECURE_CONFIG'] and not app.testing:
        for key in ('SECRET_KEY', 'JWT_SECRET_KEY'):
            value = app.config.get(key, '')
            if len(value) < 32 or value.startswith(('dev-', 'your-', 'replace-with-')):
                raise RuntimeError(f'{key} must be a private random secret of at least 32 characters.')
        if app.config['SECRET_KEY'] == app.config['JWT_SECRET_KEY']:
            raise RuntimeError('SECRET_KEY and JWT_SECRET_KEY must be different.')
    CORS(app, supports_credentials=True, origins=app.config['CORS_ORIGINS'],
         expose_headers=['Content-Range', 'Accept-Ranges'])
    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app.root_path, 'migrations'))
    jwt.init_app(app)

    from routes import auth_bp, admin_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    from routes.workspace import workspace_bp
    app.register_blueprint(workspace_bp, url_prefix='/api/v1')
    from routes.review import review_bp
    app.register_blueprint(review_bp, url_prefix='/api/v1')
    from routes.analysis import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/api/v1')
    from routes.public_api import public_api_bp
    app.register_blueprint(public_api_bp, url_prefix='/api/v1')
    from api_docs import docs_bp
    app.register_blueprint(docs_bp)
    from cli import register_cli
    register_cli(app)

    @app.before_request
    def validate_json_object():
        if request.path.startswith('/api/auth'):
            request.max_content_length = 16384
        if request.is_json and request.content_length and request.method in ('POST', 'PUT', 'PATCH'):
            data = request.get_json()
            if not isinstance(data, dict):
                raise ApiError(400, 'invalid_json', 'Ожидается JSON-объект.')
            if request.path.startswith('/api/auth'):
                for value in data.values():
                    if value is not None and not isinstance(value, str):
                        raise ApiError(400, 'invalid_field', 'Поля авторизации должны быть строками.')
                    if isinstance(value, str) and len(value) > 1024:
                        raise ApiError(400, 'invalid_field', 'Поле авторизации слишком длинное.')

    @app.after_request
    def normalize_errors(response):
        if response.status_code >= 400 and response.is_json:
            payload = response.get_json()
            if not isinstance(payload.get('error'), dict):
                response.set_data(app.json.dumps({'error': {'code': f'http_{response.status_code}', 'message': str(payload.get('message') or payload.get('error') or 'Request failed')}}))
        if request.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'no-referrer'
        if response.status_code == 429:
            response.headers['Retry-After'] = str(app.config['AUTH_WINDOW_SECONDS'])
        return response

    @app.errorhandler(ApiError)
    def handle_api(err):
        return error_response(err.status, err.code, err.message)

    @app.errorhandler(HTTPException)
    def handle_http(err):
        return error_response(err.code, f'http_{err.code}', err.description)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        db.session.rollback()
        app.logger.exception('Request failed')
        return error_response(500, 'internal_error', 'Ошибка сервера. Повторите позже.')

    @app.get('/api')
    def api_info():
        return jsonify(message='API is alive', version='1.0.0')

    @app.get('/api/ready')
    def ready():
        db.session.execute(text('SELECT 1 FROM media_records LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM camera_health_reports LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM alert_recordings LIMIT 1'))
        return jsonify(ready=True)

    return app


@jwt.expired_token_loader
def expired_token_callback(*_):
    return error_response(401, 'token_expired', 'Токен истёк.')


@jwt.invalid_token_loader
def invalid_token_callback(_):
    return error_response(401, 'token_invalid', 'Недействительный токен.')


@jwt.unauthorized_loader
def missing_token_callback(_):
    return error_response(401, 'auth_required', 'Требуется авторизация.')


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 6767)), debug=app.config['DEBUG'])
