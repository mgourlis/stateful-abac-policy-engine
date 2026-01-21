
import pytest
import time
from common.services.security import create_access_token
from httpx import AsyncClient

@pytest.mark.run(order=-100) 
@pytest.mark.asyncio
async def test_missing_principal_attribute(ac: AsyncClient):
    """Test that missing principal attributes are treated as NULL and deny access"""
    import uuid
    realm_name = f"PrincipalAttrTest_{uuid.uuid4()}"
    
    # Create Realm
    response = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert response.status_code == 200
    realm_id = response.json()["id"]
    
    # Create Type & Action
    rt_res = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "Document"})
    rt_id = rt_res.json()["id"]
    act_res = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "read"})
    act_id = act_res.json()["id"]
    
    # Create Resource
    res_data = {
        "name": "SensitiveDoc",
        "resource_type_id": rt_id,
    }
    r_res = await ac.post(f"/api/v1/realms/{realm_id}/resources", json=res_data)
    assert r_res.status_code == 200
    res_id = r_res.json()["id"]
    
    # Create Principal WITHOUT the 'clearance_level' attribute
    p_res = await ac.post(
        f"/api/v1/realms/{realm_id}/principals",
        json={"username": "user_no_clearance"}
    )
    p_id = p_res.json()["id"]
    
    # Create Role
    role_res = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "Reader"})
    role_id = role_res.json()["id"]
    
    # Create ACL that requires principal.clearance_level >= 5
    acl_data = {
        "realm_id": realm_id,
        "resource_id": res_id,
        "action_id": act_id,
        "resource_type_id": rt_id,
        "role_id": role_id,
        "principal_id": 0,
        "conditions": {
            "op": ">=",
            "source": "principal",
            "attr": "clearance_level",
            "val": 5
        }
    }
    
    acl_res = await ac.post(f"/api/v1/realms/{realm_id}/acls", json=acl_data)
    assert acl_res.status_code == 200
    
    # Create token for principal
    token = create_access_token({"sub": str(p_id)})
    
    # Check Access - should DENY because clearance_level is missing (NULL)
    check_req = {
        "realm_name": realm_name,
        "role_names": ["Reader"],
        "req_access": [
            {"resource_type_name": "Document", "action_name": "read"}
        ],
        "auth_context": {}
    }
    
    check_resp = await ac.post("/api/v1/check-access", json=check_req, headers={"Authorization": f"Bearer {token}"})
    assert check_resp.status_code == 200
    data = check_resp.json()
    
    # Expectation: Access denied (empty list) because NULL >= 5 is FALSE
    answer = data["results"][0]["answer"]
    assert answer == []

@pytest.mark.run(order=-101) 
@pytest.mark.asyncio
async def test_missing_resource_attribute(ac: AsyncClient):
    """Test that missing resource attributes are treated as NULL and deny access"""
    import uuid
    realm_name = f"ResourceAttrTest_{uuid.uuid4()}"
        
    # Create Realm
    response = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert response.status_code == 200
    realm_id = response.json()["id"]
        
    # Create Type & Action
    rt_res = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "File"})
    rt_id = rt_res.json()["id"]
    act_res = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "download"})
    act_id = act_res.json()["id"]
        
    # Create Resource WITHOUT 'status' attribute
    res_data = {
        "name": "UnpublishedFile",
        "resource_type_id": rt_id,
    }
    r_res = await ac.post(f"/api/v1/realms/{realm_id}/resources", json=res_data)
    assert r_res.status_code == 200
    res_id = r_res.json()["id"]
        
    # Create Principal
    p_res = await ac.post(
        f"/api/v1/realms/{realm_id}/principals",
        json={"username": "downloader"}
        )
    p_id = p_res.json()["id"]
        
    # Create Role
    role_res = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "Downloader"})
    role_id = role_res.json()["id"]
        
    # Create ACL that requires resource.status == "published"
    acl_data = {
        "realm_id": realm_id,
        "resource_id": res_id,
        "action_id": act_id,
        "resource_type_id": rt_id,
        "role_id": role_id,
        "principal_id": 0,
        "conditions": {
            "op": "=",
            "source": "resource",
            "attr": "status",
            "val": "published"
        }
    }
    
    acl_res = await ac.post(f"/api/v1/realms/{realm_id}/acls", json=acl_data)
    assert acl_res.status_code == 200
    
    # Create token for principal
    token = create_access_token({"sub": str(p_id)})
        
    # Check Access - should DENY because status is missing (NULL)
    check_req = {
        "realm_name": realm_name,
        "role_names": ["Downloader"],
        "req_access": [
            {"resource_type_name": "File", "action_name": "download"}
            ],
        "auth_context": {}
    }
    
    check_resp = await ac.post("/api/v1/check-access", json=check_req, headers={"Authorization": f"Bearer {token}"})
    assert check_resp.status_code == 200
    data = check_resp.json()
        
    # Expectation: Access denied (empty list) because NULL = "published" is FALSE
    answer = data["results"][0]["answer"]
    assert answer == []
