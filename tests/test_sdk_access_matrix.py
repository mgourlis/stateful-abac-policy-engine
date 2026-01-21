import pytest
import uuid
import sys
import os
from httpx import ASGITransport
from sqlalchemy import text
from app.main import app
from common.services.security import create_access_token # Need this to get a valid token for the Principal

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import Resource

@pytest.fixture
async def matrix_setup_ext(session):
    """Sets up Realm with External ID resources."""
    r = f"MatExt_{uuid.uuid4()}"
    transport = ASGITransport(app=app)
    # Instantiate unique client
    sdk_client = StatefulABACClient("http://test/api/v1", realm=r, transport=transport)
    
    # Use anonymous mode for setup (creating entities doesn't require auth in test mode)
    async with sdk_client.connect(token=None):
        # Realm auto-created on connect
        realm = await sdk_client.realms.get()
        rid = realm.id
        rt = await sdk_client.resource_types.create("File")
        act = await sdk_client.actions.create("read")
        role = await sdk_client.roles.create("Editor")
        user = await sdk_client.principals.create("matrix_user")
        
        await session.execute(text(
            "INSERT INTO principal_roles (principal_id, role_id) VALUES (:pid, :rid)"
        ), {"pid": user.id, "rid": role.id})
        await session.commit()
        
        # Create with Ext ID (Fixed Signature)
        res_plain = await sdk_client.resources.create(rt.id, external_id="RP")
        res_cond = await sdk_client.resources.create(rt.id, external_id="RC", attributes={"status": "secret"})
            
        token = create_access_token({"sub": str(user.id)})
        sdk_client.set_token(token)

        return {
            "realm": realm, "rt": rt, "act": act, 
            "role": role, "user": user,
            "res_plain": res_plain, "res_cond": res_cond,
            "client": sdk_client # Return client for use in test
        }

async def check_ids(client, data, role_names=None):
    payload = {
        "realm_name": data["realm"].name,
        "req_access": [{
            "action_name": data["act"].name, 
            "resource_type_name": data["rt"].name
        }]
    }
    if role_names:
        payload["role_names"] = role_names
    res = await client.request("POST", "/check-access", json=payload)
    return res["results"][0]["answer"]

# --- 1. Only Role ---
# User has Role. ACL on Role.

@pytest.mark.asyncio
async def test_role_type_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token): # Ensure connected with token
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id)
        ans = await check_ids(client, d)
        assert "RP" in ans
        assert "RC" in ans

@pytest.mark.asyncio
async def test_role_specific_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, resource_id=d["res_plain"].id)
        ans = await check_ids(client, d)
        assert "RP" in ans
        assert "RC" not in ans

@pytest.mark.asyncio
async def test_role_type_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        # Condition: status = secret
        cond = {"attr": "status", "op": "=", "val": "secret"}
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, conditions=cond)
        ans = await check_ids(client, d)
        assert "RC" in ans
        assert "RP" not in ans

@pytest.mark.asyncio
async def test_role_specific_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        cond = {"attr": "status", "op": "=", "val": "secret"}
        # Target res_cond explicitly with condition
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, resource_id=d["res_cond"].id, conditions=cond)
        ans = await check_ids(client, d)
        assert "RC" in ans
        assert "RP" not in ans
        
        # Target res_plain with Same Condition (Should Fail because plain lacks attribute even if ID matches? OR logic?)
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, resource_id=d["res_plain"].id, conditions=cond)
        ans = await check_ids(client, d)
        assert "RP" not in ans # Matches ID but fails Condition

# --- 2. Only Principal ---

@pytest.mark.asyncio
async def test_principal_type_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        await client.acls.create(d["rt"].id, d["act"].id, principal_id=d["user"].id)
        ans = await check_ids(client, d)
        assert "RP" in ans
        assert "RC" in ans

@pytest.mark.asyncio
async def test_principal_specific_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        await client.acls.create(d["rt"].id, d["act"].id, principal_id=d["user"].id, resource_id=d["res_plain"].id)
        ans = await check_ids(client, d)
        assert "RP" in ans
        assert "RC" not in ans

@pytest.mark.asyncio
async def test_principal_type_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        cond = {"attr": "status", "op": "=", "val": "secret"}
        await client.acls.create(d["rt"].id, d["act"].id, principal_id=d["user"].id, conditions=cond)
        ans = await check_ids(client, d)
        assert "RC" in ans
        assert "RP" not in ans

@pytest.mark.asyncio
async def test_principal_specific_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        cond = {"attr": "status", "op": "=", "val": "secret"}
        await client.acls.create(d["rt"].id, d["act"].id, principal_id=d["user"].id, resource_id=d["res_cond"].id, conditions=cond)
        ans = await check_ids(client, d)
        assert "RC" in ans
        assert "RP" not in ans

# --- 3. Active Roles ---

@pytest.mark.asyncio
async def test_active_role_type_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        # Create ACL for Role
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id)
        
        # Check WITHOUT Active Role (Should be ALLOWED default because user has role)
        # BUT User wants to verify "Active Roles". usually means:
        # 1. User has Role A.
        # 2. User checks with active_roles=['A']. -> Allow.
        # 3. User checks with active_roles=['B']. -> Deny (if user doesn't have B or rule not on B).
        
        # Correct Usage: check_ids(..., role_names=["Editor"])
        ans = await check_ids(client, d, role_names=["Editor"])
        assert "RP" in ans
        
        # Check with WRONG role
        ans_bad = await check_ids(client, d, role_names=["NonExistent"])
    assert len(ans_bad) == 0

@pytest.mark.asyncio
async def test_active_role_specific_no_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, resource_id=d["res_plain"].id)
        ans = await check_ids(client, d, role_names=["Editor"])
        assert "RP" in ans
        assert "RC" not in ans

@pytest.mark.asyncio
async def test_active_role_type_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        cond = {"attr": "status", "op": "=", "val": "secret"}
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, conditions=cond)
        ans = await check_ids(client, d, role_names=["Editor"])
        assert "RC" in ans
        assert "RP" not in ans

@pytest.mark.asyncio
async def test_active_role_specific_cond(matrix_setup_ext):
    d = matrix_setup_ext
    client = d["client"]
    async with client.connect(token=client.token):
        cond = {"attr": "status", "op": "=", "val": "secret"}
        await client.acls.create(d["rt"].id, d["act"].id, role_id=d["role"].id, resource_id=d["res_cond"].id, conditions=cond)
        ans = await check_ids(client, d, role_names=["Editor"])
        assert "RC" in ans
        assert "RP" not in ans
