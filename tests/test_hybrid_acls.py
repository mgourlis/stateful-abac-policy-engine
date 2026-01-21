import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from common.models import Realm, ResourceType, Action, AuthRole, Resource, Principal

@pytest.mark.asyncio
async def test_hybrid_acls(ac: AsyncClient, session: AsyncSession):
    # 1. Setup Data
    # Create Realm
    import uuid
    r_name = f"hybrid_realm_{uuid.uuid4()}"
    r = await ac.post("/api/v1/realms", json={"name": r_name})
    assert r.status_code == 200
    realm_id = r.json()["id"]

    # Create Resource Type
    rt = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "doc"})
    assert rt.status_code == 200
    rt_id = rt.json()["id"]

    # Create Action
    act = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "read"})
    assert act.status_code == 200
    action_id = act.json()["id"]

    # Create Role
    role = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "viewer"})
    assert role.status_code == 200
    role_id = role.json()["id"]

    # Create Principal
    p = await ac.post(f"/api/v1/realms/{realm_id}/principals", json={"username": "user1"})
    assert p.status_code == 200
    p_id = p.json()["id"]

    # Assign Role
    await ac.post(f"/api/v1/realms/{realm_id}/principals/{p_id}/roles", json=[role_id])

    # Create Resources
    # R1: dept=IT
    r1 = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r1",
        "resource_type_id": rt_id,
        "attributes": {"dept": "IT"}
    })
    r1_id = r1.json()["id"]

    # R2: dept=HR
    r2 = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r2",
        "resource_type_id": rt_id,
        "attributes": {"dept": "HR"}
    })
    r2_id = r2.json()["id"]

    # R3: dept=Sales
    r3 = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r3",
        "resource_type_id": rt_id,
        "attributes": {"dept": "Sales"}
    })
    r3_id = r3.json()["id"]

    # R4: External ID Resource
    import uuid
    ext_id = f"ext_{uuid.uuid4()}"
    r4 = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r4",
        "resource_type_id": rt_id,
        "external_id": ext_id
        # Note: API handles creating ExternalID record automatically if external_id is passed in CreateResource
    })
    assert r4.status_code == 200
    r4_id = r4.json()["id"]

    # R5: Another External ID Resource for Batch Test
    ext_id_5 = f"ext_{uuid.uuid4()}"
    r5 = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r5",
        "resource_type_id": rt_id,
        "external_id": ext_id_5
    })
    assert r5.status_code == 200
    r5_id = r5.json()["id"]

    # 2. Create Hybrid ACLs
    
    # Rule A: Type Level, Condition dept=IT
    acl1 = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "conditions": {"attr": "dept", "op": "=", "val": "IT"}
    })
    assert acl1.status_code == 200, acl1.text
    
    # Rule B: Specific Resource Level, ID=R2 (HR)
    # Even though dept != IT, this rule grants specific access
    acl2 = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "resource_id": r2_id,
        "conditions": None # No extra conditions, just the ID match implies access
        # Note: If conditions is None, it defaults to TRUE.
        # Combined with resource_id in logic: (TRUE) AND id = R2
    })
    assert acl2.status_code == 200, acl2.text

    # Rule C: External ID creation -> Resolved to Resource ID
    # Should resolve to R4
    acl3 = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "resource_external_id": ext_id
    })
    assert acl3.status_code == 200, acl3.text
    # Verify it bound to internal ID
    assert acl3.json()["resource_id"] == r4_id

    # Rule D: Batch Creation with External ID
    # Should resolve to R5
    batch_resp = await ac.post(f"/api/v1/realms/{realm_id}/acls/batch", json={
        "create": [{
            "realm_id": realm_id,
            "resource_type_id": rt_id,
            "action_id": action_id,
            "role_id": role_id,
            "resource_external_id": ext_id_5
        }]
    })
    assert batch_resp.status_code == 200, batch_resp.text

    # 3. Verify Authorization
    # User should see R1 (IT) and R2 (Explicit), but NOT R3 (Sales)
    
    # Use check-access batch or similar?
    # Or simulate get_authorized_resources SQL call?
    # Let's use the 'check-access' endpoint if available, or 'authorized_resources' endpoint.
    # Looking for endpoint that returns list of IDs?
    # /api/v1/realms/{realm_id}/auth/authorized-resources ?
    
    # Let's inspect available endpoints in auth.py logic or rely on verify logic.
    # For now, I'll execute raw SQL check using the function `get_authorized_resources`
    # to be absolutely sure of the DB logic.
    
    from sqlalchemy import text
    result = await session.execute(text("""
        SELECT id FROM get_authorized_resources(
            :rid, :pid, :rids, :rtid, :actid, :ctx, NULL
        )
    """), {
        "rid": realm_id,
        "pid": p_id,
        "rids": [role_id],
        "rtid": rt_id,
        "actid": action_id,
        "ctx": "{}"
    })
    
    ids = [row[0] for row in result.fetchall()]
    print(f"Authorized IDs: {ids}")
    
    assert r1_id in ids, "Should have access to R1 (IT)"
    assert r2_id in ids, "Should have access to R2 (HR explicit)"
    assert r4_id in ids, "Should have access to R4 (External explicit)"
    assert r5_id in ids, "Should have access to R5 (Batch External explicit)"
    assert r3_id not in ids, "Should NOT have access to R3 (Sales)"
    assert len(ids) == 4

    # 4. Upsert ACL Verification
    # Create same ACL as Rule A but with different condition (dept='Marketing' - effectively disabling it for IT context)
    # Rule A was: dept=IT. 
    # New Condition: "dept": "Marketing"
    # Sending CREATE again should update it.
    upsert_resp = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "conditions": {"attr": "dept", "op": "=", "val": "Marketing"}
    })
    assert upsert_resp.status_code == 200
    # Check if condition updated
    check_acl = await ac.get(f"/api/v1/realms/{realm_id}/acls?skip=0&limit=100")
    acls = check_acl.json()["items"]
    rule_a_updated = next(r for r in acls if r["resource_id"] is None and r["role_id"] == role_id)
    assert rule_a_updated["conditions"]["val"] == "Marketing"

    # 5. Resource Upsert Verification
    # R4 has ext_id. Let's create it again with new attribute 'status': 'updated'
    r4_upsert = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "r4_updated",
        "resource_type_id": rt_id,
        "external_id": ext_id,
        "attributes": {"dept": "HR", "status": "updated"}
    })
    assert r4_upsert.status_code == 200
    assert r4_upsert.json()["id"] == r4_id # Same ID
    assert r4_upsert.json()["attributes"]["status"] == "updated"

    # 6. Batch Update Verification (via External ID)
    # Using Rule C (External ID Rule) which targets R4.
    # Change condition to enforce 'status' = 'updated' (which R4 has now)
    batch_upd = await ac.post(f"/api/v1/realms/{realm_id}/acls/batch", json={
        "update": [{
            "resource_type_id": rt_id,
            "action_id": action_id,
            "role_id": role_id,
            "resource_external_id": ext_id, # Target R4 rule
            "conditions": {"attr": "status", "op": "=", "val": "updated"}
        }]
    })
    assert batch_upd.status_code == 200
    
    # 7. Batch Delete Verification (via External ID)
    # Delete Rule C (External ID Rule)
    batch_del = await ac.post(f"/api/v1/realms/{realm_id}/acls/batch", json={
        "delete": [{
            "resource_type_id": rt_id,
            "action_id": action_id,
            "role_id": role_id,
            "resource_external_id": ext_id # Target R4 rule
        }]
    })
    assert batch_del.status_code == 200
    
    # Verify deletion
    check_acl_final = await ac.get(f"/api/v1/realms/{realm_id}/acls")
    final_ids = [a["resource_id"] for a in check_acl_final.json()["items"]]
    assert r4_id not in final_ids # Should be gone
