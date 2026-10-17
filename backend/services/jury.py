"""A configured jury key has access only to its dedicated local account."""
from functools import wraps
import hmac
from flask import current_app, request, g
from models import db, User
from utils.errors import ApiError


def authenticate_jury():
    expected = current_app.config.get('JURY_API_KEY', '')
    if not expected or not current_app.config.get('JURY_OWNER_ID'):
        raise ApiError(503,'jury_not_configured','API жюри ещё не настроен.')
    supplied = request.headers.get('X-API-Key','')
    if not hmac.compare_digest(supplied.encode('utf-8'),expected.encode('utf-8')):
        raise ApiError(401,'invalid_api_key','Неверный API-ключ.')
    user = db.session.get(User,current_app.config['JURY_OWNER_ID'])
    if not user or not user.is_active or user.user_type != 'user':
        raise ApiError(503,'jury_account_unavailable','Учётная запись API жюри недоступна.')
    g.user = user


def jury_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        authenticate_jury()
        return fn(*args,**kwargs)
    return wrapper
