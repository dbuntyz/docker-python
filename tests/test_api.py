from unittest.mock import MagicMock
from api import main as api_main_module


def test_api_index(api_client):
    """Test GET / on API service returns service overview."""
    response = api_client.get('/')
    assert response.status_code == 200
    data = response.get_json()
    assert data['service'] == 'Separate External API'
    assert 'endpoints' in data


def test_api_stats(api_client, fake_redis):
    """Test GET /stats returns counter and keys."""
    if fake_redis is not None:
        fake_redis.set('counter', 42)
        fake_redis.info = lambda: {'redis_version': '7.0.0'}

    response = api_client.get('/stats')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['counter_value'] == 42
    assert data['redis_version'] == '7.0.0'


def test_api_stats_error(api_client):
    """Test GET /stats handles error when Redis is down."""
    original_client = api_main_module.redis_client
    broken_redis = MagicMock()
    broken_redis.get.side_effect = Exception("Redis offline")
    api_main_module.redis_client = broken_redis

    try:
        response = api_client.get('/stats')
        assert response.status_code == 500
        data = response.get_json()
        assert data['status'] == 'error'
    finally:
        api_main_module.redis_client = original_client


def test_api_set_counter(api_client, fake_redis):
    """Test POST /set-counter successfully updates counter."""
    response = api_client.post('/set-counter', json={'value': 99})
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['counter_value'] == 99

    if fake_redis is not None:
        assert fake_redis.get('counter') == '99'


def test_api_set_counter_invalid(api_client):
    """Test POST /set-counter handles invalid payload."""
    response = api_client.post('/set-counter', json={'value': 'invalid_number'})
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'


def test_api_health_success(api_client):
    """Test GET /health returns healthy status."""
    original_client = api_main_module.redis_client
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    api_main_module.redis_client = mock_redis

    try:
        response = api_client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data['redis_ping'] is True
    finally:
        api_main_module.redis_client = original_client


def test_api_health_failure(api_client):
    """Test GET /health returns 503 when ping fails."""
    original_client = api_main_module.redis_client
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("Ping failed")
    api_main_module.redis_client = mock_redis

    try:
        response = api_client.get('/health')
        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] == 'unhealthy'
    finally:
        api_main_module.redis_client = original_client
