
# 1. DB Connection Test
import pytest
import asyncpg
import asyncio

@pytest.mark.asyncio
async def test_db_connection():
    from common.core.config import settings
    # Adapt SQLAlchemy URL for asyncpg direct connection if needed
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        conn = await asyncpg.connect(db_url)
        assert conn is not None
        await conn.close()
    except Exception as e:
        pytest.fail(f"Connection failed: {e}")
