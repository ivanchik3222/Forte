"""Run every native video through real enqueue/worker/status/evidence/report paths.

By default registers existing local files (hard links). --http-upload also
exercises multipart upload and ffprobe. No mock model or violation accuracy claims.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--videos', type=Path, default=ROOT/'open/open/videos')
    parser.add_argument('--output', type=Path, default=ROOT/'runs/open_integration_v1')
    parser.add_argument('--device', default=None)
    parser.add_argument('--http-upload', action='store_true', help='Exercise real multipart upload and ffprobe as well')
    parser.add_argument('--ffprobe', type=Path)
    parser.add_argument('--limit', type=int, default=0, help='Optional smoke subset; default processes every video')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    storage = output/'media'
    storage.mkdir()
    from app import create_app
    from models import db, User, MediaRecord, uid
    from routes.auth import make_tokens
    from services.analysis import run_next_job
    from flask_migrate import upgrade
    import av
    app = create_app(dict(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///'+(output/'test.sqlite').as_posix(),
        MEDIA_ROOT=str(storage), ML_ENABLED=True, ML_DEVICE=args.device, ML_ENGINE='objects', ML_AUTO_ANALYZE=False,
        ML_WEIGHTS=str(ROOT/'deployment/cash_detector.pt')))
    if args.ffprobe:
        app.config['FFPROBE_PATH'] = str(args.ffprobe.resolve())
    app.config['UPLOADS_PER_HOUR'] = 100  # Isolated batch account, not a production setting.
    records = []
    started = time.perf_counter()
    with app.app_context():
        upgrade(directory=str(ROOT.parent/'backend/migrations'))
        user = User(email='local-batch@example.invalid', is_active=True, user_type='user')
        other = User(email='other-batch@example.invalid', is_active=True, user_type='user')
        db.session.add_all([user, other]); db.session.commit()
        owner_id = user.id
        token, _ = make_tokens(user)
        other_token, _ = make_tokens(other)
        headers = {'Authorization': 'Bearer '+token}
        client = app.test_client()
        paths = sorted([p for p in args.videos.iterdir() if p.suffix.lower() in ('.mov', '.mp4', '.webm')],
            key=lambda p: int(p.stem.split('-')[-1]))
        if args.limit:
            paths = paths[:args.limit]
        if not paths:
            raise ValueError('No videos found')
        for n, source in enumerate(paths, 1):
            began = time.perf_counter()
            item = dict(file=source.name, status='failed')
            try:
                if args.http_upload:
                    with source.open('rb') as video_file:
                        uploaded = client.post('/api/v1/media', headers={**headers, 'Idempotency-Key': f'batch-{n}'},
                            data={'file': (video_file, source.name)}, content_type='multipart/form-data')
                    assert uploaded.status_code == 201, uploaded.json
                    media_id, duration = uploaded.json['id'], uploaded.json['duration_sec']
                else:
                    with av.open(str(source)) as container:
                        duration = float(container.duration / av.time_base)
                    name = uid()+source.suffix.lower()
                    try:
                        os.link(source, storage/name)
                    except OSError:
                        shutil.copyfile(source, storage/name)
                    media = MediaRecord(owner_id=owner_id, original_name=source.name, storage_key=name,
                        size_bytes=source.stat().st_size, content_type='video/quicktime' if source.suffix.lower()=='.mov' else 'video/mp4',
                        duration_sec=duration)
                    db.session.add(media); db.session.commit()
                    media_id = media.id
                submitted = client.post(f'/api/v1/media/{media_id}/analyze', headers=headers,
                    json={'camera_profile': 'forte_open'})
                assert submitted.status_code == 202, submitted.json
                job_id = submitted.json['job_id']
                assert run_next_job() == job_id
                response = client.get(f'/api/v1/jobs/{job_id}', headers=headers)
                assert response.status_code == 200 and response.json['status'] == 'done', response.json
                result = response.json['result']
                assert result['verdict'] == 'requires_review' and result['violations'] == []
                assert result['rule_evaluation'] == 'not_performed'
                rows = result['frames']; assert rows and len(rows) == result['processed_frames']
                assert all(b['timestamp_sec'] > a['timestamp_sec'] for a,b in zip(rows, rows[1:]))
                assert rows[0]['timestamp_sec'] >= 0 and rows[-1]['timestamp_sec'] < duration+.1
                counts = Counter()
                for row in rows:
                    for box in row['boxes']:
                        x1,y1,x2,y2 = box['xyxy']
                        assert 0 <= x1 < x2 <= result['width'] and 0 <= y1 < y2 <= result['height']
                        assert 0.25 <= box['confidence'] <= 1
                        counts[box['label']] += 1
                evidence = result['evidence_frames']; assert evidence
                for frame in (evidence[0], evidence[-1]):
                    image = client.get(frame['image_url'])
                    assert image.status_code == 200 and image.data[:2] == b'\xff\xd8'
                assert client.get(f'/api/v1/jobs/{job_id}', headers={'Authorization': 'Bearer '+other_token}).status_code == 404
                playback = client.post(f'/api/v1/media/{media_id}/playback-url', headers=headers).json['url']
                assert client.get(playback, headers={'Range':'bytes=0-3'}).status_code == 206
                exported = client.get(f'/api/v1/media/{media_id}/report', headers=headers)
                assert exported.status_code == 200 and exported.json['analysis']['model_sha256'] == result['model_sha256']
                item.update(status='done', duration_sec=round(duration, 3), frames=len(rows), boxes=dict(counts),
                    events=len(result['events']), evidence_frames=len(evidence),
                    inference_seconds=result['elapsed_seconds'], job_id=job_id,
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    model_sha256=result['model_sha256'])
            except Exception as exc:
                db.session.rollback()
                item['error'] = str(exc)
            item['total_seconds'] = round(time.perf_counter()-began, 3)
            records.append(item)
            (output/'progress.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"{n}/{len(paths)} {source.name}: {item['status']} ({item['total_seconds']}s)", flush=True)
    summary = dict(videos=len(records), succeeded=sum(x['status']=='done' for x in records),
        failed=sum(x['status']!='done' for x in records),
        unique_videos=len({x.get('source_sha256') for x in records if x['status']=='done'}),
        frames=sum(x.get('frames',0) for x in records), events=sum(x.get('events',0) for x in records),
        video_seconds=round(sum(x.get('duration_sec',0) for x in records),3),
        inference_seconds=round(sum(x.get('inference_seconds',0) for x in records),3),
        elapsed_seconds=round(time.perf_counter()-started,3),
        protocol=('Real multipart upload and ffprobe; ' if args.http_upload else 'Existing files registered locally, upload/ffprobe excluded; ')+
            'real Flask API, migrations and worker; no duplicate inference cache',
        http_upload=args.http_upload,
        parameters=dict(fps=2,confidence=.25,nms_iou=.7,imgsz=640,camera_profile='forte_open'),
        limitations=['Operational integration test, not an independent accuracy evaluation',
            'Source dataset contains train/val/test videos; run not used for tuning',
            'Object detector does not classify regulatory violations; no binary accuracy inferred'], records=records)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='records'},ensure_ascii=False,indent=2),flush=True)
    if summary['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
