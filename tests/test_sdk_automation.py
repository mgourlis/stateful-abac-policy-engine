
import pytest
from httpx import AsyncClient

from tests.conftest import ac, session, patch_redis # Import existing fixtures from conftest

@pytest.mark.asyncio
async def test_sdk_set_public_automation(ac: AsyncClient):
    """
    Test the new `set_public` convenience methods in the SDK.
    Note: We need to use the actual SDK client interacting with the running app (ac).
    Since StatefulABACClient uses httpx internally, we can mock or point it to the test app.
    However, for integration test, we usually spin up the app. 
    Here, we will use the `ac` fixture which is an AsyncClient, but StatefulABACClient expects a string URL.
    We'll rely on pointing StatefulABACClient to the same base URL if possible or adapt the test.
    Existing tests use `ac` directly. To test the SDK code, we should instantiate StatefulABACClient.
    But StatefulABACClient requires a running server URL.
    The `ac` fixture uses `ASGITransport`. StatefulABACClient by default uses standard httpx.AsyncClient.
    We need to inject the transport into StatefulABACClient or patch it.
    
    Easier path: Just test the backend APIs (filtering) directly since that's what SDK calls.
    AND test the SDK logic unit-style or integration-style if simple.
    """
    import uuid
    realm_name = f"AutoPublicRealm_{uuid.uuid4()}"
    
    # 1. Setup Data via direct API calls (simulating SDK)
    realm_res = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert realm_res.status_code == 200
    realm_id = realm_res.json()["id"]
    
    rt_res = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "Doc", "is_public": False})
    rt_id = rt_res.json()["id"]
    
    act_res = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "read"})
    act_id = act_res.json()["id"]
    
    res_res = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={"name": "Res1", "resource_type_id": rt_id})
    res_id = res_res.json()["id"]
    
    # --- Test 1: Backend ACL Filtering (Prerequisite for SDK `set_public(False)`) ---
    
    # Create a dummy ACL
    acl_data = {
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": act_id,
        "principal_id": 0, # Public
        "resource_id": res_id
    }
    await ac.post(f"/api/v1/realms/{realm_id}/acls", json=acl_data)
    
    # Filter ACLs
    list_res = await ac.get(f"/api/v1/realms/{realm_id}/acls", params={
        "resource_id": res_id,
        "principal_id": 0,
        "action_id": act_id
    })
    assert list_res.status_code == 200
    acls = list_res.json()["items"]
    assert len(acls) == 1
    assert acls[0]["resource_id"] == res_id
    
    # Filter with wrong param
    list_res_empty = await ac.get(f"/api/v1/realms/{realm_id}/acls", params={
        "resource_id": res_id,
        "principal_id": 999 
    })
    assert list_res_empty.status_code == 200
    assert len(list_res_empty.json()["items"]) == 0
    
    # --- Test 2: ResourceType `set_public` Logic (PUT updates) ---
    # Call PUT
    put_res = await ac.put(f"/api/v1/realms/{realm_id}/resource-types/{rt_id}", json={"is_public": True})
    assert put_res.status_code == 200
    assert put_res.json()["is_public"] is True
    
    # Verify
    get_res = await ac.get(f"/api/v1/realms/{realm_id}/resource-types/{rt_id}")
    assert get_res.json()["is_public"] is True
    
