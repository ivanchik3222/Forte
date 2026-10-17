# Forte: два отдельных проекта

Фронтенд и бэкенд работают на разных URL. Браузер обращается к API напрямую; между проектами нет прокси. Для всего проекта используется один корневой `compose.yaml`.

## Локальная разработка

1. В `backend` скопируйте `.env.example` в `.env`, задайте собственные `SECRET_KEY` и `JWT_SECRET_KEY`, затем выполните `pip install -r requirements.txt` и `python app.py`.
2. В `frontend` выполните `npm ci` и `npm start`.
3. Фронтенд доступен на `http://localhost:3000`, API — на `http://localhost:6767/api`. Для другого адреса API задайте `REACT_APP_API_URL` в `frontend/.env.local`.

Для проверки входа создайте демонстрационную учётную запись через `POST /api/auth/register`.

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
