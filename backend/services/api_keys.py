"""Anonymous API identities, separate from interactive user sessions."""
import hashlib
from functools import wraps
from flask import request, g
from models import ApiClient, as_utc, utcnow
from utils.errors import ApiError


def key_digest(key):
    return hashlib.sha256(key.encode()).hexdigest()


def authenticate_key():
    if 'Authorization' in request.headers:
        raise ApiError(400, 'ambiguous_auth', 'Передайте только X-API-Key.')
    key = request.headers.get('X-API-Key', '')
    client = ApiClient.query.filter_by(key_hash=key_digest(key)).first() if 20 <= len(key) <= 128 else None
    if not client or client.revoked_at or as_utc(client.expires_at) <= utcnow():
        raise ApiError(401, 'invalid_api_key', 'API-ключ отсутствует, отозван или истёк.')
    g.api_client = client
    return client


def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        authenticate_key()
        return fn(*args, **kwargs)
    return wrapper
