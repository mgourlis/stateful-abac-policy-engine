
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from common.services.security import create_access_token
from common.models import Realm, ResourceType, Action, Principal, AuthRole, PrincipalRoles
from common.services.audit import AuthorizationLog

@pytest.mark.asyncio
async def test_auth_todos(ac: AsyncClient, session):
    # Cleanup
    from common.core.redis import RedisClient
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()
    
    unique_name = "AuthTodoTestRealm"
    
    # Cleanup Realm if exists
    # We might need to drop dependent tables first for this realm if we delete it? 
    # Or cascade delete provided by DB FKs.
    check_realm = await session.execute(text("SELECT id FROM realm WHERE name = :name"), {"name": unique_name})
    old_id = check_realm.scalar()
    if old_id:
        # Drop partitions first to avoid locking or schema issues? 
        # Actually, deleting data is enough if we reuse partitions, but we want to recreate partitions to be fresh.
        # But we can't drop partitions if they contain data referenced by others? 
        # Let's delete data first.
        rid = old_id
        # Order matters for FK constraints
        await session.execute(text("DELETE FROM external_ids WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM acl WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM resource WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM principal_roles WHERE principal_id IN (SELECT id FROM principal WHERE realm_id = :rid)"), {"rid": rid})
        await session.execute(text("DELETE FROM principal WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM auth_role WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM action WHERE realm_id = :rid"), {"rid": rid})
        await session.execute(text("DELETE FROM resource_type WHERE realm_id = :rid"), {"rid": rid})
        
        # Tables might depend on realm_id
        safe_old = f"todo_{old_id}"
        await session.execute(text(f"DROP TABLE IF EXISTS resource_{safe_old} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS acl_{safe_old} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS external_ids_{safe_old} CASCADE"))
        
        await session.execute(text("DELETE FROM realm WHERE id = :id"), {"id": old_id})
        await session.commit()

    # 1. Setup Data
    realm = Realm(name=unique_name)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    rt = ResourceType(name="Doc", realm_id=realm.id)
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    await session.commit()
    await session.refresh(action)
    
    # Principal
    principal = Principal(username="TestUser", realm_id=realm.id)
    session.add(principal)
    await session.commit()
    await session.refresh(principal)
    
    # Roles
    role_owned = AuthRole(name="OwnedRole", realm_id=realm.id)
    role_not_owned = AuthRole(name="NotOwnedRole", realm_id=realm.id)
    session.add(role_owned)
    session.add(role_not_owned)
    await session.commit()
    await session.refresh(role_owned)
    
    # Assign Role
    pr = PrincipalRoles(principal_id=principal.id, role_id=role_owned.id)
    session.add(pr)
    await session.commit()
    
    # Setup Partitions (mocking minimal needed for check access trigger?)
    # The check_access logic calls `get_authorized_resources`. 
    # This DB function must exist. It relies on `acl` table.
    
    # Cleanup tables from previous (failed) runs for this realm logic?
    # Since Realm ID is new, we shouldn't collision, but let's be safe.
    
    # Setup Partitions
    safe = "authtodotest"
    parent_res = f"resource_{safe}_{realm.id}"
    parent_acl = f"acl_{safe}_{realm.id}"
    parent_ext = f"external_ids_{safe}_{realm.id}" # Added realm_id to be unique? test_abac used safe only for ext?
    # external_ids partition naming in test_abac: f"external_ids_{safe}" -> Partition of external_ids VALUES IN (realm.id)
    # So naming it external_ids_authtodotest is risky if realm_id changes but safe name implies singleton.
    # Let's append realm_id to safe string to ensure uniqueness per run if realm_id changes.
    
    safe_unique = f"todo_{realm.id}"
    parent_res = f"resource_{safe_unique}"
    parent_acl = f"acl_{safe_unique}"
    parent_ext = f"external_ids_{safe_unique}"
    
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
    
    # Create dummy Principal 0 and Role 0 to satisfy FK/PK if used as wildcard
    # We must force ID 0
    await session.execute(text("INSERT INTO principal (id, username, realm_id) VALUES (0, 'wildcard', :rid) ON CONFLICT (id) DO NOTHING"), {"rid": realm.id})
    await session.execute(text("INSERT INTO auth_role (id, name, realm_id) VALUES (0, 'wildcard', :rid) ON CONFLICT (id) DO NOTHING"), {"rid": realm.id})
    await session.commit()
    
    # Create ACL entries for Roles
    # Rule 1: OwnedRole has access.
    # We use role-based ACL: principal_id = 0 (wildcard/none) and role_id = target
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, 0, :role_id, '{"op":"true"}', '1=1')
    """), {
        "rid": realm.id, "tid": rt.id, "aid": action.id, "role_id": role_owned.id
    })
    
    # Insert ACL for NotOwnedRole (same access)
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, 0, :role_id, '{"op":"true"}', '1=1')
    """), {
        "rid": realm.id, "tid": rt.id, "aid": action.id, "role_id": role_not_owned.id
    })
    
    # Create Resource and External ID
    r_res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes)
        VALUES (:rid, :tid, '{"name": "test"}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res_id = r_res.scalar()
    
    ext_id = "EXT-TODO-1"
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:rid, :mid, :tid, :ext)
    """), {"rid": res_id, "mid": realm.id, "tid": rt.id, "ext": ext_id}) # Note: param mismatch in SQL? 
    # external_ids(resource_id, realm_id, resource_type_id, external_id)
    
    await session.commit()

    # DEBUG: Try calling get_authorized_resources directly
    import json
    from sqlalchemy.dialects import postgresql
    
    rids = [role_owned.id]

    debug_ctx = {"principal": {"id": principal.id, "username": "TestUser", "realm_id": realm.id}, "context": None}
    
    params = {
        "rid": realm.id, 
        "pid": principal.id, 
        "rids": rids, 
        "tid": rt.id, 
        "aid": action.id, 
        "ctx": json.dumps(debug_ctx)
    }

    q_star = text("SELECT * FROM get_authorized_resources(:rid, :pid, :rids, :tid, :aid, :ctx, NULL);")
    res = await session.execute(q_star, params)
        
    
    # Generate Token
    token = create_access_token({"sub": str(principal.id)})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 1: Request access with OWNED role
    resp = await ac.post("/api/v1/check-access", headers=headers, json={
        "realm_name": unique_name,
        "role_names": ["OwnedRole"],
        "req_access": [{
            "action_name": "read",
            "resource_type_name": "Doc",
            "external_resource_ids": [ext_id],
            "return_type": "decision"
        }]
    })
    assert resp.status_code == 200
    assert resp.json()["results"][0]["answer"] is True
    
    # Test 2: Request access with NOT OWNED role (should be filtered out -> no roles -> deny?)
    # If filtered out, effective roles list is empty. 
    # ACL check will check principal permissions (none) and empty roles list (none).
    # Should be False.
    resp = await ac.post("/api/v1/check-access", headers=headers, json={
        "realm_name": unique_name,
        "role_names": ["NotOwnedRole"],
        "req_access": [{
            "action_name": "read",
            "resource_type_name": "Doc",
            "external_resource_ids": [ext_id],
            "return_type": "decision"
        }]
    })
    assert resp.status_code == 200
    assert resp.json()["results"][0]["answer"] is False
    
    # Test 3: Verify Audit Log has external_resource_ids
    # We must check the DB log table
    
    log_res = await session.execute(text("""
        SELECT external_resource_ids FROM authorization_log 
        WHERE realm_id = :rid ORDER BY timestamp DESC LIMIT 1
    """), {"rid": realm.id})
    # Wait for background task? It might be async.
    # In test client (httpx combined with ASGITransport), background tasks might run before response? 
    # Or start_background_tasks?
    # Usually fastAPI background tasks run after response. 
    # We might need to wait or verify if the fixture handles it?
    # With ASGITransport and TestClient, background tasks are executed.
    
    # Let's add a small sleep just in case
    import asyncio
    await asyncio.sleep(0.1)
    
    log_row = (await session.execute(text("""
        SELECT external_resource_ids FROM authorization_log 
        WHERE realm_id = :rid AND decision = false
        ORDER BY timestamp DESC LIMIT 1
    """), {"rid": realm.id})).first()
    
    # The last request was denied (result=False), but it *found* the resource via external ID?
    # Wait, if access returned False, does it mean it found it but denied?
    # In `check_access`: 
    # if `internal_ids_filter` found (it matches external ID in DB), but `authorized_internal_ids` is empty.
    # `final_answer` is empty.
    # `external_resource_ids` passed to AuditEntry is `final_external_ids` which is empty.
    
    # Ah! If access is denied, we don't return IDs. So audit log `resource_ids` and `external_resource_ids` (authorized ones) will be empty/null.
    # This is correct for "Effective Access".
    
    # Let's check the first successful request.
    log_row_success = (await session.execute(text("""
        SELECT external_resource_ids FROM authorization_log 
        WHERE realm_id = :rid AND decision = true
        ORDER BY timestamp DESC LIMIT 1
    """), {"rid": realm.id})).first()
    
    assert log_row_success is not None
    ext_ids_log = log_row_success[0]
    # JSONB might be returned as list
    assert ext_ids_log is not None
    assert ext_id in ext_ids_log
