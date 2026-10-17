from flask import Blueprint, request, jsonify

from models import db, User
from utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """Список пользователей с пагинацией и поиском"""
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)
    search = request.args.get('search', '').strip()

    query = User.query.order_by(User.created_at.desc())

    if search:
        like = f'%{search.lower()}%'
        query = query.filter(
            db.or_(
                db.func.lower(User.email).like(like),
                db.func.lower(User.nickname).like(like),
                db.func.lower(User.full_name).like(like),
            )
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'users': [u.to_dict(include_sensitive=True) for u in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    })


@admin_bp.route('/users/<int:user_id>', methods=['PATCH'])
@admin_required
def update_user(user_id):
    """Изменение статуса/роли пользователя"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'Пользователь не найден'}), 404

    data = request.get_json() or {}

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    if 'is_verified' in data:
        user.is_verified = bool(data['is_verified'])
    if 'user_type' in data and data['user_type'] in ('user', 'admin'):
        user.user_type = data['user_type']

    db.session.commit()

    return jsonify({'user': user.to_dict(include_sensitive=True)})
