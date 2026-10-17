# Forte Control

На Mac полная локальная связка запускается командой
`ML/.venv/bin/python scripts/run_local_pipeline.py`: API и worker автоматически
проверяют загруженное видео банковской моделью и добавляют описания Qwen.
Фронтенд: `cd frontend && npm start`. Веса и окружения должны быть подготовлены;
[настройка и текущий API](docs/ML_INTEGRATION.md).

Рабочий кабинет подключён к API: вход, загрузка видео, история, просмотр оригиналов, оповещения и отметки просмотра. На странице записи доступен локальный поиск объектов и движений: «Наблюдения модели». `docker compose` запускает отдельный ML worker с обученными весами. [Запуск и API](docs/ML_INTEGRATION.md), [проверка всех видео](ML/OPEN_VALIDATION.md). Автоматическая оценка нарушений пока отключена. Страницы `/monitoring` и `/shift` показывают историю проверок камер и обзор событий с видеоконтекстом.

После обновления существующей версии выполните из `backend` команду `python -m flask --app app db upgrade` (миграция 0004). Проверки качества камер и оповещения поступают через API от внешнего источника или специалиста; захват RTSP не подключён. Порядок подключения описан в [RUNBOOK](docs/RUNBOOK.md#новые-страницы-контроль-камер-и-обзор-смены).

[Запуск и переход со старой БД](docs/RUNBOOK.md) · [Контракт API](docs/API_CONTRACT.md) · [План](docs/BACKEND_PLAN.md)

Фронтенд и бэкенд работают на разных URL. Браузер обращается к API напрямую; между проектами нет прокси. Для всего проекта используется один корневой `compose.yaml`.

## Локальная разработка

1. В `backend` скопируйте `.env.example` в `.env`, задайте собственные `SECRET_KEY` и `JWT_SECRET_KEY`, затем выполните `pip install -r requirements.txt`. Для пустой БД: `flask --app app db upgrade`, `flask --app app seed-sources`, `flask --app app create-user --admin`, затем `python app.py`. Для существующей БД сначала выполните переход по RUNBOOK. Для проверки видео требуется ffprobe.
2. В `frontend` выполните `npm ci` и `npm start`.
3. Фронтенд доступен на `http://localhost:3000`, API — на `http://localhost:6767/api`. Для другого адреса API задайте `REACT_APP_API_URL` в `frontend/.env.local`.

Кнопка «Войти в тестовый аккаунт» доступна на `/login`, при входе в `/workspace` и в модальных формах входа. Она авторизует общего пользователя `demo@forte.test` с публичным паролем `ForteDemo2026!` и открывает рабочий кабинет с реальным API. Это обычный пользователь без прав администратора; его записи общие для всех посетителей этого аккаунта.

Docker автоматически выполняет `flask --app app seed-demo-user` после миграций при каждом запуске backend. Пользователь появляется и после пересоздания БД; повторный запуск сохраняет его ID и данные. При локальном запуске выполните `flask --app app init-db` или после `db upgrade` выполните `flask --app app seed-demo-user`. Профиль и пароль общего аккаунта защищены от изменения посетителями.

Личные аккаунты создаются командой `flask --app app create-user`; публичная регистрация в production отключена. Демонстрация интерфейса с готовыми примерами доступна отдельно без входа; тестовый аккаунт сам по себе не создаёт камеры, события или видео.

## Docker

Скопируйте корневой `.env.example` в `.env`, задайте два разных длинных случайных секрета и запустите `docker compose up -d --build`. По умолчанию фронтенд доступен на `http://localhost:3000`, API — на `http://localhost:6767/api`.

На VPS задайте в `/root/Forte/.env` реальные адреса и порты:

```dotenv
BACKEND_PORT=6767
FRONTEND_PORT=3000
REACT_APP_API_URL=https://foodtrack.beast-inside.kz/forte
CORS_ORIGINS=https://foodtrack.beast-inside.kz
SECRET_KEY=...
JWT_SECRET_KEY=...
```

`REACT_APP_API_URL` — базовый публичный адрес API без `/api`: клиент сам добавляет пути вида `/api/auth/login`. Для этого сайта можно также указать относительный адрес `/forte`. Значение встраивается в сборку фронтенда, поэтому после его изменения фронтенд нужно пересобрать. `CORS_ORIGINS` — точный URL фронтенда без завершающего `/`; для нескольких адресов укажите их через запятую. Настройте хост так, чтобы URL фронтенда вёл на `FRONTEND_PORT`, а URL API — на `BACKEND_PORT`. Если доменов нет, используйте разные порты одного IP и укажите их HTTP URL в этих переменных.

На VPS добавьте в `/root/Forte/.env` переменную `POSTGRES_PASSWORD` со случайным паролем. Серверный запуск использует `docker compose -p forte -f compose.yaml -f compose.production.yaml up -d --build --wait`: PostgreSQL работает в отдельном контейнере на VPS, данные хранятся в Docker volume `forte_postgres_data`, наружу порт базы не открыт. Локальный `docker compose up` и `python app.py` по-прежнему используют SQLite. Для серверного запуска всегда указывайте оба compose-файла.

При локальной разработке из корня можно запустить только одну службу: `docker compose up -d --build backend` или `docker compose up -d --build frontend`. Локальная SQLite хранится в Docker volume и сохраняется при обновлении контейнеров.

## Автодеплой из GitHub

[Workflow](.github/workflows/deploy.yml) запускает тесты на pull request и push в `main`. После успешных тестов push в `main` отправляет архив коммита на VPS по SSH и запускает Compose с `compose.yaml` и `compose.production.yaml`. VPS не нужен доступ к GitHub. Конфигурация рассчитана на `/root/Forte`: архивы коммитов размещаются в `releases/`, а общие настройки берутся из `.env` в корне.

Однократная подготовка VPS:

1. Установите Docker Engine с Compose plugin. Workflow подключается по SSH к `root`, поэтому в секрете `VPS_USER` укажите `root`; вход по ключу для этого пользователя должен быть разрешён.
2. В существующем `/root/Forte` создайте папку `releases`: `mkdir -p /root/Forte/releases`. Создайте `/root/Forte/.env` по корневому `.env.example`, впишите публичные URL и два разных случайных секрета (например, `openssl rand -hex 32`), затем выполните `chmod 600 /root/Forte/.env`.
3. Создайте SSH-ключ для деплоя и добавьте его публичную часть в `/root/.ssh/authorized_keys` на VPS.
4. В GitHub репозитории откройте **Settings → Secrets and variables → Actions** и добавьте `VPS_HOST`, `VPS_USER`, `VPS_PORT`, `VPS_SSH_KEY` (полный приватный ключ) и `VPS_KNOWN_HOSTS` (строка из `ssh-keyscan -p PORT HOST` после проверки отпечатка VPS).
5. После push в `main` проверьте GitHub Actions и оба публичных URL. Если изменили `REACT_APP_API_URL`, выполните новый деплой: это значение записывается в JavaScript при сборке.

Файл `.env` остаётся на VPS и не передаётся workflow.
