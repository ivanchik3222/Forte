from datetime import timedelta
import pytest

from models import db, AnalysisJob, MediaRecord, AuthSession, utcnow
from routes.auth import make_tokens
from services.analysis import run_next_job, available


@pytest.fixture
def local_ml(app, tmp_path, monkeypatch, user1):
    monkeypatch.setitem(app.config, 'MEDIA_ROOT', str(tmp_path))
    weights = tmp_path/'weights.pt'
    weights.write_bytes(b'test weights; inference is replaced in unit tests')
    monkeypatch.setitem(app.config, 'ML_WEIGHTS', str(weights))
    monkeypatch.setitem(app.config, 'ML_ENABLED', True)
    monkeypatch.setitem(app.config, 'ML_ENGINE', 'objects')
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


def test_caption_engine_requires_local_runtime_and_weights(app, monkeypatch, local_ml):
    _, folder = local_ml
    monkeypatch.setitem(app.config, 'ML_ENGINE', 'dense_vlm')
    monkeypatch.setitem(app.config, 'ML_ROOT', str(folder))
    monkeypatch.setitem(app.config, 'ML_VLM_PYTHON', str(folder/'python'))
    monkeypatch.setitem(app.config, 'ML_VLM_ADAPTER', None)
    assert not available()
    (folder/'python').write_bytes(b'local test runtime')
    weights = folder/'models/qwen3_vl_4b_mlx/model.safetensors'
    weights.parent.mkdir(parents=True); weights.write_bytes(b'local test weights')
    assert available()
    monkeypatch.setitem(app.config, 'ML_ENGINE', 'unknown')
    assert not available()


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
    assert 'image_url' in report['analysis']['evidence_frames'][0]
    assert 'image_file' not in report['analysis']['evidence_frames'][0]
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


def test_upload_automatically_enqueues_once_and_preserves_file_when_queue_full(client, auth_headers, app, monkeypatch, local_ml):
    import io
    monkeypatch.setattr('services.media.probe', lambda *args: 10)
    monkeypatch.setitem(app.config, 'ML_AUTO_ANALYZE', True)
    def upload(key):
        return client.post('/api/v1/media', headers={**auth_headers, 'Idempotency-Key': key},
            data={'file': (io.BytesIO(b'synthetic video'), 'video.mov')}, content_type='multipart/form-data')
    first = upload('auto-one')
    assert first.status_code == 201 and first.json['analysis_status'] == 'queued'
    again = upload('auto-one')
    assert again.status_code == 200 and again.json['id'] == first.json['id']
    assert AnalysisJob.query.count() == 1
    monkeypatch.setitem(app.config, 'ML_QUEUE_LIMIT', 1)
    blocked = upload('auto-two')
    assert blocked.status_code == 201 and blocked.json['analysis_status'] == 'not_requested'
    assert blocked.json['analysis_submission_error']['code'] == 'analysis_busy'
    assert client.get('/api/v1/media/'+blocked.json['id'], headers=auth_headers).status_code == 200


def test_pipeline_availability_checks_both_models(app, monkeypatch, local_ml):
    _, folder = local_ml
    monkeypatch.setitem(app.config, 'ML_ENGINE', 'reviewed_pipeline')
    monkeypatch.setitem(app.config, 'ML_ROOT', str(folder))
    for setting, name in [('ML_REVIEWED_PYTHON', 'python'), ('ML_REVIEWED_BACKBONE', 'backbone.pth'),
                          ('ML_REVIEWED_BUNDLE', 'model_bundle.json'), ('ML_VLM_PYTHON', 'python')]:
        monkeypatch.setitem(app.config, setting, str(folder/name))
        (folder/name).write_bytes(b'test')
    (folder/'bank_only.npz').write_bytes(b'test')
    monkeypatch.setitem(app.config, 'ML_VLM_ADAPTER', None)
    monkeypatch.setitem(app.config, 'ML_VLM_MODEL_SIZE', '4b')
    assert not available()
    weights = folder/'models/qwen3_vl_4b_mlx/model.safetensors'
    weights.parent.mkdir(parents=True); weights.write_bytes(b'test')
    assert available()
    monkeypatch.setitem(app.config, 'ML_VLM_MODEL_SIZE', '8b')
    assert not available()
    for shard in (1, 2):
        path = folder/f'models/qwen3_vl_8b_mlx/model-{shard:05d}-of-00002.safetensors'
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'test')
    assert available()


def test_processing_stage_is_visible_and_old_progress_ignored_on_retry(client, auth_headers, local_ml):
    import json
    media_id, folder = local_ml
    job_id = submit(client, auth_headers, media_id).json['job_id']
    path = folder/'analysis'/job_id
    path.mkdir(parents=True); (path/'progress.json').write_text(json.dumps({'stage':'describing_actions'}))
    assert client.get('/api/v1/jobs/'+job_id, headers=auth_headers).json['stage'] is None
    job = db.session.get(AnalysisJob, job_id); job.status = 'processing'; db.session.commit()
    assert client.get('/api/v1/jobs/'+job_id, headers=auth_headers).json['stage'] == 'describing_actions'
