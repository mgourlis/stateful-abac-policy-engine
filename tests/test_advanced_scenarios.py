import pytest
import json
from httpx import AsyncClient
from sqlalchemy import text
from common.services.security import create_access_token
from common.models import Realm, ResourceType, Action, Principal, AuthRole, PrincipalRoles
from sqlalchemy.future import select

# Helper for setup
async def create_realm_scope(session, realm_name, resource_type_name):
    from common.core.config import settings
    import redis.asyncio as redis
    r = redis.from_url(settings.REDIS_URL)
    await r.flushall()
    await r.aclose()
    await r.aclose()

    # Cleanup from previous runs
    realm_query = await session.execute(text("SELECT id FROM realm WHERE name = :name"), {"name": realm_name})
    existing_id = realm_query.scalar()
    if existing_id:
        safe = realm_name.lower().replace(" ", "_")
        await session.execute(text(f"DROP TABLE IF EXISTS external_ids_{safe} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS acl_{safe}_{existing_id} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS resource_{safe}_{existing_id} CASCADE"))
        
        await session.execute(text("DELETE FROM resource WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM acl WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM principal_roles WHERE principal_id IN (SELECT id FROM principal WHERE realm_id = :rid)"), {"rid": existing_id})
        await session.execute(text("DELETE FROM principal WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM auth_role WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM action WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM resource_type WHERE realm_id = :rid"), {"rid": existing_id})
        await session.execute(text("DELETE FROM realm WHERE id = :rid"), {"rid": existing_id})
        await session.commit()

    # Setup Realm
    realm = Realm(name=realm_name)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    # Create resource type
    rt = ResourceType(name=resource_type_name, realm_id=realm.id)
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    
    # Manual Partition Workaround
    safe_name = realm_name.lower().replace(" ", "_")
    safe_type = resource_type_name.lower().replace(" ", "_")
    parent_res = f"resource_{safe_name}_{realm.id}"
    parent_acl = f"acl_{safe_name}_{realm.id}"
    parent_ext = f"external_ids_{safe_name}"
    
    # Create parent partitions
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res} PARTITION OF resource FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl} PARTITION OF acl FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext} PARTITION OF external_ids FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    
    # Create subpartitions for this resource type
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res}_{safe_type} PARTITION OF {parent_res} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl}_{safe_type} PARTITION OF {parent_acl} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext}_{safe_type} PARTITION OF {parent_ext} FOR VALUES IN ({rt.id})"))
    await session.commit()

    return realm, rt

@pytest.mark.asyncio
async def test_logical_operators(ac: AsyncClient, session):
    """Test AND / OR nested logic"""
    realm, rt = await create_realm_scope(session, "LogicRealm", "Doc")
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="LogicUser", realm_id=realm.id, attributes={"dept": "IT", "clearance": 2})
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: (dept='IT' AND clearance >= 2) OR (dept='HR')
    conditions = {
        "op": "or",
        "conditions": [
            {
                "op": "and",
                "conditions": [
                    {"op": "=", "source": "principal", "attr": "dept", "val": "IT"},
                    {"op": ">=", "source": "principal", "attr": "clearance", "val": 2} # Numeric
                ]
            },
            {"op": "=", "source": "principal", "attr": "dept", "val": "HR"}
        ]
    }

    # Insert ACL
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    await session.commit()
    
    # DEBUG: Check ACL
    acl_rows = await session.execute(text("SELECT compiled_sql FROM acl WHERE realm_id = :rid"), {"rid": realm.id})
    for row in acl_rows:
        print(f"ACL Row: {row}")

    # Resource (Attributes don't matter much here as rule relies on principal, but let's have one)
    res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res_id = res.scalar()
    
    # Phase 8: Map resource to external ID
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:res, :rid, :tid, 'LOGIC-DOC-1')
    """), {"res": res_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    # Check Access
    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "LogicRealm",
            "req_access": [{"action_name": "read", "resource_type_name": "Doc"}]
        }
    )
    assert resp.status_code == 200
    # Phase 8: Expect external ID
    assert "LOGIC-DOC-1" in resp.json()["results"][0]["answer"]

@pytest.mark.asyncio
async def test_context_placeholders(ac: AsyncClient, session):
    """Test $context.ip and other dynamic placeholders"""
    realm, rt = await create_realm_scope(session, "ContextRealm", "File")
    action = Action(name="download", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="ContextUser", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: context.ip = '10.0.0.1'
    conditions = {
        "op": "=",
        "source": "context",
        "attr": "ip",
        "val": "10.0.0.1"
    }

    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    
    # Resource
    res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res_id = res.scalar()
    
    # Phase 8: Map resource to external ID  
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:res, :rid, :tid, 'FILE-CTX-1')
    """), {"res": res_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    
    # 1. Valid Context
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "ContextRealm",
            "req_access": [{"action_name": "download", "resource_type_name": "File"}],
            "auth_context": {"ip": "10.0.0.1"}
        }
    )
    assert resp.status_code == 200
    # Phase 8: Expect external ID
    assert "FILE-CTX-1" in resp.json()["results"][0]["answer"]

    # 2. Invalid Context
    resp_fail = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "ContextRealm",
            "req_access": [{"action_name": "download", "resource_type_name": "File"}],
            "auth_context": {"ip": "192.168.1.1"}
        }
    )
    assert len(resp_fail.json()["results"][0]["answer"]) == 0

@pytest.mark.asyncio
async def test_rbac_scenario(ac: AsyncClient, session):
    """Test Role-Based logic where rule is attached to a Role"""
    realm, rt = await create_realm_scope(session, "RBACRealm", "Report")
    action = Action(name="view", realm_id=realm.id)
    session.add(action)
    
    # Role
    role = AuthRole(name="Manager", realm_id=realm.id)
    session.add(role)
    await session.commit()
    await session.refresh(role)

    # Principal with Role
    pid = Principal(username="MgrUser", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    pr = PrincipalRoles(principal_id=pid.id, role_id=role.id)
    session.add(pr)
    await session.commit()

    # Rule attached to Role (principal_id=0, role_id=role.id)
    # Rule: TRUE (Allow all for managers)
    # Or condition: resource.secret = false
    conditions = {
        "op": "=",
        "source": "resource",
        "attr": "secret",
        "val": False
    }

    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, 0, :rid_role, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "rid_role": role.id, "cond": json.dumps(conditions)})
    await session.commit()

    # Resources
    # Secret=False (Allowed)
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{"secret": false}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res1_id = res1.scalar()

    # Secret=True (Denied)
    res2 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{"secret": true}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    res2_id = res2.scalar()
    
    # Phase 8: Map resources to external IDs
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:r1, :rid, :tid, 'REPORT-PUBLIC'), (:r2, :rid, :tid, 'REPORT-SECRET')
    """), {"r1": res1_id, "r2": res2_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RBACRealm",
            "req_access": [{"action_name": "view", "resource_type_name": "Report"}]
        }
    )
    ans = resp.json()["results"][0]["answer"]
    # Phase 8: Expect external IDs
    assert "REPORT-PUBLIC" in ans
    assert "REPORT-SECRET" not in ans

@pytest.mark.asyncio
async def test_in_operator(ac: AsyncClient, session):
    """Test IN operator for checking lists"""
    realm, rt = await create_realm_scope(session, "InOpRealm", "Post")
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="UserIn", realm_id=realm.id)
    session. add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: resource.status IN ['published', 'archived']
    conditions = {
        "op": "in",
        "source": "resource",
        "attr": "status",
        "val": ["published", "archived"]
    }

    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    
    # Resources
    r1 = await session.execute(text("INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{\"status\": \"published\"}') RETURNING id"), {"rid": realm.id, "tid": rt.id})
    r2 = await session.execute(text("INSERT INTO resource (realm_id, resource_type_id, attributes) VALUES (:rid, :tid, '{\"status\": \"draft\"}') RETURNING id"), {"rid": realm.id, "tid": rt.id})
    r1_id = r1.scalar()
    r2_id = r2.scalar()
    
    # Phase 8: Map resources to external IDs
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:r1, :rid, :tid, 'POST-PUBLISHED'), (:r2, :rid, :tid, 'POST-DRAFT') 
    """), {"r1": r1_id, "r2": r2_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "InOpRealm",
            "req_access": [{"action_name": "read", "resource_type_name": "Post"}]
        }
    )
    ans = resp.json()["results"][0]["answer"]
    # Phase 8: Expect external IDs
    assert "POST-PUBLISHED" in ans
    assert "POST-DRAFT" not in ans
