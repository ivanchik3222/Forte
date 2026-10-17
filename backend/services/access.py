"""Object authorization shared by lists, details, exports and signed files."""
from flask import g
from sqlalchemy import select, or_
from models import db, Camera, CameraAlert, CameraScope, BranchAccess, CameraAccess
from services.demo_account import is_demo_user
from utils.errors import ApiError


def camera_query():
    query = Camera.query
    if g.user.user_type == 'admin' and not is_demo_user(g.user):
        return query
    query = query.join(CameraScope, CameraScope.camera_id == Camera.id)
    if is_demo_user(g.user):
        return query.filter(CameraScope.is_demo.is_(True))
    return query.filter(CameraScope.is_demo.is_(False), or_(
        CameraScope.branch_id.in_(select(BranchAccess.branch_id).where(BranchAccess.user_id == g.user.id)),
        Camera.id.in_(select(CameraAccess.camera_id).where(CameraAccess.user_id == g.user.id))))


def camera_ids():
    return camera_query().with_entities(Camera.id).statement


def alert_query():
    return CameraAlert.query.filter(CameraAlert.camera_id.in_(camera_ids()))


def get_alert(alert_id):
    alert = alert_query().filter(CameraAlert.id == alert_id).first()
    if not alert:
        raise ApiError(404, 'not_found', 'Событие не найдено.')
    return alert
