"""Publish a small, frame-free summary of the native integration batch."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('summary', type=Path)
    args = parser.parse_args()
    report = json.loads(args.summary.read_text(encoding='utf-8'))
    assert report['failed'] == 0 and report['succeeded'] == report['videos']
    target = ROOT/'validation'
    target.mkdir(exist_ok=True)
    (target/'open_integration_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [
        '# Проверка всех видео из open', '',
        'Прогон 17 октября 2026: настоящие рабочие веса YOLO11n, Flask API и отдельная тестовая БД через миграции 0001–0004. Успешно обработаны **%s из %s видео**, ошибок **%s**.' % (report['succeeded'], report['videos'], report['failed']), '',
        '- Источник: `ML/open/open/videos`, %s уникальных видео и 2 дубликата. Каждый файл обработан полностью, без кэша предсказаний.' % report['unique_videos'],
        '- Объём видео: %.3f с (%.2f мин); %s выбранных кадров, %s наблюдаемых интервалов.' % (report['video_seconds'], report['video_seconds']/60, report['frames'], report['events']),
        '- GPU: RTX 4050 Laptop; суммарное время inference и сохранения кадров %.3f с, весь тест %.3f с (включая инициализацию, миграции и запросы).' % (report['inference_seconds'], report['elapsed_seconds']),
        '- Параметры: 2 кадра/с, imgsz=640, conf=0.25, NMS IoU=0.7, профиль `forte_open`, ROI `[0,300,464,610]`.',
        '- SHA-256 весов: `'+report['records'][0]['model_sha256']+'`.', '',
        'Проверены постановка в очередь, настоящий worker, получение результата, возрастающие PTS внутри длительности видео, боксы в исходных координатах, JPEG первого/последнего выбранного кадра, Range оригинала, JSON-экспорт и запрет чтения задачи чужим пользователем. Исходники зарегистрированы локально через hard links: HTTP-загрузка и ffprobe не входят в этот batch и проверяются отдельно тестами backend.', '',
        '**Это функциональный тест, не оценка точности нарушений.** В прогоне есть train/val/test; параметры и веса по его результатам не менялись. Разметка с видеоуровневыми флагами не задаёт истину для каждого бокса или движения. Поэтому accuracy/F1 нарушений не вычисляются. Пустые детекции не означают отсутствие денег или нарушений; найденные интервалы не подтверждают передачу/пересчёт/сокрытие.', '',
        'Полные приватные результаты, БД и кадры: `ML/runs/open_integration_v2/media/analysis/{job_id}`. В Git включён только [сводный JSON](validation/open_integration_summary.json), без изображений и видео. [Запуск и API](../docs/ML_INTEGRATION.md).', '',
        '| Видео | Длительность, с | Кадры | Интервалы | Обработка, с |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for row in report['records']:
        lines.append('| %s | %.3f | %s | %s | %.3f |' % (row['file'], row['duration_sec'], row['frames'], row['events'], row['inference_seconds']))
    (ROOT/'OPEN_VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved OPEN_VALIDATION.md and validation/open_integration_summary.json')


if __name__ == '__main__': main()
