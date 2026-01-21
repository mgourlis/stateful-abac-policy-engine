import pytest
import httpx
import time
from app.main import app

# Use ASGI app directly
BASE_URL = "http://test/api/v1"

@pytest.mark.run(order=-102)
@pytest.mark.asyncio
async def test_metadata_endpoint(session):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/meta/acl-options")
        assert response.status_code == 200
        data = response.json()
        
        assert "sources" in data
        assert "operators" in data
        assert "context_attributes" in data
        
        # Check for Entity Lists
        assert "principals" in data
        assert "roles" in data
        assert "actions" in data
        assert "resource_types" in data
        
        assert len(data["operators"]) > 0
        
        # Check specific operator existence
        ops = [op["value"] for op in data["operators"]]
        assert "=" in ops
        assert "in" in ops
        assert "st_dwithin" in ops

@pytest.mark.run(order=-101)
@pytest.mark.asyncio
async def test_metadata_filtering(session):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

        # 1. Create a Realm and entities to verify filtering
        realm_name = f"test-meta-{int(time.time())}"
        resp = await ac.post("/api/v1/realms", json={"name": realm_name, "is_active": True})
        assert resp.status_code == 200
        realm_id = resp.json()["id"]
        
        try:
            # Create Role
            await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "test-role-meta"})
            # Create Principal
            await ac.post(f"/api/v1/realms/{realm_id}/principals", json={"username": "test-user-meta"})
            
            # 2. Call metadata endpoint WITH realm_id filter
            resp = await ac.get(f"/api/v1/meta/acl-options?realm_id={realm_id}")
            assert resp.status_code == 200
            data_filtered = resp.json()
            
            # Check existence
            assert any(r["name"] == "test-role-meta" for r in data_filtered["roles"])
            assert any(p["username"] == "test-user-meta" for p in data_filtered["principals"])
            
        finally:
            # Cleanup
            await ac.delete(f"/api/v1/realms/{realm_id}")
