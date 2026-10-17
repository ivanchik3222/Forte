# Бэкенд Forte Control

Flask API для учётных записей, видео, камер, оповещений и справочников. Подключена очередь локального поиска объектов и движений с YOLO11n; запуск worker и контракт — [ML_INTEGRATION.md](../docs/ML_INTEGRATION.md). Загруженное видео имеет статус stored, analysis_status отражает обработку, verdict=null: автоматическое подтверждение нарушений отключено. PostgreSQL используется в production, SQLite поддерживается локально.

- [Запуск, миграция существующей БД и эксплуатация](../docs/RUNBOOK.md)
- [Контракт API](../docs/API_CONTRACT.md)
- [План реализации](../docs/BACKEND_PLAN.md)

Из каталога backend после настройки .env и установки requirements.txt:

```text
python -m flask --app app db upgrade
python -m flask --app app seed-sources
python -m flask --app app create-user --admin
python app.py
```

Команда db upgrade предназначена для пустой или уже версионированной БД. Для прежней users-only схемы используйте процедуру adopt-legacy-db из RUNBOOK после резервного копирования. Импорт приложения не создаёт и не меняет таблицы.

Тесты: `python -m pytest tests -q`. Для полной проверки видео установите ffmpeg/ffprobe. MEDIA_ROOT хранит оригиналы и кадры вне public/static. Доступ к файлам выдаётся только после проверки сессии.
## Swagger / OpenAPI

После установки `pip install -r requirements.txt` и запуска backend:

- Swagger UI: <http://localhost:6767/api/docs/>
- OpenAPI 3.0.3 JSON: <http://localhost:6767/api/openapi.json>

UI и его JS/CSS раздаются backend без CDN. За reverse proxy с префиксом
используйте, например, `/forte/api/docs/` (с завершающим `/`).

Для JWT выполните `POST /api/auth/login` через **Try it out**, затем вставьте
`access_token` в **Authorize → BearerAuth** без префикса `Bearer`.
Refresh-cookie браузер сохранит автоматически; `csrf_token` вставьте в
**CsrfToken** для refresh/logout. После refresh обновите оба значения.
Для публичного API создайте ключ через `POST /api/v1/api-keys`, вставьте его в
**ApiKeyAuth**. Для `/jobs/{job_id}` используйте только один способ авторизации.
Подписанные файлы требуют **SignedToken** из URL соответствующего объекта.

Try it out выполняет реальные запросы, включая загрузку и изменение данных.
Токены не сохраняются Swagger в localStorage. Admin-операции требуют роли
администратора и настроенного MFA в production. При TLS-терминации на proxy
добавьте публичный origin backend в `CORS_ORIGINS` для входа из Swagger.

Контракт описан в `api_docs.py`; при изменении API обновляйте его вместе с
маршрутами. `python -m pytest tests/test_api_docs.py -q` проверяет покрытие
маршрутов, локальные ресурсы и авторизацию. Спецификация не требует миграций БД.
