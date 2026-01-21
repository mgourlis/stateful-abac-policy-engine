
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from common.models import Resource
from common.services.geometry_service import GeometryService

import uuid

# We assume a base realm/type setup fixture exists or we create one
@pytest.fixture
async def setup_srid_test_env(ac: AsyncClient):
    # Create realm
    name = f"SRIDTestRealm_{uuid.uuid4().hex[:8]}"
    r_resp = await ac.post("/api/v1/realms", json={"name": name})
    assert r_resp.status_code == 200
    r_id = r_resp.json()["id"]
    
    # Create type
    rt_resp = await ac.post(f"/api/v1/realms/{r_id}/resource-types", json={"name": "poi"})
    assert rt_resp.status_code == 200
    rt_id = rt_resp.json()["id"]
    
    return r_id, rt_id

@pytest.mark.asyncio
async def test_resource_create_with_srid(ac: AsyncClient, setup_srid_test_env, session):
    r_id, rt_id = setup_srid_test_env
    
    # Point in WGS84 (Athens)
    # 23.7275, 37.9838
    # Using explicit SRID 4326 via dict/geojson
    payload = {
        "resource_type_id": rt_id,
        "external_id": "poi-1",
        "attributes": {"label": "Acropolis"},
        "geometry": {
            "type": "Point",
            "coordinates": [23.7275, 37.9838]
        },
        "srid": 4326
    }
    
    resp = await ac.post(f"/api/v1/realms/{r_id}/resources", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    res_id = data["id"]
    
    # Verify DB storage (should be normalized to 3857)
    # We can check by fetching directly
    res = await session.execute(select(Resource).where(Resource.id == res_id))
    resource = res.scalar_one()
    
    # GeometryService.parse checks:
    # 4326 input -> transformed to 3857
    # 23.7275, 37.9838 roughly -> 2641476.9, 4576978.3
    
    # Verify geometry is set
    assert resource.geometry is not None
    
    # Test Update with explicit SRID change (e.g. Greek Grid? No let's stick to 4326 vs implicit)
    # Update to different point
    update_payload = {
        "geometry": {
            "type": "Point",
            "coordinates": [23.0, 38.0]
        },
        "srid": 4326
    }
    
    resp_upd = await ac.put(f"/api/v1/realms/{r_id}/resources/{res_id}", json=update_payload)
    assert resp_upd.status_code == 200
    
    # Verify update
    await session.refresh(resource)
    # Just checking no error and valid geometry

@pytest.mark.asyncio
async def test_batch_resource_with_srid(ac: AsyncClient, setup_srid_test_env):
    r_id, rt_id = setup_srid_test_env
    
    batch_payload = {
        "create": [
            {
                "resource_type_id": rt_id,
                "external_id": "batch-1",
                "geometry": "POINT(23.7275 37.9838)", # WKT
                "srid": 4326 # Explicit SRID for WKT
            },
            {
                "resource_type_id": rt_id,
                "external_id": "batch-2",
                "geometry": {"type": "Point", "coordinates": [23.7275, 37.9838]},
                # No srid implies default/4326 usually
            }
        ]
    }
    
    resp = await ac.post(f"/api/v1/realms/{r_id}/resources/batch", json=batch_payload)
    assert resp.status_code == 200
    
