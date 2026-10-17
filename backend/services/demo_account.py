"""The public, shared account used by the quick sign-in button."""
from sqlalchemy.exc import IntegrityError
from models import db, User

DEMO_EMAIL = 'demo@forte.test'
# Public demo credentials, intentionally shared with the frontend.
DEMO_PASSWORD = 'ForteDemo2026!'


def is_demo_user(user):
    return bool(user and (user.email or '').lower() == DEMO_EMAIL)


def seed_demo_user():
    user = User.query.filter(db.func.lower(User.email) == DEMO_EMAIL).first()
    if user is None:
        user = User(email=DEMO_EMAIL, full_name='Тестовый пользователь',
                    user_type='user', is_active=True, is_verified=True)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            # Another startup may have created the same reserved account.
            db.session.rollback()
            user = User.query.filter(db.func.lower(User.email) == DEMO_EMAIL).first()
            if user is None:
                raise
    if user.user_type != 'user' or not user.check_password(DEMO_PASSWORD):
        raise ValueError('Demo email belongs to an incompatible account; no existing user was changed.')
    return user
