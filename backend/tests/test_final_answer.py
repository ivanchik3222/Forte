import base64
import io
import pytest
from PIL import Image
from datetime import timedelta

from models import db, AnalysisJob, MediaRecord, utcnow
from services.final_answer import final_answer, DecisionUnavailable


def report(directory):
    Image.new('RGB',(16,16),'white').save(directory/'frame.jpg','JPEG')
    return dict(classification_complete=True,rule_evaluation='performed',
        evidence_frames=[dict(timestamp_sec=3.5,image_file='frame.jpg')],
        violations=[dict(type='Проверяемый тип события',timecode_sec=3.5,description='Наблюдаемое действие и обоснование.',
            evidence_frame_indices=[0],rule=dict(title='Проверенный источник',section='Пункт',
                url='https://adilet.zan.kz/rus/docs/V1900019680',explanation='Применимость установлена классификатором.'))])


def test_two_verdict_contract_and_actual_base64(tmp_path):
    data=report(tmp_path)
    answer=final_answer('job',data,tmp_path)
    assert answer['status']=='done' and answer['verdict']=='violation'
    assert base64.b64decode(answer['violations'][0]['evidence_frames'][0]['image_base64'])==(tmp_path/'frame.jpg').read_bytes()
    data['violations']=[]
    assert final_answer('job',data,tmp_path)==dict(job_id='job',status='done',verdict='no_violation',violations=[])


def test_no_false_negative_from_missing_classifier(tmp_path):
    with pytest.raises(DecisionUnavailable):
        final_answer('job',dict(verdict='requires_review',violations=[],rule_evaluation='not_performed'),tmp_path)


@pytest.mark.parametrize('mutation', ['no_rule','wrong_time','too_many_frames','path_escape'])
def test_rejects_incomplete_or_irrelevant_evidence(tmp_path,mutation):
    data=report(tmp_path)
    if mutation=='no_rule': data['violations'][0].pop('rule')
    if mutation=='wrong_time': data['violations'][0]['timecode_sec']=7
    if mutation=='too_many_frames': data['violations'][0]['evidence_frame_indices']=[0,0,0,0]
    if mutation=='path_escape': data['evidence_frames'][0]['image_file']='../frame.jpg'
    with pytest.raises(DecisionUnavailable): final_answer('job',data,tmp_path)


@pytest.fixture
def jury(app,user1,monkeypatch,tmp_path):
    monkeypatch.setitem(app.config,'JURY_API_KEY','unit-test-jury-key')
    monkeypatch.setitem(app.config,'JURY_OWNER_ID',user1.id)
    monkeypatch.setitem(app.config,'MEDIA_ROOT',str(tmp_path))
    monkeypatch.setitem(app.config,'MIN_FREE_BYTES',0)
    monkeypatch.setitem(app.config,'ML_ENABLED',True)
    monkeypatch.setitem(app.config,'ML_WEIGHTS',str(tmp_path/'weights.pt'))
    (tmp_path/'weights.pt').write_bytes(b'test-only')
    monkeypatch.setattr('services.media.probe',lambda path,ext: 4.)
    return {'X-API-Key':'unit-test-jury-key'},tmp_path


def test_jury_upload_without_jwt_or_idempotency_key(client,jury):
    headers,_=jury
    assert client.post('/api/v1/analyze',headers={'X-API-Key':'wrong'}).status_code==401
    assert client.post('/api/v1/analyze').status_code==401
    response=client.post('/api/v1/analyze',headers=headers,
        data={'file':(io.BytesIO(b'video'),'test.mov')},content_type='multipart/form-data')
    assert response.status_code==202 and list(response.json)==['job_id']
    job_id=response.json['job_id']
    status=client.get('/api/v1/jobs/'+job_id,headers=headers)
    assert status.json==dict(job_id=job_id,status='processing')
    assert client.get('/api/v1/jobs/'+job_id,headers={'X-API-Key':'wrong'}).status_code==401
    job=db.session.get(AnalysisJob,job_id)
    assert job.camera_profile=='full_frame'
    job.status='done'; job.result=dict(rule_evaluation='not_performed',violations=[])
    db.session.commit()
    answer=client.get('/api/v1/jobs/'+job_id,headers=headers).json
    assert answer['status']=='failed' and answer['error_code']=='classification_not_ready'
    assert 'verdict' not in answer


def test_jury_sees_only_its_account_and_returns_final_schema(client,auth_headers,user2,jury):
    headers,directory=jury
    media=MediaRecord(owner_id=user2.id,original_name='private.mov',storage_key='private.mov',
        size_bytes=10,content_type='video/quicktime')
    db.session.add(media); db.session.flush()
    job=AnalysisJob(media_id=media.id,camera_profile='full_frame',status='done')
    db.session.add(job); db.session.commit()
    assert client.get('/api/v1/jobs/'+job.id,headers=headers).status_code==404
    media.owner_id=client.application.config['JURY_OWNER_ID']; db.session.commit()
    target=directory/'analysis'/job.id; target.mkdir(parents=True)
    job.result=report(target); db.session.commit()
    answer=client.get('/api/v1/jobs/'+job.id,headers=headers).json
    assert answer['status']=='done' and answer['verdict']=='violation'
    assert answer['violations'][0]['rule']['section']=='Пункт'
    job.created_at=utcnow()-timedelta(seconds=301); db.session.commit()
    late=client.get('/api/v1/jobs/'+job.id,headers=headers).json
    assert late['status']=='failed' and late['error_code']=='deadline_exceeded'
