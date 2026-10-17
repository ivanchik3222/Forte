from flask import Blueprint, request, jsonify

from models import db, User, AuthSession, utcnow
from utils.errors import ApiError
from utils.decorators import admin_required
from services.demo_account import is_demo_user

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """Список пользователей с пагинацией и поиском"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        if page < 1 or not 1 <= per_page <= 100:
            raise ValueError()
    except ValueError:
        raise ApiError(400, 'invalid_pagination', 'Некорректная пагинация.')
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
    for field in ('is_active', 'is_verified'):
        if field in data and not isinstance(data[field], bool):
            raise ApiError(422, 'invalid_field', f'{field} должен быть boolean.')
    if 'user_type' in data and data['user_type'] not in ('user', 'admin'):
        raise ApiError(422, 'invalid_role', 'Допустимы роли user и admin.')
    if is_demo_user(user) and data.get('user_type', 'user') != 'user':
        raise ApiError(403, 'demo_account_shared', 'Тестовому аккаунту нельзя выдавать права администратора.')

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
        if not user.is_active:
            AuthSession.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': utcnow()})
    if 'is_verified' in data:
        user.is_verified = bool(data['is_verified'])
    if 'user_type' in data and data['user_type'] in ('user', 'admin'):
        user.user_type = data['user_type']

    db.session.commit()

    return jsonify({'user': user.to_dict(include_sensitive=True)})


@admin_bp.post('/branches')
@admin_required
def create_branch():
    from models import Branch
    data = request.get_json() or {}
    name = data.get('name')
    if set(data) != {'name'} or not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ApiError(422, 'invalid_field', 'Нужно название отделения до 120 символов.')
    branch = Branch(name=name.strip())
    db.session.add(branch); db.session.commit()
    return jsonify(id=branch.id, name=branch.name), 201


@admin_bp.get('/branches')
@admin_required
def list_branches():
    from models import Branch
    return jsonify(items=[dict(id=b.id, name=b.name) for b in Branch.query.order_by(Branch.name)])


@admin_bp.put('/cameras/<camera_id>/scope')
@admin_required
def camera_scope(camera_id):
    from flask import current_app
    from models import Camera, CameraScope, Branch
    data = request.get_json() or {}
    if set(data) - {'branch_id', 'is_demo'} or not isinstance(data.get('branch_id'), str) or not isinstance(data.get('is_demo', False), bool):
        raise ApiError(422, 'invalid_field', 'Нужны branch_id и is_demo (boolean).')
    if not db.session.get(Camera, camera_id) or not db.session.get(Branch, data['branch_id']):
        raise ApiError(404, 'not_found', 'Камера или отделение не найдены.')
    scope = db.session.get(CameraScope, camera_id)
    demo = data.get('is_demo', False)
    if demo:
        # Never reclassify an existing real camera (or its history) as public demo.
        from models import CameraAlert, CameraHealthReport
        if not current_app.config['DEMO_MODE'] or (scope and not scope.is_demo) or CameraAlert.query.filter_by(camera_id=camera_id).first() or CameraHealthReport.query.filter_by(camera_id=camera_id).first():
            raise ApiError(403, 'demo_scope_denied', 'Демокамера должна быть новой, в отдельном демонстрационном окружении.')
    if not scope:
        scope = CameraScope(camera_id=camera_id)
        db.session.add(scope)
    scope.branch_id, scope.is_demo = data['branch_id'], demo
    db.session.commit()
    return jsonify(camera_id=camera_id, branch_id=scope.branch_id, is_demo=scope.is_demo)


@admin_bp.get('/users/<int:user_id>/access')
@admin_required
def get_user_access(user_id):
    from models import BranchAccess, CameraAccess
    if not db.session.get(User, user_id):
        raise ApiError(404, 'not_found', 'Пользователь не найден.')
    return jsonify(branch_ids=[r.branch_id for r in BranchAccess.query.filter_by(user_id=user_id)],
                   camera_ids=[r.camera_id for r in CameraAccess.query.filter_by(user_id=user_id)])


@admin_bp.put('/users/<int:user_id>/access')
@admin_required
def set_user_access(user_id):
    from models import Branch, Camera, BranchAccess, CameraAccess
    user = db.session.get(User, user_id)
    if not user:
        raise ApiError(404, 'not_found', 'Пользователь не найден.')
    if is_demo_user(user):
        raise ApiError(403, 'demo_account_shared', 'Демоаккаунту нельзя выдавать доступ к рабочим камерам.')
    data = request.get_json() or {}
    if set(data) != {'branch_ids', 'camera_ids'}:
        raise ApiError(422, 'invalid_field', 'Передайте branch_ids и camera_ids.')
    for field, model in [('branch_ids', Branch), ('camera_ids', Camera)]:
        ids = data[field]
        if not isinstance(ids, list) or len(ids) > 1000 or any(not isinstance(i, str) for i in ids):
            raise ApiError(422, 'invalid_field', 'Ожидается список ID (до 1000).')
        if model.query.filter(model.id.in_(set(ids))).count() != len(set(ids)):
            raise ApiError(404, 'not_found', 'Объект доступа не найден.')
    BranchAccess.query.filter_by(user_id=user_id).delete()
    CameraAccess.query.filter_by(user_id=user_id).delete()
    for bid in set(data['branch_ids']):
        db.session.add(BranchAccess(user_id=user_id, branch_id=bid))
    for cid in set(data['camera_ids']):
        db.session.add(CameraAccess(user_id=user_id, camera_id=cid))
    db.session.commit()
    return jsonify(**data)
