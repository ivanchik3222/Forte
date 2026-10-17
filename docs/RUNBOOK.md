# Запуск и проверка Forte Control

## Локальная разработка

1. Установить Python 3.11+, Node.js и ffprobe из FFmpeg. [Официальная страница FFmpeg](https://ffmpeg.org/download.html) ссылается на сборки для Windows. Для локального Windows можно задать полный путь `FFPROBE_PATH` в `backend/.env`.
2. Скопировать `backend/.env.example` в `backend/.env`, задать собственные SECRET_KEY и JWT_SECRET_KEY. Установить зависимости: `python -m pip install -r backend/requirements.txt`.
3. Для **пустой** БД из каталога backend выполнить:

```powershell
python -m flask --app app db upgrade
python -m flask --app app seed-sources
python -m flask --app app create-user --admin
python app.py
```

Пароль команды create-user вводится скрыто; не помещайте его в историю команд. Обычный аккаунт создаётся той же командой без `--admin`.

4. В другом терминале из frontend: `npm ci`, затем `npm start`.
5. Открыть `http://localhost:3000/workspace`, войти созданным аккаунтом. API — `http://localhost:6767`. MOV/MP4/WebM до 200 МиБ сохраняются без анализа. Если ffprobe отсутствует, сервер возвращает понятную ошибку 503 и не создаёт запись.

В development регистрация через `/api/auth/register` доступна. В production она отключена. Рабочий кабинет использует JWT аккаунта; API-ключ ML не требуется. Демо выбирается отдельно на экране входа или в настройках; после перезагрузки приложение возвращается к рабочему режиму.

## Переход с прежней БД

Автоматический create_all удалён. База, содержащая старую таблицу users без alembic_version, не должна проходить обычный db upgrade до принятия baseline.

1. Остановить запись в приложение и сделать резервную копию БД. Для SQLite используйте sqlite backup API или копию закрытой БД; для PostgreSQL — pg_dump. Проверить возможность восстановления копии в отдельную БД.
2. На этой БД выполнить `python -m flask --app app adopt-legacy-db --backup-confirmed`.
3. Команда проверяет, что существует только users и её схема соответствует исходной модели. При расхождении останавливается без stamp. При совпадении ставит baseline 0001 и применяет 0002. Пароли и пользователи сохраняются.
4. Старые JWT больше не действуют: потребуется войти заново, чтобы получить серверную сессию.

Команда не создаёт backup сама. Флаг подтверждает, что восстановимая копия уже подготовлена. На реально используемой БД в рамках разработки этой версии миграция не запускалась.

## Docker и production

Из корня: `docker compose up -d --build`. Для production: `docker compose -p forte -f compose.yaml -f compose.production.yaml up -d --build --wait`.

Entrypoint применяет миграции и заполняет справочник источников перед запуском Gunicorn. У уже существующей БД сначала выполните переход выше через одноразовый контейнер, например `docker compose -p forte -f compose.yaml -f compose.production.yaml run --rm --entrypoint flask backend --app app adopt-legacy-db --backup-confirmed` после подготовки backup.

В production используются PostgreSQL и постоянный `media_data` volume. БД и видео должны сохраняться вместе между релизами. Не запускайте `docker compose down -v`, если данные нужны. Миграции запускаются один раз до workers; для нескольких API-контейнеров потребуется отдельная migration job.

Для HTTPS production задаются CORS_ORIGINS и REACT_APP_API_URL фактического фронтенда/API. Compose production включает Secure cookie. При API по адресу `/forte` задайте `AUTH_COOKIE_PATH=/forte/api/auth`; proxy должен снимать префикс перед передачей Flask. Frontend не проксирует API. Для локального HTTP в корневом .env используется COOKIE_SECURE=false.

Внешний reverse proxy должен принимать body не меньше 201 МиБ и не обрывать загрузку раньше Gunicorn (600 секунд). Пример параметров nginx в существующем location API:

```nginx
client_max_body_size 201m;
client_body_timeout 600s;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
```

Не журналируйте query string на `/content`: он содержит короткую подпись доступа. Для access_log используйте формат с `$uri`, а не `$request`/`$request_uri`. Сервис разработки Flask предназначен только для локальной проверки.

Проверка готовности — `/api/ready`: обращается к доменной таблице БД. `/api` проверяет только жизнь процесса. Схема БД проверяется `flask --app app db check`; свободное место хранилища проверяется при загрузке.

## Камеры и тестовые события

Камеры добавляет admin через POST `/api/v1/cameras` с JSON `{name,location}`. Начальный статус unknown. Отправка heartbeat и подключение RTSP пока не реализованы.

В development из backend: `python -m flask --app app import-test-events tests/fixtures/events.json`. Повтор команды не дублирует событие. Если detected_at отсутствует, берётся время первого импорта. В интерфейсе событие обозначено как тестовое. В fixture можно добавить frames с `path` к JPEG в том же каталоге и `timestamp_sec`. В production команда запрещена по умолчанию; автоматического создания событий нет.

`flask --app app cleanup-media` показывает осиротевшие/временные файлы старше суток. `--apply` удаляет только такие файлы внутри настроенного MEDIA_ROOT. Действующие media_records и evidence_frames сохраняются, симлинки и lock-файлы пропускаются. Периодичность запуска определяется эксплуатацией.

## Резервная копия и восстановление

На время согласованного backup остановить API и импорт событий. Сохранить дамп PostgreSQL либо SQLite backup, а также media volume и защищённые настройки окружения. После копирования API можно запускать. Для восстановления использовать отдельные пустые БД и media directory/volume, восстановить оба компонента, применить миграции и проверить историю, метаданные и выдачу файла. Перезапись рабочей БД не является частью проверки.

Локальный автоматический тест проверяет восстановление связанного набора SQLite + media в отдельную директорию. Производственный backup PostgreSQL и восстановление Docker volumes должны дополнительно проверяться на сервере с его фактической конфигурацией.

## Автоматические проверки

```powershell
python -m pytest backend/tests -q
cd frontend
$env:CI='true'
npm test -- --watchAll=false --runInBand
npx tsc --noEmit
npm run build
```

Тест настоящих контейнеров использует ffmpeg и ffprobe из PATH либо переменные TEST_FFMPEG и FFPROBE_PATH. Он пропускается, если бинарники отсутствуют; это явно видно в отчёте pytest. Остальные upload-тесты подменяют только технический probe, проверяя реальное сохранение, HTTP и БД.

CI содержит отдельную PostgreSQL 16 службу: upgrade, проверка отсутствия расхождений схемы, API-тесты. TEST_DATABASE_URL предназначен **только для отдельной тестовой БД**: тесты создают и удаляют таблицы. После успешных CI-проверок существующий workflow по push в main запускает деплой; в рамках этой работы push и деплой не выполняются.

## Результаты проверки реализации

17 октября 2026 года выполнены:

- 52 backend-теста на SQLite и те же 52 на отдельном PostgreSQL 16, включая настоящие MOV/MP4/WebM без пропусков.
- Миграции пустого PostgreSQL и `db check` без расхождений; отдельно проверен переход users-only PostgreSQL с сохранением пользователя и хеша пароля.
- 34 frontend-теста, TypeScript и production build с CI=true.
- HTTP-сценарий на локальном Flask: вход, настоящий MP4, история, детали, Range, JSON, восстановление cookie-сессии, logout и отказ старой подписанной ссылки.
- Восстановление тестовой SQLite и media в новую директорию.

Браузерный инструмент не предоставил доступного браузера, поэтому визуальная проверка интерфейса остаётся невыполненной. Docker Engine на этой машине отсутствует: контейнерный запуск, внешний proxy, production backup и деплой на VPS не проверялись. Рабочая БД проекта не изменялась; проверки использовали отдельные временные базы и хранилища.
