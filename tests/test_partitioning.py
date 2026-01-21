
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from common.models import Realm
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

@pytest.mark.asyncio
async def test_partition_creation(ac: AsyncClient, session: AsyncSession):
    # 1. Create Realm via API (Should create partitioned tables)
    unique_suffix = str(uuid.uuid4())[:8]
    realm_name = f"PartTestRealm_{unique_suffix}"
    
    resp = await ac.post("/api/v1/realms", json={
        "name": realm_name,
        "description": "Partition Test Realm",
        "is_active": True
    })
    assert resp.status_code == 200
    realm_data = resp.json()
    realm_id = realm_data["id"]
    
    # Verify Realm-level tables are partitioned
    # We check pg_class or try to create a partition on it manually to see if it allows?
    # Or check if it has 'r' (relation) or 'p' (partitioned table) in pg_class.relkind?
    # 'p' is for partitioned table.
    
    # Check resource_<rid>
    res = await session.execute(text(f"SELECT relkind FROM pg_class WHERE relname = 'resource_{realm_id}'"))
    kind = res.scalar()
    # Handle possible bytes return
    if isinstance(kind, bytes):
        kind = kind.decode('utf-8')
    assert kind == 'p', f"resource_{realm_id} should be a partitioned table (relkind='p')"

    # Check acl_<rid>
    res = await session.execute(text(f"SELECT relkind FROM pg_class WHERE relname = 'acl_{realm_id}'"))
    kind = res.scalar()
    if isinstance(kind, bytes):
        kind = kind.decode('utf-8')
    assert kind == 'p'

    # Check external_ids_<rid>
    res = await session.execute(text(f"SELECT relkind FROM pg_class WHERE relname = 'external_ids_{realm_id}'"))
    kind = res.scalar()
    if isinstance(kind, bytes):
        kind = kind.decode('utf-8')
    assert kind == 'p'

    # 2. Create Resource Type via API (Should create sub-partitions)
    resp_rt = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={
        "name": "PartDoc"
    })
    assert resp_rt.status_code == 200
    rt_data = resp_rt.json()
    rt_id = rt_data["id"]
    
    # Verify Sub-partitions exist
    # resource_<rid>_<tid> should exist and be a table ('r') or partition?
    # It is a leaf partition, so 'r' (ordinary table) or 'p' if further partitioned? 
    # Usually 'r' if it holds data.
    
    target_table = f"resource_{realm_id}_{rt_id}"
    res = await session.execute(text(f"SELECT relname FROM pg_class WHERE relname = '{target_table}'"))
    found = res.scalar()
    assert found == target_table, f"Sub-partition {target_table} not found"

    # Verify inheritance/attachment
    # SELECT inherits from pg_inherits... slightly complex.
    # We can just try to insert into parent partition (resource_<rid>) with the correct type_id and see if it works without error.
    
    # Insert Resource via API (should succeed and route to sub-partition)
    resp_res = await ac.post(f"/api/v1/realms/{realm_id}/resources", json={
        "name": "test_part",
        "resource_type_id": rt_id,
        "attributes": {"name": "test_part"}
    })
    if resp_res.status_code != 200:
        print(f"DEBUG: Resource Create Failed: {resp_res.json()}")
    assert resp_res.status_code == 200
    res_id = resp_res.json()["id"]
    
    # Verify row exists in sub-partition table directy
    count = await session.execute(text(f"SELECT COUNT(*) FROM {target_table} WHERE id = :id"), {"id": res_id})
    assert count.scalar() == 1

