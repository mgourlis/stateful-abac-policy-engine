import pytest
import uuid
from common.models import Realm, ResourceType, Action, Principal, AuthRole, PrincipalRoles
from common.services.security import create_access_token
from common.services.cache import CacheService
from sqlalchemy import text
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_role_cache_optimization(ac: AsyncClient, session):
    # 1. Setup Data
    unique_suffix = str(uuid.uuid4())[:8]
    realm_name = f"CacheTestRealm_{unique_suffix}"
    
    realm = Realm(name=realm_name)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)

    rt = ResourceType(name="Doc", realm_id=realm.id)
    session.add(rt)
    await session.commit()

    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    await session.commit()

    # Principal
    principal = Principal(username="CacheTestUser", realm_id=realm.id)
    session.add(principal)
    await session.commit()
    await session.refresh(principal)

    # Roles
    role_owned = AuthRole(name="OwnedCacheRole", realm_id=realm.id)
    role_unowned = AuthRole(name="UnownedCacheRole", realm_id=realm.id)
    session.add(role_owned)
    session.add(role_unowned)
    await session.commit()
    await session.refresh(role_owned)
    await session.refresh(role_unowned)

    # Join Principal to Owned Role
    pr = PrincipalRoles(principal_id=principal.id, role_id=role_owned.id)
    session.add(pr)
    await session.commit()
    
    # Setup Partitions
    safe_realm = f"cache_test_{realm.id}"
    parent_res = f"resource_{safe_realm}"
    parent_acl = f"acl_{safe_realm}"
    parent_ext = f"external_ids_{safe_realm}"

    # Drop first to be sure
    await session.execute(text(f"DROP TABLE IF EXISTS {parent_res} CASCADE"))
    await session.execute(text(f"DROP TABLE IF EXISTS {parent_acl} CASCADE"))
    await session.execute(text(f"DROP TABLE IF EXISTS {parent_ext} CASCADE"))

    await session.execute(text(f"CREATE TABLE {parent_res} PARTITION OF resource FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE {parent_acl} PARTITION OF acl FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE {parent_ext} PARTITION OF external_ids FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))

    # Create subpartitions for Document type
    await session.execute(text(f"CREATE TABLE {parent_res}_doc PARTITION OF {parent_res} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE {parent_acl}_doc PARTITION OF {parent_acl} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE {parent_ext}_doc PARTITION OF {parent_ext} FOR VALUES IN ({rt.id})"))
    await session.commit()
    
    # Create Principal 0 (Wildcard) - Crucial for DB consistency if any
    await session.execute(text("INSERT INTO principal (id, username, realm_id) VALUES (0, 'wildcard', :rid) ON CONFLICT (id) DO NOTHING"), {"rid": realm.id})
    await session.commit()

    # 2. Setup ACL 
    # Use '1=1' for compiled_sql to match test_auth_todos convention, though TRUE should work.
    
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, 0, :role_id, '{"op":"true"}', '1=1')
    """), {
        "rid": realm.id, 
        "tid": rt.id, 
        "aid": action.id, 
        "role_id": role_owned.id
    })
    
    # Insert resource to find
    # We use external ID methodology like test_auth_todos.py
    ext_id = "EXT-CACHE-1"
    
    # Insert Resource + External ID
    # Note: test_auth_todos uses `external_ids` table.
    res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes)
        VALUES (:rid, :tid, '{"name": "test_res"}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res_id = res.scalar()
    
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:rid, :realm_id, :tid, :ext_id)
    """), {"rid": res_id, "realm_id": realm.id, "tid": rt.id, "ext_id": ext_id})
    
    await session.commit()
    
    # Generate Token
    token = create_access_token({"sub": str(principal.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. First Request - Owned Role -> Expect Decision TRUE
    resp = await ac.post("/api/v1/check-access", headers=headers, json={
        "realm_name": realm_name,
        "role_names": ["OwnedCacheRole"],
        "auth_context": {},
        "req_access": [{
            "action_name": "read",
            "resource_type_name": "Doc",
            "external_resource_ids": [ext_id],
            "return_type": "decision"
        }]
    })
    
    if resp.status_code != 200:
        print(f"DEBUG: Check access failed: {resp.json()}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["answer"] is True

    # 4. Verify Cache Content
    realm_map = await CacheService.get_realm_map(realm_name)
    assert f"role:{role_owned.name}" in realm_map
    assert realm_map[f"role:{role_owned.name}"] == str(role_owned.id)
    assert f"role:{role_unowned.name}" in realm_map
    assert realm_map[f"role:{role_unowned.name}"] == str(role_unowned.id)
    
    print("DEBUG: Cache Verification PASSED - Roles found in Map")

    # 5. Test Optimization Logic w/ Unowned Role
    # We request "UnownedCacheRole". 
    # Logic: 
    # 1. Resolve Name -> ID via Cache (Should find ID)
    # 2. Check Ownership in DB (Should return False/Empty)
    # 3. Exec ACL check with Empty Role List -> access denied (unless public access, but we set ACL only for OwnedRole)
    
    resp_unowned = await ac.post("/api/v1/check-access", headers=headers, json={
        "realm_name": realm_name,
        "role_names": ["UnownedCacheRole"],
        "auth_context": {},
        "req_access": [{
            "action_name": "read",
            "resource_type_name": "Doc",
            "return_type": "decision"
        }]
    })
    assert resp_unowned.status_code == 200
    # Should be False because we filtered out the unowned role, so effectively we checked with NO roles.
    # And our ACL requires OwnedRole.
    assert resp_unowned.json()["results"][0]["answer"] is False
    print("DEBUG: Logic Verification PASSED - Unowned Role rejected")

    # 6. Test Invalid Role
    # Request "NonExistentRole". Cache resolve returns None. List empty. Access False.
    resp_invalid = await ac.post("/api/v1/check-access", headers=headers, json={
        "realm_name": realm_name,
        "role_names": ["NonExistentRole"],
        "auth_context": {},
        "req_access": [{
            "action_name": "read",
            "resource_type_name": "Doc",
            "return_type": "decision"
        }]
    })
    assert resp_invalid.status_code == 200
    assert resp_invalid.json()["results"][0]["answer"] is False
    print("DEBUG: Logic Verification PASSED - Invalid Role rejected")
