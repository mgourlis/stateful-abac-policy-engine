import pytest
import uuid
import sys
import os
import json

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from httpx import ASGITransport, AsyncClient
from app.main import app



@pytest.fixture
async def ac():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_manifest_export_sdk(sdk_client):
    """Test SDK manifest export functionality"""
    client = sdk_client
    realm_name = client.realm
    
    async with client.connect(token=None):
        # Create a realm with some entities
        # connect auto-creates realm. update description?
        await client.realms.update(description="Test realm for export")
        
        # rid = (await client.realms.get()).id
        # Use try/except to avoid errors if they already exist (shared realm)
        try: await client.resource_types.create(name="Document")
        except: pass
        try: await client.actions.create("read") 
        except: pass
        try: await client.roles.create("Reader")
        except: pass
        try: await client.principals.create("testuser", roles=["Reader"])
        except: pass
        try: await client.resources.create(resource_type_name="Document", external_id="DOC-001")
        except: pass
        
        # Export manifest
        manifest = await client.export_manifest(realm_name)
        
    # Verify structure
    assert "realm" in manifest
    assert manifest["realm"]["name"] == realm_name
    assert "resource_types" in manifest
    # assert len(manifest["resource_types"]) == 1 # Shared realm might have more
    assert any(rt["name"] == "Document" for rt in manifest["resource_types"])
    assert "actions" in manifest
    assert "read" in manifest["actions"]
    assert "roles" in manifest
    assert any(r["name"] == "Reader" for r in manifest["roles"])
    assert "principals" in manifest
    assert any(p["username"] == "testuser" for p in manifest["principals"])
    # assert manifest["principals"][0]["username"] == "testuser"
    # assert "Reader" in manifest["principals"][0]["roles"]
    assert "resources" in manifest
    assert any(r["external_id"] == "DOC-001" for r in manifest["resources"])

@pytest.mark.asyncio
async def test_manifest_api_export_api(ac):
    """Test API manifest export endpoint"""
    realm_name = f"APIExportTest_{uuid.uuid4().hex[:8]}"
    
    # Create a realm with some entities via API
    response = await ac.post("/api/v1/realms", json={"name": realm_name, "description": "Test"})
    try:
        assert response.status_code == 200
        realm_data = response.json()
        realm_id = realm_data["id"]
        
        response = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "File"})
        assert response.status_code == 200
        
        # Export via API
        response = await ac.get(f"/api/v1/realms/{realm_name}/manifest")
        assert response.status_code == 200
        
        manifest = response.json()
        assert manifest["realm"]["name"] == realm_name
        assert len(manifest["resource_types"]) == 1
    finally:
        # Cleanup via API
        try:
            # We need realm_id to delete via API? Or name?
            # API DELETE /realms/{id}
             if 'realm_id' in locals():
                await ac.delete(f"/api/v1/realms/{realm_id}")
        except: pass

@pytest.mark.asyncio
async def test_manifest_apply_mode_update(ac, tmp_path):
    """Test manifest apply in update mode (default upsert)"""
    realm_name = f"UpdateMode_{uuid.uuid4().hex[:8]}"
    
    # Create initial manifest
    manifest1 = {
        "realm": {
            "name": realm_name,
            "description": "Initial"
        },
        "resource_types": [{"name": "TypeA", "is_public": False}],
        "actions": ["read"]
    }
    
    manifest_file = tmp_path / "manifest1.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest1, f)
    
    # Apply first time
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)
    
    try:
        async with client.connect(token=None):
            result = await client.apply_manifest(str(manifest_file), mode='update')
        assert "realm" in result
        assert result["realm"] in ["created", "updated"]
        
        # Verify realm exists
        async with client.connect(token=None):
            realm = await client.realms.get()
            assert realm.description == "Initial"
        
            # Apply again with updated description
            manifest1["realm"]["description"] = "Updated"
            with open(manifest_file, 'w') as f:
                json.dump(manifest1, f)
            
            result = await client.apply_manifest(str(manifest_file), mode='update')
            assert result["realm"] == "updated"
            
            # Verify update
            realm = await client.realms.get()
            assert realm.description == "Updated"
    finally:
        try:
             async with client.connect(token=None):
                await client.realms.delete()
        except: pass

@pytest.mark.asyncio
async def test_manifest_apply_mode_create(ac, tmp_path):
    """Test manifest apply in create mode (skip if exists)"""
    realm_name = f"CreateMode_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {
            "name": realm_name,
            "description": "First"
        }
    }
    
    manifest_file = tmp_path / "manifest_create.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    # Apply first time
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)
    
    try:
        # Do NOT connect() as it auto-creates realm. Use direct apply (which creates temp client)
        result = await client.apply_manifest(str(manifest_file), mode='create')
        assert result["realm"] == "created"
        
        # Apply again with create mode - should skip
        manifest["realm"]["description"] = "Second"
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f)
        
        result = await client.apply_manifest(str(manifest_file), mode='create')
        assert result["realm"] == "skipped"
        
        # Verify description NOT updated
        async with client.connect(token=None):
             realm = await client.realms.get()
             assert realm.description == "First"
    finally:
        try:
             async with client.connect(token=None):
                await client.realms.delete()
        except: pass

@pytest.mark.asyncio
async def test_manifest_apply_mode_replace(ac, tmp_path):
    """Test manifest apply in replace mode (delete and recreate)"""
    realm_name = f"ReplaceMode_{uuid.uuid4().hex[:8]}"
    
    # Create initial realm with entities
    manifest1 = {
        "realm": {
            "name": realm_name,
            "description": "Original"
        },
        "resource_types": [{"name": "OldType", "is_public": False}]
    }
    
    manifest_file = tmp_path / "manifest_replace.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest1, f)
    
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)
    
    try:
        # We can use update mode first to seed it
        async with client.connect(token=None):
            await client.apply_manifest(str(manifest_file), mode='update')
            
            # Verify old type exists
            types = await client.resource_types.list()
            assert len(types) == 1
            assert types[0].name == "OldType"
            
            # Apply with replace mode and new entities
            manifest2 = {
                "realm": {
                    "name": realm_name,
                    "description": "Replaced"
                },
                "resource_types": [{"name": "NewType", "is_public": False}]
            }
            
            with open(manifest_file, 'w') as f:
                json.dump(manifest2, f)
            
            result = await client.apply_manifest(str(manifest_file), mode='replace')
            assert "realm_deleted" in result
            assert result["realm"] == "created"
            
            # Invalidate lookup cache because ID changed
            client.lookup.invalidate_realm(realm_name)
            
            # Verify realm was replaced
            realm = await client.realms.get()
            assert realm.description == "Replaced"
            
            # Verify old type is gone, new type exists
            types = await client.resource_types.list()
            assert len(types) == 1
            assert types[0].name == "NewType"
    finally:
        try:
             async with client.connect(token=None):
                await client.realms.delete()
        except: pass
