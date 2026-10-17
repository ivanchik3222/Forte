# Запуск и проверка Forte Control

## Локальная разработка

1. Установить Python 3.11+, Node.js и ffprobe из FFmpeg. [Официальная страница FFmpeg](https://ffmpeg.org/download.html) ссылается на сборки для Windows. Для локального Windows можно задать полный путь `FFPROBE_PATH` в `backend/.env`.
2. Скопировать `backend/.env.example` в `backend/.env`, задать собственные SECRET_KEY и JWT_SECRET_KEY. Установить зависимости: `python -m pip install -r backend/requirements.txt`.
3. Для **пустой** БД из каталога backend выполнить:

```powershell
python -m flask --app app db upgrade
python -m flask --app app seed-demo-user
python -m flask --app app seed-sources
python -m flask --app app create-user --admin
python app.py
```

Пароль команды create-user вводится скрыто; не помещайте его в историю команд. Обычный аккаунт создаётся той же командой без `--admin`.

Тестовый вход: кнопка «Войти в тестовый аккаунт» или email `demo@forte.test`, публичный пароль `ForteDemo2026!`. Docker создаёт аккаунт автоматически после миграций, в том числе на новой БД. Команда `init-db` также создаёт его. `seed-demo-user` можно повторять: она сохраняет ID, записи и существующие сессии, не меняет чужие аккаунты. Тестовый пользователь имеет роль `user`, не может менять свой профиль/пароль или удалять аккаунт; администратор не может повысить его роль до `admin`. Камеры, события и видео эта команда не создаёт.

4. В другом терминале из frontend: `npm ci`, затем `npm start`.
5. Открыть `http://localhost:3000/workspace`, войти созданным аккаунтом. API — `http://localhost:6767`. MOV/MP4/WebM до 200 МиБ сохраняются без анализа. Если ffprobe отсутствует, сервер возвращает понятную ошибку 503 и не создаёт запись.

В development регистрация через `/api/auth/register` доступна. В production она отключена. Рабочий кабинет использует JWT аккаунта; API-ключ ML не требуется. Демо выбирается отдельно на экране входа или в настройках; после перезагрузки приложение возвращается к рабочему режиму.

## Переход с прежней БД

Автоматический create_all удалён. База, содержащая старую таблицу users без alembic_version, не должна проходить обычный db upgrade до принятия baseline.

1. Остановить запись в приложение и сделать резервную копию БД. Для SQLite используйте sqlite backup API или копию закрытой БД; для PostgreSQL — pg_dump. Проверить возможность восстановления копии в отдельную БД.
2. На этой БД выполнить `python -m flask --app app adopt-legacy-db --backup-confirmed`.
3. Команда проверяет, что существует только users и её схема соответствует исходной модели. При расхождении останавливается без stamp. При совпадении ставит baseline 0001 и применяет последующие миграции до текущей версии (0003). Пароли и пользователи сохраняются.
4. Старые JWT больше не действуют: потребуется войти заново, чтобы получить серверную сессию.

Команда не создаёт backup сама. Флаг подтверждает, что восстановимая копия уже подготовлена. На реально используемой БД в рамках разработки этой версии миграция не запускалась.

### Восстановление после `DuplicateTable: relation "users" already exists`

Это сбой запуска миграций при переходе со старого приложения, которое создавало таблицу users через create_all. Образы при этом могут успешно собраться. Для существующего PostgreSQL нужна проверка и принятие исходной схемы командой adopt-legacy-db, затем обычный upgrade. Команда сверяет схему с baseline и сохраняет пользователей и хеши паролей; при расхождениях отказывается от изменений.

Для контейнеров `forte-backend-1` и `forte-postgres-1` из текущего workflow выполнить на VPS:

```bash
(
  set -eu
  umask 077
  cd "$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' forte-backend-1)"
  compose() { docker compose -p forte -f compose.yaml -f compose.production.yaml "$@"; }

  compose stop backend
  mkdir -p /root/Forte/backups
  backup="$(mktemp /root/Forte/backups/forte-before-migrations.dump.XXXXXX)"
  docker exec forte-postgres-1 pg_dump -U forte -d forte -Fc > "$backup"
  test -s "$backup"
  docker exec -i forte-postgres-1 pg_restore --list < "$backup" > /dev/null

  compose run --rm --no-deps --entrypoint flask backend --app app adopt-legacy-db --backup-confirmed
  compose up -d --wait --wait-timeout 180 backend
  compose ps
)
```

Рабочий каталог берётся из метки контейнера: при неудачном деплое ссылка `/root/Forte/current` может указывать на предыдущий релиз. Backend останавливается перед backup, чтобы прервать цикл перезапусков и миграций. Архив получает уникальное имя и права только владельца; проверяется успешность pg_dump и читаемость его каталога. Если команда остановилась, следующие шаги не выполняются. После успешного запуска повторить неудачный deploy job в GitHub Actions, чтобы workflow завершил публикацию и обновил ссылку current.

Воспроизведение на отдельном PostgreSQL 16 проверено: users-only → неудачный db upgrade с DuplicateTable → backup и восстановление архива в другую тестовую БД → adopt-legacy-db → /api/ready=200, пользователь и хеш пароля сохранены. Эта проверка не меняет рабочую БД VPS.

При других причинах unhealthy нужны `docker logs --tail 160 forte-backend-1` и `docker inspect --format '{{json .State.Health}}' forte-backend-1`. Workflow теперь автоматически выводит статус контейнеров, лог backend и результат healthcheck при ошибке deploy, сохраняя исходный код ошибки.

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

Камеры добавляет admin через POST `/api/v1/cameras` с JSON `{name,location}`. Начальный статус unknown. Приём проверок состояния реализован через POST `/api/v1/cameras/{id}/health`; подключение RTSP и автоматические проверки изображения требуют внешнего коллектора.

## Новые страницы: контроль камер и обзор смены

1. Для БД на версии 0002 подготовить резервную копию и выполнить `python -m flask --app app db upgrade` из backend, затем перезапустить backend. Миграция 0003 добавляет три таблицы и сохраняет пользователей, видео, события и read-отметки. `flask --app app db check` проверяет соответствие схеме. Docker entrypoint выполняет upgrade автоматически.
2. Войти администратором, создать камеры через API. Загрузить исходное видео в кабинете: его UUID находится в URL карточки `/analysis/{id}`. Владельцем файла остаётся загрузивший аккаунт. Если всем проверяющим требуется общий доступ к видео, это отдельная модель прав, в текущей версии доступны только собственные записи и доступ admin.
3. Подключить отправку проверок коллектора на `/api/v1/cameras/{id}/health`. Точный JSON и правила порядка описаны в [контракте](API_CONTRACT.md#контроль-наблюдения-миграция-0003). Проверки должны быть чаще 90 секунд, например каждые 30 секунд, и отражать реальное состояние потока/изображения. Простая авторизация или доступность API не подтверждает наблюдение.
4. Передать реальные события с описаниями и таймкодами через POST `/api/v1/events`, указав media_id. Для старых событий можно вызвать PUT `/api/v1/notifications/{id}/recording`. Без ИИ допустимы ручные отметки специалиста (`source=manual`). Времена detected_at должны соответствовать смене, а timecode_sec — началу загруженного файла. Автоматического создания нарушений нет.
5. Открыть `/monitoring`: карточки камер, журнал с фильтрами и пагинацией, суммы перерывов/неизвестности/сниженной видимости. Затем `/shift`: выбрать день/камеру, посмотреть подборку, перейти к контексту и отметить событие просмотренным. Обе страницы обновляются раз в 15 секунд в активной вкладке; смена аккаунта очищает их состояние.

Проверка интеграции: отправить свежий offline, затем несколько offline с интервалом 30 секунд, затем observing. Должен получиться один закрытый интервал. Прекратить проверки более чем на 90 секунд: статус станет unknown, в журнале появится отдельный пробел. После восстановления он сохранится с конечным временем. Выполнять такие искусственные сценарии на тестовой камере, не выдавая их за состояние реального объекта.

Пример приёма ручного события через PowerShell после подготовки камеры и загрузки файла:

```powershell
$taskApi = 'http://localhost:6767'
$taskCredential = Get-Credential -Message 'Аккаунт администратора Forte'
$taskLogin = @{ email=$taskCredential.UserName; password=$taskCredential.GetNetworkCredential().Password } | ConvertTo-Json
$taskSession = Invoke-RestMethod "$taskApi/api/auth/login" -Method Post -ContentType 'application/json' -Body $taskLogin
$taskHeaders = @{ Authorization="Bearer $($taskSession.access_token)" }
$taskEvent = @{
  camera_id='UUID камеры'; media_id='UUID видео'; source='manual'
  external_event_id=[guid]::NewGuid().ToString()
  detected_at=(Get-Date).ToUniversalTime().ToString('o')
  timecode_sec=30; type='Эпизод для проверки'; description='Ручная отметка специалиста'
} | ConvertTo-Json
Invoke-RestMethod "$taskApi/api/v1/events" -Method Post -Headers $taskHeaders -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($taskEvent))
```

В примере заменить UUID, время и описание фактическими данными; видео должно быть длиннее 30 секунд. Ответ содержит созданное событие. Подписи файлов выдаются по запросу плеера, живут 15 минут и отзываются при выходе. Форматы/лимит загрузки прежние: MOV/MP4/WebM до 200 МиБ. Восьмичасовая запись должна укладываться в этот лимит; увеличение лимита и хранение сегментированных потоков — отдельная задача. Отдельного MP4 с монтажом подборки эта версия не создаёт.

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

- 77 backend-тестов на SQLite и те же 77 на отдельном PostgreSQL 16, включая настоящие MOV/MP4/WebM без пропусков. В новых проверках: TTL, слияние/закрытие интервалов, переход суток, пробелы телеметрии, конкурентная доставка, порядок событий, ограничения доступа к записи и персональные read-отметки.
- Миграции пустого PostgreSQL и `db check` без расхождений; отдельно проверены переход users-only PostgreSQL с сохранением пользователя и хеша пароля и обновление 0002 → 0003. На SQLite проверен также downgrade/upgrade новой миграции с сохранением прежних данных.
- 57 frontend-тестов, TypeScript и production build с CI=true. Новые страницы проверены компонентными тестами: запросы API, фильтры, пагинация, отсутствие подмены демоданными, проигрывание/контекст, обновление подписи, ошибка read, сохранение выбранного эпизода при polling и остановка расширения журнала при потере связи.
- HTTP-сценарий на локальном Flask: вход, настоящий MP4, история, детали, Range, JSON, восстановление cookie-сессии, logout и отказ старой подписанной ссылки.
- Отдельный HTTP-сценарий новых функций: миграции, вход, загрузка настоящего MP4 длительностью 20 секунд, проверки offline → observing, закрытый интервал 30 секунд, ручное событие, подборка, Range 206 и сохранённая read-отметка.
- Восстановление тестовой SQLite и media в новую директорию.

Браузерный инструмент не предоставил доступного браузера, поэтому визуальная проверка интерфейса остаётся невыполненной. Docker Engine на этой машине отсутствует: контейнерный запуск, внешний proxy, production backup и деплой на VPS не проверялись. Рабочая БД проекта не изменялась; проверки использовали отдельные временные базы и хранилища.
