
import pytest
import uuid
import sys
import os

# Ensure SDK is importable (it's local)
sys.path.append(os.path.abspath("python-sdk/src"))

from stateful_abac_sdk import StatefulABACClient
from httpx import AsyncClient

# Use the same base URL as the tests usually use, with API prefix
BASE_URL = "http://test/api/v1"

@pytest.mark.asyncio
async def test_public_access_scenarios(ac: AsyncClient, session):
    from common.models import Realm, Principal
    from common.services.security import create_access_token
    
    # 1. Bootstrap: Create Realm & Admin Principal
    r_name = f"sdk_test_{uuid.uuid4()}"
    realm = Realm(name=r_name, is_active=True)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    # Manually create Realm partitions (since we bypassed API)
    rid = realm.id
    from sqlalchemy import text
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{rid} PARTITION OF resource FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{rid} PARTITION OF acl FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
    await session.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{rid} PARTITION OF external_ids FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
    await session.commit()
    
    # Create Admin
    admin = Principal(username="admin", realm_id=realm.id)
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    
    # Generate Token
    token = create_access_token({"sub": str(admin.id)})
    
    # 2. Init SDK Client (Authenticated)
    # Inject the app transport to allow calls to the in-memory test app
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token) as client:
        
        # A. Setup Resource Types via SDK
        # Public Type
        rt_pub = await client.resource_types.create(
            name="public_sdk_layer", 
            is_public=True
        )
        
        # Private Type
        rt_priv = await client.resource_types.create(
            name="private_sdk_layer", 
            is_public=False
        )
        
        # B. Setup Resources
        res_pub = await client.resources.create(
            resource_type_id=rt_pub.id,
            attributes={"description": "Public Map"},
            external_id="pub-1"
        )
        
        res_priv = await client.resources.create(
            resource_type_id=rt_priv.id,
            attributes={"description": "Secret Map"},
            external_id="priv-1"
        )
        
        # Control Resource (No ACL)
        res_priv_denied = await client.resources.create(
            resource_type_id=rt_priv.id,
            attributes={"description": "Should not see this"},
            external_id="priv-denied"
        )
        
        # C. Create Action
        action = await client.actions.create(name="view")
        
        # D. Setup ACL for Level 3 (Private Item specific)
        # We want to allow 'admin' to see 'res_priv' specifically? 
        # Actually let's create a SECOND user for the test cases.
        pass

    # 3. Create a Second User (Alice)
    alice = Principal(username="alice", realm_id=realm.id)
    session.add(alice)
    await session.commit()
    await session.refresh(alice)
    token_alice = create_access_token({"sub": str(alice.id)})

    # ACL: Grant Alice specific access to Private Item
    # We need to re-open Admin client to create ACL?
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token) as admin_client:
        await admin_client.acls.create(
            resource_type_id=rt_priv.id,
            action_id=action.id,
            principal_id=alice.id,
            resource_id=res_priv.id,
            conditions={} # "True"
        )

    # 4. Verify: Anonymous Client (Level 1)
    # No token provided
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=None) as anon_client:
        # Check Public Access
        from stateful_abac_sdk.models import CheckAccessItem
        
        decision_pub = await anon_client.auth.check_access(
            resources=[
                CheckAccessItem(resource_type_name=rt_pub.name, action_name=action.name, return_type="decision")
            ]
        )
        # Should be True
        assert decision_pub.results[0].answer is True
        
        # Check Private Access
        decision_priv = await anon_client.auth.check_access(
            resources=[
                CheckAccessItem(resource_type_name=rt_priv.name, action_name=action.name, return_type="decision")
            ]
        )
        # Should be False
        assert decision_priv.results[0].answer is False

    # 5. Verify: Alice Client (Level 3)
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token_alice) as alice_client:
        # Alice check Private Type (id_list)
        # Should see ONLY res_priv (Due to specific ACL)
        resp = await alice_client.auth.check_access(
            resources=[
                CheckAccessItem(resource_type_name=rt_priv.name, action_name=action.name, return_type="id_list")
            ]
        )
        ids = resp.results[0].answer
        # Expecting External IDs
        assert res_priv.external_id in ids
        assert "priv-denied" not in ids
        assert len(ids) == 1

    # 6. Verify Level 2: Type-Level ACL (Pattern)
    # Create another private type
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token) as client:
        rt_l2 = await client.resource_types.create(
            name="level2_type",
            is_public=False
        )
        res_l2_a = await client.resources.create(
            resource_type_id=rt_l2.id,
            external_id="l2-a"
        )
        res_l2_b = await client.resources.create(
            resource_type_id=rt_l2.id,
            external_id="l2-b"
        )
        
        # Grant Alice access to ALL level2_type items via Type-Level ACL (resource_id=None)
        await client.acls.create(
            resource_type_id=rt_l2.id,
            action_id=action.id,
            principal_id=alice.id,
            resource_id=None, # WILDCARD / PATTERN
            conditions={} 
        )

    # Verify Alice checks Level 2
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token_alice) as alice_client:
        resp_l2 = await alice_client.auth.check_access(
            resources=[
                CheckAccessItem(resource_type_name="level2_type", action_name=action.name, return_type="id_list")
            ]
        )
        l2_ids = resp_l2.results[0].answer
        assert "l2-a" in l2_ids
        assert "l2-b" in l2_ids
        assert len(l2_ids) == 2

    # 7. Verify Level 3: Granular Public Access (Hybrid)
    # Make 'priv-1' (res_priv) public via explicit ACL for principal_id=0
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=token) as client:
        await client.acls.create(
            resource_type_id=rt_priv.id,
            action_id=action.id,
            principal_id=0, # PUBLIC / ANONYMOUS
            resource_external_id=res_priv.external_id,
            conditions={}
        )

    # Verify Anonymous Access to the specific private item
    async with StatefulABACClient(BASE_URL, realm=r_name, transport=ac._transport).connect(token=None) as anon_client:
        # Check specific item
        resp_hybrid = await anon_client.auth.check_access(
            resources=[
                CheckAccessItem(
                    resource_type_name=rt_priv.name, 
                    action_name=action.name, 
                    return_type="decision",
                    external_resource_ids=[res_priv.external_id]
                ),
                CheckAccessItem(
                     resource_type_name=rt_priv.name, 
                     action_name=action.name, 
                     return_type="decision",
                     # res_priv_denied is still private and has no ACL
                     external_resource_ids=[res_priv_denied.external_id] 
                )
            ]
        )
        # 1. Allowed (priv-1)
        assert resp_hybrid.results[0].answer is True
        # 2. Denied (priv-denied)
        assert resp_hybrid.results[1].answer is False
    
    # cleanup handled by test rollback usually
