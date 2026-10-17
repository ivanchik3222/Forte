import os

# Подхватываем backend/.env до чтения любых os.environ
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_jwt_extended.exceptions import JWTExtendedException
from werkzeug.exceptions import HTTPException

from config import get_config, DATABASE_DIR
from models import db, User

# Инициализация расширений
migrate = Migrate()
jwt = JWTManager()


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())
    CORS(app, supports_credentials=True, origins=app.config['CORS_ORIGINS'])

    # Создаём папку для БД, если её нет
    os.makedirs(DATABASE_DIR, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    with app.app_context():
        db.create_all()

    # Регистрация блюпринтов
    from routes import auth_bp, admin_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    # Главная страница API
    @app.route('/api')
    def api_info():
        return jsonify({
            'message': 'API is alive',
            'version': '1.0.0',
            'endpoints': {
                'auth': '/api/auth - авторизация и регистрация',
                'admin': '/api/admin - администрирование пользователей',
            },
        })

    return app


app = create_app()


# Обработчики ошибок
@app.errorhandler(422)
def handle_unprocessable_entity(err):
    return jsonify({'error': 'Validation error', 'message': str(err)}), 422


@app.errorhandler(JWTExtendedException)
def handle_jwt_error(e):
    return jsonify({'error': 'JWT Error', 'message': str(e)}), 401


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    return jsonify({'error': e.code, 'message': e.description}), e.code


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'error': 'Токен истек'}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'error': 'Недействительный токен'}), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({'error': 'Требуется авторизация'}), 401


# CLI команды
@app.cli.command()
def init_db():
    """Инициализация базы данных"""
    print('Инициализация базы данных...')
    db.create_all()
    print('База данных инициализирована!')


@app.cli.command()
def create_admin():
    """Создать администратора"""
    email = input('Email администратора: ')
    password = input('Пароль: ')
    full_name = input('Полное имя: ')

    if User.query.filter_by(email=email).first():
        print('Пользователь с таким email уже существует')
        return

    admin = User(full_name=full_name, email=email, user_type='admin', is_verified=True)
    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    print(f'Администратор {email} создан')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 6767)))
