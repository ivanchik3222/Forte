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
