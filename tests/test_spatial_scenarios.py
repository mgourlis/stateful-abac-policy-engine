import pytest
import json
from httpx import AsyncClient
from sqlalchemy import text
from common.services.security import create_access_token
from common.models import Realm, ResourceType, Action, Principal

# Helper for setup
async def create_realm_scope(session, realm_name, resource_types=[]):
    # Flush Redis  
    from common.core.redis import RedisClient
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()

    realm_query = await session.execute(text("SELECT id FROM realm WHERE name = :name"), {"name": realm_name})
    existing_id = realm_query.scalar()
    if existing_id:
        safe_drop = realm_name.lower().replace(" ", "_")
        await session.execute(text(f"DROP TABLE IF EXISTS external_ids_{safe_drop} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS acl_{safe_drop}_{existing_id} CASCADE"))
        await session.execute(text(f"DROP TABLE IF EXISTS resource_{safe_drop}_{existing_id} CASCADE"))
        
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
    
    # Manual Partition Guarantee (Must match Phase 7 naming)
    safe = realm_name.lower().replace(" ", "_")
    parent_res = f"resource_{safe}_{realm.id}"
    parent_acl = f"acl_{safe}_{realm.id}"
    parent_ext = f"external_ids_{safe}"
    
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_res} PARTITION OF resource FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_acl} PARTITION OF acl FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS {parent_ext} PARTITION OF external_ids FOR VALUES IN ({realm.id}) PARTITION BY LIST (resource_type_id)"))
    
    # Create subpartitions for provided resource types
    type_map = {}
    for rt_name in resource_types:
        rt = ResourceType(name=rt_name, realm_id=realm.id)
        session.add(rt)
        await session.commit()
        await session.refresh(rt)
        type_map[rt_name] = rt
        
        safe_type = rt_name.lower().replace(" ", "_")
        
        # Subpartitions
        sub_res = f"{parent_res}_{safe_type}"
        sub_acl = f"{parent_acl}_{safe_type}"
        sub_ext = f"{parent_ext}_{safe_type}"
        
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_res} PARTITION OF {parent_res} FOR VALUES IN ({rt.id})"))
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_acl} PARTITION OF {parent_acl} FOR VALUES IN ({rt.id})"))
        await session.execute(text(f"CREATE TABLE IF NOT EXISTS {sub_ext} PARTITION OF {parent_ext} FOR VALUES IN ({rt.id})"))

    await session.commit()

    return realm, type_map

@pytest.mark.asyncio
async def test_spatial_dwithin(ac: AsyncClient, session):
    """Test ST_DWithin: Is Resource within 5km of Point?"""
    realm, tmap = await create_realm_scope(session, "SpatialRealm", ["Place"])
    rt = tmap["Place"]
    action = Action(name="visit", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="UserSpace", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: ST_DWithin(resource.geometry, context.location, 5000 meters)
    # SRID 3857 uses meters for distance
    # We'll use realistic coordinates near origin in 3857
    
    conditions = {
        "op": "st_dwithin",
        "attr": "geometry",
        "val": "POINT(0 0)",  # Will be transformed from 4326 to 3857
        "args": 10000  # 10km in meters
    }

    # Insert ACL
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    
    # 1. Nearby Resource (~5km from origin in 3857)
    # Transform from 4326 origin: (0,0) -> 3857 is about (0, 0)
    # Use ST_Transform for proper placement
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, geometry, attributes) 
        VALUES (:rid, :tid, ST_Transform(ST_SetSRID(ST_MakePoint(0, 0.04), 4326), 3857), '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r1_id = res1.scalar()

    # 2. Far Resource (~200km away in 4326 terms)
    res2 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, geometry, attributes) 
        VALUES (:rid, :tid, ST_Transform(ST_SetSRID(ST_MakePoint(2, 2), 4326), 3857), '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r2_id = res2.scalar()
    
    # Phase 8: Map resources to external IDs
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:r1, :rid, :tid, 'PLACE-NEAR'), (:r2, :rid, :tid, 'PLACE-FAR')
    """), {"r1": r1_id, "r2": r2_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "SpatialRealm",
            "req_access": [{"action_name": "visit", "resource_type_name": "Place"}]
        }
    )
    assert resp.status_code == 200
    ans = resp.json()["results"][0]["answer"]
    # Phase 8: Expect External IDs
    assert "PLACE-NEAR" in ans
    assert "PLACE-FAR" not in ans

@pytest.mark.asyncio
async def test_spatial_contains(ac: AsyncClient, session):
    """Test ST_Contains: Resource Polygon CONTAINS User Location (Context)"""
    realm, tmap = await create_realm_scope(session, "RegionRealm", ["Zone"])
    rt = tmap["Zone"]
    action = Action(name="enter", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="UserRegion", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: ST_Contains(resource.geometry, $context.location)
    conditions = {
        "op": "st_contains",
        "attr": "geometry",
        "val": "$context.location"
    }
    
    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})

    # Resource: A Polygon covering a small area in 3857 (transform from 4326)
    # Use a box around (5,5) in 4326
    res = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, geometry, attributes) 
        VALUES (:rid, :tid, ST_Transform(ST_SetSRID(ST_GeomFromText('POLYGON((4 4, 4 6, 6 6, 6 4, 4 4))'), 4326), 3857), '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r_id = res.scalar()
    
    # Phase 8: Map resource to external ID
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:rid_res, :rid, :tid, 'ZONE-POLYGON')
    """), {"rid_res": r_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    
    # 1. User inside (5,5) -> ALLOW
    resp_in = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RegionRealm",
            "req_access": [{"action_name": "enter", "resource_type_name": "Zone"}],
            "auth_context": {"location": "SRID=4326;POINT(5 5)"}
        }
    )
    assert resp_in.status_code == 200
    # Phase 8: Expect External ID
    assert "ZONE-POLYGON" in resp_in.json()["results"][0]["answer"]

    # 2. User outside (20,20) -> DENY
    resp_out = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "RegionRealm",
            "req_access": [{"action_name": "enter", "resource_type_name": "Zone"}],
            "auth_context": {"location": "SRID=4326;POINT(20 20)"}
        }
    )
    assert len(resp_out.json()["results"][0]["answer"]) == 0

@pytest.mark.asyncio
async def test_spatial_geojson(ac: AsyncClient, session):
    """Test GeoJSON Format Support"""
    realm, tmap = await create_realm_scope(session, "GeoJSONRealm", ["Site"])
    rt = tmap["Site"]
    action = Action(name="access", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="UserGeoJSON", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: ST_DWithin using GeoJSON Point
    conditions = {
        "op": "st_dwithin",
        "attr": "geometry",
        "val": '{"type":"Point","coordinates":[0,0]}', # GeoJSON Point (4326) -> Transformed to 3857
        "args": 10000 # 10km in meters
    }

    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    
    # Nearby resource (approx 5km away in 3857)
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, geometry, attributes) 
        VALUES (:rid, :tid, ST_Transform(ST_SetSRID(ST_MakePoint(0, 0.04), 4326), 3857), '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r1_id = res1.scalar()
    
    # Phase 8: Map resource to external ID
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:rid_res, :rid, :tid, 'GEOJSON-SITE-1')
    """), {"rid_res": r1_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "GeoJSONRealm",
            "req_access": [{"action_name": "access", "resource_type_name": "Site"}]
        }
    )
    assert resp.status_code == 200
    ans = resp.json()["results"][0]["answer"]
    # Phase 8: Expect External ID
    assert "GEOJSON-SITE-1" in ans

@pytest.mark.asyncio
async def test_spatial_ewkt(ac: AsyncClient, session):
    """Test EWKT Format Support"""
    realm, tmap = await create_realm_scope(session, "EWKTRealm", ["Location"])
    rt = tmap["Location"]
    action = Action(name="view", realm_id=realm.id)
    session.add(action)
    pid = Principal(username="UserEWKT", realm_id=realm.id)
    session.add(pid)
    await session.commit()
    await session.refresh(pid)

    # Rule: ST_DWithin using EWKT
    # Rule: ST_DWithin using EWKT
    # EWKT SRID=3857 is used directly (meters) defined.
    # But wait, 0 0 in 3857 is origin.
    # args 10000 = 10km.
    
    conditions = {
        "op": "st_dwithin",
        "attr": "geometry",
        "val": "SRID=3857;POINT(0 0)",
        "args": 10000
    }

    await session.execute(text("""
        INSERT INTO acl (realm_id, resource_type_id, action_id, principal_id, role_id, conditions)
        VALUES (:rid, :tid, :aid, :pid, 0, :cond)
    """), {"rid": realm.id, "tid": rt.id, "aid": action.id, "pid": pid.id, "cond": json.dumps(conditions)})
    
    # Nearby resource (using 3857 coords directly, say 5000m north)
    res1 = await session.execute(text("""
        INSERT INTO resource (realm_id, resource_type_id, geometry, attributes) 
        VALUES (:rid, :tid, ST_GeomFromText('POINT(0 5000)', 3857), '{}') RETURNING id
    """), {"rid": realm.id, "tid": rt.id})
    r1_id = res1.scalar()
    
    # Phase 8: Map resource to external ID
    await session.execute(text("""
        INSERT INTO external_ids (resource_id, realm_id, resource_type_id, external_id)
        VALUES (:rid_res, :rid, :tid, 'EWKT-LOC-1')
    """), {"rid_res": r1_id, "rid": realm.id, "tid": rt.id})
    await session.commit()

    token = create_access_token({"sub": str(pid.id)})
    resp = await ac.post(
        "/api/v1/check-access",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": "EWKTRealm",
            "req_access": [{"action_name": "view", "resource_type_name": "Location"}]
        }
    )
    assert resp.status_code == 200
    ans = resp.json()["results"][0]["answer"]
    # Phase 8: Expect External ID
    assert "EWKT-LOC-1" in ans
