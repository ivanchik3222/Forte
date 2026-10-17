from flask import Blueprint, request, jsonify, current_app, g
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt, set_refresh_cookies, unset_jwt_cookies, decode_token
from models import db, User, AuthSession, SessionSecurity, MediaRecord, uid, utcnow, as_utc
from utils.decorators import active_required, personal_account_required, current_user
from services.demo_account import DEMO_EMAIL, is_demo_user
from utils.errors import ApiError
from datetime import datetime, timedelta, timezone
import re

from services.security import throttle, valid_password, verify_mfa
from sqlalchemy import update

auth_bp = Blueprint('auth', __name__)


def validate_email(email):
    """Валидация email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_nickname(nickname):
    """Валидация никнейма: 3-20 символов, буквы, цифры, точки, подчёркивания, дефисы"""
    pattern = r'^[a-zA-Z0-9._-]{3,20}$'
    return bool(re.match(pattern, nickname))


def is_email(identifier):
    """Проверяет, является ли identifier email-ом"""
    return '@' in identifier and '.' in identifier


def make_tokens(user, mfa_verified=False):
    sid = uid()
    claims = {'sid': sid}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)
    session = AuthSession(id=sid, user_id=user.id,
                          expires_at=utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'])
    db.session.add(session)
    db.session.flush()
    db.session.add(SessionSecurity(session_id=sid, refresh_jti=decode_token(refresh)['jti'], mfa_verified=mfa_verified))
    db.session.commit()
    return access, refresh


def session_response(user, access, refresh, status=200):
    response = jsonify(user=user.to_dict(include_sensitive=True), access_token=access,
                       csrf_token=decode_token(refresh)['csrf'])
    set_refresh_cookies(response, refresh)
    return response, status


@auth_bp.before_request
def check_origin():
    if request.method == 'POST' and request.path.rsplit('/', 1)[-1] in ('login', 'register', 'forgot-password', 'reset-password', 'verify-email'):
        throttle(request.remote_addr or 'unknown', 'ip')
    origin = request.headers.get('Origin')
    if origin and origin not in current_app.config['CORS_ORIGINS']:
        raise ApiError(403, 'origin_rejected', 'Origin is not allowed.')


@auth_bp.route('/register', methods=['POST'])
def register():
    """Регистрация пользователя по email или nickname"""
    if not current_app.config['PUBLIC_REGISTRATION']:
        raise ApiError(403, 'registration_disabled', 'Account registration is disabled.')
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Данные не предоставлены'}), 400

    # Поля (email или nickname - хотя бы одно обязательно)
    email = data.get('email', '').strip().lower() if data.get('email') else None
    nickname = data.get('nickname', '').strip() if data.get('nickname') else None
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip() if data.get('full_name') else ''

    # Поддержка identifier (определяем email это или nickname)
    identifier = data.get('identifier', '').strip() if data.get('identifier') else None
    if identifier and not email and not nickname:
        if is_email(identifier):
            email = identifier.lower()
        else:
            nickname = identifier

    if not email and not nickname:
        return jsonify({'error': 'Укажите email или nickname'}), 400

    if email == DEMO_EMAIL:
        raise ApiError(409, 'reserved_account', 'Этот email используется общим тестовым аккаунтом.')

    if not password:
        return jsonify({'error': 'Пароль обязателен'}), 400

    if email and not validate_email(email):
        return jsonify({'error': 'Неверный формат email'}), 400

    if nickname and not validate_nickname(nickname):
        return jsonify({'error': 'Nickname должен содержать 3-20 символов (буквы, цифры, точки, подчёркивания, дефисы)'}), 400

    if not valid_password(password):
        return jsonify({'error': 'Пароль должен содержать от 12 до 128 символов'}), 400

    if email and User.query.filter_by(email=email).first():
        return jsonify({'error': 'Пользователь с таким email уже существует'}), 400

    if nickname and User.query.filter(db.func.lower(User.nickname) == nickname.lower()).first():
        return jsonify({'error': 'Пользователь с таким nickname уже существует'}), 400

    try:
        user = User(
            email=email,
            nickname=nickname,
            full_name=full_name or nickname or (email.split('@')[0] if email else None),
            user_type='user',
            is_active=True,
            is_verified=False,
            last_login=datetime.now(timezone.utc)
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        access_token, refresh_token = make_tokens(user)

        return session_response(user, access_token, refresh_token, 201)

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка регистрации: {e}')
        return jsonify({'error': 'Ошибка при создании аккаунта'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """Вход пользователя по email, nickname или identifier"""
    data = request.get_json()

    if not data or not data.get('password'):
        return jsonify({'error': 'Заполните все поля'}), 400

    password = data.get('password', '')

    identifier = data.get('identifier', '').strip().lower() if data.get('identifier') else ''
    email = data.get('email', '').strip().lower() if data.get('email') else ''
    nickname = data.get('nickname', '').strip().lower() if data.get('nickname') else ''

    user = None

    if identifier:
        if is_email(identifier):
            user = User.query.filter_by(email=identifier, is_active=True).first()
        else:
            user = User.query.filter(
                db.func.lower(User.nickname) == identifier,
                User.is_active == True
            ).first()
    elif email:
        user = User.query.filter_by(email=email, is_active=True).first()
    elif nickname:
        user = User.query.filter(
            db.func.lower(User.nickname) == nickname,
            User.is_active == True
        ).first()
    else:
        return jsonify({'error': 'Укажите email, nickname или identifier'}), 400

    throttle(str(user.id) if user else (identifier or email or nickname or '').casefold())
    if len(password) > current_app.config['MAX_PASSWORD_LENGTH']:
        return jsonify({'error': 'Неверные данные для входа'}), 401
    if user and is_demo_user(user) and not current_app.config['DEMO_MODE']:
        user = None
    if not user or not user.check_password(password):
        return jsonify({'error': 'Неверные данные для входа'}), 401

    mfa_verified = verify_mfa(user, data.get('otp', ''))
    try:
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        access_token, refresh_token = make_tokens(user, mfa_verified=mfa_verified)

        return session_response(user, access_token, refresh_token)
    except Exception as e:
        db.session.rollback()
        print(f'Ошибка входа: {e}')
        return jsonify({'error': 'Ошибка при входе'}), 500


@auth_bp.get('/session-csrf')
@jwt_required(refresh=True, locations=['cookies'])
def session_csrf():
    current_user()
    return jsonify(csrf_token=get_jwt()['csrf'])


@auth_bp.post('/refresh')
@jwt_required(refresh=True, locations=['cookies'])
def refresh():
    user = current_user()
    jwt = get_jwt()
    session = db.session.get(AuthSession, jwt['sid'])
    remaining = as_utc(session.expires_at) - utcnow()
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={'sid': session.id}, expires_delta=remaining)
    changed = db.session.execute(update(SessionSecurity).where(
        SessionSecurity.session_id == session.id, SessionSecurity.refresh_jti == jwt['jti'])
        .values(refresh_jti=decode_token(refresh_token)['jti'])).rowcount
    if not changed:
        session.revoked_at = utcnow()
        db.session.commit()
        raise ApiError(401, 'refresh_reused', 'Сессия отозвана: повторное использование токена.')
    db.session.commit()
    access = create_access_token(identity=str(user.id), additional_claims={'sid': session.id})
    return session_response(user, access, refresh_token)



@auth_bp.post('/logout')
@jwt_required(refresh=True, locations=['cookies'])
def logout():
    session = db.session.get(AuthSession, get_jwt().get('sid'))
    if session:
        session.revoked_at = utcnow()
        db.session.commit()
    response = jsonify(message='Logged out')
    unset_jwt_cookies(response)
    return response


@auth_bp.route('/me', methods=['GET'])
@active_required
def get_current_user():
    """Получить данные текущего пользователя"""
    try:
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)

        if not user or not user.is_active:
            return jsonify({'error': 'Пользователь не найден'}), 404

        return jsonify({
            'data': {
                'user': user.to_dict(include_sensitive=True)
            }
        })

    except Exception as e:
        print(f'Ошибка получения пользователя: {e}')
        return jsonify({'error': 'Ошибка получения данных пользователя'}), 500


@auth_bp.route('/profile', methods=['PUT'])
@personal_account_required
def update_profile():
    """Обновление профиля пользователя"""
    try:
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)

        if not user or not user.is_active:
            return jsonify({'error': 'Пользователь не найден'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Данные не предоставлены'}), 400

        if 'full_name' in data and data['full_name']:
            user.full_name = data['full_name'].strip()

        if 'nickname' in data and data['nickname']:
            new_nickname = data['nickname'].strip()
            if not validate_nickname(new_nickname):
                return jsonify({'error': 'Nickname должен содержать 3-20 символов (буквы, цифры, точки, подчёркивания, дефисы)'}), 400
            existing = User.query.filter(
                db.func.lower(User.nickname) == new_nickname.lower(),
                User.id != user.id
            ).first()
            if existing:
                return jsonify({'error': 'Этот nickname уже занят'}), 400
            user.nickname = new_nickname

        db.session.commit()

        return jsonify({
            'data': {
                'user': user.to_dict(include_sensitive=True)
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка обновления профиля: {e}')
        return jsonify({'error': 'Ошибка при обновлении профиля'}), 500


@auth_bp.route('/change-password', methods=['POST'])
@personal_account_required
def change_password():
    """Смена пароля"""
    try:
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)

        if not user or not user.is_active:
            return jsonify({'error': 'Пользователь не найден'}), 404

        data = request.get_json()
        if not data or not data.get('current_password') or not data.get('new_password'):
            return jsonify({'error': 'Необходимы текущий и новый пароль'}), 400

        if not user.check_password(data['current_password']):
            return jsonify({'error': 'Неверный текущий пароль'}), 400

        if not valid_password(data['new_password']):
            return jsonify({'error': 'Новый пароль должен содержать от 12 до 128 символов'}), 400

        user.set_password(data['new_password'])
        AuthSession.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': utcnow()})
        db.session.commit()

        return jsonify({'message': 'Пароль успешно изменен'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка смены пароля: {e}')
        return jsonify({'error': 'Ошибка при смене пароля'}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Восстановление пароля"""
    data = request.get_json()

    if not data or not data.get('email'):
        return jsonify({'error': 'Email обязателен'}), 400

    user = User.query.filter_by(email=data['email'].lower(), is_active=True).first()

    if not user or is_demo_user(user):
        # Не сообщаем о том, что пользователь не найден (безопасность)
        return jsonify({'message': 'Если пользователь с таким email существует, инструкции отправлены на почту'})

    try:
        import secrets
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)

        db.session.commit()

        # TODO: Реализовать отправку email с токеном сброса

        return jsonify({'message': 'Инструкции отправлены на почту'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка восстановления пароля: {e}')
        return jsonify({'error': 'Ошибка при отправке инструкций'}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Сброс пароля по токену"""
    data = request.get_json()

    if not data or not data.get('token') or not data.get('password'):
        return jsonify({'error': 'Токен и новый пароль обязательны'}), 400

    user = User.query.filter_by(reset_token=data['token']).first()

    if not user or not user.reset_token_expires or as_utc(user.reset_token_expires) < datetime.now(timezone.utc):
        return jsonify({'error': 'Недействительный или истекший токен'}), 400

    if is_demo_user(user):
        raise ApiError(403, 'demo_account_shared', 'Пароль общего тестового аккаунта нельзя изменять.')

    if not valid_password(data['password']):
        return jsonify({'error': 'Пароль должен содержать от 12 до 128 символов'}), 400

    try:
        user.set_password(data['password'])
        AuthSession.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': utcnow()})
        user.reset_token = None
        user.reset_token_expires = None

        db.session.commit()

        return jsonify({'message': 'Пароль успешно изменен'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка сброса пароля: {e}')
        return jsonify({'error': 'Ошибка при смене пароля'}), 500


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """Верификация email"""
    data = request.get_json()

    if not data or not data.get('token'):
        return jsonify({'error': 'Токен верификации обязателен'}), 400

    user = User.query.filter_by(verification_token=data['token']).first()

    if not user:
        return jsonify({'error': 'Недействительный токен верификации'}), 400

    try:
        user.is_verified = True
        user.verification_token = None

        db.session.commit()

        return jsonify({'message': 'Email успешно подтвержден'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка верификации email: {e}')
        return jsonify({'error': 'Ошибка при подтверждении email'}), 500


@auth_bp.route('/deactivate', methods=['POST'])
@personal_account_required
def deactivate_account():
    """Деактивация аккаунта"""
    try:
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)

        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        data = request.get_json()
        if not data or not data.get('password'):
            return jsonify({'error': 'Подтверждение паролем обязательно'}), 400

        if not user.check_password(data['password']):
            return jsonify({'error': 'Неверный пароль'}), 400

        user.is_active = False
        AuthSession.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': utcnow()})
        db.session.commit()

        return jsonify({'message': 'Аккаунт деактивирован'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка деактивации аккаунта: {e}')
        return jsonify({'error': 'Ошибка при деактивации аккаунта'}), 500


@auth_bp.route('/deactivate', methods=['DELETE'])
@personal_account_required
def delete_account():
    """Удаление аккаунта"""
    try:
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)

        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        if MediaRecord.query.filter_by(owner_id=user.id).first():
            return jsonify({'error': 'Сначала требуется урегулировать хранение записей пользователя; используйте деактивацию.'}), 409
        db.session.delete(user)
        db.session.commit()

        return jsonify({'message': 'Аккаунт удален'})

    except Exception as e:
        db.session.rollback()
        print(f'Ошибка удаления аккаунта: {e}')
        return jsonify({'error': 'Ошибка при удалении аккаунта'}), 500
