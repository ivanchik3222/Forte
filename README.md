# Forte: два отдельных проекта

Фронтенд и бэкенд работают на разных URL. Браузер обращается к API напрямую; между проектами нет прокси. Для всего проекта используется один корневой `compose.yaml`.

## Локальная разработка

1. В `backend` скопируйте `.env.example` в `.env`, задайте собственные `SECRET_KEY` и `JWT_SECRET_KEY`, затем выполните `pip install -r requirements.txt` и `python app.py`.
2. В `frontend` выполните `npm ci` и `npm start`.
3. Фронтенд доступен на `http://localhost:3000`, API — на `http://localhost:6767/api`. Для другого адреса API задайте `REACT_APP_API_URL` в `frontend/.env.local`.

Для проверки входа создайте демонстрационную учётную запись через `POST /api/auth/register`.

## Docker

Скопируйте корневой `.env.example` в `.env`, задайте два разных длинных случайных секрета и запустите `docker compose up -d --build`. По умолчанию фронтенд доступен на `http://localhost:8080`, API — на `http://localhost:6767/api`.

На VPS задайте в `/opt/forte/.env` реальные адреса и порты:

```dotenv
BACKEND_PORT=6767
FRONTEND_PORT=8080
REACT_APP_API_URL=https://api.example.com
CORS_ORIGINS=https://app.example.com
SECRET_KEY=...
JWT_SECRET_KEY=...
```

`REACT_APP_API_URL` — публичный URL бэкенда, доступный из браузера. Он встраивается в сборку фронтенда. `CORS_ORIGINS` — точный URL фронтенда без завершающего `/`; для нескольких адресов укажите их через запятую. Настройте хост так, чтобы URL фронтенда вёл на `FRONTEND_PORT`, а URL API — на `BACKEND_PORT`. Если доменов нет, используйте разные порты одного IP и укажите их HTTP URL в этих переменных.

При необходимости из корня можно запустить только одну службу: `docker compose up -d --build backend` или `docker compose up -d --build frontend`. SQLite хранится в Docker volume и сохраняется при обновлении контейнеров.

## Автодеплой из GitHub

[Workflow](.github/workflows/deploy.yml) запускает тесты на pull request и push в `main`. После успешных тестов push в `main` отправляет архив коммита на VPS по SSH и выполняет корневой `docker compose up -d --build --wait`. VPS не нужен доступ к GitHub. Конфигурация рассчитана на `/opt/forte`.

Однократная подготовка VPS:

1. Установите Docker Engine с Compose plugin. SSH-пользователь должен иметь доступ к `docker compose` без `sudo`.
2. Под этим пользователем создайте рабочую папку: `sudo mkdir -p /opt/forte/releases && sudo chown -R "$USER:$USER" /opt/forte`. Создайте `/opt/forte/.env` по корневому `.env.example`, впишите публичные URL и два разных случайных секрета (например, `openssl rand -hex 32`), затем выполните `chmod 600 /opt/forte/.env`.
3. Создайте SSH-ключ для деплоя и добавьте его публичную часть в `~/.ssh/authorized_keys` этого пользователя на VPS.
4. В GitHub репозитории откройте **Settings → Secrets and variables → Actions** и добавьте `VPS_HOST`, `VPS_USER`, `VPS_PORT`, `VPS_SSH_KEY` (полный приватный ключ) и `VPS_KNOWN_HOSTS` (строка из `ssh-keyscan -p PORT HOST` после проверки отпечатка VPS).
5. После push в `main` проверьте GitHub Actions и оба публичных URL. Если изменили `REACT_APP_API_URL`, выполните новый деплой: это значение записывается в JavaScript при сборке.

Файл `.env` остаётся на VPS и не передаётся workflow.
