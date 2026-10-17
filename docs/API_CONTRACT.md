# Контракт API Forte Control

Реализованная версия без ИИ. Базовый URL задаётся через `REACT_APP_API_URL` **без `/api`**, например `http://localhost:6767` или `https://example.com/forte`. В последнем случае reverse proxy снимает `/forte` перед передачей запроса Flask. Демо не вызывает доменные API.

## Сессии и доступ

- `POST /api/auth/login`, JSON `{identifier,password}` → `{user,access_token,csrf_token}`. Refresh JWT возвращается только в HttpOnly cookie. Регистрация доступна в development/test, отключена в production.
- `GET /api/auth/session-csrf` с cookie → `{csrf_token}`. Используется после перезагрузки страницы. Разрешён только origin фронтенда; ответ нельзя кешировать.
- `POST /api/auth/refresh` с cookie и `X-CSRF-TOKEN` → `{user,access_token}`.
- `GET /api/auth/me` с Bearer access → `{data:{user}}`.
- `POST /api/auth/logout` с cookie и `X-CSRF-TOKEN` → отзыв серверной сессии, очистка cookie. Старые access-токены и ссылки этой сессии перестают работать.

Доменные endpoints требуют `Authorization: Bearer <access_token>`, кроме выдачи содержимого по подписи. Сервер проверяет активность пользователя и сессии при каждом запросе. Видео доступны владельцу и текущему администратору. Камеры, события и источники общие для одного рабочего пространства; read-отметки персональные. Изоляция разных организаций/отделений пока не реализована.

Для разных origins клиент передаёт `credentials: include`. Настройки: `CORS_ORIGINS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `AUTH_COOKIE_PATH`. Для публичного префикса `/forte` cookie path должен быть `/forte/api/auth`. В production используется HTTPS и Secure cookie. Разные сайты требуют SameSite=None и Secure; развёртывание на одном сайте предпочтительнее из-за ограничений сторонних cookies браузерами.

## Общие правила

Ошибки: `{error:{code,message}}`. HTTP-коды: 400 — формат запроса/параметры, 401 — сессия, 403 — права/origin, 404 — отсутствующий или чужой объект, 409 — конфликт ключа, 413 — размер, 415 — формат видео, 422 — поля, 429 — лимит, 500 — внутренняя ошибка, 503 — хранилище/ffprobe/анализ недоступны.

Списки: `{items,page,per_page,total}`. `page >= 1`, `per_page` по умолчанию 20, максимум 100. Номер страницы вне диапазона возвращает пустой items. Имена JSON-полей — snake_case. Время — ISO 8601 с UTC-смещением. День событий — `Asia/Almaty`.

## Видео

| Метод и путь | Вход и результат |
| --- | --- |
| GET `/api/v1/capabilities` | `{uploads:true,analysis:false,camera_stream:false,formats:["mov","mp4","webm"],max_file_size:209715200}` |
| POST `/api/v1/media` | Multipart, один `file`, обязательный `Idempotency-Key` до 80 букв/цифр/`-`/`_`. 201 для новой записи, 200 для повтора |
| GET `/api/v1/media` | `search` по имени, `status=all|stored`, `sort=newest|oldest`, page/per_page |
| GET `/api/v1/media/{id}` | Одна запись |
| POST `/api/v1/media/{id}/playback-url` | `{url,expires_in:900}`; url относительный от корня API-сервера |
| GET `/api/v1/media/{id}/content?token=...` | Подписанная выдача; Range → 206, неверный диапазон → 416, `download=1` для скачивания |
| GET `/api/v1/media/{id}/report` | JSON метаданных с `notice`, Content-Disposition attachment |
| POST `/api/v1/analyze` | 503, code=`analysis_unavailable`; задача не создаётся |

Запись имеет форму:

```json
{
  "id": "UUID",
  "file_name": "cash.mov",
  "file_size": 31457280,
  "created_at": "2026-10-17T10:00:00+00:00",
  "duration_sec": 82,
  "status": "stored",
  "analysis_status": "not_requested",
  "verdict": null,
  "violations": []
}
```

`duration_sec` может быть null. Состояния stored/not_requested постоянны для этой версии и вычисляются сериализатором: в БД не создаются фиктивные задания или результаты анализа. Служебные storage_key и owner_id в DTO не раскрываются.

Лимит файла — 200 МиБ; HTTP-body допускает дополнительно 1 МиБ для multipart. Файл проверяется ffprobe по контейнеру и видеопотоку. На пользователя разрешена одна одновременная загрузка и 30 новых записей в час. Повтор ключа сравнивает SHA-256 содержимого и исходного имени; другой файл с тем же ключом → 409. Ключ хранится вместе с записью без автоматического истечения. При потере ответа повторяется тот же ключ. Отмена ожидания в браузере не гарантирует отмену уже сохранённого файла.

Короткая ссылка проверяет подпись, срок, объект, текущую активность владельца сессии и доступ. Она перестаёт работать после logout. В access-логах proxy нельзя сохранять query string с подписью. Исходный JWT в URL не передаётся.

## Камеры и события

| Метод и путь | Вход и результат |
| --- | --- |
| GET `/api/v1/cameras` | Постраничный список `{id,name,location,status,last_seen_at,is_active}` |
| POST `/api/v1/cameras` | Admin: `{name,location,is_active?}` → 201 |
| PATCH `/api/v1/cameras/{id}` | Admin: name/location/is_active → 200. Произвольное выставление online запрещено |
| GET `/api/v1/notifications` | `date=YYYY-MM-DD` (сегодня по умолчанию), `camera_id`, `read=all|new|read`, page/per_page |
| GET `/api/v1/notifications/{id}` | Детали и подписанные URL кадров |
| POST `/api/v1/notifications/read` | `{ids:[...]}`, до 100 ID. Возвращает `{items:[{id,read_at}]}`. Если есть неизвестный ID, весь запрос отклоняется |
| GET `/api/v1/frames/{id}/content?token=...` | JPEG по короткой подписи |

Список уведомлений дополнительно возвращает `counts:{all,new,read}` за выбранный день/камеру, до фильтра read и пагинации. В списках кадры не загружаются; детали возвращают `evidence_frames:[{timestamp_sec,image_url}]`.

Событие: `{id,camera_id,camera_name,location,detected_at,source,read_at,event}`. `event` содержит `type,description,timecode_sec,evidence_frames,rule`; rule nullable, при наличии — `title,section?,url?,explanation?`. `read_at` nullable. `source=test` явно обозначает тестовое событие. Повторная отметка не меняет первое время просмотра. Дедупликация при импорте — source/external_event_id.

Камера без heartbeat имеет `status=unknown`. Непрерывного захвата потока нет. Реальная лента начинается пустой; тестовый импорт выполняется отдельно через CLI и запрещён в production по умолчанию.

## Сводка и источники

- `GET /api/v1/overview?date=YYYY-MM-DD` → `date,today_total,today_read,today_unread,unread_total,camera_total,media_total,recent_alerts,recent_media`. unread_total относится ко всем дням пользователя, media_total — ко всем доступным ему записям. Последние события ограничены 5, видео — 3. Счётчики не зависят от страниц списков.
- `GET /api/v1/sources` → постраничный список `{id,title,number,document_date,url,publisher}`; отсутствующие справочные поля могут быть null.

Фронтенд обновляет сводку и открытую ленту раз в 15 секунд в видимой вкладке; при ошибках увеличивает интервал до 60 секунд. После возврата в окно обновляет сразу. При временной ошибке сохраняет ранее полученные данные и показывает ошибку.
