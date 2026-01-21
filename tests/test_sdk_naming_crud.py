
import pytest
import uuid
import sys
import os

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from httpx import ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_resource_type_crud_by_name(sdk_client):
    client = sdk_client
    name = f"Type-{uuid.uuid4().hex[:4]}"
    
    async with client.connect(token=None):
        # Create
        rt = await client.resource_types.create(name=name)
        assert rt.id is not None
        
        # Get by Name 
        fetched = await client.resource_types.get(type_id=name)
        assert fetched.id == rt.id
        
        # Update by Name
        updated = await client.resource_types.update(type_id=name, is_public=True)
        assert updated.is_public is True
        
        # Delete by Name
        await client.resource_types.delete(type_id=name)
        
        # Verify Gone
        try:
            await client.resource_types.get(type_id=name)
            assert False, "Should have thrown ValueError or ApiError"
        except Exception:
            pass

@pytest.mark.asyncio
async def test_action_crud_by_name(sdk_client):
    client = sdk_client
    name = f"act-{uuid.uuid4().hex[:4]}"
    
    async with client.connect(token=None):
        act = await client.actions.create(name)
        
        # Get by Name
        fetched = await client.actions.get(name)
        assert fetched.id == act.id
        
        # Update by Name
        new_name = f"{name}-upd"
        updated = await client.actions.update(name, name=new_name)
        assert updated.name == new_name
        
        # Get by New Name
        fetched2 = await client.actions.get(new_name)
        assert fetched2.id == act.id
        
        # Delete by Name
        await client.actions.delete(new_name)

@pytest.mark.asyncio
async def test_role_crud_by_name(sdk_client):
    client = sdk_client
    name = f"Role-{uuid.uuid4().hex[:4]}"
    
    async with client.connect(token=None):
        role = await client.roles.create(name, attributes={"power": 10})
        
        # Get by Name
        fetched = await client.roles.get(name)
        assert fetched.id == role.id
        assert fetched.attributes["power"] == 10
        
        # Update by Name
        updated = await client.roles.update(name, attributes={"power": 20})
        assert updated.attributes["power"] == 20
        
        # Delete by Name
        await client.roles.delete(name)

@pytest.mark.asyncio
async def test_principal_crud_by_name(sdk_client):
    client = sdk_client
    name = f"user-{uuid.uuid4().hex[:4]}"
    
    async with client.connect(token=None):
        user = await client.principals.create(name)
        
        # Get by Name
        fetched = await client.principals.get(name)
        assert fetched.id == user.id
        
        # Update by Name
        updated = await client.principals.update(name, attributes={"email": "alice@test.com"})
        assert updated.attributes["email"] == "alice@test.com"
        
        # Delete by Name
        await client.principals.delete(name)

@pytest.mark.asyncio
async def test_resource_external_id_crud(sdk_client):
    client = sdk_client
    realm_name = client.realm
    
    async with client.connect(token=None):
        # Create Types (tolerant if exist)
        try: await client.resource_types.create(name="Doc")
        except: pass
        try: await client.resource_types.create(name="Image")
        except: pass
        
        # Create Resources with SHARED External ID
        # create(self, resource_type_id=None, external_id=None, ..., resource_type_name=None)
        # Randomize ext ID to avoid collision in shared realm
        ext_id = f"EXT-{uuid.uuid4().hex[:4]}"
        r1 = await client.resources.create(resource_type_name="Doc", external_id=ext_id, attributes={"v": 1})
        r2 = await client.resources.create(resource_type_name="Image", external_id=ext_id, attributes={"v": 1})
        
        # Get by External ID + Type NAME
        f1 = await client.resources.get(ext_id, resource_type="Doc")
        assert f1.id == r1.id
        
        # Get by External ID + Type ID
        t2_id = (await client.resource_types.get(type_id="Image")).id
        f2 = await client.resources.get(ext_id, resource_type=t2_id)
        assert f2.id == r2.id
    
        # Update by External ID + Type NAME
        u1 = await client.resources.update(ext_id, resource_type="Doc", attributes={"v": 2})
        assert u1.attributes["v"] == 2
        
        # Delete by External ID + Type NAME
        await client.resources.delete(ext_id, resource_type="Doc")
        
        # Verify Gone
        try:
            await client.resources.get(ext_id, resource_type="Doc")
            assert False, "Should be gone"
        except Exception:
            pass
            
        # Verify Image still there
        f2b = await client.resources.get(ext_id, resource_type="Image")
        assert f2b.id == r2.id
