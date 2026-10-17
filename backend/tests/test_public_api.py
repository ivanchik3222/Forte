import base64
import io
from datetime import timedelta
import pytest
from sqlalchemy.exc import IntegrityError
from models import db, ApiClient, AnalysisJob, MediaRecord, utcnow
from services.analysis import run_next_job


def issue(client):
    response = client.post('/api/v1/api-keys')
    assert response.status_code == 201
    return {'X-API-Key': response.json['api_key']}


@pytest.fixture
def public_ml(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    weights = tmp_path / 'weights.pt'
    weights.write_bytes(b'test')
    monkeypatch.setitem(app.config, 'ML_ENABLED', True)
    monkeypatch.setitem(app.config, 'ML_ENGINE', 'objects')
    monkeypatch.setitem(app.config, 'ML_WEIGHTS', str(weights))
    monkeypatch.setattr('services.media.probe', lambda *args: 2.0)
    return tmp_path


def upload(client, headers, name='video.mov', content=b'video'):
    return client.post('/api/v1/analyze', headers=headers,
                       data={'file': (io.BytesIO(content), name)})


def test_key_issuance_hash_limits_and_revocation(client):
    headers = issue(client)
    row = ApiClient.query.one()
    assert row.key_hash != headers['X-API-Key'] and len(row.key_hash) == 64
    assert client.delete('/api/v1/api-keys/current', headers=headers).status_code == 204
    assert client.get('/api/v1/jobs/absent', headers=headers).status_code == 401
    issue(client); issue(client)
    assert client.post('/api/v1/api-keys').status_code == 429


def test_isolated_ownership_and_auth(client, auth_headers, admin_headers, public_ml):
    a, b = issue(client), issue(client)
    response = upload(client, a)
    assert response.status_code == 202
    job_id = response.json['job_id']
    record = MediaRecord.query.one()
    assert record.owner_id is None and record.api_client_id
    assert client.get('/api/v1/jobs/' + job_id, headers=a).json['status'] == 'processing'
    for headers in (b, auth_headers, admin_headers):
        assert client.get('/api/v1/jobs/' + job_id, headers=headers).status_code == 404
    assert client.get('/api/v1/media/' + record.id, headers=admin_headers).status_code == 404
    assert client.get('/api/v1/media', headers=auth_headers).json['total'] == 0
    assert client.get('/api/v1/cameras', headers=a).status_code == 401
    assert client.get('/api/v1/jobs/' + job_id).status_code == 401
    assert client.get('/api/v1/jobs/' + job_id, headers={**a, **auth_headers}).status_code == 400
    assert upload(client, {}).status_code == 401
    assert upload(client, {'X-API-Key': 'invalid'}).status_code == 401


def test_expired_key(client):
    headers = issue(client)
    ApiClient.query.one().expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert upload(client, headers).status_code == 401


def test_upload_validation_and_limits(client, public_ml, app, monkeypatch):
    headers = issue(client)
    assert upload(client, headers, name='test.txt').status_code == 415
    assert upload(client, headers, content=b'').status_code == 422
    assert MediaRecord.query.count() == 0
    assert upload(client, headers).status_code == 202
    assert upload(client, headers).status_code == 429
    assert MediaRecord.query.count() == 1
    monkeypatch.setitem(app.config, 'ML_QUEUE_LIMIT', 1)
    assert upload(client, issue(client)).status_code == 429


def test_worker_observations_do_not_become_negative_verdict(client, public_ml, monkeypatch):
    headers = issue(client)
    job_id = upload(client, headers).json['job_id']
    class Detector:
        def analyze(self, *args):
            return dict(verdict='requires_review', violations=[])
    monkeypatch.setattr('services.analysis.detector', lambda: Detector())
    assert run_next_job() == job_id
    result = client.get('/api/v1/jobs/' + job_id, headers=headers).json
    assert result['status'] == 'failed' and result['error']['code'] == 'verdict_unavailable'
    assert 'verdict' not in result


@pytest.mark.parametrize('verdict', ['violation', 'no_violation'])
def test_completed_contract(client, public_ml, verdict):
    headers = issue(client)
    job_id = upload(client, headers).json['job_id']
    job = db.session.get(AnalysisJob, job_id)
    folder = public_ml / 'analysis' / job_id
    folder.mkdir(parents=True)
    image = b'\xff\xd8test-jpeg'
    (folder / 'frame.jpg').write_bytes(image)
    violation = dict(type='test', description='Visible event', timecode_sec=1.0,
        evidence_frames=[dict(timestamp_sec=1.0, image_file='frame.jpg')])
    job.result = dict(verdict=verdict, violations=[violation] if verdict == 'violation' else [])
    job.status, job.finished_at = 'done', utcnow()
    db.session.commit()
    result = client.get('/api/v1/jobs/' + job_id, headers=headers).json
    assert set(result) == {'job_id', 'status', 'verdict', 'violations'}
    assert result['status'] == 'done' and result['verdict'] == verdict
    if verdict == 'violation':
        frame = result['violations'][0]['evidence_frames'][0]
        assert base64.b64decode(frame['image_base64']) == image
        assert set(frame) == {'timestamp_sec', 'image_base64'}


def test_evidence_traversal_and_timeout(client, public_ml):
    headers = issue(client)
    job_id = upload(client, headers).json['job_id']
    job = db.session.get(AnalysisJob, job_id)
    job.status, job.finished_at = 'done', utcnow()
    job.result = dict(verdict='violation', violations=[dict(type='test', description='test', timecode_sec=0,
        evidence_frames=[dict(timestamp_sec=0, image_file='../../private.jpg')])])
    db.session.commit()
    assert client.get('/api/v1/jobs/' + job_id, headers=headers).json['error']['code'] == 'invalid_result'
    job.created_at = utcnow() - timedelta(minutes=6)
    db.session.commit()
    assert client.get('/api/v1/jobs/' + job_id, headers=headers).json['error']['code'] == 'analysis_timeout'


def test_database_rejects_missing_owner():
    db.session.add(MediaRecord(original_name='x.mov', storage_key='x.mov', size_bytes=1, content_type='video/quicktime'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_upload_rollback_removes_file(client, public_ml, monkeypatch):
    headers = issue(client)
    from sqlalchemy.orm import Session
    original = Session.commit
    def broken_commit(session):
        if session.new and any(isinstance(row, AnalysisJob) for row in session.new):
            raise RuntimeError('test failure')
        return original(session)
    monkeypatch.setattr(Session, 'commit', broken_commit)
    assert upload(client, headers).status_code == 500
    assert MediaRecord.query.count() == 0
    assert not list(public_ml.glob('*.mov'))


def test_expired_queued_job_releases_client_capacity(client, public_ml):
    headers = issue(client)
    job_id = upload(client, headers).json['job_id']
    old = db.session.get(AnalysisJob, job_id)
    old.created_at = utcnow() - timedelta(minutes=6)
    db.session.commit()
    assert upload(client, headers).status_code == 202
    db.session.refresh(old)
    assert old.status == 'failed'


def test_api_migration_preserves_children_and_checks_ownership(tmp_path):
    from app import create_app
    from flask_migrate import upgrade, downgrade
    from sqlalchemy import text
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "migration.db"}'})
    with app.app_context():
        upgrade(revision='0005')
        db.session.execute(text("INSERT INTO users (id,email) VALUES (1,'old@test.local')"))
        db.session.execute(text("""INSERT INTO media_records
            (id,owner_id,original_name,search_name,storage_key,size_bytes,content_type,created_at)
            VALUES ('old',1,'old.mov','old.mov','old.mov',5,'video/quicktime',CURRENT_TIMESTAMP)"""))
        db.session.execute(text("""INSERT INTO upload_requests (id,owner_id,key,fingerprint,media_id,created_at)
            VALUES ('upload',1,'key','hash','old',CURRENT_TIMESTAMP)"""))
        db.session.execute(text("""INSERT INTO analysis_jobs (id,media_id,camera_profile,status,created_at)
            VALUES ('job','old','full_frame','queued',CURRENT_TIMESTAMP)"""))
        db.session.commit()
        upgrade()
        assert db.session.execute(text('SELECT COUNT(*) FROM upload_requests')).scalar() == 1
        assert db.session.execute(text('SELECT COUNT(*) FROM analysis_jobs')).scalar() == 1
        assert db.session.get(MediaRecord, 'old').owner_id == 1
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        assert db.session.execute(text('PRAGMA foreign_key_check')).all() == []
        # New schema also works for accountless uploads after upgrading populated DB.
        client = ApiClient(key_hash='a' * 64, expires_at=utcnow() + timedelta(days=1))
        db.session.add(client); db.session.flush()
        record = MediaRecord(api_client_id=client.id, original_name='new.mov', storage_key='new.mov',
                             size_bytes=1, content_type='video/quicktime')
        db.session.add(record); db.session.commit()
        db.session.remove()
        with pytest.raises(SystemExit) as failure:
            downgrade(revision='0005')
        assert failure.value.code == 1
        assert MediaRecord.query.count() == 2
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        db.session.remove(); db.engine.dispose()
