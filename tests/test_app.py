from unittest.mock import MagicMock
import app as main_app_module


def test_home_page_with_redis(web_client, fake_redis):
    """Test GET / increments visit counter and returns 200 OK."""
    response = web_client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert "Hello from Flask!" in html
    assert "Redis Status: Connected" in html
    assert "Page visits:" in html

    # Subsequent request should increment counter
    response2 = web_client.get('/')
    assert response2.status_code == 200
    if fake_redis is not None:
        assert fake_redis.get('counter') == '2'


def test_api_counter_endpoint(web_client, fake_redis):
    """Test GET /api/counter returns JSON with increments."""
    response = web_client.get('/api/counter')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['redis_status'] == 'Connected'
    assert data['visits'] is not None


def test_home_page_redis_failure(web_client):
    """Test GET / gracefully handles Redis failure."""
    original_client = main_app_module.redis_client
    broken_redis = MagicMock()
    broken_redis.incr.side_effect = Exception("Connection refused")
    main_app_module.redis_client = broken_redis

    try:
        response = web_client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "N/A" in html
        assert "Error: Connection refused" in html
    finally:
        main_app_module.redis_client = original_client


def test_api_counter_redis_failure(web_client):
    """Test GET /api/counter returns 500 when Redis fails."""
    original_client = main_app_module.redis_client
    broken_redis = MagicMock()
    broken_redis.incr.side_effect = Exception("Connection refused")
    main_app_module.redis_client = broken_redis

    try:
        response = web_client.get('/api/counter')
        assert response.status_code == 500
        data = response.get_json()
        assert data['status'] == 'error'
        assert "Connection refused" in data['redis_status']
    finally:
        main_app_module.redis_client = original_client


def test_not_found_handler(web_client):
    """Test custom 404 handler returns structured JSON."""
    response = web_client.get('/non-existent-route')
    assert response.status_code == 404
    data = response.get_json()
    assert 'error' in data
    assert data['error']['code'] == 'NOT_FOUND'


def test_healthz_endpoint_healthy(web_client):
    """Test GET /healthz returns healthy status."""
    response = web_client.get('/healthz')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'healthy'
    assert data['service'] == 'flask-web'
    assert data['redis_status'] == 'Connected'


def test_healthz_endpoint_redis_disconnected(web_client):
    """Test GET /healthz reports disconnected Redis when ping fails."""
    original_client = main_app_module.redis_client
    broken_redis = MagicMock()
    broken_redis.ping.side_effect = Exception("Connection lost")
    main_app_module.redis_client = broken_redis

    try:
        response = web_client.get('/healthz')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert "Disconnected: Connection lost" in data['redis_status']
    finally:
        main_app_module.redis_client = original_client
