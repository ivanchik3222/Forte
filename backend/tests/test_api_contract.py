"""Both key types must expose the same real model-report/evidence contract."""
import base64
from datetime import timedelta
from pathlib import Path

import pytest
from PIL import Image

from models import db, AnalysisJob, utcnow
from services.analysis import run_next_job
from tests.test_jury import jury, upload


@pytest.fixture(params=['jury', 'issued'])
def api_key(request, client, jury):
    if request.param == 'jury':
        return jury
    return {'X-API-Key': client.post('/api/v1/api-keys').json['api_key']}


def completed(client, headers):
    queued = upload(client, headers)
    assert queued.status_code == 202, queued.json
    job_id = queued.json['job_id']
    assert run_next_job() == job_id
    assert client.get('/api/v1/jobs/' + job_id, headers=headers).json['status'] == 'done'
    return db.session.get(AnalysisJob, job_id)


def result(client, headers, job):
    response = client.get('/api/v1/jobs/' + job.id, headers=headers)
    assert response.status_code == 200
    return response.json


def test_both_keys_preserve_trained_positive_and_unclassified_evidence(client, api_key, app):
    job = completed(client, api_key)
    report = dict(job.result)
    original = report['violations'][0]
    report['violations'] = [dict(original, classification_status='unclassified', rule=None,
        type='Признаки нарушения — тип не определён')]
    report['assessment_coverage'] = 'partial'
    job.result = report
    db.session.commit()
    answer = result(client, api_key, job)
    assert answer['status'] == 'done' and answer['verdict'] == report['verdict']
    assert answer['coverage_status'] == 'partial'
    event = answer['violations'][0]
    assert event['classification_status'] == 'unclassified' and event['rule'] is None
    assert event['type'] == report['violations'][0]['type']
    assert event['description'] == original['description'] and event['timecode_sec'] == original['timecode_sec']
    frame = event['evidence_frames'][0]
    expected = Path(app.config['MEDIA_ROOT']) / 'analysis' / job.id / 'chosen.jpg'
    assert base64.b64decode(frame['image_base64'], validate=True) == expected.read_bytes()
    assert set(frame) == {'timestamp_sec', 'image_base64'}


@pytest.mark.parametrize('damage', [
    'zero_frames', 'four_frames', 'duplicate_frames', 'missing_evidence', 'negative_index',
    'out_of_bounds_index', 'boolean_index', 'bad_frame_object', 'bad_event_object',
    'negative_time', 'outside_video', 'nonnumeric_time', 'unmatched_keyframe', 'reference_time_mismatch',
    'empty_type', 'bad_description', 'inconsistent_verdict', 'missing_file', 'path_traversal',
    'png', 'truncated_jpeg',
])
def test_invalid_model_reports_fail_without_http_500(client, api_key, app, damage):
    job = completed(client, api_key)
    report = dict(job.result)
    event = report['violations'][0]
    ref = event['evidence'][0]
    folder = Path(app.config['MEDIA_ROOT']) / 'analysis' / job.id
    if damage == 'zero_frames': event['evidence'] = []
    elif damage == 'four_frames': event['evidence'] = [ref] * 4
    elif damage == 'duplicate_frames': event['evidence'] = [ref] * 2
    elif damage == 'missing_evidence': del event['evidence']
    elif damage == 'negative_index': ref['evidence_index'] = -1
    elif damage == 'out_of_bounds_index': ref['evidence_index'] = 10
    elif damage == 'boolean_index': ref['evidence_index'] = True
    elif damage == 'bad_frame_object': report['evidence_frames'] = [None]
    elif damage == 'bad_event_object': report['violations'] = [None]
    elif damage == 'negative_time': event['timecode_sec'] = -1
    elif damage == 'outside_video': event['timecode_sec'] = 20
    elif damage == 'nonnumeric_time': event['timecode_sec'] = 'NaN'
    elif damage == 'unmatched_keyframe': event['timecode_sec'] = 3.5
    elif damage == 'reference_time_mismatch': ref['timestamp_sec'] = 4
    elif damage == 'empty_type': event['type'] = ' '
    elif damage == 'bad_description': event['description'] = []
    elif damage == 'inconsistent_verdict': report['verdict'] = 'no_violation'
    elif damage == 'missing_file': (folder / 'chosen.jpg').unlink()
    elif damage == 'path_traversal': report['evidence_frames'][0]['image_file'] = '../../secret.jpg'
    elif damage == 'png': Image.new('RGB', (12, 12)).save(folder / 'chosen.jpg', format='PNG')
    elif damage == 'truncated_jpeg':
        image = folder / 'chosen.jpg'
        image.write_bytes(image.read_bytes()[:100])
    # Use a fresh dict so SQLAlchemy detects nested JSON changes.
    from sqlalchemy.orm.attributes import flag_modified
    job.result = report
    flag_modified(job, 'result')
    db.session.commit()
    answer = result(client, api_key, job)
    assert answer['status'] == 'failed' and answer['error']['code'] == 'invalid_result'
    assert 'verdict' not in answer and 'violations' not in answer


@pytest.mark.parametrize('timecode', [float('nan'), float('inf'), -float('inf'), True])
def test_nonfinite_in_memory_model_output_is_not_serialized(app, timecode):
    # PostgreSQL correctly rejects NaN/Infinity in JSON before storage, while
    # SQLite permits them. Exercise the response boundary without DB insertion.
    from types import SimpleNamespace
    from services.api_result import response
    job = SimpleNamespace(id='synthetic', status='done', created_at=utcnow(), finished_at=utcnow(),
        result=dict(verdict='violation', violations=[dict(type='test', description='test', timecode_sec=timecode)]))
    answer = response(job, SimpleNamespace(duration_sec=10))
    assert answer['status'] == 'failed' and answer['error']['code'] == 'invalid_result'
    assert 'verdict' not in answer


def test_negative_verdict_requires_completed_assessment(client, api_key):
    job = completed(client, api_key)
    job.result = dict(job.result, verdict='no_violation', violations=[], assessment_coverage='done')
    db.session.commit()
    answer = result(client, api_key, job)
    assert answer['verdict'] == 'no_violation' and answer['violations'] == []
    job.result = dict(job.result, assessment_coverage='partial')
    db.session.commit()
    answer = result(client, api_key, job)
    assert answer['status'] == 'failed' and answer['error']['code'] == 'incomplete_analysis'


def test_caption_failure_does_not_erase_explicit_trained_positive(client, api_key):
    job = completed(client, api_key)
    event = dict(job.result['violations'][0], classification_status='unclassified', rule=None)
    job.result = dict(job.result, violations=[event], events=[dict(timecode_sec=event['timecode_sec'])],
        candidate_status='candidates_found', rule_evaluation='not_performed', assessment_coverage='partial')
    db.session.commit()
    answer = result(client, api_key, job)
    assert answer['status'] == 'done' and answer['verdict'] == 'violation'
    assert answer['rule_evaluation'] == 'not_performed'
    assert answer['violations'][0]['classification_status'] == 'unclassified'
    assert answer['violations'][0]['rule'] is None
    # A purported grounded finding without rule assessment is still rejected.
    job.result = dict(job.result, violations=[dict(event, classification_status='grounded')])
    db.session.commit()
    assert result(client, api_key, job)['error']['code'] == 'verdict_unavailable'


@pytest.mark.parametrize('state', ['queued', 'processing'])
def test_expired_api_jobs_fail_and_release_capacity(client, api_key, state):
    job_id = upload(client, api_key).json['job_id']
    job = db.session.get(AnalysisJob, job_id)
    job.status = state
    job.created_at = utcnow() - timedelta(seconds=301)
    job.started_at = utcnow() - timedelta(seconds=300) if state == 'processing' else None
    db.session.commit()
    assert result(client, api_key, job)['error']['code'] == 'analysis_timeout'
    assert upload(client, api_key).status_code == 202
    db.session.refresh(job)
    assert job.status == 'failed'


def test_finished_in_time_stays_available_but_late_result_is_rejected(client, api_key):
    job = completed(client, api_key)
    job.created_at = utcnow() - timedelta(hours=1)
    job.finished_at = job.created_at + timedelta(seconds=299)
    db.session.commit()
    assert result(client, api_key, job)['status'] == 'done'
    job.finished_at = job.created_at + timedelta(seconds=300)
    db.session.commit()
    assert result(client, api_key, job)['error']['code'] == 'analysis_timeout'


@pytest.mark.parametrize('overrun', [False, True])
def test_worker_budget_includes_queue_and_rejects_overrun(client, api_key, monkeypatch, overrun):
    import services.analysis as analysis
    clock = [utcnow()]
    monkeypatch.setattr(analysis, 'utcnow', lambda: clock[0])
    job_id = upload(client, api_key).json['job_id']
    job = db.session.get(AnalysisJob, job_id)
    job.created_at = clock[0] - timedelta(seconds=299)
    db.session.commit()
    engine = analysis.detector()
    class TimedEngine:
        def analyze(self, source, output, profile, timeout):
            assert 0 < timeout <= 1
            report = engine.analyze(source, output, profile, timeout)
            if overrun: clock[0] += timedelta(seconds=2)
            return report
    monkeypatch.setattr(analysis, 'detector', lambda: TimedEngine())
    assert run_next_job() == job_id
    job = db.session.get(AnalysisJob, job_id)
    assert job.status == ('failed' if overrun else 'done')
    answer = result(client, api_key, job)
    if overrun:
        assert answer['error']['code'] == 'analysis_timeout' and 'verdict' not in answer
    else:
        assert answer['status'] == 'done'
