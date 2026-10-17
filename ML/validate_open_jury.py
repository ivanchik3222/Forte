"""Actual jury API batch; labels are used only after inference for comparison.

No mocked model, no label-based decisions, no invented action/rule labels. The
local HTML preserves failure responses and separates reference/diagnostic frames.
"""
import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import re
import secrets
import shutil
import sys
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

import av
from PIL import Image
from jury_contract import success_errors

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'backend'))


def annotation_rows(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as book:
        strings=[]
        if 'xl/sharedStrings.xml' in book.namelist():
            strings=[''.join(n.itertext()) for n in ET.fromstring(book.read('xl/sharedStrings.xml'))]
        result={}
        for row in ET.fromstring(book.read('xl/worksheets/sheet1.xml')).findall('.//s:row',ns)[1:]:
            cells={}
            for cell in row.findall('s:c',ns):
                value=''.join(cell.itertext())
                cells[re.sub(r'\d+','',cell.attrib['r'])]=strings[int(value)] if cell.attrib.get('t')=='s' else value
            if not cells.get('A'): continue
            vid=int(re.search(r'\d+',cells['A']).group())
            label=cells.get('C','').strip()
            if label not in ('нарушение','без нарушения'): raise ValueError('Unknown annotation label')
            parts=[int(v) for v in re.findall(r'\d+',cells.get('B',''))]
            sec=(parts[0]*60+parts[1] if len(parts)==2 else parts[0]) if parts else None
            if label=='нарушение' and sec is None: raise ValueError('Missing positive point')
            if vid in result: raise ValueError('Duplicate annotation ID')
            result[vid]=dict(verdict='violation' if label=='нарушение' else 'no_violation',timestamp_sec=sec)
    return result


def reference_frame(source,target,destination):
    """Nearest real PTS; selection uses annotation solely for reference display."""
    best=None
    with av.open(str(source)) as video:
        stream=video.streams.video[0]
        origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else None
        for frame in video.decode(stream):
            if frame.time is None: raise ValueError('Missing PTS')
            if origin is None: origin=float(frame.time)
            sec=float(frame.time)-origin
            if best is None or abs(sec-target)<abs(best[0]-target):
                best=(sec,frame.to_ndarray(format='rgb24'))
            if sec>=target: break
    if best is None: raise ValueError('No reference frame')
    Image.fromarray(best[1]).save(destination,'JPEG',quality=92)
    with Image.open(destination) as image: image.verify()
    return round(best[0],6)


def write_html(output,summary):
    cards=[]
    for row in summary['records']:
        correct=row.get('contract_ok',False)
        actual=row.get('jury_response',{})
        expectation=row.get('annotation',{})
        expected='нарушение' if expectation.get('verdict')=='violation' else 'без нарушения'
        images=[]
        for key,title in [('reference_frame','Кадр по разметке — не предсказание модели'),
                          ('diagnostic_frame','Кадр наблюдений модели — не доказательство нарушения')]:
            frame=row.get(key)
            if frame:
                if key=='reference_frame' and expectation.get('timestamp_sec') is None:
                    title='Иллюстративный кадр: эталонный таймкод отсутствует'
                images.append(f'<figure><img loading="lazy" src="{escape(quote(frame["path"]))}" alt="{escape(title)}">'
                              f'<figcaption>{escape(title)}<br>PTS {frame["timestamp_sec"]:.3f} с</figcaption></figure>')
        label='Ответ по ТЗ готов' if correct else 'Ответ по ТЗ не получен'
        cards.append(f'<article data-label="{expectation.get("verdict","")}" data-ok="{str(correct).lower()}">'
            f'<h2>{escape(row["file"])}</h2><p class="{"ok" if correct else "bad"}">{label}</p>'
            f'<p>Разметка: <strong>{expected}</strong>'
            f'{" · "+str(expectation["timestamp_sec"])+" с" if expectation.get("timestamp_sec") is not None else ""}</p>'
            f'<p>API: {escape(str(actual.get("status","transport error")))} · {escape(str(actual.get("error_code","")))}</p>'
            '<div class="images">'+''.join(images)+'</div>'
            f'<details><summary>Настоящий ответ API</summary><pre>{escape(json.dumps(actual,ensure_ascii=False,indent=2))}</pre></details>'
            f'<p><a href="{escape(row.get("response_file","#"))}">JSON API</a> · {row.get("total_seconds",0):.2f} с</p></article>')
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Open — проверка API по ТЗ</title><style>
body{font:16px system-ui,sans-serif;margin:0;background:#f3f4f7;color:#20212b}main{max-width:1280px;margin:auto;padding:28px}
h1{font-size:30px}article{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin:20px 0}
.bad{color:#a31d38;font-weight:650}.ok{color:#147141}.notice{padding:16px;background:#fff1d6;border-radius:10px;line-height:1.6}
.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}figure{margin:0}img{height:400px;width:100%;object-fit:contain;background:#14141b;border-radius:8px}figcaption{font-size:14px;margin:8px 0;line-height:1.5}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f5f5f8;padding:12px}select{font:inherit;padding:8px}a{color:#8b1645}
</style><main><h1>Проверка open через API жюри</h1>'''
    page+=f'<p>Видео: {summary["videos"]} · модель отработала: {summary["worker_done"]} · успешных ответов по ТЗ: <strong>{summary["jury_done"]}</strong> · JPEG в отчёте: {summary["reference_jpegs"]+summary["diagnostic_jpegs"]}</p>'
    page+='<p class="notice">Это настоящий прогон модели. Разметка использована только для сравнения и выбора отдельно подписанного эталонного кадра. Она не подставлялась в ответ API. Наблюдения объектов не подтверждают нарушение. Ошибка классификации не считается ответом «нарушений нет».</p>'
    page+='<label>Показать: <select id="filter"><option value="all">Все видео</option><option value="violation">Нарушение по разметке</option><option value="no_violation">Без нарушения по разметке</option><option value="failed">Без ответа по ТЗ</option><option value="done">Ответ по ТЗ готов</option></select></label>'
    page+=''.join(cards)+'''</main><script>document.getElementById('filter').onchange=function(){document.querySelectorAll('article').forEach(a=>{a.hidden=!(this.value==='all'||a.dataset.label===this.value||(this.value==='failed'&&a.dataset.ok==='false')||(this.value==='done'&&a.dataset.ok==='true'))})}</script></html>'''
    (output/'report.html').write_text(page,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'open/open')
    p.add_argument('--output',type=Path,default=ROOT/'runs/open_tz_validation_v1')
    p.add_argument('--ffprobe',type=Path)
    p.add_argument('--limit',type=int,default=0)
    args=p.parse_args()
    ffprobe=args.ffprobe or next((ROOT/'cache/ffmpeg').glob('*/bin/ffprobe.exe'),None) or shutil.which('ffprobe')
    if not ffprobe: raise FileNotFoundError('ffprobe is required for actual HTTP uploads')
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    for name in ('responses','reference_frames','predicted_frames','media'): (output/name).mkdir()
    from app import create_app
    from flask_migrate import upgrade
    from models import db,User,AnalysisJob,MediaRecord
    from routes.auth import make_tokens
    from services.analysis import run_next_job
    app=create_app(dict(TESTING=True,ML_ENABLED=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///'+(output/'test.sqlite').as_posix(),
        MEDIA_ROOT=str(output/'media'),FFPROBE_PATH=str(Path(ffprobe).resolve()),MIN_FREE_BYTES=0,
        ML_WEIGHTS=str(ROOT/'deployment/cash_detector.pt'),UPLOADS_PER_HOUR=100,JURY_API_KEY=secrets.token_urlsafe(32)))
    paths=sorted((args.data/'videos').glob('*.mov'),key=lambda f:int(re.search(r'\d+',f.stem).group()))
    if args.limit: paths=paths[:args.limit]
    if not paths: raise ValueError('No input videos')
    # Reference data never enters POST /analyze or the worker.
    annotations=annotation_rows(args.data/'open_labels.xlsx')
    records=[]; started=time.perf_counter()
    with app.app_context():
        upgrade(directory=str(ROOT.parent/'backend/migrations'))
        owner=User(email='jury-batch@example.invalid',is_active=True,user_type='user')
        db.session.add(owner);db.session.commit()
        app.config['JURY_OWNER_ID']=owner.id
        token,_=make_tokens(owner)
        headers={'X-API-Key':app.config['JURY_API_KEY']}
        jwt_headers={'Authorization':'Bearer '+token}
        client=app.test_client()
        for n,source in enumerate(paths,1):
            began=time.perf_counter();vid=int(re.search(r'\d+',source.stem).group())
            row=dict(file=source.name,video_id=vid,contract_ok=False,worker_status='not_run')
            try:
                with source.open('rb') as video:
                    response=client.post('/api/v1/analyze',headers=headers,data={'file':(video,source.name)},content_type='multipart/form-data')
                assert response.status_code==202,response.json
                job_id=response.json['job_id'];row['job_id']=job_id
                assert client.get('/api/v1/jobs/'+job_id,headers=headers).json['status']=='processing'
                assert run_next_job()==job_id
                job=db.session.get(AnalysisJob,job_id)
                media=db.session.get(MediaRecord,job.media_id)
                duration=media.duration_sec
                assert duration and duration>0
                row['duration_sec']=round(duration,3);row['worker_status']=job.status
                actual=client.get('/api/v1/jobs/'+job_id,headers=headers)
                assert actual.status_code==200,actual.json
                answer=actual.json
                response_file=f'responses/video_{vid:03d}.json'
                (output/response_file).write_text(json.dumps(answer,ensure_ascii=False,indent=2),encoding='utf-8')
                row.update(jury_response=answer,response_file=response_file,
                    contract_errors=success_errors(answer,job_id,duration))
                row['contract_ok']=not row['contract_errors']
                internal=client.get('/api/v1/jobs/'+job_id,headers=jwt_headers)
                assert internal.status_code==200,internal.json
                model=internal.json.get('result')
                if model:
                    row['processed_frames']=model['processed_frames'];row['model_sha256']=model['model_sha256']
                    row['profile']=model['camera_profile'];row['classification_complete']=model['classification_complete']
                    row['additional_checks']=model['additional_checks']
                    samples=job.result['evidence_frames']
                    assert samples
                    def salience(e):
                        return max((b['confidence'] for b in e['boxes'] if b['label']=='cash'),default=0.)
                    chosen=max(samples,key=salience)
                    diagnostic=output/'media/analysis'/job_id/chosen['image_file']
                    with Image.open(diagnostic) as image: image.verify()
                    row['diagnostic_frame']=dict(path=diagnostic.relative_to(output).as_posix(),timestamp_sec=chosen['timestamp_sec'])
                # Compare only AFTER the unmodified real response is saved.
                truth=annotations[vid];row['annotation']=truth
                target=truth['timestamp_sec'] if truth['timestamp_sec'] is not None else duration/2
                filename=f'reference_frames/video_{vid:03d}.jpg'
                pts=reference_frame(source,target,output/filename)
                row['reference_frame']=dict(path=filename,timestamp_sec=pts,target_sec=target,
                    purpose='annotation_reference_not_model_prediction',selection_error_sec=round(abs(pts-target),6))
                row['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                if row['contract_ok']:
                    row['verdict_matches_annotation']=answer['verdict']==truth['verdict']
                    extracted=[]
                    for i,event in enumerate(answer['violations']):
                        for j,frame in enumerate(event['evidence_frames']):
                            import base64
                            path=output/f'predicted_frames/video_{vid:03d}_{i}_{j}.jpg'
                            path.write_bytes(base64.b64decode(frame['image_base64'],validate=True))
                            extracted.append(path.relative_to(output).as_posix())
                    row['predicted_evidence_jpegs']=extracted
            except Exception as exc:
                db.session.rollback();row['test_error']=str(exc)
            row['total_seconds']=round(time.perf_counter()-began,3);records.append(row)
            (output/'progress.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'{n}/{len(paths)} {source.name}: worker={row["worker_status"]}, jury={row.get("jury_response",{}).get("status","error")}, JPEG={"reference_frame" in row}',flush=True)
    valid=[r for r in records if r['contract_ok']]
    summary=dict(videos=len(records),worker_done=sum(r['worker_status']=='done' for r in records),
        jury_done=len(valid),jury_failed=sum(r.get('jury_response',{}).get('status')=='failed' for r in records),
        test_errors=sum('test_error' in r for r in records),
        reference_jpegs=sum('reference_frame' in r for r in records),
        diagnostic_jpegs=sum('diagnostic_frame' in r for r in records),
        predicted_evidence_jpegs=sum(len(r.get('predicted_evidence_jpegs',[])) for r in records),
        errors=dict(Counter(r.get('jury_response',{}).get('error_code','none') for r in records)),
        verdict_coverage=len(valid)/len(records),
        accuracy_on_answered_videos=sum(r['verdict_matches_annotation'] for r in valid)/len(valid) if valid else None,
        annotated_positive_videos=sum(r.get('annotation',{}).get('verdict')=='violation' for r in records),
        annotated_negative_videos=sum(r.get('annotation',{}).get('verdict')=='no_violation' for r in records),
        elapsed_seconds=round(time.perf_counter()-started,3),
        protocol='Real multipart MOV uploads, real ffprobe, real model/worker, real jury and JWT APIs; labels only for comparison/reference JPEGs; no mocks or learning',
        records=records)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    write_html(output,summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='records'},ensure_ascii=False,indent=2),flush=True)
    if len(valid)!=len(records): raise SystemExit(1)


if __name__=='__main__':main()
