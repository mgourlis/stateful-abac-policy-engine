import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from common.models import Realm, Resource, ResourceType, Action, ACL
from sqlalchemy import select, delete

@pytest.mark.asyncio
async def test_spatial_missing_context(ac: AsyncClient):
    # 1. Setup Realm and Resource
    realm_name = "SpatialFailTest"
    
    # Create Realm
    response = await ac.post("/api/v1/realms", json={"name": realm_name})
    if response.status_code == 201:
        realm_id = response.json()["id"]
    else:
        # Maybe exists
        stmt = "SELECT id FROM realm WHERE name = :name"
        # Can't easily execute raw SQL without session here, assume fresh DB or handle error
        # Just use existing or fetch
        r = await ac.get(f"/api/v1/realms") # List? No endpoint for list by name easily
        # Let's trust the test env is clean enough or just use a unique name
        # If 400, it exists, ignored for brevity of this quick check.
        # But we need the ID.
        pass

    # Actually better to use a fixture or just create unique
    import uuid
    realm_name = f"SpatialFail_{uuid.uuid4()}"
    response = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert response.status_code == 200
    realm_id = response.json()["id"]

    # Create Type & Action
    rt_res = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "Zone"})
    rt_id = rt_res.json()["id"]
    act_res = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "enter"})
    act_id = act_res.json()["id"]

    # Create Resource with Geometry
    res_data = {
        "name": "RestrictedZone",
        "resource_type_id": rt_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0,0], [0,10], [10,10], [10,0], [0,0]]]
        }
    }
    r_res = await ac.post(f"/api/v1/realms/{realm_id}/resources", json=res_data)
    assert r_res.status_code == 200
    res_id = r_res.json()["id"]

    # Create ACL with Missing Context Variable
    acl_data = {
        "realm_id": realm_id, # Required field
        "resource_id": res_id,
        "action_id": act_id,
        "resource_type_id": rt_id,
        "role_id": None, 
        "principal_id": 0, 
        # The schema requires either principal or role usually for the partition Check.
        # But we can create a "Role" and check access with it.
        "role_id": None # Wait, let's make a role
    }

    # Create Role
    role_res = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "Visitor"})
    role_id = role_res.json()["id"]
    
    # Update ACL to use this role
    acl_data["role_id"] = role_id
    acl_data["conditions"] = {
        "op": "st_dwithin",
        "attr": "geometry",
        "val": "$context.location", # <--- Expects this
        "args": 5000
    }
    
    acl_res = await ac.post(f"/api/v1/realms/{realm_id}/acls", json=acl_data)
    assert acl_res.status_code == 200

    # Create Dummy Principal for Auth
    from common.services.security import create_access_token
    # We need a principal to sign the token.
    # Just insert one using API or assume ID 99999 if secret key works without DB?
    # Better to create one.
    p_res = await ac.post(f"/api/v1/realms/{realm_id}/principals", json={"username": "tester"})
    p_id = p_res.json()["id"]
    token = create_access_token({"sub": str(p_id)})

    # 2. Check Access WITHOUT providing 'location' in context
    check_req = {
        "realm_name": realm_name,
        "role_names": ["Visitor"],
        "req_access": [
            {"resource_type_name": "Zone", "action_name": "enter"}
        ],
        "auth_context": {
            # "location": ... MISSING
        }
    }
    
    check_resp = await ac.post("/api/v1/check-access", json=check_req, headers={"Authorization": f"Bearer {token}"})
    assert check_resp.status_code == 200
    data = check_resp.json()
    
    # Expectation: Should fail gracefully (return empty list), NOT crash 500
    answer = data["results"][0]["answer"]
    assert answer == [] 
