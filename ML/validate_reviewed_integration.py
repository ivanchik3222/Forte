"""Real multipart upload -> automatic queue -> R3D + local Qwen -> signed evidence.

Uses one development video only. Prints aggregate checks, never video captions.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--video-id',type=int,default=1)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    records = json.loads((ROOT/'audit/mac_manifest.json').read_text())
    record = next(r for r in records if args.video_id in r['video_ids'])
    from training_split import read_split
    assert record['sha256'] not in read_split()['holdout_source_hashes']
    from app import create_app
    from models import db, User, AnalysisJob
    from routes.auth import make_tokens
    from services.analysis import run_next_job
    from flask_migrate import upgrade
    import shutil
    app = create_app(dict(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///'+str(output/'test.sqlite'),
        MEDIA_ROOT=str(output/'media'), ML_ENABLED=True, ML_ENGINE='reviewed_pipeline', ML_AUTO_ANALYZE=True,
        FFPROBE_PATH=shutil.which('ffprobe') or 'ffprobe'))
    started = time.monotonic()
    with app.app_context():
        upgrade(directory=str(ROOT.parent/'backend/migrations'))
        user = User(email='pipeline-smoke@example.invalid', is_active=True, user_type='user')
        other = User(email='pipeline-other@example.invalid', is_active=True, user_type='user')
        db.session.add_all([user, other]); db.session.commit()
        token, _ = make_tokens(user); other_token, _ = make_tokens(other)
        headers = {'Authorization': 'Bearer '+token, 'Idempotency-Key': 'reviewed-smoke'}
        client = app.test_client()
        caps = client.get('/api/v1/capabilities', headers=headers).json
        assert caps['analysis'] and caps['analysis_engine'] == 'reviewed_pipeline'
        with Path(record['path']).open('rb') as video:
            uploaded = client.post('/api/v1/media', headers=headers, data={'file': (video, 'development.mov')}, content_type='multipart/form-data')
        assert uploaded.status_code == 201 and uploaded.json['analysis_status'] == 'queued', uploaded.json
        media_id = uploaded.json['id']
        job = client.get(f'/api/v1/media/{media_id}/analysis', headers=headers).json
        assert job['status'] == 'queued'
        with Path(record['path']).open('rb') as video:
            repeat = client.post('/api/v1/media', headers=headers, data={'file': (video, 'development.mov')}, content_type='multipart/form-data')
        assert repeat.status_code == 200 and AnalysisJob.query.count() == 1
        print('Multipart upload and automatic idempotent enqueue passed', flush=True)
        assert run_next_job() == job['job_id']
        response = client.get('/api/v1/jobs/'+job['job_id'], headers=headers)
        payload = response.json
        assert payload['status'] == 'done', payload.get('error')
        result = payload['result']
        assert result['engine'] == 'reviewed_pipeline' and result['verdict'] in ('violation','no_violation')
        assert result['caption_status'] in ('done', 'partial'), result['caption_status']
        assert bool(result['violations']) == (result['verdict']=='violation') and result['rule_evaluation'] == 'performed'
        assert result['model_sha256'] == 'f4f1a06a7296d63a3ea6f95a1da7e50ea41f84c1348648713142c861c4070902'
        evidence = result['evidence_frames']
        for event in result['events'] + result['observations']:
            assert event['mean_detector_confidence'] is None
            assert 0 <= event['start_sec'] <= event['end_sec'] <= uploaded.json['duration_sec']
            for index in event['evidence_indices']:
                assert 0 <= index < len(evidence)
                assert event['start_sec']-1e-5 <= evidence[index]['timestamp_sec'] <= event['end_sec']+1e-5
        for frame in evidence:
            image = client.get(frame['image_url'])
            assert image.status_code == 200 and image.data[:2] == b'\xff\xd8'
        for finding in result['violations']:
            assert 1 <= len(finding['evidence_frames']) <= 3
            assert any(e['timestamp_sec']==finding['timecode_sec'] for e in finding['evidence_frames'])
            if finding['classification_status']=='grounded':
                assert finding['rule']['url'] == 'https://adilet.zan.kz/rus/docs/V1900019680'
            else:
                assert finding['classification_status']=='unclassified' and finding['rule'] is None
            for e in finding['evidence_frames']:
                assert finding['start_sec'] <= e['timestamp_sec'] <= finding['end_sec']
                assert e['explanation'] and client.get(e['image_url']).status_code==200
        assert client.get('/api/v1/jobs/'+job['job_id'], headers={'Authorization':'Bearer '+other_token}).status_code == 404
        report = client.get(f'/api/v1/media/{media_id}/report', headers=headers)
        assert report.status_code == 200 and report.json['analysis']['engine'] == 'reviewed_pipeline'
        # Full response stays on local disk for frontend contract checks only.
        (output/'api-response.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        summary = dict(status='passed', engine=result['engine'], candidate_status=result['candidate_status'],
            candidate_events=len(result['events']), observations=len(result['observations']), evidence_frames=len(evidence),
            caption_status=result['caption_status'], elapsed_seconds=round(time.monotonic()-started, 2),
            verdict=result['verdict'],violations=len(result['violations']),unclassified_count=result['unclassified_count'],assessment_coverage=result['assessment_coverage'],
            source_seen_during_training=result['source_seen_during_training'], reserved_test_used=False,
            checks=['real multipart upload', 'automatic enqueue', 'idempotency', 'real frozen candidate model',
                'real offline Qwen', 'binary verdict', 'explicit classification status', 'event/evidence timestamps', 'signed JPEG access', 'owner isolation', 'JSON export'],
            limitation='Operational integration check on one development video, not a new accuracy measurement')
        (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
