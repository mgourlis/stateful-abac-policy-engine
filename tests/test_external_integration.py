import pytest
from httpx import AsyncClient
from sqlalchemy import text
from common.services.security import create_access_token
from common.models import Realm, ResourceType, Action, Principal, AuthRole
import json

# Setup Helper (reused)
async def create_external_realm(session, realm_name, resource_types=[]):
    from common.core.redis import RedisClient
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()

    realm_query = await session.execute(text("SELECT id FROM realm WHERE name = :name"), {"name": realm_name})
    existing_id = realm_query.scalar()
    if existing_id:
        safe_drop = realm_name.lower().replace(" ", "_")
        await session.execute(text(f"DROP TABLE IF EXISTS external_ids_{safe_drop} CASCADE"))
        # ACL and Resource use ID suffix in legacy triggers
        await session.execute(text(f"DROP TABLE IF EXISTS acl_{safe_drop}_{existing_id} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS resource_{safe_drop}_{existing_id} CASCADE"))
        
        await session.execute(text("DELETE FROM resource WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM acl WHERE realm_id = :rid"), {"rid": existing_id})
        # Delete mappings first
        await session.execute(text("DELETE FROM principal_roles WHERE principal_id IN (SELECT id FROM principal WHERE realm_id = :rid)"), {"rid": existing_id})
        await session.execute(text("DELETE FROM auth_role WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM principal WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM resource_type WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM action WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM realm WHERE id = :rid"), {"rid": existing_id})
        await session.commit()

    realm = Realm(name=realm_name)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    

    # Sentinel Seeds (Dummies)
    dummy_p = Principal(username="dummy_sentinel", realm_id=realm.id)
    dummy_r = AuthRole(name="dummy_sentinel", realm_id=realm.id)
    session.add_all([dummy_p, dummy_r])
    await session.commit()
    await session.refresh(dummy_p)
    await session.refresh(dummy_r)

    # Manual Partitions (Must match Schema Triggers)
    safe = realm_name.lower().replace(" ", "_")
    
    # 1. Resource & ACL: Legacy triggers likely use {name}_{id}
    # We inferred this from "resource_extrealm_38" error.
    parent_res = f"resource_{safe}_{realm.id}"
    parent_acl = f"acl_{safe}_{realm.id}"
    
    # 2. External IDs: New trigger uses {name} only (verified in migration)
    parent_ext = f"external_ids_{safe}"
    
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res} PARTITION OF resource FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl} PARTITION OF acl FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext} PARTITION OF external_ids FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))

    # Manual Subpartitions for provided Resource Types
    # To bypass flaky Triggers
    type_map = {}
    for rt_name in resource_types:
        rt = ResourceType(name=rt_name, realm_id=realm.id)
        session.add(rt)
        await session.commit()
        await session.refresh(rt)
        type_map[rt_name] = rt
        
        safe_type = rt_name.lower().replace(" ", "_")
        
        # Subpartitions
        # Check if parent exists? We created it above.
        # acl_{safe}
        # acl_{safe}_{safe_type}
        # The parent was created as 'acl_{safe}'.
        # Subpartition name: acl_{safe}_{safe_type}
        # Trigger naming: acl_{safe}_{safe_type} (using formatted names)
        
        # subpartition naming usually follows parent_{typename} or parent_{safe_typename}
        # Migration logic shows: subpartition_table := format('%s_%s', parent_table, safe_resource_type_name);
        
        sub_acl = f"{parent_acl}_{safe_type}"
        sub_res = f"{parent_res}_{safe_type}"
        sub_ext = f"{parent_ext}_{safe_type}"
        
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_acl} PARTITION OF {parent_acl} FOR VALUES IN ({rt.id})"))
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_res} PARTITION OF {parent_res} FOR VALUES IN ({rt.id})"))
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_ext} PARTITION OF {parent_ext} FOR VALUES IN ({rt.id})"))
    
    await session.commit()
    return realm, dummy_p, dummy_r, type_map

 

@pytest.mark.asyncio
async def test_active_roles(ac: AsyncClient, session):
    """Test RBAC Override via role_names"""
    realm, dummy_p, dummy_r, tmap = await create_external_realm(session, "RoleRealm", ["Report"])
    rt = tmap["Report"]
    # session.add(rt) -> Already added
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    
    # User has NO roles initially (or irrelevant one)
    pid = Principal(username="RoleUser", realm_id=realm.id)
    session.add(pid)
    
    # Roles
    role_mgr = AuthRole(name="Manager", realm_id=realm.id)
    role_gst = AuthRole(name="Guest", realm_id=realm.id)
    session.add_all([role_mgr, role_gst])
    await session.commit()
    await session.refresh(pid)

    # Assign Manager Role to User
    await session.execute(text("INSERT INTO principal_roles (principal_id, role_id) VALUES (:pid, :rid)"), {"pid": pid.id, "rid": role_mgr.id})
    await session.commit()

    # Rule: Manager can read
    # role_id is set in ACL. Principal ID set to dummy_p (Sentinel)
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, NULL, :role, NULL, 'TRUE')
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "role": role_mgr.id})
    
    # Resource
    res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res_id = res.scalar()
    await session.commit()
    
    # KEY CHANGES for Phase 8: Mapped Resource for Active Role Test
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:id, :rid, :tid, 'MGR-RES-1')
    """), {"id": res_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    
    # 1. Request WITHOUT roles -> ALLOW (Default uses assigned roles, which includes Manager)
    resp1 = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RoleRealm",
            "req_access": [{"action_name": "read", "resource_type_name": "Report"}]
        }
    )
    assert resp1.status_code == 200
    assert "MGR-RES-1" in resp1.json()["results"][0]["answer"]
    
    # 2. Request WITH 'Manager' role -> ALLOW
    resp2 = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RoleRealm",
            "role_names": ["Manager"],
            "req_access": [{"action_name": "read", "resource_type_name": "Report"}]
        }
    )
    assert resp2.status_code == 200
    # Phase 8: Expect External ID "MGR-RES-1" by default
    assert "MGR-RES-1" in resp2.json()["results"][0]["answer"]

@pytest.mark.asyncio
async def test_external_ids(ac: AsyncClient, session):
    """Test External ID Resolution"""
    realm, dummy_p, dummy_r, tmap = await create_external_realm(session, "ExtRealm", ["Image"])
    rt = tmap["Image"]
    action = Action(name="view", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="ExtUser", realm_id=realm.id, attributes={"role": "admin"})
    session.add(pid)
    await session.commit()
    await session.refresh(pid)
    
    # Rule: Allow all (TRUE)
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, :pid, NULL, NULL, 'TRUE')
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id})
    
    # Resources
    # Internal 100 -> External "IMG-A"
    # Internal 200 -> External "IMG-B"
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    id1 = res1.scalar()
    
    res2 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    id2 = res2.scalar()
    
    await session.commit()
    
    # Map External IDs
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:id1, :rid, :tid, 'IMG-A'), (:id2, :rid, :tid, 'IMG-B')
    """), {"id1": id1, "id2": id2, "rid": realm.id, "tid": rt.id})
    await session.commit()
    
    token = create_access_token({"sub": str(pid.id)})
    
    # Request for "IMG-A"
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "ExtRealm",
            "req_access": [{
                "action_name": "view", 
                "resource_type_name": "Image",
                "external_resource_ids": ["IMG-A", "IMG-UNKNOWN"]
            }]
        }
    )
    assert resp.status_code == 200
    ans = resp.json()["results"][0]["answer"]
    
    # Should contain "IMG-A", check Mapping
    assert "IMG-A" in ans
    assert "IMG-B" not in ans # Not requested
    assert id1 not in ans # Should be external format
    assert len(ans) == 1

@pytest.mark.asyncio
async def test_reverse_mapping(ac: AsyncClient, session):
    """Test Reverse Mapping: Unfiltered Request -> External IDs"""
    realm, dummy_p, dummy_r, tmap = await create_external_realm(session, "RevRealm", ["Doc"])
    rt = tmap["Doc"]
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="RevUser", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)
    
    # Rule: Allow All
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, :pid, NULL, NULL, 'TRUE')
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id})
    
    # Resources: 
    # 1. EXT-100 (Mapped)
    # 2. INT-ONLY (Unmapped)
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    id1 = res1.scalar()
    
    res2 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    id2 = res2.scalar()
    
    await session.commit()
    
    # Map only ID1
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:id1, :rid, :tid, 'EXT-100')
    """), {"id1": id1, "rid": realm.id, "tid": rt.id})
    await session.commit()
    
    token = create_access_token({"sub": str(pid.id)})
    
    # 1. Request WITHOUT filter
    # Expect: ["EXT-100"] 
    # (id2 is authorized internal, but has no external ID, so it is hidden)
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RevRealm",
            "req_access": [{"action_name": "read", "resource_type_name": "Doc"}]
        }
    )
    assert resp.status_code == 200
    ans = resp.json()["results"][0]["answer"]
    
    assert "EXT-100" in ans
    assert id2 not in ans
    assert len(ans) == 1
