import base64

import pytest
from PIL import Image

from services.final_answer import DecisionUnavailable, final_answer


def report(directory):
    Image.new('RGB', (16, 16), 'white').save(directory / 'frame.jpg', 'JPEG')
    return dict(
        classification_complete=True,
        rule_evaluation='performed',
        evidence_frames=[dict(timestamp_sec=3.5, image_file='frame.jpg')],
        violations=[dict(
            type='reviewed_event',
            timecode_sec=3.5,
            description='Observed action and its rationale.',
            evidence_frame_indices=[0],
            rule=dict(
                title='Reviewed source',
                section='Section',
                url='https://adilet.zan.kz/rus/docs/V1900019680',
                explanation='Applicability was confirmed by the classifier.',
            ),
        )],
    )


def test_two_verdict_contract_and_actual_base64(tmp_path):
    data = report(tmp_path)
    answer = final_answer('job', data, tmp_path)
    assert answer['status'] == 'done' and answer['verdict'] == 'violation'
    frame = answer['violations'][0]['evidence_frames'][0]
    assert base64.b64decode(frame['image_base64']) == (tmp_path / 'frame.jpg').read_bytes()

    data['violations'] = []
    assert final_answer('job', data, tmp_path) == dict(
        job_id='job', status='done', verdict='no_violation', violations=[])


def test_no_false_negative_from_missing_classifier(tmp_path):
    report_without_classifier = dict(
        verdict='requires_review', violations=[], rule_evaluation='not_performed')
    with pytest.raises(DecisionUnavailable):
        final_answer('job', report_without_classifier, tmp_path)


@pytest.mark.parametrize('mutation', ['no_rule', 'wrong_time', 'too_many_frames', 'path_escape'])
def test_rejects_incomplete_or_irrelevant_evidence(tmp_path, mutation):
    data = report(tmp_path)
    if mutation == 'no_rule':
        data['violations'][0].pop('rule')
    if mutation == 'wrong_time':
        data['violations'][0]['timecode_sec'] = 7
    if mutation == 'too_many_frames':
        data['violations'][0]['evidence_frame_indices'] = [0, 0, 0, 0]
    if mutation == 'path_escape':
        data['evidence_frames'][0]['image_file'] = '../frame.jpg'
    with pytest.raises(DecisionUnavailable):
        final_answer('job', data, tmp_path)
