
"""
Advanced Manifest Builder Tests
Replicating tests/test_advanced_acl_conditions.py using the new Fluent ManifestBuilder.
"""
import pytest
import pytest_asyncio
import uuid
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import StatefulABACClient, ManifestBuilder, ConditionBuilder
from httpx import ASGITransport
from app.main import app

@pytest.fixture
def sdk_client():
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)

@pytest.mark.asyncio
async def test_builder_complex_mixed_spatial(sdk_client, ac, tmp_path):
    """
    Builder version of test_complex_mixed_spatial_and_standard_conditions.
    Uses the clean fluent API.
    """
    realm_name = f"BuildSpatial_{uuid.uuid4().hex[:8]}"
    
    # Build manifest using fluent API
    builder = ManifestBuilder(realm_name, description="Mixed spatial builder test")
    
    # Define schema
    builder.add_resource_type("asset")
    builder.add_action("view")
    builder.add_role("field_agent")
    
    # Add principal
    builder.add_principal("agent1").with_role("field_agent").end()
    
    # Add resources with geometry
    builder.add_resource("ASSET-001", "asset") \
        .with_attribute("status", "active") \
        .with_attribute("classification", "restricted") \
        .with_geometry({"type": "Point", "coordinates": [23.7275, 37.9838]}) \
        .end()

    builder.add_resource("ASSET-002", "asset") \
        .with_attribute("status", "inactive") \
        .with_attribute("classification", "restricted") \
        .with_geometry({"type": "Point", "coordinates": [23.7350, 37.9900]}) \
        .end()

    builder.add_resource("ASSET-003", "asset") \
        .with_attribute("status", "active") \
        .with_attribute("classification", "public") \
        .with_geometry({"type": "Point", "coordinates": [24.0000, 38.0000]}) \
        .end()

    # ACL: View for field_agent
    # Conditions: (classification='public') OR (dwithin(5km) AND status='active')
    builder.add_acl("asset", "view") \
        .for_role("field_agent") \
        .when(
            ConditionBuilder.or_(
                ConditionBuilder.attr("classification").eq("public"),
                ConditionBuilder.and_(
                    ConditionBuilder.attr("geometry").dwithin("$context.location", 5000),
                    ConditionBuilder.attr("status").eq("active")
                )
            )
        ) \
        .end()
            
    # Apply manifest
    manifest_file = tmp_path / "builder_spatial.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
        
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Verify Access
    from common.services.security import create_access_token
    token = create_access_token({"sub": "agent1", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "asset", "action_name": "view", "return_type": "id_list"}],
            "auth_context": {"location": {"type": "Point", "coordinates": [23.7280, 37.9840]}}
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "ASSET-001" in ids   # Within 5km AND active
    assert "ASSET-003" in ids   # Public (no spatial requirement)
    assert "ASSET-002" not in ids  # Inactive

@pytest.mark.asyncio
async def test_builder_nested_conditions(sdk_client, ac, tmp_path):
    """
    Builder version of test_nested_spatial_and_principal_attribute_conditions.
    Uses the clean fluent API.
    """
    realm_name = f"BuildNested_{uuid.uuid4().hex[:8]}"
    builder = ManifestBuilder(realm_name)
    
    # Define schema
    builder.add_resource_type("facility")
    builder.add_action("enter")
    builder.add_role("security_officer")
    
    # Principals with clearance attributes
    builder.add_principal("officer_alpha") \
        .with_role("security_officer") \
        .with_attribute("clearance", 5) \
        .end()
        
    builder.add_principal("officer_beta") \
        .with_role("security_officer") \
        .with_attribute("clearance", 2) \
        .end()
    
    # Resources with geometry and clearance requirements
    builder.add_resource("FAC-HQ", "facility") \
        .with_geometry({"type": "Point", "coordinates": [23.7275, 37.9838]}) \
        .with_attribute("category", "high_security") \
        .with_attribute("min_clearance", 5) \
        .end()
            
    builder.add_resource("FAC-OFFICE", "facility") \
        .with_geometry({"type": "Point", "coordinates": [23.7350, 37.9900]}) \
        .with_attribute("category", "standard") \
        .with_attribute("min_clearance", 1) \
        .end()
            
    # ACL: Enter for security_officer
    # Conditions:
    #   (dwithin 100m) AND
    #   ((principal.clearance >= resource.min_clearance) OR (category='standard')) AND
    #   (hour >= 6 AND hour <= 22)
    builder.add_acl("facility", "enter") \
        .for_role("security_officer") \
        .when(
            ConditionBuilder.and_(
                ConditionBuilder.attr("geometry").dwithin("$context.current_location", 100),
                ConditionBuilder.or_(
                    ConditionBuilder.attr("clearance").from_principal().gte("$resource.min_clearance"),
                    ConditionBuilder.attr("category").eq("standard")
                ),
                ConditionBuilder.attr("hour").from_context().gte(6),
                ConditionBuilder.attr("hour").from_context().lte(22)
            )
        ) \
        .end()
            
    # Save and Apply
    manifest_file = tmp_path / "builder_nested.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Test 1: officer_alpha (clearance=5) near HQ during work hours
    from common.services.security import create_access_token
    token = create_access_token({"sub": "officer_alpha", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "facility", "action_name": "enter", "return_type": "id_list"}],
            "auth_context": {
                "current_location": {"type": "Point", "coordinates": [23.7276, 37.9839]},
                "hour": 14
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "FAC-HQ" in ids  # High clearance officer near HQ

