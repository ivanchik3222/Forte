# Flask Backend Template

Базовый шаблон Flask-бэкенда (вынесен из проекта FoodTrack). Из коробки: JWT-авторизация, модель пользователя, админ-эндпоинты, тесты, Docker.

## Что внутри

```
flask-template/
├── app.py                  # Фабрика приложения, error handlers, CLI-команды
├── config.py               # Config / Development / Testing / Production
├── models.py               # db + модель User
├── routes/
│   ├── auth.py             # register, login, refresh, me, profile,
│   │                       # change/forgot/reset password, verify-email,
│   │                       # deactivate, delete
│   └── admin.py            # список пользователей, смена роли/статуса
├── services/               # бизнес-логика (пусто, добавляй свои сервисы)
├── utils/
│   ├── decorators.py       # @admin_required
│   └── request_helpers.py  # IP клиента, парсинг User-Agent
├── tests/
│   ├── conftest.py         # фикстуры: app, client, create_user, auth_headers...
│   └── test_auth.py        # тесты auth + admin
├── database/               # SQLite здесь (в git не попадает)
├── Dockerfile / entrypoint.sh
├── requirements.txt
└── .env.example
```

## Быстрый старт

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env         # и заполнить секреты

python app.py                  # http://localhost:6767/api
```

Тесты:

```bash
pytest tests/ -v
```

Создать администратора:

```bash
flask create-admin
```

Docker (из корня всего проекта, после настройки корневого `.env`):

```bash
docker compose up -d --build backend
```

## API

| Метод | URL | Описание |
|---|---|---|
| POST | `/api/auth/register` | Регистрация (email / nickname / identifier + password) |
| POST | `/api/auth/login` | Вход, возвращает access + refresh токены |
| POST | `/api/auth/refresh` | Обновление access-токена (refresh-токен в заголовке) |
| GET | `/api/auth/me` | Текущий пользователь |
| PUT | `/api/auth/profile` | Обновление full_name / nickname |
| POST | `/api/auth/change-password` | Смена пароля |
| POST | `/api/auth/forgot-password` | Запрос сброса пароля (отправка email — TODO) |
| POST | `/api/auth/reset-password` | Сброс пароля по токену |
| POST | `/api/auth/verify-email` | Подтверждение email по токену |
| POST | `/api/auth/deactivate` | Деактивация аккаунта (с паролем) |
| DELETE | `/api/auth/deactivate` | Полное удаление аккаунта |
| GET | `/api/admin/users` | Список пользователей (пагинация, поиск) — только admin |
| PATCH | `/api/admin/users/<id>` | Смена is_active / is_verified / user_type — только admin |

## Как расширять

**Новая модель** — добавь класс в `models.py` (или разбей на пакет `models/`), связи на User вешай через `db.relationship(..., cascade='all, delete-orphan')`.

**Новый блюпринт** — файл в `routes/`, экспорт в `routes/__init__.py`, регистрация в `app.py`:

```python
app.register_blueprint(items_bp, url_prefix='/api/items')
```

**Бизнес-логика** — в `services/` (не забывай, что `services/__init__.py` должен существовать).

**Миграции** — Flask-Migrate уже подключён:

```bash
flask db init && flask db migrate -m "..." && flask db upgrade
```

## Что осталось в FoodTrack (бери оттуда при необходимости)

- **OAuth** (Google/GitHub/Apple/Telegram) — `routes/oauth.py` + `services/oauth_service.py` + поля oauth_* в User
- **WebAuthn / биометрия** — `routes/webauthn.py`
- **WebSocket** (flask-sock) — `services/websocket_service.py` + `@sock.route` в `app.py`
- **Web Push** (pywebpush, VAPID) — `services/push_service.py` + CLI `generate-vapid`
- **Планировщик** (APScheduler) — `services/scheduler_service.py`
- **Аудит-лог входов** — `services/auth_logger.py` + модель `AuditLog`
