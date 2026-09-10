import os
import sys
import pytest

# Ensure root project directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app as main_app_module  # noqa: E402
from api import main as api_main_module  # noqa: E402

try:
    import fakeredis
except ImportError:
    fakeredis = None


@pytest.fixture
def fake_redis():
    """Provides a fresh in-memory fake redis instance for testing."""
    if fakeredis is not None:
        return fakeredis.FakeRedis(decode_responses=True)
    return None


@pytest.fixture
def web_client(fake_redis):
    """Flask test client for root web app (app.py)."""
    main_app_module.app.config['TESTING'] = True
    original_client = main_app_module.redis_client

    if fake_redis is not None:
        main_app_module.redis_client = fake_redis

    with main_app_module.app.test_client() as client:
        yield client

    main_app_module.redis_client = original_client


@pytest.fixture
def api_client(fake_redis):
    """Flask test client for separate API app (api/main.py)."""
    api_main_module.app.config['TESTING'] = True
    original_client = api_main_module.redis_client

    if fake_redis is not None:
        api_main_module.redis_client = fake_redis

    with api_main_module.app.test_client() as client:
        yield client

    api_main_module.redis_client = original_client
