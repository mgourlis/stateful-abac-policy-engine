import pytest
import time
from httpx import AsyncClient, ASGITransport
from app.main import app
from common.services.cache import CacheService
from common.core.redis import RedisClient

@pytest.mark.asyncio
async def test_auto_cache_invalidation(session):
    redis_client = RedisClient.get_instance()
    # Use ASGITransport to test API layer integration
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        realm_name = f"test-auto-inv-{int(time.time())}"
        
        # 1. Create Realm
        resp = await ac.post("/api/v1/realms", json={"name": realm_name, "is_active": True})
        assert resp.status_code == 200
        realm_id = resp.json()["id"]
        
        try:
            # 2. Create Initial Entities (Role, Action, RT)
            await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "role1"})
            await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "action1"})
            
            # 3. Populate Cache (Simulate Usage)
            # Call get_realm_map which caches it
            mapping = await CacheService.get_realm_map(realm_name, db_session=session)
            assert "role:role1" in mapping
            assert "action:action1" in mapping
            
            # Verify Key in Redis
            key = f"realm:{realm_name}"
            assert await redis_client.exists(key) == 1
            print("Cache Populated and Verified")
            
            # 4. Modify Entity -> Should Invalidate
            # Create NEW role
            print("Creating new role...")
            await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "role2"})
            
            # Verify Invalidation
            # We expect key to be gone because invalidation deletes it.
            # (It won't be refreshed until next read)
            exists = await redis_client.exists(key)
            assert exists == 0, "Cache should be invalidated after creating role"
            print("Cache Invalidated (Role Create)")
            
            # 5. Populate again
            await CacheService.get_realm_map(realm_name, db_session=session)
            assert await redis_client.exists(key) == 1
            
            # 6. Update Action
            print("Updating action...")
            # Need action ID
            mapping = await CacheService.get_realm_map(realm_name, db_session=session)
            action_id = int(mapping["action:action1"])
            
            await ac.put(f"/api/v1/realms/{realm_id}/actions/{action_id}", json={"name": "action1_updated"})
            
            exists = await redis_client.exists(key)
            assert exists == 0, "Cache should be invalidated after updating action"
            print("Cache Invalidated (Action Update)")
            
            # 7. Realm Update (Name Change)
            # Populate again
            await CacheService.get_realm_map(realm_name, db_session=session) # Caches 'realm:old_name'
            
            new_name = realm_name + "_updated"
            print(f"Updating realm name to {new_name}...")
            await ac.put(f"/api/v1/realms/{realm_id}", json={"name": new_name})
            
            # Verify OLD key is gone
            exists_old = await redis_client.exists(key)
            assert exists_old == 0, "Old realm cache key should be gone"
            print("Cache Invalidated (Realm Name Update)")
            
            # Verify new name works
            mapping_new = await CacheService.get_realm_map(new_name, db_session=session)
            assert mapping_new["_id"] == str(realm_id)
            
        finally:
            # Cleanup
            await ac.delete(f"/api/v1/realms/{realm_id}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_auto_cache_invalidation())
