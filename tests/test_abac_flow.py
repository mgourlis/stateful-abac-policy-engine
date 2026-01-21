import pytest
from httpx import AsyncClient
from sqlalchemy import text
from common.services.security import create_access_token
from common.models import Realm, ResourceType, Action, Principal
from sqlalchemy.future import select

@pytest.mark.asyncio
async def test_abac_flow(ac: AsyncClient, session):
    # Cleanup from previous runs
    from common.core.redis import RedisClient
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()
    
    realm_query = await session.execute(text("SELECT id FROM realm WHERE name = 'TestRealm'"))
    existing_realm_id = realm_query.scalar()
    if existing_realm_id:
        safe = "testrealm"
        await session.execute(text(f"DROP TABLE IF EXISTS external_ids_{safe} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS acl_{safe}_{existing_realm_id} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS resource_{safe}_{existing_realm_id} CASCADE"))
        
        await session.execute(text("DELETE FROM resource WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM acl WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM principal_roles WHERE principal_id IN (SELECT id FROM principal WHERE realm_id = :rid)"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM principal WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM auth_role WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM action WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM resource_type WHERE realm_id = :rid"), {"rid": existing_realm_id})
        await session.execute(text("DELETE FROM realm WHERE id = :rid"), {"rid": existing_realm_id})
        await session.commit()

    # 1. Setup Data
    # Realm
    realm = Realm(name="TestRealm", description="Integration Test Realm")
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    # Resource Type
    rt = ResourceType(name="Document", realm_id=realm.id)
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    
    # Action
    action = Action(name="read", realm_id=realm.id)
    session.add(action)
    await session.commit()
    await session.refresh(action)
    
    # Principal
    principal = Principal(username="UserA", realm_id=realm.id, attributes={"level": "05"})
    session.add(principal)
    await session.commit()
    await session.refresh(principal)

    # Manual partitions (matching spatial helper pattern)
    safe_name = "testrealm"
    parent_res = f"resource_{safe_name}_{realm.id}"
    parent_acl = f"acl_{safe_name}_{realm.id}"
    parent_ext = f"external_ids_{safe_name}"
    
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res} PARTITION OF resource FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl} PARTITION OF acl FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext} PARTITION OF external_ids FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    
    # Create subpartitions for Document type
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res}_document PARTITION OF {parent_res} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl}_document PARTITION OF {parent_acl} FOR VALUES IN ({rt.id})"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext}_document PARTITION OF {parent_ext} FOR VALUES IN ({rt.id})"))
    await session.commit()
        
    # ACL Rule: resource.security_level <= principal.level
    # Insert raw into ACL partition (or parent, auto-routes)
    conditions = {
        "op": "<=",
        "source": "resource",
        "attr": "security_level",
        "val": "$principal.level"
    }
    
    # Use raw SQL to insert into ACL because we didn't model ACL in SQLAlchemy models.py
    # We rely on parent table 'acl'
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions, compiled_sql)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond, NULL)
    """), {
        "rid": realm.id,
        "tid": rt.id,
        "aid": action.id,
        "pid": principal.id,
        "cond": str(conditions).replace("'", '"') # simple json conversion or import json
    })
    # Note: Trigger will compile SQL.
    await session.commit()
    
    # Insert Resources
    # Resource 1: Level 3 (Should be allowed)
    await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes)
        VALUES (:rid, :tid, '{"security_level": "03"}')
    """), {"rid": realm.id, "tid": rt.id})
    
    # Resource 2: Level 10 (Should be denied)
    # We need IDs to verify.
    # Let's insert and capture ID? RETURNING id?
    r1_res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes)
        VALUES (:rid, :tid, '{"security_level": "03"}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r1_id = r1_res.scalar()
    
    r2_res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, attributes)
        VALUES (:rid, :tid, '{"security_level": "10"}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r2_id = r2_res.scalar()
    
    # Phase 8: Map resources to external IDs
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:r1, :rid, :tid, 'DOC-LEVEL-03'), (:r2, :rid, :tid, 'DOC-LEVEL-10')
    """), {"r1": r1_id, "r2": r2_id, "rid": realm.id, "tid": rt.id})
    await session.commit()
    
    # 2. Generate Token
    token = create_access_token({"sub": str(principal.id)})
    
    # 3. Call API
    response = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "TestRealm",
            "req_access": [
                {
                    "action_name": "read",
                    "resource_type_name": "Document",
                    "return_type": "id_list"
                }
            ]
        }
    )
    
    # 4. Assert
    assert response.status_code == 200
    data = response.json()
    results = data["results"]
    assert len(results) == 1
    
    res_ids = results[0]["answer"]
    assert isinstance(res_ids, list)
    
    print(f"Authorized IDs: {res_ids}")
    
    # Phase 8: Expect external IDs
    assert "DOC-LEVEL-03" in res_ids
    assert "DOC-LEVEL-10" not in res_ids
