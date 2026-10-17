"""Helper функции для работы с request контекстом"""

from user_agents import parse


def get_client_ip(request):
    """Получить IP клиента (с поддержкой proxies)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def parse_user_agent(user_agent_string):
    """Спарсить User-Agent в структурированные данные"""
    try:
        ua = parse(user_agent_string)
        return {
            'device_type': str(ua.device.family),  # Desktop, Mobile, Tablet
            'browser': str(ua.browser.family),  # Chrome, Safari, Firefox
            'os': str(ua.os.family),  # Windows, macOS, Linux, iOS, Android
            'browser_version': str(ua.browser.version_string),
            'os_version': str(ua.os.version_string),
        }
    except Exception as e:
        print(f'[WARN] Failed to parse user agent: {str(e)}')
        return {
            'device_type': 'Unknown',
            'browser': 'Unknown',
            'os': 'Unknown',
            'browser_version': '',
            'os_version': '',
        }


def get_device_info(request):
    """Получить информацию об устройстве из request"""
    ua_string = request.headers.get('User-Agent', 'Unknown')
    return parse_user_agent(ua_string)


def get_request_context(request):
    """Получить полный контекст запроса (IP, User-Agent, device info)"""
    device_info = get_device_info(request)
    return {
        'ip_address': get_client_ip(request),
        'user_agent': request.headers.get('User-Agent', 'Unknown'),
        'device_type': device_info['device_type'],
        'browser': device_info['browser'],
        'os': device_info['os'],
    }
