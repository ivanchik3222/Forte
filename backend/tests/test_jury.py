import base64
import io
import pytest
from PIL import Image
from models import db, MediaRecord, AnalysisJob
from services.analysis import run_next_job


@pytest.fixture
def jury(app,tmp_path,monkeypatch):
    monkeypatch.setitem(app.config,'MEDIA_ROOT',str(tmp_path))
    monkeypatch.setitem(app.config,'ML_ENABLED',True)
    monkeypatch.setitem(app.config,'ML_ENGINE','reviewed_pipeline')
    monkeypatch.setitem(app.config,'JURY_API_KEY','synthetic-test-key')
    monkeypatch.setattr('services.analysis.available',lambda:True)
    monkeypatch.setattr('services.media.probe',lambda *args:10)
    class Engine:
        def analyze(self,source,output,*args):
            output.mkdir(parents=True)
            Image.new('RGB', (12, 12), 'blue').save(output/'chosen.jpg', format='JPEG')
            return dict(engine='reviewed_pipeline',verdict='violation',rule_evaluation='performed',
                assessment_coverage='done',decision_scope='visible_signs_of_possible_violations',
                evidence_frames=[dict(timestamp_sec=2.033,image_file='chosen.jpg',boxes=[])],
                violations=[dict(type='Уход до окончания обслуживания',timecode_sec=2.033,start_sec=1,end_sec=4,
                    description='Кассир покидает место при незавершённом обслуживании.',
                    rule=dict(title='НБРК № 231',section='22',url='https://adilet.zan.kz/rus/docs/V1900019680'),
                    evidence=[dict(evidence_index=0,timestamp_sec=2.033,explanation='Кассир вышел, клиент остаётся.')])])
    monkeypatch.setattr('services.analysis.detector',lambda:Engine())
    return {'X-API-Key':'synthetic-test-key'}


def upload(client,headers):
    return client.post('/api/v1/analyze',headers=headers,data={'file':(io.BytesIO(b'video'),'test.mov')})


def test_jury_flat_contract_binary_verdict_and_selected_base64(client,jury):
    queued=upload(client,jury)
    assert queued.status_code==202 and queued.json['status']=='processing'
    id=queued.json['job_id']
    assert run_next_job()==id
    result=client.get('/api/v1/jobs/'+id,headers=jury).json
    assert result['status']=='done' and result['verdict']=='violation' and 'result' not in result
    v=result['violations'][0]
    assert v['timecode_sec']==v['evidence_frames'][0]['timestamp_sec']==2.033
    with Image.open(io.BytesIO(base64.b64decode(v['evidence_frames'][0]['image_base64']))) as picture:
        assert picture.format == 'JPEG' and picture.size == (12, 12)
        picture.load()
    assert len(v['evidence_frames'])==1 and v['rule']['section']=='22'
    assert 'image_file' not in str(result)


def test_key_cannot_read_private_web_job_and_jwt_does_not_replace_key(client,jury,auth_headers,user1):
    assert upload(client,{}).status_code==401
    assert upload(client,{'X-API-Key':'wrong'}).status_code==401
    assert upload(client,auth_headers).status_code==401
    own=upload(client,jury).json['job_id']
    record=MediaRecord(owner_id=user1.id,original_name='private.mov',storage_key='private.mov',size_bytes=5,content_type='video/quicktime')
    db.session.add(record);db.session.flush()
    private=AnalysisJob(media_id=record.id,camera_profile='full_frame')
    db.session.add(private);db.session.commit()
    assert client.get('/api/v1/jobs/'+private.id,headers=jury).status_code==404
    assert client.get('/api/v1/jobs/'+own,headers=auth_headers).status_code==404
    assert client.get('/api/v1/jobs/'+own,headers={'X-API-Key':'wrong'}).status_code==401


def test_jury_rejects_busy_queue_and_does_not_return_false_clean_on_failure(client,jury,monkeypatch):
    id=upload(client,jury).json['job_id']
    assert upload(client,jury).status_code==429
    class Broken:
        def analyze(self,*args): raise ValueError('Local model failed')
    monkeypatch.setattr('services.analysis.detector',lambda:Broken())
    run_next_job()
    result=client.get('/api/v1/jobs/'+id,headers=jury).json
    assert result['status']=='failed' and 'verdict' not in result


def test_web_uses_same_verdict_and_own_evidence_as_api(client,jury,user1,auth_headers):
    owner=user1.id
    id=upload(client,jury).json['job_id'];run_next_job()
    job=db.session.get(AnalysisJob,id)
    media=db.session.get(MediaRecord,job.media_id)
    # Synthetic transfer for this fixture; actual identities remain separated.
    media.owner_id=owner;db.session.commit()
    web=client.get('/api/v1/jobs/'+id,headers=auth_headers).json['result']
    assert web['verdict']=='violation'
    e=web['violations'][0]['evidence_frames'][0]
    assert e['image_url']==web['evidence_frames'][0]['image_url'] and 'image_file' not in e
    assert client.get(e['image_url']).status_code==200
    listing=client.get('/api/v1/media/'+media.id,headers=auth_headers).json
    assert listing['verdict']=='violation' and len(listing['violations'])==1
