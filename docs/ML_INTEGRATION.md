# Локальный анализ видео

Подключена основная обученная YOLO11n: `ML/deployment/cash_detector.pt`, SHA-256 `be1ff4056ffd36fea226fca6c0beb3cbd5f84bfc2bff34a673934e406ba2ec4f`. Веса включены в Git (около 5,5 МиБ), карточка модели, лицензия и атрибуция лежат рядом. Исходные видео, кадры, исследовательские веса, `.env` и ключи в Git не отправляются.

После загрузки записи появился блок «Наблюдения модели»: выбор профиля, запуск, статус очереди, кадры с боксами, интервалы и переход к времени оригинала. Полный JSON скачивается существующей кнопкой. История отличает готовые наблюдения от записей без анализа. Детектор и эвристики движения не обучены определять последовательность кассовых операций. `rules.json` остаётся с выключенными автоматическими правилами.

## Запуск

`docker compose up -d --build` поднимает API, фронтенд и отдельный `ml-worker`. В production используется также `compose.production.yaml`; worker получает тот же PostgreSQL и том видео, что и API. Сборка worker устанавливает CPU PyTorch; локальный CUDA venv сохранён. GPU в Docker этим изменением не настраивается.

Для локального Windows-запуска сначала из корня:

```powershell
ML/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -r ML/requirements-inference.txt
```

Из папки `backend`:

```powershell
../ML/.venv/Scripts/python.exe -m flask --app app db upgrade
../ML/.venv/Scripts/python.exe -m flask --app app run --port 6767
# В другом терминале, тоже из backend:
../ML/.venv/Scripts/python.exe -m flask --app app analysis-worker
```

В третьем терминале, из `frontend`: `npm.cmd ci`, затем `npm.cmd start`. Перед запуском задайте настройки по `backend/.env.example`; для проверки контейнера при загрузке нужен `ffprobe` в PATH или `FFPROBE_PATH`. `ML/.env` с ключом Roboflow worker не читает. Для новой установки PyTorch сначала выбрать CPU/CUDA по [ML/README.md](../ML/README.md).

Настройки: `ML_ENABLED` (по умолчанию true), `ML_WEIGHTS` (локальный путь, автоматической загрузки нет), `ML_DEVICE` (`cpu` или `0`; локально выбирается CUDA при наличии). `ML_ENABLED=false` отключает постановку задач. Наличие файла весов определяет `capabilities.analysis`; это не проверка здоровья worker. Если worker остановлен, задачи остаются в очереди. Диагностика: `docker compose logs ml-worker`.

## API

JSON-запросы используют существующую JWT-сессию и доступ к записи (владелец/администратор).

| Метод | Путь | Результат |
| --- | --- | --- |
| POST | `/api/v1/media/{id}/analyze` | `{camera_profile:"forte_open"|"full_frame"}` → 202 с задачей; повтор → 200 |
| GET | `/api/v1/media/{id}/analysis` | Задача записи или `null` |
| GET | `/api/v1/jobs/{job_id}` | `queued`, `processing`, `done` или `failed` |
| GET | `/api/v1/jobs/{job_id}/evidence/{index}?token=...` | JPEG по подписанной ссылке из результата |
| GET | `/api/v1/media/{id}/report` | Метаданные и полный результат с кадрами, боксами и интервалами |

Завершённая задача содержит `result.verdict="requires_review"`, `violations=[]`, `rule_evaluation="not_performed"`, `frames`, `events`, `evidence_frames`, SHA модели и параметры. `mean_detector_confidence` описывает уверенность детектора, не вероятность нарушения. Отсутствие денег в детекциях означает неизвестную видимость. На карточке записи `verdict` остаётся `null`; `analysis_status` отражает состояние задачи.

`forte_open` требует исходные 464×848 и использует ROI `[0,300,464,610]`; для другой камеры выбирается `full_frame`, качество переноса не проверено. Обработка: реальные PTS, 2 кадра/с, imgsz=640, conf=0.25, NMS IoU=0.7. Эти параметры зафиксированы до прогона всех видео. Верхняя часть кадра в native-профиле не анализируется; шкаф может частично обрезаться.

Задачи хранятся в таблице `analysis_jobs` (миграция `0004`). Один worker держит общий файловый lock на всё время обработки; используется одна загруженная модель. Ограничение очереди — 20 активных задач; 429 требует повторить запрос позже. Для одной записи сохраняется одна задача; запрос другого профиля после успешного анализа возвращает 409. Ошибочную задачу можно повторить. При рестарте старая processing-задача помечается failed после 390 секунд от старта. Внутренний лимит анализа — 300 секунд с проверкой между кадрами. Для очереди и декодирования больших файлов SLA не установлен.

Кадры хранятся в приватном `MEDIA_ROOT/analysis/{job_id}`. Ссылки действуют 15 минут, проверяют доступ и отзыв сессии. На странице есть обновление ссылок. Существующий endpoint `/api/v1/analyze`, предполагавший классификацию нарушений, остаётся недоступным; для наблюдений используется новый контракт выше.

## Проверка исходных видео

Из корня: `ML/.venv/Scripts/python.exe ML/validate_open_integration.py --output ML/runs/open_integration_new`.

Скрипт создаёт отдельную SQLite через миграции, регистрирует локальные файлы с hard links (при недоступности копирует), вызывает настоящий enqueue API, worker с рабочими весами, статус, выдачу JPEG, Range оригинала и экспорт отчёта. Чужая учётная запись не получает задачу. В этом скрипте HTTP-загрузка/ffprobe не проверяются: они проверяются отдельно тестами backend. Все видео проходят inference, включая два дубликата; кэш предсказаний не используется. Это функциональный тест на train/val/test вместе, не независимая оценка точности. Результаты — [ML/OPEN_VALIDATION.md](../ML/OPEN_VALIDATION.md).

В CI добавлен CPU smoke test с настоящими весами на синтетическом видео; тесты API не требуют установки PyTorch. Локальный smoke: `ML/.venv/Scripts/python.exe ML/smoke_inference.py`.

Проверена также настоящая multipart-загрузка `X-1.mov` через Flask test client → ffprobe → очередь → модель → кадры/JSON: 52 кадра, 12 интервалов, без ошибок. Команда: `ML/.venv/Scripts/python.exe ML/validate_open_integration.py --http-upload --limit 1 --ffprobe ML/cache/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe --output ML/runs/http_upload_smoke_new`. Для полного HTTP-прогона убрать `--limit 1`. Флаг лимита загрузок изменяется только в изолированном batch-приложении.

Для этой локальной проверки FFmpeg/ffprobe 9.0.2 скачаны в `ML/cache/ffmpeg` из [сборки Gyan](https://www.gyan.dev/ffmpeg/builds/), на которую ссылается [FFmpeg](https://ffmpeg.org/download.html). SHA-256 архива проверен по опубликованному checksum. Кэш в Git не включается. Проверки: 90 backend-тестов и отдельно 3 проверки настоящих MOV/MP4/WebM (первоначально пропущены без ffprobe), 66 frontend-тестов, 25 ML-тестов, TypeScript, production build, CPU inference smoke. Оба Compose-конфига проверены; Docker-контейнеры здесь не запускались, локальный Docker daemon недоступен.
