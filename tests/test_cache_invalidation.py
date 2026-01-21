import pytest
import time
import asyncio
from common.services.cache import CacheService
from common.core.redis import RedisClient
from common.models import Realm
from common.core.database import AsyncSessionLocal
from sqlalchemy import delete

@pytest.mark.asyncio
async def test_cache_invalidation(session):
    redis_client = RedisClient.get_instance()
    
    realm_name = f"test-cache-inv-{int(time.time())}"
    
    # 1. Create Realm direct in DB (to avoid API overhead/deps)
    r = Realm(name=realm_name, is_active=True)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    realm_id = r.id
    
    try:
        # 2. Populate Cache
        print(f"Populating cache for {realm_name}...")
        mapping = await CacheService.get_realm_map(realm_name, db_session=session)
        assert mapping is not None
        assert mapping["_id"] == str(realm_id)
        
        # Verify key exists in Redis
        key = f"realm:{realm_name}"
        exists = await redis_client.exists(key)
        assert exists == 1
        print("Cache key verified in Redis")
        
        # 3. Invalidate
        print("Invalidating cache...")
        await CacheService.invalidate_realm(realm_name)
        
        # 4. Verify key gone
        exists_after = await redis_client.exists(key)
        assert exists_after == 0
        print("Cache key verified REMOVED from Redis")
        
    finally:
        # Cleanup
        await session.execute(delete(Realm).where(Realm.id == realm_id))
        await session.commit()

if __name__ == "__main__":
    asyncio.run(test_cache_invalidation())
