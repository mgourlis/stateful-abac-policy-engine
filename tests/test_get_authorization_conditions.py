"""
Tests for get_authorization_conditions endpoint and SDK methods.

This tests the new functionality for single-query authorization,
where authorization conditions are returned as JSON DSL that can be
converted to SearchQuery and merged with user queries.
"""
import pytest
import uuid
import json
from httpx import AsyncClient, ASGITransport
from app.main import app
from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import CheckAccessItem
from common.services.security import create_access_token


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sdk_client_for_auth_conditions():
    """SDK client fixture using ASGI transport for testing."""
    transport = ASGITransport(app=app)
    realm_name = f"auth_cond_test_{uuid.uuid4().hex[:8]}"
    return StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)


@pytest.fixture
def db_sdk_client_for_auth_conditions():
    """Fixture for DB-mode SDK client."""
    realm_name = f"auth_cond_db_test_{uuid.uuid4().hex[:8]}"
    client = StatefulABACClient(mode="db", realm=realm_name)
    return client


# ============================================================================
# Test: Blanket Access (granted_all)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_granted_all(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has unconditional type-level access,
    get_authorization_conditions returns filter_type='granted_all'.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("document")
        action = await client.actions.create("read")
        role = await client.roles.create("admin")
        
        # Create principal with role (use role name, not ID)
        principal = await client.principals.create("admin_user", roles=["admin"])
        
        # Create ACL: unconditional type-level access (no conditions, no resource_id)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            conditions=None  # No conditions = blanket access
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="document",
            action_name="read"
        )
        
        # Should return granted_all
        assert result.filter_type == "granted_all"
        assert result.conditions_dsl is None
        assert result.external_ids is None
        assert result.has_context_refs is False


# ============================================================================
# Test: No Access (denied_all)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_denied_all(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has no ACLs granting access,
    get_authorization_conditions returns filter_type='denied_all'.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        
        # Create resource type, action
        rt = await client.resource_types.create("secret_document")
        action = await client.actions.create("read")
        
        # Create principal WITHOUT any roles or ACLs
        principal = await client.principals.create("no_access_user")
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="secret_document",
            action_name="read"
        )
        
        # Should return denied_all
        assert result.filter_type == "denied_all"
        assert result.conditions_dsl is None
        assert result.external_ids is None


# ============================================================================
# Test: Conditional Access (conditions DSL returned)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_with_conditions(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has conditional access,
    get_authorization_conditions returns the conditions as JSON DSL.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("report")
        action = await client.actions.create("view")
        role = await client.roles.create("analyst")
        
        # Create principal with role (use role name, not ID)
        principal = await client.principals.create("analyst_user", roles=["analyst"])
        
        # Create ACL with condition: department = 'engineering'
        conditions = {"op": "=", "attr": "department", "val": "engineering"}
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            conditions=conditions
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="report",
            action_name="view"
        )
        
        # Should return conditions
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        assert result.conditions_dsl["op"] == "="
        assert result.conditions_dsl["attr"] == "department"
        assert result.conditions_dsl["val"] == "engineering"
        assert result.has_context_refs is False


# ============================================================================
# Test: Multiple Conditions (OR combined)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_multiple_acls(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has multiple conditional ACLs,
    they are combined with OR logic.
    
    Note: The database has a unique constraint on (realm, resource_type, action, principal/role, resource).
    So to have multiple conditional ACLs, we need to use different roles for each.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action
        rt = await client.resource_types.create("file")
        action = await client.actions.create("access")
        
        # Create TWO different roles (unique constraint requires different role per ACL)
        role1 = await client.roles.create("user_region")
        role2 = await client.roles.create("user_public")
        
        # Create principal with BOTH roles
        principal = await client.principals.create("multi_acl_user", roles=["user_region", "user_public"])
        
        # Create ACL 1: region_id = 5 (for role1)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role1.id,
            conditions={"op": "=", "attr": "region_id", "val": 5}
        )
        
        # Create ACL 2: status = 'public' (for role2)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role2.id,
            conditions={"op": "=", "attr": "status", "val": "public"}
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="file",
            action_name="access"
        )
        
        # Should return combined conditions with OR
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        assert result.conditions_dsl["op"] == "or"
        assert "conditions" in result.conditions_dsl
        assert len(result.conditions_dsl["conditions"]) == 2


# ============================================================================
# Test: Resource-Level ACLs (external_ids returned)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_with_external_ids(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has resource-level ACLs (specific resources granted),
    the external_ids are returned.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("confidential_doc")
        action = await client.actions.create("read")
        role = await client.roles.create("special_access")
        
        # Create principal with role (use role name, not ID)
        principal = await client.principals.create("special_user", roles=["special_access"])
        
        # Create specific resources with external IDs
        ext_id_1 = f"DOC-{uuid.uuid4().hex[:8]}"
        ext_id_2 = f"DOC-{uuid.uuid4().hex[:8]}"
        
        res1 = await client.resources.create(
            resource_type_id=rt.id,
            external_id=ext_id_1,
            attributes={"title": "Secret Doc 1"}
        )
        res2 = await client.resources.create(
            resource_type_id=rt.id,
            external_id=ext_id_2,
            attributes={"title": "Secret Doc 2"}
        )
        
        # Create resource-level ACLs (specific resource_id, no conditions)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            resource_id=res1.id
        )
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            resource_id=res2.id
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="confidential_doc",
            action_name="read"
        )
        
        # Should return external_ids
        assert result.filter_type == "conditions"
        assert result.external_ids is not None
        assert len(result.external_ids) == 2
        assert ext_id_1 in result.external_ids
        assert ext_id_2 in result.external_ids


# ============================================================================
# Test: Hybrid Access (conditions + external_ids)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_hybrid(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has both conditional ACLs and resource-level ACLs,
    both conditions_dsl and external_ids are returned.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("hybrid_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("hybrid_role")
        
        # Create principal with role (use role name, not ID)
        principal = await client.principals.create("hybrid_user", roles=["hybrid_role"])
        
        # Create a specific resource with external ID
        ext_id = f"HYBRID-{uuid.uuid4().hex[:8]}"
        res = await client.resources.create(
            resource_type_id=rt.id,
            external_id=ext_id,
            attributes={"type": "special"}
        )
        
        # Create conditional ACL: status = 'active'
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            conditions={"op": "=", "attr": "status", "val": "active"}
        )
        
        # Create resource-level ACL (specific resource)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            resource_id=res.id
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="hybrid_resource",
            action_name="access"
        )
        
        # Should return both conditions and external_ids
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        assert result.external_ids is not None
        assert ext_id in result.external_ids


# ============================================================================
# Test: Context References Detection
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_context_refs(sdk_client_for_auth_conditions, session):
    """
    Test that has_context_refs is True when conditions reference
    $context.* or $principal.* variables.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("context_resource")
        action = await client.actions.create("view")
        role = await client.roles.create("context_role")
        
        # Create principal with role (use role name, not ID)
        principal = await client.principals.create("context_user", roles=["context_role"])
        
        # Create ACL with context reference: resource.owner = $principal.id
        conditions = {
            "op": "=",
            "source": "resource",
            "attr": "owner_id",
            "val": "$principal.id"
        }
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            conditions=conditions
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="context_resource",
            action_name="view"
        )
        
        # Should detect context references
        assert result.filter_type == "conditions"
        assert result.has_context_refs is True


# ============================================================================
# Test: DB Mode Client
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_db_mode(db_sdk_client_for_auth_conditions, tmp_path, session):
    """
    Test get_authorization_conditions using DB mode SDK client.
    """
    client = db_sdk_client_for_auth_conditions
    realm_name = client.realm
    
    # Create manifest for setup
    manifest = {
        "realm": {"name": realm_name, "description": "DB Mode Auth Conditions Test"},
        "resource_types": [{"name": "db_document", "is_public": False}],
        "actions": ["read", "write"],
        "roles": [{"name": "db_reader"}],
        "principals": [{"username": "db_user", "roles": ["db_reader"]}],
        "acls": [
            {
                "resource_type": "db_document",
                "action": "read",
                "role": "db_reader",
                "conditions": {"op": "=", "attr": "visibility", "val": "public"}
            }
        ]
    }
    
    manifest_file = tmp_path / "db_auth_cond_manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
    
    # Apply manifest
    await client.apply_manifest(str(manifest_file))
    
    # Generate token for principal
    token = create_access_token({"sub": "db_user", "realm": realm_name})
    client.set_token(token)
    
    # Call get_authorization_conditions
    result = await client.auth.get_authorization_conditions(
        resource_type_name="db_document",
        action_name="read"
    )
    
    # Should return conditions
    assert result.filter_type == "conditions"
    assert result.conditions_dsl is not None
    assert result.conditions_dsl["attr"] == "visibility"
    assert result.conditions_dsl["val"] == "public"
    
    await client.close()


# ============================================================================
# Test: HTTP API Direct Call
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_http_api(ac: AsyncClient, session):
    """
    Test the HTTP API endpoint directly.
    """
    import uuid
    from common.core.redis import RedisClient
    
    # Clear Redis cache
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()
    
    realm_name = f"http_api_test_{uuid.uuid4().hex[:8]}"
    
    # Create realm
    r = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert r.status_code == 200
    realm_id = r.json()["id"]
    
    # Create resource type
    rt = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "api_resource"})
    assert rt.status_code == 200
    rt_id = rt.json()["id"]
    
    # Create action
    action = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "query"})
    assert action.status_code == 200
    action_id = action.json()["id"]
    
    # Create role
    role = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "querier"})
    assert role.status_code == 200
    role_id = role.json()["id"]
    
    # Create principal with role assigned (use role name in the request)
    p = await ac.post(f"/api/v1/realms/{realm_id}/principals", json={
        "username": "api_user",
        "roles": ["querier"]  # Assign role by name during creation
    })
    assert p.status_code == 200
    p_id = p.json()["id"]
    
    # Create conditional ACL
    acl = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "conditions": {"op": "in", "attr": "category", "val": ["A", "B", "C"]}
    })
    assert acl.status_code == 200
    
    # Generate token
    token = create_access_token({"sub": str(p_id), "realm": realm_name})
    
    # Call the API endpoint
    response = await ac.post(
        "/api/v1/get-authorization-conditions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": realm_name,
            "resource_type_name": "api_resource",
            "action_name": "query"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["filter_type"] == "conditions"
    assert data["conditions_dsl"] is not None
    assert data["conditions_dsl"]["op"] == "in"
    assert data["conditions_dsl"]["attr"] == "category"
    assert data["conditions_dsl"]["val"] == ["A", "B", "C"]


# ============================================================================
# Test: Anonymous User (denied_all)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_anonymous(ac: AsyncClient, session):
    """
    Test that anonymous users (no token) get denied_all.
    """
    import uuid
    
    realm_name = f"anon_test_{uuid.uuid4().hex[:8]}"
    
    # Create realm
    r = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert r.status_code == 200
    realm_id = r.json()["id"]
    
    # Create resource type
    rt = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "protected"})
    assert rt.status_code == 200
    
    # Create action
    action = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "access"})
    assert action.status_code == 200
    
    # Call the API endpoint WITHOUT token
    response = await ac.post(
        "/api/v1/get-authorization-conditions",
        json={
            "realm_name": realm_name,
            "resource_type_name": "protected",
            "action_name": "access"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Anonymous user should be denied
    assert data["filter_type"] == "denied_all"


# ============================================================================
# Test: Role Filter
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_with_role_filter(sdk_client_for_auth_conditions, session):
    """
    Test that role_names filter works correctly.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action
        rt = await client.resource_types.create("multi_role_resource")
        action = await client.actions.create("view")
        
        # Create two roles
        role_admin = await client.roles.create("admin")
        role_viewer = await client.roles.create("viewer")
        
        # Create principal with both roles (use role names, not IDs)
        principal = await client.principals.create("multi_role_user", roles=["admin", "viewer"])
        
        # Create ACL for admin: status = 'any' (broad access)
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role_admin.id,
            conditions=None  # Blanket access
        )
        
        # Create ACL for viewer: status = 'public' only
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role_viewer.id,
            conditions={"op": "=", "attr": "status", "val": "public"}
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Without role filter - should get granted_all (admin has blanket access)
        result_all = await client.auth.get_authorization_conditions(
            resource_type_name="multi_role_resource",
            action_name="view"
        )
        assert result_all.filter_type == "granted_all"
        
        # With role filter for viewer only - should get conditions
        result_viewer = await client.auth.get_authorization_conditions(
            resource_type_name="multi_role_resource",
            action_name="view",
            role_names=["viewer"]
        )
        assert result_viewer.filter_type == "conditions"
        assert result_viewer.conditions_dsl["attr"] == "status"
        assert result_viewer.conditions_dsl["val"] == "public"
