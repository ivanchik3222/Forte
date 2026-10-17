from models import db, Branch, CameraScope, CameraAccess


def grant_camera(camera, *users):
    db.session.flush()
    branch = db.session.get(Branch, 'test-office')
    if not branch:
        branch = Branch(id='test-office', name='Test office')
        db.session.add(branch); db.session.flush()
    if not db.session.get(CameraScope, camera.id):
        db.session.add(CameraScope(camera_id=camera.id, branch_id=branch.id, is_demo=False))
    for user in users:
        if not db.session.get(CameraAccess, (user.id, camera.id)):
            db.session.add(CameraAccess(user_id=user.id, camera_id=camera.id))
    db.session.commit()
