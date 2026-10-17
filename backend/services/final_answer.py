"""The two-verdict jury contract. Observations alone cannot become a decision."""
import base64
import math
from io import BytesIO
from pathlib import Path
from PIL import Image


class DecisionUnavailable(ValueError):
    pass


def final_answer(job_id, report, directory):
    if not isinstance(report,dict) or report.get('classification_complete') is not True or report.get('rule_evaluation') != 'performed':
        raise DecisionUnavailable('Классификация событий и проверка правил ещё не выполнены.')
    violations = report.get('violations')
    if not isinstance(violations, list):
        raise DecisionUnavailable('Отсутствует результат классификации событий.')
    directory = Path(directory).resolve()
    frames = report.get('evidence_frames', [])
    if not isinstance(frames,list):
        raise DecisionUnavailable('Некорректный список кадров.')
    result = []
    for event in violations:
        if not isinstance(event,dict):
            raise DecisionUnavailable('Некорректное событие.')
        sec = event.get('timecode_sec')
        if isinstance(sec, bool) or not isinstance(sec, (int,float)) or not math.isfinite(sec) or sec < 0:
            raise DecisionUnavailable('Некорректный таймкод события.')
        if any(not isinstance(event.get(k),str) or not event[k].strip() for k in ('type','description')):
            raise DecisionUnavailable('Не указан тип или обоснование события.')
        rule = event.get('rule')
        if not isinstance(rule,dict) or any(not isinstance(rule.get(k),str) or not rule[k].strip()
                for k in ('title','section','url','explanation')):
            raise DecisionUnavailable('Не указаны правило и нормативный источник.')
        indices = event.get('evidence_frame_indices')
        if not isinstance(indices,list) or not 1 <= len(indices) <= 3 or any(type(i) is not int for i in indices) or len(set(indices)) != len(indices):
            raise DecisionUnavailable('Для события нужны 1–3 разных кадра-доказательства.')
        evidence = []
        for index in indices:
            if isinstance(index,bool) or not isinstance(index,int) or not 0 <= index < len(frames):
                raise DecisionUnavailable('Кадр события не найден.')
            frame = frames[index]
            if not isinstance(frame,dict) or not isinstance(frame.get('image_file'),str):
                raise DecisionUnavailable('Некорректный кадр.')
            timestamp=frame.get('timestamp_sec')
            if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or timestamp < 0:
                raise DecisionUnavailable('Некорректный таймкод кадра.')
            path = (directory/frame['image_file']).resolve()
            if path.parent != directory or not path.is_file():
                raise DecisionUnavailable('Кадр события недоступен.')
            data = path.read_bytes()
            if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                raise DecisionUnavailable('Кадр должен быть JPEG.')
            try:
                with Image.open(BytesIO(data)) as picture:
                    if picture.format != 'JPEG': raise ValueError('Not JPEG')
                    picture.verify()
            except (OSError,ValueError) as exc:
                raise DecisionUnavailable('JPEG повреждён.') from exc
            evidence.append(dict(timestamp_sec=frame['timestamp_sec'], image_base64=base64.b64encode(data).decode('ascii')))
        if not any(abs(e['timestamp_sec']-sec) <= .001 for e in evidence):
            raise DecisionUnavailable('Таймкод события должен указывать на конкретный кадр-доказательство.')
        result.append(dict(type=event['type'], timecode_sec=sec, description=event['description'],
            evidence_frames=evidence, rule=rule))
    return dict(job_id=job_id,status='done',verdict='violation' if result else 'no_violation',violations=result)
