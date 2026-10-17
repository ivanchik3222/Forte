from functools import wraps

from flask import g, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from models import db, User, AuthSession, SessionSecurity, utcnow, as_utc
from utils.errors import ApiError
from services.demo_account import is_demo_user


def current_user():
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (ValueError, TypeError):
        user = None
    if not user or not user.is_active:
        raise ApiError(401, 'session_invalid', 'Войдите в аккаунт заново.')
    sid = get_jwt().get('sid')
    session = db.session.get(AuthSession, sid) if sid else None
    if not session or session.user_id != user.id or session.revoked_at or as_utc(session.expires_at) <= utcnow():
        raise ApiError(401, 'session_invalid', 'Сессия завершена. Войдите заново.')
    validate_user_security(user, sid)
    return user


def active_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        g.user = current_user()
        return fn(*args, **kwargs)
    return wrapper


def personal_account_required(fn):
    """Keep a shared demo login available to the next visitor."""
    @active_required
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if is_demo_user(g.user):
            raise ApiError(403, 'demo_account_shared', 'Профиль общего тестового аккаунта нельзя изменять или удалять.')
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """Проверяет текущую роль в БД, а не устаревшую роль в JWT."""
    @active_required
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if g.user.user_type != 'admin':
            raise ApiError(403, 'forbidden', 'Требуются права администратора')
        return fn(*args, **kwargs)
    return wrapper


def validate_user_security(user, sid):
    if is_demo_user(user) and not current_app.config['DEMO_MODE']:
        raise ApiError(401, 'session_invalid', 'Демонстрационный доступ отключён.')
    security = db.session.get(SessionSecurity, sid)
    if not security:
        raise ApiError(401, 'session_invalid', 'Войдите повторно.')
    if current_app.config['ADMIN_MFA_REQUIRED'] and user.user_type == 'admin' and not security.mfa_verified:
        raise ApiError(401, 'mfa_required', 'Войдите с MFA.')
