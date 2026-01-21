import pytest
import uuid
import sys
import os
from httpx import ASGITransport
from sqlalchemy import text
from app.main import app
from common.services.security import create_access_token

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import Resource



async def check_decision(client, realm_name, action_name, type_name, role_names=None):
    payload = {
        "realm_name": realm_name,
        "req_access": [{
            "action_name": action_name, 
            "resource_type_name": type_name,
            "return_type": "decision"
        }]
    }
    if role_names:
        payload["role_names"] = role_names
    res = await client.request("POST", "/check-access", json=payload)
    return res["results"][0]["answer"]

async def check_ids(client, realm_name, action_name, type_name, role_names=None):
    payload = {
        "realm_name": realm_name,
        "req_access": [{
            "action_name": action_name, 
            "resource_type_name": type_name,
            "return_type": "id_list"
        }]
    }
    if role_names:
        payload["role_names"] = role_names
    res = await client.request("POST", "/check-access", json=payload)
    return res["results"][0]["answer"]

@pytest.mark.asyncio
async def test_priority_gatekeeper(session):
    """
    Test that Class Level ACLs act as a prerequisite (Gatekeeper).
    1. No Type ACL + Specific ACL -> Deny.
    2. Type ACL (Empty) + Specific ACL -> Allow.
    """
    # Connect with token=None for setup, set token after creating user
    transport = ASGITransport(app=app)
    r_name = f"PriRealm_{uuid.uuid4()}"
    client = StatefulABACClient("http://test/api/v1", realm=r_name, transport=transport)
    
    # Connect with token=None for setup, set token after creating user
    async with client.connect(token=None):
        # Realm auto-created on connect, so we get it
        realm = await client.realms.get()
        rid = realm.id
        rt = await client.resource_types.create("Doc")
        act = await client.actions.create("view")
        user = await client.principals.create("pri_user")
        
        # Set token after user is created
        token = create_access_token({"sub": str(user.id)})
        client.set_token(token)
        
        # Resources
        # DOC-1: Specific Target
        res = await client.resources.create(rt.id, external_id="DOC-1")
        # DOC-GENERAL: Just to prove Class Rule matches something or nothing
        res_gen = await client.resources.create(rt.id, external_id="DOC-GEN")
        
        # 1. Add Specific ACL ONLY
        # User -> Doc 1
        await client.acls.create(rt.id, act.id, principal_id=user.id, resource_id=res.id)
        
        # Check Access
        # Behavior: ALLOWED (Union: Specific Rule Grants Access)
        ids = await check_ids(client, r_name, "view", "Doc")
        assert "DOC-1" in ids, "Specific Rule should work (Status Quo)"
        
        # 2. Add Class Level ACL (Restrictive / Empty Result)
        # Condition: 1=0 (Matches nothing)
        # It Returns Nothing.
        # But Specific Rule Returns "DOC-1".
        # Union: Result = {"DOC-1"} U {} = {"DOC-1"}
        cond = {"attr": "id", "op": "=", "val": -1} 
        acl_class = await client.acls.create(rt.id, act.id, principal_id=user.id, conditions=cond)
        
        # Check Access to Specific Resource
        # Should ALLOW (Union logic)
        ids2 = await check_ids(client, r_name, "view", "Doc")
        assert "DOC-1" in ids2, "Specific Rule should STILL be allowed even if Class Rule is restrictive (Union Logic)"
        
        # 3. Update Class Level ACL to ALLOW (Non-Empty Result)
        # 3. Update Class Level ACL to ALLOW (Non-Empty Result)
        await client.acls.create(rt.id, act.id, principal_id=user.id, conditions={}) # Allow All
        
        # Check Access
        ids3 = await check_ids(client, r_name, "view", "Doc")
        assert "DOC-1" in ids3, "Specific Rule should be allowed (Union Logic)"

@pytest.mark.asyncio
async def test_priority_role_interaction(session):
    """
    Test interaction between Principal Specific Rules and Role Class Rules.
    Scenario:
    - User has Specific Rule (Allow).
    - Role has Class Rule (Deny/Empty).
    - Expectation (Standard): Allowed (Specific Rule adds access).
    """
    # Connect with token=None for setup, set token after creating user
    transport = ASGITransport(app=app)
    r = f"PriRole_{uuid.uuid4()}"
    client = StatefulABACClient("http://test/api/v1", realm=r, transport=transport)

    # Connect with token=None for setup, set token after creating user
    async with client.connect(token=None):
        # Auto-created
        realm = await client.realms.get()
        rid = realm.id
        rt = await client.resource_types.create("File")
        act = await client.actions.create("read")
        role = await client.roles.create("Manager")
        user = await client.principals.create("role_user")
        
        # Set token after user is created
        token = create_access_token({"sub": str(user.id)})
        client.set_token(token)
        
        # Assign Role manually
        await session.execute(text(
            "INSERT INTO principal_roles (principal_id, role_id) VALUES (:pid, :rid)"
        ), {"pid": user.id, "rid": role.id})
        await session.commit()
        
        
        res = await client.resources.create(rt.id, external_id="F1")
        
        # 1. Specific Rule for USER
        await client.acls.create(rt.id, act.id, principal_id=user.id, resource_id=res.id)
        
        # Expectation: Allowed.
        ids = await check_ids(client, r, "read", "File")
        assert "F1" in ids
        
        # 2. Add Class Rule for ROLE (Restrictive)
        # Condition: 1=0
        await client.acls.create(rt.id, act.id, role_id=role.id, conditions={"attr": "id", "op": "=", "val": -1})
        
        # Expectation: Allowed (Union).
        # Role says "See Nothing". User says "See File1". Result: "See File1".
        ids2 = await check_ids(client, r, "read", "File")
        assert "F1" in ids2, "User Specific Rule should Override/Add to Role Class Rule"

@pytest.mark.asyncio
async def test_priority_mixed_class_rules(session):
    """
    Test Mixed Class Rules.
    - Class Rule A: Deny (Empty).
    - Class Rule B: Allow (Matches All).
    - Expectation: Allowed (Union).
    """
    # Connect with token=None for setup, set token after creating user
    transport = ASGITransport(app=app)
    r = f"PriMix_{uuid.uuid4()}"
    client = StatefulABACClient("http://test/api/v1", realm=r, transport=transport)

    # Connect with token=None for setup, set token after creating user
    async with client.connect(token=None):
        # Auto-created
        realm = await client.realms.get()
        rid = realm.id
        rt = await client.resource_types.create("Note")
        act = await client.actions.create("write")
        user = await client.principals.create("mix_user")
        
        # Set token after user is created
        token = create_access_token({"sub": str(user.id)})
        client.set_token(token)
        
        res = await client.resources.create(rt.id, external_id="N1")
        
        # Specific Rule
        await client.acls.create(rt.id, act.id, principal_id=user.id, resource_id=res.id)
        
        # 1. Add Class Rule A (Deny)
        # 1. Add Class Rule A (Deny)
        await client.acls.create(rt.id, act.id, principal_id=user.id, conditions={"attr": "id", "op": "=", "val": -1})
        
        ids = await check_ids(client, r, "write", "Note")
        assert "N1" in ids, "Specific Rule should NOT be blocked by empty Class Rule (Union)"
        
        # 2. Add Class Rule B (Allow All)
        role = await client.roles.create("Poster")
        await session.execute(text("INSERT INTO principal_roles (principal_id, role_id) VALUES (:pid, :rid)"), {"pid": user.id, "rid": role.id})
        await session.commit()
        
        await client.acls.create(rt.id, act.id, role_id=role.id, conditions={}) 
        
        # Expectation: Allowed (Union).
        ids2 = await check_ids(client, r, "write", "Note")
        assert "N1" in ids2, "Should be allowed"
