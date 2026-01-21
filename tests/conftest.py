import os
os.environ["TESTING"] = "true"  # Must be before imports
os.environ["STATEFUL_ABAC_TESTING"] = "true"  # For SDK/common config

# Default to docker-compose dev DB if not set (port 5433 is docker-compose exposed port)
if "STATEFUL_ABAC_DATABASE_URL" not in os.environ:
    os.environ["STATEFUL_ABAC_DATABASE_URL"] = "postgresql+asyncpg://postgres:123456@localhost:5433/demo_auth_db"

# Default Redis to docker-compose (port 6378 is docker-compose exposed port)
if "STATEFUL_ABAC_REDIS_URL" not in os.environ:
    os.environ["STATEFUL_ABAC_REDIS_URL"] = "redis://localhost:6378/0"

# Default SDK to HTTP mode for tests (matching ASGI transport)
# SDK uses STATEFUL_ABAC_CLIENT_MODE and STATEFUL_ABAC_CLIENT_BASE_URL
if "STATEFUL_ABAC_CLIENT_MODE" not in os.environ:
    os.environ["STATEFUL_ABAC_CLIENT_MODE"] = "http"
if "STATEFUL_ABAC_CLIENT_BASE_URL" not in os.environ:
    os.environ["STATEFUL_ABAC_CLIENT_BASE_URL"] = "http://test"

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from common.core.database import engine
from common.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import pytest
from app.main import app
import sys
from pathlib import Path

# Add SDK to path for tests
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from stateful_abac_sdk import StatefulABACClient

# Use a test database URL or existing?
# For simplicity, we use the same DB but ideally cleaning up.
# Integration test usually runs against running DB in this context.

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="function")
async def ac():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
def sdk_client():
    """Shared SDK client fixture using ASGI transport for testing."""
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)

@pytest_asyncio.fixture(scope="function")
async def session(): 
    await engine.dispose()
    # Helper to access DB directly for setup
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        yield s
    await engine.dispose()
    

@pytest_asyncio.fixture(scope="function", autouse=True)
async def reset_engine():
    await engine.dispose()
    yield
    await engine.dispose()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def patch_redis(monkeypatch):
    import common.core.redis
    from common.core.config import settings
    import redis.asyncio as redis
    
    # Create new client for this loop
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Patch the singleton instance directly or the get_instance method
    # Since get_instance uses _instance, we can just set _instance provided we clear it first/after
    # or just patch get_instance to be safe across tests if they run in parallel (function scope)
    monkeypatch.setattr(common.core.redis.RedisClient, "get_instance", lambda: client)
    
    yield
    
    await client.aclose()
