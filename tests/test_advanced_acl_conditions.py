"""
Advanced ACL Condition Tests - Testing complex spatial and standard conditions
with missing and provided context scenarios
"""
import pytest
import pytest_asyncio
import json
import uuid
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import StatefulABACClient
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.fixture
def sdk_client():
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)


# Note: Uses the 'ac' fixture from conftest.py


@pytest.mark.asyncio
async def test_complex_mixed_spatial_and_standard_conditions(sdk_client, ac, tmp_path, session):
    """
    Test complex ACL with mixed spatial (st_dwithin) and standard attribute conditions.
    Scenario: Field agents can view resources if they are:
    - Within 5km of the resource AND status is 'active'
    - OR classification is 'public' (regardless of location)
    """
    realm_name = f"SpatialMix_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name, "description": "Mixed spatial and attribute test"},
        "resource_types": [{"name": "asset", "is_public": False}],
        "actions": ["view"],
        "roles": [{"name": "field_agent"}],
        "principals": [{"username": "agent1", "roles": ["field_agent"]}],
        "resources": [
            {
                "type": "asset",
                "external_id": "ASSET-001",
               "geometry": {"type": "Point", "coordinates": [23.7275, 37.9838]},  # Athens
                "attributes": {"status": "active", "classification": "restricted"}
            },
            {
                "type": "asset",
                "external_id": "ASSET-002",
                "geometry": {"type": "Point", "coordinates": [23.7350, 37.9900]},  # ~1km away
                "attributes": {"status": "inactive", "classification": "restricted"}
            },
            {
                "type": "asset",
                "external_id": "ASSET-003",
                "geometry": {"type": "Point", "coordinates": [24.0000, 38.0000]},  # ~30km away
                "attributes": {"status": "active", "classification": "public"}
            }
        ],
        "acls": [
            {
                "resource_type": "asset",
                "action": "view",
                "role": "field_agent",
                "conditions": {
                    "op": "or",
                    "conditions": [
                        # Public classification (any location)
                        {"op": "=", "source": "resource", "attr": "classification", "val": "public"},
                        # Within 5km AND active status
                        {
                            "op": "and",
                            "conditions": [
                                {"op": "st_dwithin", "attr": "geometry", "val": "$context.location", "args": 5000},
                                {"op": "=", "source": "resource", "attr": "status", "val": "active"}
                            ]
                        }
                    ]
                }
            }
        ]
    }
    
    manifest_file = tmp_path / "spatial_mix.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Get token for agent1
    from common.services.security import create_access_token
    token = create_access_token({"sub": "agent1", "realm": realm_name})
    
    # Test 1: Agent at location near ASSET-001 (active, restricted)
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "asset",
                "action_name": "view",
                "return_type": "id_list"
            }],
            "auth_context": {
                "location": {"type": "Point", "coordinates": [23.7280, 37.9840]}  # Very close to ASSET-001
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    
    # Should see ASSET-001 (within 5km AND active) and ASSET-003 (public)
    assert "ASSET-001" in ids
    assert "ASSET-002" not in ids  # Not active
    assert "ASSET-003" in ids  # Public


@pytest.mark.asyncio
async def test_complex_conditions_with_missing_context(sdk_client, ac, tmp_path):
    """
    Test ACL conditions when required context variables are MISSING.
    Expected: Missing context should evaluate to NULL, causing deny decision.
    """
    realm_name = f"MissingCtx_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name, "description": "Missing context test"},
        "resource_types": [{"name": "document", "is_public": False}],
        "actions": ["read"],
        "roles": [{"name": "contractor"}],
        "principals": [{"username": "john", "roles": ["contractor"]}],
        "resources": [
            {
                "type": "document",
                "external_id": "DOC-SECURE",
                "attributes": {"level": 3}
            }
        ],
        "acls": [
            {
                "resource_type": "document",
                "action": "read",
                "role": "contractor",
                "conditions": {
                    "op": "and",
                    "conditions": [
                        # Requires context.clearance_level to be >= resource.level
                        {"op": ">=", "source": "context", "attr": "clearance_level", "val": "$resource.level"},
                        # Requires context.ip to match
                        {"op": "=", "source": "context", "attr": "ip", "val": "10.0.0.100"}
                    ]
                }
            }
        ]
    }
    
    manifest_file = tmp_path / "missing_ctx.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    await sdk_client.apply_manifest(str(manifest_file))
    
    from common.services.security import create_access_token
    token = create_access_token({"sub": "john", "realm": realm_name})
    
    # Test 1: Missing ALL context - should deny
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "document",
                "action_name": "read",
                "return_type": "id_list"
            }],
            "auth_context": {}  # Empty context
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert len(ids) == 0  # No access due to missing context
    
    # Test 2: Missing ONE required field (ip present, clearance_level missing)
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "document",
                "action_name": "read",
                "return_type": "id_list"
            }],
            "auth_context": {
                "ip": "10.0.0.100"  # Only IP, missing clearance_level
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert len(ids) == 0  # Still denied (AND condition fails)
    
    # Test 3: ALL context provided correctly
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "document",
                "action_name": "read",
                "return_type": "id_list"
            }],
            "auth_context": {
                "clearance_level": 5,  # >= 3
                "ip": "10.0.0.100"
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert "DOC-SECURE" in ids  # Now has access


@pytest.mark.asyncio
async def test_nested_spatial_and_principal_attribute_conditions(sdk_client, ac, tmp_path):
    """
    Test deeply nested conditions combining:
    - Spatial proximity (st_dwithin)
    - Principal attributes (clearance level)
    - Resource attributes (category)
    - Context variables (time window)
    """
    realm_name = f"NestedComplex_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name, "description": "Nested complex conditions"},
        "resource_types": [{"name": "facility", "is_public": False}],
        "actions": ["enter"],
        "roles": [{"name": "security_officer"}],
        "principals": [
            {"username": "officer_alpha", "roles": ["security_officer"], "attributes": {"clearance": 5}},
            {"username": "officer_beta", "roles": ["security_officer"], "attributes": {"clearance": 2}}
        ],
        "resources": [
            {
                "type": "facility",
                "external_id": "FAC-HQ",
                "geometry": {"type": "Point", "coordinates": [23.7275, 37.9838]},
                "attributes": {"category": "high_security", "min_clearance": 5}
            },
            {
                "type": "facility",
                "external_id": "FAC-OFFICE",
                "geometry": {"type": "Point", "coordinates": [23.7350, 37.9900]},
                "attributes": {"category": "standard", "min_clearance": 1}
            }
        ],
        "acls": [
            {
                "resource_type": "facility",
                "action": "enter",
                "role": "security_officer",
                "conditions": {
                    "op": "and",
                    "conditions": [
                        # Must be within 100m of facility
                        {"op": "st_dwithin", "attr": "geometry", "val": "$context.current_location", "args": 100},
                        # Clearance check OR standard facility
                        {
                            "op": "or",
                            "conditions": [
                                # High clearance allows any facility
                                {"op": ">=", "source": "principal", "attr": "clearance", "val": "$resource.min_clearance"},
                                # Standard facilities accessible to all
                                {"op": "=", "source": "resource", "attr": "category", "val": "standard"}
                            ]
                        },
                        # Time window check (business hours)
                        {"op": ">=", "source": "context", "attr": "hour", "val": 6},
                        {"op": "<=", "source": "context", "attr": "hour", "val": 22}
                    ]
                }
            }
        ]
    }
    
    manifest_file = tmp_path / "nested_complex.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    await sdk_client.apply_manifest(str(manifest_file))
    
    from common.services.security import create_access_token
    
    # Test 1: High clearance officer at HQ location during business hours
    token_alpha = create_access_token({"sub": "officer_alpha", "realm": realm_name})
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "facility",
                "action_name": "enter",
                "return_type": "id_list"
            }],
            "auth_context": {
                "current_location": {"type": "Point", "coordinates": [23.7276, 37.9839]},  # ~10m from HQ
                "hour": 14  # 2 PM
            }
        },
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert "FAC-HQ" in ids  # Within 100m AND high clearance AND business hours
    
    # Test 2: Low clearance officer at HQ (should be denied)
    token_beta = create_access_token({"sub": "officer_beta", "realm": realm_name})
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "facility",
                "action_name": "enter",
                "return_type": "id_list"
            }],
            "auth_context": {
                "current_location": {"type": "Point", "coordinates": [23.7276, 37.9839]},
                "hour": 14
            }
        },
        headers={"Authorization": f"Bearer {token_beta}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert "FAC-HQ" not in ids  # Clearance too low
    
    # Test 3: Low clearance at OFFICE (standard facility)
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "facility",
                "action_name": "enter",
                "return_type": "id_list"
            }],
            "auth_context": {
                "current_location": {"type": "Point", "coordinates": [23.7351, 37.9901]},  # Near OFFICE
                "hour": 10
            }
        },
        headers={"Authorization": f"Bearer {token_beta}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert "FAC-OFFICE" in ids  # Standard facility accessible
    
    # Test 4: Missing location context (should deny even with clearance)
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "facility",
                "action_name": "enter",
                "return_type": "id_list"
            }],
            "auth_context": {
                "hour": 14  # Only time, no location
            }
        },
        headers={"Authorization": f"Bearer {token_alpha}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    assert len(ids) == 0  # Denied due to missing spatial context


@pytest.mark.asyncio
async def test_mixed_conditions_with_partial_context(sdk_client, ac, tmp_path):
    """
    Test conditions where some context is provided and some is missing.
    Use IN operator, spatial, and standard conditions together.
    """
    realm_name = f"PartialCtx_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name, "description": "Partial context test"},
        "resource_types": [{"name": "sensor", "is_public": False}],
        "actions": ["read"],
        "roles": [{"name": "technician"}],
        "principals": [{"username": "tech1", "roles": ["technician"]}],
        "resources": [
            {
                "type": "sensor",
                "external_id": "SENSOR-TEMP-01",
                "geometry": {"type": "Point", "coordinates": [23.7275, 37.9838]},
                "attributes": {"sensor_type": "temperature", "status": "active"}
            },
            {
                "type": "sensor",
                "external_id": "SENSOR-PRESS-01",
                "geometry": {"type": "Point", "coordinates": [23.7350, 37.9900]},
                "attributes": {"sensor_type": "pressure", "status": "active"}
            },
            {
                "type": "sensor",
                "external_id": "SENSOR-HUMID-01",
                "geometry": {"type": "Point", "coordinates": [23.7400, 37.9950]},
                "attributes": {"sensor_type": "humidity", "status": "maintenance"}
            }
        ],
        "acls": [
            {
                "resource_type": "sensor",
                "action": "read",
                "role": "technician",
                "conditions": {
                    "op": "and",
                    "conditions": [
                        # Sensor type must be in allowed list
                        {"op": "in", "source": "resource", "attr": "sensor_type", "val": ["temperature", "pressure", "humidity"]},
                        # Status must be active
                        {"op": "=", "source": "resource", "attr": "status", "val": "active"},
                        # OPTIONAL: If location provided, must be within 10km (uses OR with location check)
                        {
                            "op": "or",
                            "conditions": [
                                # Either no location constraint (missing context is NULL)
                                {"op": "st_dwithin", "attr": "geometry", "val": "$context.tech_location", "args": 10000},
                                # OR context.tech_location is not provided (this won't work as expected - it will just be NULL)
                            ]
                        }
                    ]
                }
            }
        ]
    }
    
    manifest_file = tmp_path / "partial_ctx.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    await sdk_client.apply_manifest(str(manifest_file))
    
    from common.services.security import create_access_token
    token = create_access_token({"sub": "tech1", "realm": realm_name})
    
    # Test 1: With location context
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "sensor",
                "action_name": "read",
                "return_type": "id_list"
            }],
            "auth_context": {
                "tech_location": {"type": "Point", "coordinates": [23.7280, 37.9840]}
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    # Should see active sensors within 10km
    assert "SENSOR-TEMP-01" in ids
    assert "SENSOR-PRESS-01" in ids
    assert "SENSOR-HUMID-01" not in ids  # Not active
    
    # Test 2: Without location context (spatial check will fail with NULL)
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{
                "resource_type_name": "sensor",
                "action_name": "read",
                "return_type": "id_list"
            }],
            "auth_context": {}  # No location
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    result = response.json()
    ids = result["results"][0]["answer"]
    # With missing context, spatial check returns NULL/false, so OR fails
    assert len(ids) == 0
