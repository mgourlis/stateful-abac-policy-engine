
import pytest
import pytest_asyncio
import uuid
import sys
import os

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from httpx import ASGITransport
from app.main import app
from stateful_abac_sdk import StatefulABACClient

# Reuse fixtures from conftest.py (ac, sdk_client, etc.) - sdk_client NOT in conftest
# We need to define it here or import it if compatible. 



@pytest.mark.asyncio
async def test_sdk_naming_resolution(ac):
    """
    Test that SDK can resolve Names to IDs using the LookupService.
    """
    import uuid
    # 1. Setup Realm and Definitions
    r_name = f"NamingRealm_{uuid.uuid4()}"
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=r_name, transport=transport)
    
    async with client.connect():
        # Realm auto-created
        realm = await client.realms.get()
        rid = realm.id
        
        # Create Type, Action, Role, Principal (using standard ID return to verify later)
        rt = await client.resource_types.create("SecretDoc")
        act = await client.actions.create("burn_after_reading")
        role = await client.roles.create("Spy")
        user = await client.principals.create("JamesBond")
        
        # 2. Test ResourceManager.create with resource_type_name
        print("Testing Resource Creation by Name...")
        res = await client.resources.create( 
            resource_type_name="SecretDoc",  # <--- Using Name
            external_id="M-007"
        )
        assert res.id is not None
        assert res.resource_type_id == rt.id
        
        # 3. Test ACLManager.create with Names (Role)
        print("Testing ACL (Type-Role) by Name...")
        acl1 = await client.acls.create(
            resource_type_name="SecretDoc",
            action_name="burn_after_reading",
            role_name="Spy"
        )
        assert acl1.resource_type_id == rt.id
        assert acl1.action_id == act.id
        assert acl1.role_id == role.id
        assert acl1.principal_id is None # Correct expectation for Role-based ACL
        
        # 4. Test ACLManager.create with Names (Principal)
        print("Testing ACL (Resource-Principal) by Name...")
        acl2 = await client.acls.create(
            resource_type_name="SecretDoc",
            action_name="burn_after_reading",
            principal_name="JamesBond",
            resource_id=res.id
        )
        assert acl2.principal_id == user.id
        assert acl2.role_id is None
        
        # 5. Test ResourceManager.set_public with Names
        print("Testing Set Public by Name...")
        # Make resource public
        success = await client.resources.set_public(
            resource_id=res.id,
            resource_type_name="SecretDoc",
            action_name="burn_after_reading",
            is_public=True
        )
        assert success is True
        
        # Verify ACL created (Level 3 Exception)
        # Using LIST with Name filtering
        acls = await client.acls.list(
            resource_type_name="SecretDoc",
            action_name="burn_after_reading",
            principal_id=0, # Anonymous
            resource_id=res.id
        )
        assert len(acls) == 1
        assert acls[0].principal_id == 0
        
        print("All Naming Tests Passed!")

        print("All Naming Tests Passed!")

@pytest.mark.asyncio
async def test_cache_invalidation(ac):
    """
    Verify that creating a new entity invalidates cache and allows subsequent lookup.
    """
    import uuid
    r_name = f"CacheRealm_{uuid.uuid4()}"
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=r_name, transport=transport)
    
    async with client.connect():
        realm = await client.realms.get()
        r_id = realm.id
        
        # 1. Initial State: Cache Empty for this realm
        # We can inspect internal cache if we want, but behavioral test is better.
        
        # 2. Create Type A
        rt1 = await client.resource_types.create("TypeA")
        
        # 3. Lookup Type A (Should Populate Cache)
        # lookup.get_id still takes realm_id? Let's check lookup.py.
        # Assuming it does because it's a lower level service helper.
        id1 = await client.lookup.get_id(r_id, "resource_types", "TypeA")
        assert id1 == rt1.id
        
        # 4. Create Type B (Should Invalidate Cache)
        rt2 = await client.resource_types.create("TypeB")
        
        # 5. Lookup Type B (Should Refetch and Find It)
        # If cache wasn't invalidated, this might fail or return None if logic was naive
        id2 = await client.lookup.get_id(r_id, "resource_types", "TypeB")
        assert id2 == rt2.id
        
        print("Cache Invalidation Test Passed!")
