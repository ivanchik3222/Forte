"""Database-backed controls shared by every Gunicorn worker."""
import base64
import hashlib
import hmac
import time
import pyotp
from cryptography.fernet import Fernet
from flask import current_app
from sqlalchemy import case, update
from models import db, LoginBucket, UserMFA
from utils.errors import ApiError


def valid_password(value):
    return isinstance(value, str) and current_app.config['MIN_PASSWORD_LENGTH'] <= len(value) <= current_app.config['MAX_PASSWORD_LENGTH']


def throttle(identity, kind='account'):
    """Fixed-window counters increment atomically; aliases resolve to user ID."""
    seconds = current_app.config['AUTH_WINDOW_SECONDS']
    window = int(time.time()) // seconds
    key = hmac.new(current_app.config['SECRET_KEY'].encode(),
                   f'{kind}:{identity}'.encode(), hashlib.sha256).hexdigest()
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    insert = postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    stmt = insert(LoginBucket).values(key=key, window=window, count=1)
    stmt = stmt.on_conflict_do_update(index_elements=['key'], set_={
        'window': window,
        'count': case((LoginBucket.window == window, LoginBucket.count + 1), else_=1),
    }).returning(LoginBucket.count)
    count = db.session.execute(stmt).scalar_one()
    # Expired buckets need not accumulate permanently.
    LoginBucket.query.filter(LoginBucket.window < window - 2).delete(synchronize_session=False)
    db.session.commit()
    limit = current_app.config['AUTH_IP_LIMIT' if kind == 'ip' else 'AUTH_ACCOUNT_LIMIT']
    if count > limit:
        raise ApiError(429, 'auth_rate_limit', 'Слишком много попыток. Повторите через 5 минут.')


def mfa_cipher():
    key = hmac.new(current_app.config['SECRET_KEY'].encode(), b'forte-mfa-encryption-v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def verify_mfa(user, code):
    row = db.session.get(UserMFA, user.id)
    required = current_app.config['ADMIN_MFA_REQUIRED'] and user.user_type == 'admin'
    if not row:
        if required:
            raise ApiError(403, 'mfa_setup_required', 'Администратор должен настроить MFA через защищённую консоль сервера.')
        return False
    if not code:
        raise ApiError(401, 'mfa_required', 'Введите код из приложения-аутентификатора.')
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ApiError(401, 'mfa_invalid', 'Неверный или уже использованный код MFA.')
    totp = pyotp.TOTP(mfa_cipher().decrypt(row.secret.encode()).decode())
    step = int(time.time()) // 30
    matched = next((n for n in (step, step - 1, step + 1) if hmac.compare_digest(totp.at(n * 30), code)), None)
    if matched is None:
        raise ApiError(401, 'mfa_invalid', 'Неверный или уже использованный код MFA.')
    changed = db.session.execute(update(UserMFA).where(UserMFA.user_id == user.id,
        UserMFA.last_step < matched).values(last_step=matched)).rowcount
    db.session.commit()
    if not changed:
        raise ApiError(401, 'mfa_invalid', 'Неверный или уже использованный код MFA.')
    return True
