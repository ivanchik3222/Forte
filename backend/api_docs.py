"""OpenAPI contract and locally served Swagger UI (no CDN required)."""
import re

from flask import Blueprint, jsonify, render_template, send_from_directory
from swagger_ui_bundle import swagger_ui_path


docs_bp = Blueprint('api_docs', __name__)


def obj(properties=None, required=(), **kwargs):
    schema = dict(type='object', properties=properties or {}, **kwargs)
    if required:
        schema['required'] = list(required)
    return schema


def string(**kwargs):
    return dict(type='string', **kwargs)


def array(items, **kwargs):
    return dict(type='array', items=items, **kwargs)


def ref(name):
    return {'$ref': f'#/components/schemas/{name}'}


def parameter(name, schema=None, location='query', required=False, description=''):
    return dict(name=name, schema=schema or string(), **{'in': location},
                required=required, description=description)


def response(schema, description='Успешный ответ', media_type='application/json'):
    return dict(description=description, content={media_type: {'schema': schema}})


def build_spec():
    boolean = {'type': 'boolean'}
    integer = {'type': 'integer'}
    number = {'type': 'number', 'minimum': 0}
    date_time = string(format='date-time')
    nullable_time = string(format='date-time', nullable=True)
    schemas = {
        'Error': obj({'error': obj({'code': string(), 'message': string()}, ('code', 'message'))}, ('error',)),
        'Message': obj({'message': string()}),
        'User': obj({'id': integer, 'email': string(nullable=True), 'nickname': string(nullable=True),
                     'full_name': string(nullable=True), 'user_type': string(enum=['user', 'admin']),
                     'is_active': boolean, 'is_verified': boolean, 'created_at': date_time,
                     'last_login': nullable_time}),
        'Session': obj({'user': ref('User'), 'access_token': string(), 'csrf_token': string()}),
        'Media': obj({'id': string(), 'file_name': string(), 'file_size': integer,
                      'duration_sec': dict(number, nullable=True), 'created_at': date_time,
                      'status': string(enum=['stored']), 'analysis_status': string(enum=[
                          'not_requested', 'queued', 'processing', 'done', 'failed']),
                      'verdict': string(nullable=True, description='Сейчас всегда null.'),
                      'violations': array(obj(), description='Сейчас пустой список.')}),
        'Camera': obj({'id': string(), 'name': string(), 'location': string(), 'status': string(),
                       'health_status': string(), 'last_seen_at': nullable_time, 'is_active': boolean}),
        'Alert': obj({'id': string(), 'camera_id': string(), 'camera_name': string(),
                      'location': string(), 'detected_at': date_time, 'source': string(),
                      'read_at': nullable_time, 'recording': obj({'media_id': string(),
                          'duration_sec': dict(number, nullable=True)}, nullable=True),
                      'event': obj({'type': string(), 'description': string(), 'timecode_sec': number,
                          'rule': obj(nullable=True), 'evidence_frames': array(obj({
                              'timestamp_sec': number, 'image_url': string()}))})}),
        'Job': obj({'job_id': string(), 'media_id': string(),
                    'status': string(enum=['queued', 'processing', 'done', 'failed']),
                    'camera_profile': string(enum=['full_frame', 'forte_open']),
                    'created_at': date_time, 'started_at': nullable_time, 'finished_at': nullable_time,
                    'error': string(nullable=True), 'result': obj(nullable=True,
                        description='Исходный отчёт модели; включает вердикт, если движок его сформировал.')},
                    ('job_id', 'media_id', 'status', 'result')),
        'EvidenceFrame': obj({'timestamp_sec': number, 'image_base64': string(format='byte',
            description='Полный JPEG в base64 без data-URI.')}, ('timestamp_sec', 'image_base64')),
        'Violation': obj({'type': string(minLength=1), 'description': string(minLength=1),
            'timecode_sec': number, 'evidence_frames': array(ref('EvidenceFrame'), minItems=1, maxItems=3),
            'rule': obj(nullable=True), 'classification_status': string()},
            ('type', 'timecode_sec', 'description', 'evidence_frames')),
        'ApiJobProcessing': obj({'job_id': string(), 'status': string(enum=['processing'])}, ('job_id', 'status')),
        'ApiJobDone': obj({'job_id': string(), 'status': string(enum=['done']),
            'verdict': string(enum=['violation', 'no_violation']), 'violations': array(ref('Violation')),
            'coverage_status': string(), 'decision_scope': string(), 'rule_evaluation': string()}, ('job_id', 'status', 'verdict', 'violations')),
        'ApiJobFailed': obj({'job_id': string(), 'status': string(enum=['failed']),
            'error': obj({'code': string(), 'message': string()}, ('code', 'message'))}, ('job_id', 'status', 'error')),
        'PublicJob': {'oneOf': [ref('ApiJobProcessing'), ref('ApiJobDone'), ref('ApiJobFailed')]},
        'Branch': obj({'id': string(), 'name': string()}),
        'Access': obj({'branch_ids': array(string(), maxItems=1000),
                       'camera_ids': array(string(), maxItems=1000)}, ('branch_ids', 'camera_ids'),
                      additionalProperties=False),
    }
    paths = {}

    def add(method, path, summary, tag, result=None, body=None, required=True,
            security=None, params=(), codes=(200,), description='', multipart=False):
        operation = dict(summary=summary, tags=[tag],
                         operationId=method + '_' + re.sub(r'[^a-zA-Z0-9]+', '_', path).strip('_'),
                         security=[{'BearerAuth': []}] if security is None else security,
                         responses={str(code): ({'description': 'Без тела ответа'} if code == 204 else
                                    response(result if result is not None else obj())) for code in codes})
        operation['responses']['default'] = response(ref('Error'), 'Ошибка: code и message; 400/401/403/404/409/413/415/422/429/500/503 в зависимости от операции.')
        if description:
            operation['description'] = description
        parameters = [parameter(name, integer if name in ('user_id', 'index') else string(),
                                'path', True) for name in re.findall(r'{(\w+)}', path)] + list(params)
        if parameters:
            operation['parameters'] = parameters
        if body is not None:
            operation['requestBody'] = dict(required=required, content={
                'multipart/form-data' if multipart else 'application/json': {'schema': body}})
        paths.setdefault(path, {})[method] = operation
        return operation

    def paged(item):
        return obj({'items': array(item), 'page': integer, 'per_page': integer, 'total': integer})

    schemas['MonitoringSummary'] = obj({'problems': integer, 'unknown': integer,
        'unavailable_minutes': number, 'unknown_minutes': number, 'degraded_minutes': number})
    schemas['Incident'] = obj({'id': string(), 'cameraId': string(), 'mode': string(),
        'kind': string(), 'startedAt': date_time, 'endedAt': nullable_time, 'duration_sec': number})
    schemas['Monitoring'] = obj({'date': string(format='date'), 'as_of': date_time,
        'ttl_seconds': integer, 'cameras': array(ref('Camera')), 'summary': ref('MonitoringSummary'),
        'signals': {'type': 'object', 'additionalProperties': obj({'cameraId': string(),
            'mode': string(), 'status': string(), 'checkedAt': nullable_time, 'source': string(nullable=True)})},
        'incidents': paged(ref('Incident'))})
    schemas['Shift'] = obj({'date': string(format='date'), 'total': integer,
        'episodes': array(ref('Alert'), maxItems=6), 'cameras': array(ref('Camera')),
        'incidents': array(ref('Incident')), 'monitoring_summary': ref('MonitoringSummary'),
        'as_of': date_time, 'selection': string(enum=['latest_six']), 'max_duration_sec': number})
    schemas['Overview'] = obj({'date': string(format='date'), 'monitoring_summary': ref('MonitoringSummary'),
        **{key: integer for key in ('today_total', 'today_read', 'today_unread', 'unread_total', 'camera_total', 'media_total')},
        'recent_alerts': array(ref('Alert')), 'recent_media': array(ref('Media'))})

    pagination = [parameter('page', dict(integer, minimum=1, default=1)),
                  parameter('per_page', dict(integer, minimum=1, maximum=100, default=20))]
    day = [parameter('date', string(format='date'), description='По умолчанию сегодня, Asia/Almaty.'),
           parameter('camera_id')]
    add('get', '/api', 'Проверка API', 'Система', obj({'message': string(), 'version': string()}), security=[])
    add('get', '/api/ready', 'Готовность БД', 'Система', obj({'ready': boolean}), security=[])
    credentials = {'identifier': string(example='user@example.com'), 'email': string(format='email'),
                   'nickname': string(), 'password': string(format='password'), 'otp': string()}
    login = obj(credentials, ('password',), anyOf=[{'required': [key]} for key in ('identifier', 'email', 'nickname')])
    add('post', '/api/auth/login', 'Войти', 'Авторизация', ref('Session'), login, security=[],
        description='Укажите identifier, email или nickname и пароль. OTP нужен при настроенном MFA. Refresh JWT устанавливается в HttpOnly cookie. Скопируйте access_token в Authorize → BearerAuth, csrf_token → CsrfToken.')
    registration = obj({key: value for key, value in credentials.items() if key != 'otp'}, ('password',),
                       anyOf=[{'required': [key]} for key in ('identifier', 'email', 'nickname')])
    registration['properties']['password'] = string(format='password', minLength=12, maxLength=128)
    registration['properties']['full_name'] = string()
    add('post', '/api/auth/register', 'Регистрация', 'Авторизация', ref('Session'), registration,
        security=[], codes=(201,), description='В production регистрация отключена по умолчанию.')
    add('get', '/api/auth/session-csrf', 'Получить CSRF текущей сессии', 'Авторизация',
        obj({'csrf_token': string()}), security=[{'RefreshCookie': []}])
    for action in ('refresh', 'logout'):
        add('post', '/api/auth/' + action, 'Обновить сессию' if action == 'refresh' else 'Выйти',
            'Авторизация', ref('Session' if action == 'refresh' else 'Message'),
            security=[{'RefreshCookie': [], 'CsrfToken': []}],
            description='Cookie браузер передаёт после login. X-CSRF-TOKEN берётся из session-csrf или login. После refresh обновите BearerAuth и CsrfToken значениями нового ответа.')
    add('get', '/api/auth/me', 'Текущий пользователь', 'Авторизация', obj({'data': obj({'user': ref('User')})}))
    add('put', '/api/auth/profile', 'Изменить профиль', 'Авторизация', obj({'data': obj({'user': ref('User')})}),
        obj({'full_name': string(), 'nickname': string(pattern=r'^[a-zA-Z0-9._-]{3,20}$')}))
    for action, title, fields, public in [
        ('change-password', 'Изменить пароль', ('current_password', 'new_password'), False),
        ('forgot-password', 'Запросить сброс пароля', ('email',), True),
        ('reset-password', 'Сбросить пароль', ('token', 'password'), True),
        ('verify-email', 'Подтвердить email', ('token',), True),
        ('deactivate', 'Деактивировать аккаунт', ('password',), False),
    ]:
        add('post', '/api/auth/' + action, title, 'Авторизация', ref('Message'),
            obj({key: string(format='password') if 'password' in key else string() for key in fields}, fields),
            security=[] if public else None,
            description='Отправка email пока не реализована.' if action == 'forgot-password' else '')
    add('delete', '/api/auth/deactivate', 'Удалить аккаунт', 'Авторизация', ref('Message'),
        description='При наличии загруженных видео возвращает 409. Общий демоаккаунт изменять нельзя.')

    add('get', '/api/admin/users', 'Пользователи', 'Администрирование', obj({'users': array(ref('User')),
        'total': integer, 'page': integer, 'pages': integer}), params=pagination + [parameter('search')])
    add('patch', '/api/admin/users/{user_id}', 'Изменить роль или статус', 'Администрирование',
        obj({'user': ref('User')}), obj({'is_active': boolean, 'is_verified': boolean,
                                      'user_type': string(enum=['user', 'admin'])}))
    add('get', '/api/admin/branches', 'Отделения', 'Администрирование', obj({'items': array(ref('Branch'))}))
    add('post', '/api/admin/branches', 'Создать отделение', 'Администрирование', ref('Branch'),
        obj({'name': string(minLength=1, maxLength=120)}, ('name',), additionalProperties=False), codes=(201,))
    scope = obj({'branch_id': string(), 'is_demo': boolean}, ('branch_id',), additionalProperties=False)
    add('put', '/api/admin/cameras/{camera_id}/scope', 'Назначить отделение камеры', 'Администрирование',
        obj({'camera_id': string(), 'branch_id': string(), 'is_demo': boolean}), scope)
    for method in ('get', 'put'):
        add(method, '/api/admin/users/{user_id}/access', 'Доступ пользователя к камерам и отделениям',
            'Администрирование', ref('Access'), ref('Access') if method == 'put' else None)

    add('get', '/api/v1/capabilities', 'Возможности сервера', 'Видео', obj({'uploads': boolean,
        'analysis': boolean, 'analysis_kind': string(), 'automatic_violation_detection': boolean,
        'camera_stream': boolean, 'monitoring': boolean, 'shift_review': boolean,
        'automatic_quality_checks': boolean, 'formats': array(string()), 'max_file_size': integer}))
    upload = obj({'file': string(format='binary', description='MOV, MP4 или WebM, до 1 ГиБ.')}, ('file',))
    add('post', '/api/v1/media', 'Загрузить видео', 'Видео', ref('Media'), upload, multipart=True,
        params=[parameter('Idempotency-Key', string(minLength=1, maxLength=80), 'header', True,
                          'Буквы, цифры, дефис, подчёркивание. Повтор того же файла и ключа возвращает 200.')], codes=(201, 200))
    add('get', '/api/v1/media', 'Список видео', 'Видео', paged(ref('Media')), params=pagination + [
        parameter('search'), parameter('status', string(enum=['all', 'stored'], default='all')),
        parameter('sort', string(enum=['newest', 'oldest'], default='newest'))])
    add('get', '/api/v1/media/{record_id}', 'Метаданные видео', 'Видео', ref('Media'))
    add('post', '/api/v1/media/{record_id}/playback-url', 'Ссылка на видео', 'Видео',
        obj({'url': string(), 'expires_in': integer}), description='Подписанная ссылка действует 900 секунд и отзывается вместе с сессией.')
    add('get', '/api/v1/media/{record_id}/report', 'Скачать JSON-отчёт', 'Видео',
        {'allOf': [ref('Media'), obj({'analysis': obj(nullable=True), 'notice': string()})]},
        description='Метаданные записи и notice; Content-Disposition: attachment.')
    for path, mime, title in [('/api/v1/media/{record_id}/content', 'video/mp4', 'Содержимое видео'),
                              ('/api/v1/frames/{frame_id}/content', 'image/jpeg', 'Кадр события'),
                              ('/api/v1/jobs/{job_id}/evidence/{index}', 'image/jpeg', 'Кадр анализа')]:
        params = [parameter('Range', string(example='bytes=0-1023'), 'header')]
        if mime.startswith('video'):
            params.append(parameter('download', string(enum=['1']), description='Скачать файл.'))
        operation = add('get', path, title, 'Файлы', security=[{'SignedToken': []}], params=params,
                        description='Подпись token берётся из playback-url или DTO. Для видео MIME соответствует исходному MOV/MP4/WebM.')
        operation['responses']['200'] = response(string(format='binary'), media_type=mime)
        operation['responses']['206'] = response(string(format='binary'), 'Частичное содержимое', mime)
        operation['responses']['416'] = response(ref('Error'), 'Неверный Range')

    camera = {'name': string(minLength=1, maxLength=120), 'location': string(minLength=1, maxLength=255), 'is_active': boolean}
    add('get', '/api/v1/cameras', 'Камеры', 'Мониторинг', paged(ref('Camera')), params=pagination)
    for method, path in [('post', '/api/v1/cameras'), ('patch', '/api/v1/cameras/{camera_id}')]:
        add(method, path, 'Настроить камеру (admin)', 'Мониторинг', ref('Camera'),
            obj(camera, ('name', 'location') if method == 'post' else (), additionalProperties=False),
            codes=(201,) if method == 'post' else (200,))
    add('post', '/api/v1/cameras/{camera_id}/health', 'Проверка камеры (admin)', 'Мониторинг',
        obj({'id': string(), 'camera_id': string(), 'status': string(), 'checked_at': date_time}),
        obj({'external_id': string(maxLength=120), 'source': string(maxLength=80), 'checked_at': date_time,
             'status': string(enum=['observing', 'offline', 'occluded', 'frozen', 'poor_visibility'])},
            ('external_id', 'source', 'checked_at', 'status'), additionalProperties=False), codes=(201, 200),
        description='Проверка действительна 90 секунд. Время с часовым поясом, не в будущем, строго возрастает. Идентичный повтор external_id возвращает 200, конфликт — 409.')
    for endpoint, title in [('monitoring', 'Состояние камер и журнал'), ('shift', 'Обзор смены'), ('overview', 'Сводка')]:
        add('get', '/api/v1/' + endpoint, title, 'Мониторинг', ref(endpoint.title()), params=day + ([pagination[0],
            parameter('per_page', dict(integer, minimum=1, maximum=100, default=50))] if endpoint == 'monitoring' else []),
            description='Сводка за выбранный день и доступные камеры. Подробный формат: docs/API_CONTRACT.md.')
    alerts = paged(ref('Alert'))
    alerts['properties']['counts'] = obj({'all': integer, 'new': integer, 'read': integer})
    add('get', '/api/v1/notifications', 'Уведомления', 'События', alerts, params=day + pagination + [
        parameter('read', string(enum=['all', 'new', 'read'], default='all'))])
    add('get', '/api/v1/notifications/{alert_id}', 'Событие с кадрами', 'События', ref('Alert'))
    add('post', '/api/v1/notifications/read', 'Отметить прочитанными', 'События',
        obj({'items': array(obj({'id': string(), 'read_at': date_time}))}),
        obj({'ids': array(string(), maxItems=100)}, ('ids',)))
    add('post', '/api/v1/events', 'Создать событие (admin)', 'События', ref('Alert'), obj({
        'camera_id': string(maxLength=36), 'source': string(maxLength=80), 'external_event_id': string(maxLength=120),
        'detected_at': date_time, 'type': string(maxLength=255), 'description': string(maxLength=10000),
        'timecode_sec': dict(number, default=0), 'media_id': string(nullable=True)},
        ('camera_id', 'source', 'external_event_id', 'detected_at', 'type', 'description'), additionalProperties=False),
        codes=(201, 200), description='Дедупликация source/external_event_id. detected_at не в будущем. Не запускает ИИ.')
    add('put', '/api/v1/notifications/{alert_id}/recording', 'Связать событие с видео (admin)', 'События',
        ref('Alert'), obj({'media_id': string()}, ('media_id',), additionalProperties=False))
    add('get', '/api/v1/sources', 'Нормативные источники', 'События', paged(obj({key: string(nullable=True)
        for key in ('id', 'title', 'number', 'document_date', 'url', 'publisher')})), params=pagination)

    add('post', '/api/v1/media/{record_id}/analyze', 'Запустить анализ видео', 'Анализ', ref('Job'),
        obj({'camera_profile': string(enum=['full_frame', 'forte_open'], default='full_frame')}, additionalProperties=False),
        required=False, codes=(202, 200), description='Наблюдения модели требуют проверки специалистом; не являются вердиктом о нарушениях.')
    add('get', '/api/v1/media/{record_id}/analysis', 'Последняя задача видео', 'Анализ',
        dict(schemas['Job'], nullable=True), description='null, если анализ ещё не запрошен.')
    add('get', '/api/v1/jobs/{job_id}', 'Состояние задачи', 'Анализ',
        {'oneOf': [ref('Job'), ref('PublicJob')]}, security=[{'BearerAuth': []}, {'ApiKeyAuth': []}],
        description='JWT → Job; X-API-Key → PublicJob. Используйте только один способ авторизации: оба заголовка дают 400. Публичный результат наблюдений возвращает failed/verdict_unavailable, а не no_violation.')
    add('post', '/api/v1/api-keys', 'Выдать API-ключ без регистрации', 'Публичный API',
        obj({'api_key': string(), 'expires_at': date_time}), security=[], codes=(201,),
        description='Ключ возвращается один раз, срок по умолчанию 30 дней. Скопируйте его в Authorize → ApiKeyAuth.')
    add('delete', '/api/v1/api-keys/current', 'Отозвать API-ключ', 'Публичный API',
        security=[{'ApiKeyAuth': []}], codes=(204,))
    add('post', '/api/v1/analyze', 'Загрузить видео для анализа по API-ключу', 'Публичный API',
        ref('PublicJob'), upload,
        security=[{'ApiKeyAuth': []}], codes=(202, 200), multipart=True,
        description='X-API-Key: выданный через /api/v1/api-keys или настроенный JURY_API_KEY. GET /api/v1/jobs/{job_id} использует тот же ключ; формат результата одинаков для обоих типов ключа. Один файл до 1 ГиБ; дедлайн 300 секунд от создания задачи, включая очередь. Наблюдения без бинарного вердикта возвращают failed.')
    return {
        'openapi': '3.0.3', 'info': {'title': 'Forte Control API', 'version': '1.0.0',
            'description': 'Интерактивная документация backend. JWT: выполните login и вставьте access_token в Authorize без Bearer. '
                           'API-ключ: выполните POST /api/v1/api-keys и вставьте api_key в ApiKeyAuth. '
                           'Не включайте одновременно JWT и API-ключ для публичного анализа. '
                           'Операции admin требуют администратора и MFA в production. Try it out выполняет реальные запросы.'},
        # Resolved against /api/openapi.json, preserving a reverse-proxy prefix.
        'servers': [{'url': '..', 'description': 'Текущий backend'}],
        'paths': paths, 'components': {'schemas': schemas, 'securitySchemes': {
            'BearerAuth': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'},
            'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'},
            'RefreshCookie': {'type': 'apiKey', 'in': 'cookie', 'name': 'refresh_token_cookie',
                              'description': 'Устанавливается браузером после login; вручную вводить не нужно.'},
            'CsrfToken': {'type': 'apiKey', 'in': 'header', 'name': 'X-CSRF-TOKEN'},
            'SignedToken': {'type': 'apiKey', 'in': 'query', 'name': 'token',
                            'description': 'Подпись из URL конкретного видео или кадра; не JWT.'},
        }},
    }


@docs_bp.get('/api/openapi.json')
def openapi():
    return jsonify(build_spec())


@docs_bp.get('/api/docs/')
def swagger_ui():
    return render_template('swagger.html')


@docs_bp.get('/api/docs/assets/<path:filename>')
def swagger_assets(filename):
    return send_from_directory(swagger_ui_path, filename)
