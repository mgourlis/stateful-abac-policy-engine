import pytest
import sys
import os
import uuid
from httpx import ASGITransport
from app.main import app

# Add SDK logic to path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import Role, Resource

@pytest.mark.asyncio
async def test_sdk_full_flow():
    """Test the SDK using the internal ASGI app transport."""
    transport = ASGITransport(app=app)
    
    # Init client with custom transport
    realm_name = f"SDK_Test_{uuid.uuid4()}"
    
    # Init client with custom transport and realm
    client = StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)
    
    async with client.connect(token=None):
        # connect() auto-provisions the realm, so we just get it
        realm = await client.realms.get()
        assert realm.name == realm_name
        realm_id = realm.id
        print(f"SDK: Got realm {realm_id}")
        
        # Update realm with description
        realm = await client.realms.update(description="Created via SDK")
        assert realm.description == "Created via SDK"
        
        # 2. Create Dependencies
        rt = await client.resource_types.create("sdk_doc")
        act = await client.actions.create("sdk_read")
        
        # 3. Create Principal
        p = await client.principals.create("sdk_user", attributes={"tier": "gold"})
        assert p.username == "sdk_user"
        
        # 3a. Sync Roles
        roles_payload = [Role(name="sdk_admin", realm_id=realm_id), Role(name="sdk_viewer", realm_id=realm_id)]
        await client.roles.sync(roles_payload)
        
        # 4. Batch Create Resources
        resources = [
            Resource(name="doc1", resource_type_id=rt.id, external_id="ext-doc-1", realm_id=realm_id),
            Resource(name="doc2", resource_type_id=rt.id, external_id="ext-doc-2", realm_id=realm_id)
        ]
        
        # sync() calling batch_update internally
        sync_res = await client.resources.sync(resources)
        assert "create" in sync_res
        assert len(sync_res["create"]) == 2
        
        # Verify Resources Created by updating one
        update_payload = [Resource(external_id="ext-doc-1", attributes={"checked": True}, realm_id=realm_id)]
        upd_res = await client.resources.batch_update(update=update_payload)
        assert "update" in upd_res
