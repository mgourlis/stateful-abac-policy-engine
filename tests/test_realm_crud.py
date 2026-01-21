
import pytest
import time
from httpx import AsyncClient

@pytest.mark.run(order=-99)  # Run this test last
@pytest.mark.asyncio
async def test_realm_crud(ac: AsyncClient):
    # 0. Cleanup (if exists from previous run)
    # We don't have ID, but can try to create and if fails, we might need a way to find it.
    # But we don't have GET /realms?name=... endpoint explicitly tested/implemented.
    # Let's just use a timestamp in name to be unique.
    
    realm_name = f"test-realm-ext-{int(time.time())}"
    
    # 1. Create Realm
    print(f"Creating Realm {realm_name}...")
    response = await ac.post("/api/v1/realms", json={
        "name": realm_name,
        "description": "Test Realm for External ID Verification",
        "is_active": True
    })
    assert response.status_code == 200, f"Failed to create realm: {response.text}"

    realm = response.json()
    realm_id = realm["id"]
    print(f"Created Realm ID: {realm_id}")

    try:
        # 2. Setup Dependencies (Action, ResourceType)
        print("\nSetting up deps...")
        # Create ResourceType
        rt_resp = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "widgets"})
        assert rt_resp.status_code == 200
        rt = rt_resp.json()
        rt_id = rt["id"]
        
        # 3. Batch Create Resources with External ID
        print("\nBatch Creating Resources with External ID...")
        res_data = {
            "create": [
                {"name": "widget1", "resource_type_id": rt_id, "external_id": "ext-1"},
                {"name": "widget2", "resource_type_id": rt_id, "external_id": "ext-2"}
            ]
        }
        resp = await ac.post(f"/api/v1/realms/{realm_id}/resources/batch", json=res_data)
        assert resp.status_code == 200, f"Failed batch create: {resp.text}"
        print("Batch Create Success")

        # 4. Batch Update using External ID
        print("\nBatch Updating using External ID...")
        update_data = {
            "update": [
                {"external_id": "ext-1", "attributes": {"updated": True}} # Simplified: no resource_type_id
            ]
        }
        resp = await ac.post(f"/api/v1/realms/{realm_id}/resources/batch", json=update_data)
        assert resp.status_code == 200, f"Failed batch update: {resp.text}"
        print("Batch Update Success")
            
        # Verify update
        # Get resource list and check attributes
        all_res = (await ac.get(f"/api/v1/realms/{realm_id}/resources")).json()["items"]
        updated_res = next((r for r in all_res if r["external_id"] == "ext-1" or (isinstance(r["external_id"], list) and "ext-1" in r["external_id"])), None)
        
        assert updated_res is not None
        assert updated_res.get("attributes", {}).get("updated") is True
        print("Verified Update")

        # 5. Batch Delete using External ID
        print("\nBatch Deleting using External ID...")
        delete_data = {
            "delete": [
                {"external_id": "ext-2", "resource_type_id": rt_id}
            ]
        }
        resp = await ac.post(f"/api/v1/realms/{realm_id}/resources/batch", json=delete_data)
        assert resp.status_code == 200, f"Failed batch delete: {resp.text}"
        print("Batch Delete Success")
        
        # Verify delete
        all_res_after = (await ac.get(f"/api/v1/realms/{realm_id}/resources")).json()["items"]
        deleted_res = next((r for r in all_res_after if r["external_id"] == "ext-2" or (isinstance(r["external_id"], list) and "ext-2" in r["external_id"])), None)
        assert deleted_res is None
        print("Verified Delete")

        # --- Verify Single Resource External ID Endpoints ---
        print("\nVerifying Single Resource External ID Endpoints...")
        # 1. Create a resource with external ID
        ext_id_single = f"single-ext-{int(time.time())}"
        res_data_single = {
            "name": "single-ext-res",
            "resource_type_id": rt_id,
            "attributes": {"description": "test resource"},
            "external_id": ext_id_single
        }
        resp = await ac.post(f"/api/v1/realms/{realm_id}/resources", json=res_data_single)
        assert resp.status_code == 200, f"Failed to create single resource: {resp.text}"
        print("Created Single Resource with External ID")
            
        # 2. GET by External ID
        # Path: /realms/{realm_id}/resources/external/{external_id}
        resp = await ac.get(f"/api/v1/realms/{realm_id}/resources/external/{rt_id}/{ext_id_single}")
        assert resp.status_code == 200, f"Failed GET by ExtID: {resp.text}"
        print("GET by ExtID Success")
            
        # 3. PUT by External ID
        update_data = {"attributes": {"name": "updated-single-ext"}}
        resp = await ac.put(f"/api/v1/realms/{realm_id}/resources/external/{rt_id}/{ext_id_single}", json=update_data)
        assert resp.status_code == 200, f"Failed PUT by ExtID: {resp.text}"
        print("PUT by ExtID Success")
            
        # 4. DELETE by External ID
        resp = await ac.delete(f"/api/v1/realms/{realm_id}/resources/external/{rt_id}/{ext_id_single}")
        assert resp.status_code == 200, f"Failed DELETE by ExtID: {resp.text}"
        print("DELETE by ExtID Success")

    finally:
        # 6. Cleanup
        print("\nDeleting Realm...")
        await ac.delete(f"/api/v1/realms/{realm_id}")
        print("Done.")
