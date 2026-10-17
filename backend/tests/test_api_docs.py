import re
from urllib.parse import urljoin


def test_spec_covers_every_api_operation(client, app):
    response = client.get('/api/openapi.json')
    assert response.status_code == 200
    spec = response.json
    expected = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api') and rule.endpoint.split('.')[0] != 'api_docs':
            path = re.sub(r'<(?:[^:<>]+:)?([^<>]+)>', r'{\1}', rule.rule)
            expected.update((path, method.lower()) for method in rule.methods - {'HEAD', 'OPTIONS'})
    actual = {(path, method) for path, operations in spec['paths'].items() for method in operations}
    assert actual == expected
    identifiers = [operation['operationId'] for operations in spec['paths'].values() for operation in operations.values()]
    assert len(identifiers) == len(set(identifiers))
    assert spec['paths']['/api/v1/jobs/{job_id}']['get']['security'] == [
        {'BearerAuth': []}, {'ApiKeyAuth': []}]
    assert spec['paths']['/api/auth/refresh']['post']['security'] == [
        {'RefreshCookie': [], 'CsrfToken': []}]
    assert 'content' not in spec['paths']['/api/v1/api-keys/current']['delete']['responses']['204']


def test_swagger_serves_local_assets_and_preserves_proxy_prefix(client):
    assert client.get('/api/docs').status_code == 308
    response = client.get('/api/docs/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for asset in re.findall(r'(?:src|href)="(\./assets/[^"]+)"', html):
        result = client.get(urljoin('/api/docs/', asset))
        assert result.status_code == 200
        assert len(result.data) > 1000
    assert 'persistAuthorization: false' in html
    assert 'validatorUrl: null' in html
    spec_url = urljoin('https://example.test/forte/api/docs/', '../openapi.json')
    server = client.get('/api/openapi.json').json['servers'][0]['url']
    assert urljoin(spec_url, server).rstrip('/') + '/api/v1/media' == 'https://example.test/forte/api/v1/media'


def test_swagger_same_origin_login_and_refresh(client, user1):
    login = client.post('/api/auth/login', json={'identifier': user1.email, 'password': 'test1234'},
                        headers={'Origin': 'http://localhost'})
    assert login.status_code == 200
    token = login.json['access_token']
    assert client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    refresh = client.post('/api/auth/refresh', headers={
        'Origin': 'http://localhost', 'X-CSRF-TOKEN': login.json['csrf_token']})
    assert refresh.status_code == 200
    rejected = client.post('/api/auth/login', json={'identifier': user1.email, 'password': 'test1234'},
                           headers={'Origin': 'https://untrusted.example'})
    assert rejected.status_code == 403
    assert rejected.json['error']['code'] == 'origin_rejected'
