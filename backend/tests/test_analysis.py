from datetime import timedelta
import pytest

from models import db, AnalysisJob, MediaRecord, AuthSession, utcnow
from routes.auth import make_tokens
from services.analysis import run_next_job


@pytest.fixture
def local_ml(app, tmp_path, monkeypatch, user1):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    weights = tmp_path/'weights.pt'
    weights.write_bytes(b'test weights; inference is replaced in unit tests')
    monkeypatch.setitem(app.config, 'ML_WEIGHTS', str(weights))
    monkeypatch.setitem(app.config, 'ML_ENABLED', True)
    record = MediaRecord(owner_id=user1.id, original_name='cash.mov', storage_key='cash.mov',
        size_bytes=5, content_type='video/quicktime', duration_sec=1)
    (tmp_path/'cash.mov').write_bytes(b'video')
    db.session.add(record); db.session.commit()
    return record.id, tmp_path


def submit(client, headers, media_id, profile='forte_open'):
    return client.post(f'/api/v1/media/{media_id}/analyze', headers=headers,
        json={'camera_profile': profile})


def test_queue_scope_idempotency_and_capability(client, auth_headers, user2, local_ml):
    media_id, _ = local_ml
    capabilities = client.get('/api/v1/capabilities', headers=auth_headers).json
    assert capabilities['analysis'] and not capabilities['automatic_violation_detection']
    assert client.get(f'/api/v1/media/{media_id}/analysis', headers=auth_headers).json is None
    first = submit(client, auth_headers, media_id)
    assert first.status_code == 202 and first.json['status'] == 'queued'
    repeat = submit(client, auth_headers, media_id)
    assert repeat.status_code == 200 and repeat.json['job_id'] == first.json['job_id']
    assert submit(client, auth_headers, media_id, 'full_frame').status_code == 409
    assert submit(client, auth_headers, media_id, 'unknown').status_code == 422
    other, _ = make_tokens(user2)
    headers = {'Authorization': 'Bearer '+other}
    assert client.get('/api/v1/jobs/'+first.json['job_id'], headers=headers).status_code == 404
    assert submit(client, headers, media_id).status_code == 404
    assert client.get('/api/v1/jobs/'+first.json['job_id']).status_code == 401


def test_disabled_model_and_queue_limit(client, auth_headers, app, monkeypatch, local_ml):
    media_id, _ = local_ml
    monkeypatch.setitem(app.config, 'ML_QUEUE_LIMIT', 0)
    assert submit(client, auth_headers, media_id).status_code == 429
    monkeypatch.setitem(app.config, 'ML_ENABLED', False)
    assert submit(client, auth_headers, media_id).status_code == 503


def test_worker_results_evidence_export_and_revoked_session(client, auth_headers, app, monkeypatch, local_ml):
    media_id, _ = local_ml
    class FakeDetector:
        def analyze(self, source, output, profile, timeout):
            assert source.read_bytes() == b'video' and profile == 'forte_open'
            output.mkdir(parents=True)
            (output/'evidence-000.jpg').write_bytes(b'\xff\xd8test')
            return dict(verdict='requires_review', violations=[], rule_evaluation='not_performed',
                frames=[dict(timestamp_sec=0,boxes=[])], events=[],
                evidence_frames=[dict(timestamp_sec=0,boxes=[],image_file='evidence-000.jpg')])
    monkeypatch.setattr('services.analysis.detector', lambda: FakeDetector())
    job_id = submit(client, auth_headers, media_id).json['job_id']
    assert run_next_job() == job_id and run_next_job() is None
    job = client.get('/api/v1/jobs/'+job_id, headers=auth_headers).json
    assert job['status'] == 'done' and job['result']['verdict'] == 'requires_review'
    assert client.get(f'/api/v1/media/{media_id}', headers=auth_headers).json['analysis_status'] == 'done'
    report = client.get(f'/api/v1/media/{media_id}/report', headers=auth_headers).json
    assert report['analysis']['violations'] == [] and report['verdict'] is None
    url = job['result']['evidence_frames'][0]['image_url']
    assert client.get(url).status_code == 200
    assert client.get(url.split('?')[0]).status_code == 401
    session = AuthSession.query.filter_by(revoked_at=None).first()
    session.revoked_at = utcnow(); db.session.commit()
    assert client.get(url).status_code == 401


def test_worker_failure_is_retryable_without_raw_error_exposure(client, auth_headers, monkeypatch, local_ml):
    media_id, _ = local_ml
    class BrokenDetector:
        def analyze(self, *args):
            raise RuntimeError('private internal path or diagnostic')
    monkeypatch.setattr('services.analysis.detector', lambda: BrokenDetector())
    job_id = submit(client, auth_headers, media_id).json['job_id']
    run_next_job()
    failed = client.get('/api/v1/jobs/'+job_id, headers=auth_headers).json
    assert failed['status'] == 'failed' and failed['result'] is None
    assert 'private' not in failed['error']
    retry = submit(client, auth_headers, media_id, 'full_frame')
    assert retry.status_code == 202 and retry.json['job_id'] == job_id
    assert retry.json['started_at'] is None and retry.json['camera_profile'] == 'full_frame'


def test_abandoned_processing_job_is_closed(local_ml):
    media_id, _ = local_ml
    job = AnalysisJob(media_id=media_id,camera_profile='forte_open',status='processing',
        started_at=utcnow()-timedelta(hours=1))
    db.session.add(job); db.session.commit()
    job_id = job.id
    assert run_next_job() is None
    assert db.session.get(AnalysisJob,job_id).status == 'failed'
