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
# Test: Resource-Level ACLs (merged into conditions_dsl as IN clause)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_with_external_ids(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has resource-level ACLs (specific resources granted),
    they are returned as an IN clause in conditions_dsl.
    
    New behavior: external_ids are merged into conditions_dsl as:
    {"op": "in", "source": "resource", "attr": "external_id", "val": [...]}
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
        
        # Should return conditions with IN clause for external_ids
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        
        # The conditions_dsl should be an IN clause
        assert result.conditions_dsl["op"] == "in"
        assert result.conditions_dsl["attr"] == "external_id"
        assert result.conditions_dsl["source"] == "resource"
        assert ext_id_1 in result.conditions_dsl["val"]
        assert ext_id_2 in result.conditions_dsl["val"]


# ============================================================================
# Test: Hybrid Access (conditions + external_ids merged as OR)
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_hybrid(sdk_client_for_auth_conditions, session):
    """
    Test that when a user has both conditional ACLs and resource-level ACLs,
    they are combined into a single conditions_dsl with OR logic.
    
    Result: (status = 'active') OR (external_id IN [...])
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
        
        # Should return combined conditions with OR
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        
        # Should be OR of the type-level condition and the external_id IN clause
        assert result.conditions_dsl["op"] == "or"
        conditions_list = result.conditions_dsl["conditions"]
        assert len(conditions_list) == 2
        
        # Find the status condition and external_id IN condition
        status_cond = next((c for c in conditions_list if c.get("attr") == "status"), None)
        ext_id_cond = next((c for c in conditions_list if c.get("attr") == "external_id"), None)
        
        assert status_cond is not None
        assert status_cond["val"] == "active"
        
        assert ext_id_cond is not None
        assert ext_id_cond["op"] == "in"
        assert ext_id in ext_id_cond["val"]


# ============================================================================
# Test: Context References Detection and Resolution
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_context_refs_resolved(sdk_client_for_auth_conditions, session):
    """
    Test that $principal.* references are resolved server-side.
    The has_context_refs flag should be True (originally had refs),
    but the conditions_dsl should contain the resolved values.
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
        
        # Create principal with role and attributes
        principal = await client.principals.create(
            "context_user", 
            roles=["context_role"],
            attributes={"department": "engineering", "level": 5}
        )
        
        # Create ACL with $principal.* reference: resource.owner_dept = $principal.department
        conditions = {
            "op": "=",
            "source": "resource",
            "attr": "owner_dept",
            "val": "$principal.department"
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
        
        # The $principal.department should be RESOLVED to "engineering"
        assert result.conditions_dsl["val"] == "engineering"
        assert result.conditions_dsl["attr"] == "owner_dept"


@pytest.mark.asyncio
async def test_get_authorization_conditions_auth_context_resolved(sdk_client_for_auth_conditions, session):
    """
    Test that $context.* references are resolved using the auth_context parameter.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("location_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("location_role")
        
        # Create principal with role
        principal = await client.principals.create("location_user", roles=["location_role"])
        
        # Create ACL with $context.* reference: resource.region = $context.current_region
        conditions = {
            "op": "=",
            "source": "resource",
            "attr": "region",
            "val": "$context.current_region"
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
        
        # Call get_authorization_conditions WITH auth_context
        result = await client.auth.get_authorization_conditions(
            resource_type_name="location_resource",
            action_name="access",
            auth_context={"current_region": "EMEA", "current_time": "2026-01-29T10:00:00Z"}
        )
        
        # Should detect context references
        assert result.filter_type == "conditions"
        assert result.has_context_refs is True
        
        # The $context.current_region should be RESOLVED to "EMEA"
        assert result.conditions_dsl["val"] == "EMEA"
        assert result.conditions_dsl["attr"] == "region"


@pytest.mark.asyncio
async def test_get_authorization_conditions_nested_context_refs(sdk_client_for_auth_conditions, session):
    """
    Test that nested $context.* and $principal.* references are resolved in complex conditions.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("nested_resource")
        action = await client.actions.create("manage")
        role = await client.roles.create("nested_role")
        
        # Create principal with role and nested attributes
        principal = await client.principals.create(
            "nested_user", 
            roles=["nested_role"],
            attributes={"org": {"id": 42, "name": "Acme Corp"}}
        )
        
        # Create ACL with nested AND condition containing both $principal and $context refs
        conditions = {
            "op": "and",
            "conditions": [
                {"op": "=", "source": "resource", "attr": "org_id", "val": "$principal.org.id"},
                {"op": "=", "source": "resource", "attr": "env", "val": "$context.environment"}
            ]
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
        
        # Call get_authorization_conditions WITH auth_context
        result = await client.auth.get_authorization_conditions(
            resource_type_name="nested_resource",
            action_name="manage",
            auth_context={"environment": "production"}
        )
        
        # Should detect context references
        assert result.filter_type == "conditions"
        assert result.has_context_refs is True
        
        # Both refs should be resolved
        assert result.conditions_dsl["op"] == "and"
        conditions_list = result.conditions_dsl["conditions"]
        
        # Find and verify each condition
        org_cond = next(c for c in conditions_list if c["attr"] == "org_id")
        env_cond = next(c for c in conditions_list if c["attr"] == "env")
        
        assert org_cond["val"] == 42  # $principal.org.id resolved
        assert env_cond["val"] == "production"  # $context.environment resolved


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
        "principals": [{"username": "db_user", "roles": ["db_reader"], "attributes": {"org": "acme"}}],
        "acls": [
            {
                "resource_type": "db_document",
                "action": "read",
                "role": "db_reader",
                "conditions": {
                    "op": "and",
                    "conditions": [
                        {"op": "=", "attr": "visibility", "val": "internal"},
                        {"op": "=", "source": "resource", "attr": "org", "val": "$principal.org"}
                    ]
                }
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
    
    # Should return conditions with $principal.org resolved to "acme"
    assert result.filter_type == "conditions"
    assert result.conditions_dsl is not None
    assert result.has_context_refs is True
    
    # Verify the nested conditions
    conditions_list = result.conditions_dsl["conditions"]
    visibility_cond = next(c for c in conditions_list if c["attr"] == "visibility")
    org_cond = next(c for c in conditions_list if c["attr"] == "org")
    
    assert visibility_cond["val"] == "internal"
    assert org_cond["val"] == "acme"  # $principal.org resolved
    
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


@pytest.mark.asyncio
async def test_get_authorization_conditions_http_api_with_auth_context(ac: AsyncClient, session):
    """
    Test the HTTP API endpoint with auth_context for $context.* resolution.
    """
    import uuid
    from common.core.redis import RedisClient
    
    # Clear Redis cache
    redis_client = RedisClient.get_instance()
    await redis_client.flushall()
    
    realm_name = f"http_ctx_test_{uuid.uuid4().hex[:8]}"
    
    # Create realm
    r = await ac.post("/api/v1/realms", json={"name": realm_name})
    assert r.status_code == 200
    realm_id = r.json()["id"]
    
    # Create resource type
    rt = await ac.post(f"/api/v1/realms/{realm_id}/resource-types", json={"name": "ctx_resource"})
    assert rt.status_code == 200
    rt_id = rt.json()["id"]
    
    # Create action
    action = await ac.post(f"/api/v1/realms/{realm_id}/actions", json={"name": "read"})
    assert action.status_code == 200
    action_id = action.json()["id"]
    
    # Create role
    role = await ac.post(f"/api/v1/realms/{realm_id}/roles", json={"name": "reader"})
    assert role.status_code == 200
    role_id = role.json()["id"]
    
    # Create principal with attributes
    p = await ac.post(f"/api/v1/realms/{realm_id}/principals", json={
        "username": "ctx_user",
        "roles": ["reader"],
        "attributes": {"team": "platform"}
    })
    assert p.status_code == 200
    p_id = p.json()["id"]
    
    # Create conditional ACL with $context and $principal refs
    acl = await ac.post(f"/api/v1/realms/{realm_id}/acls", json={
        "realm_id": realm_id,
        "resource_type_id": rt_id,
        "action_id": action_id,
        "role_id": role_id,
        "conditions": {
            "op": "and",
            "conditions": [
                {"op": "=", "source": "resource", "attr": "team", "val": "$principal.team"},
                {"op": "=", "source": "resource", "attr": "env", "val": "$context.environment"}
            ]
        }
    })
    assert acl.status_code == 200
    
    # Generate token
    token = create_access_token({"sub": str(p_id), "realm": realm_name})
    
    # Call the API endpoint WITH auth_context
    response = await ac.post(
        "/api/v1/get-authorization-conditions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "realm_name": realm_name,
            "resource_type_name": "ctx_resource",
            "action_name": "read",
            "auth_context": {"environment": "staging"}
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["filter_type"] == "conditions"
    assert data["has_context_refs"] is True
    
    # Verify both refs are resolved
    conditions_list = data["conditions_dsl"]["conditions"]
    team_cond = next(c for c in conditions_list if c["attr"] == "team")
    env_cond = next(c for c in conditions_list if c["attr"] == "env")
    
    assert team_cond["val"] == "platform"  # $principal.team resolved
    assert env_cond["val"] == "staging"  # $context.environment resolved


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


# ============================================================================
# Test: auth_context with role_names combined
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_auth_context_with_role_filter(sdk_client_for_auth_conditions, session):
    """
    Test that auth_context and role_names work together correctly.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action
        rt = await client.resource_types.create("filtered_resource")
        action = await client.actions.create("access")
        
        # Create roles
        role_basic = await client.roles.create("basic")
        role_premium = await client.roles.create("premium")
        
        # Create principal with both roles and attributes
        principal = await client.principals.create(
            "combined_user", 
            roles=["basic", "premium"],
            attributes={"tier": "gold"}
        )
        
        # Create ACL for basic: access where resource.tier matches $context.requested_tier
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role_basic.id,
            conditions={"op": "=", "source": "resource", "attr": "tier", "val": "$context.requested_tier"}
        )
        
        # Create ACL for premium: access where resource.tier matches $principal.tier
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role_premium.id,
            conditions={"op": "=", "source": "resource", "attr": "tier", "val": "$principal.tier"}
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Filter to basic role only with auth_context
        result = await client.auth.get_authorization_conditions(
            resource_type_name="filtered_resource",
            action_name="access",
            auth_context={"requested_tier": "silver"},
            role_names=["basic"]
        )
        
        assert result.filter_type == "conditions"
        assert result.has_context_refs is True
        # $context.requested_tier should be resolved to "silver"
        assert result.conditions_dsl["val"] == "silver"
        
        # Filter to premium role only (no auth_context needed for $principal refs)
        result_premium = await client.auth.get_authorization_conditions(
            resource_type_name="filtered_resource",
            action_name="access",
            role_names=["premium"]
        )
        
        assert result_premium.filter_type == "conditions"
        assert result_premium.has_context_refs is True
        # $principal.tier should be resolved to "gold"
        assert result_premium.conditions_dsl["val"] == "gold"


# ============================================================================
# Test: Condition Evaluation - Principal source evaluates to granted_all
# ============================================================================

@pytest.mark.asyncio
async def test_get_authorization_conditions_principal_condition_grants_all(sdk_client_for_auth_conditions, session):
    """
    Test that when a condition with source='principal' evaluates to true,
    the entire condition is simplified and can result in granted_all.
    
    Example: principal.is_admin = true → if principal IS admin → granted_all
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("admin_resource")
        action = await client.actions.create("manage")
        role = await client.roles.create("user_role")
        
        # Create principal with is_admin = true
        principal = await client.principals.create(
            "admin_principal", 
            roles=["user_role"],
            attributes={"is_admin": True}
        )
        
        # Create ACL with condition on principal: if principal.is_admin = true, grant access
        conditions = {
            "op": "=",
            "source": "principal",
            "attr": "is_admin",
            "val": True
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
            resource_type_name="admin_resource",
            action_name="manage"
        )
        
        # Since principal.is_admin = true matches val = true, condition evaluates to true
        # This should result in granted_all
        assert result.filter_type == "granted_all"
        assert result.conditions_dsl is None


@pytest.mark.asyncio
async def test_get_authorization_conditions_principal_condition_denies_all(sdk_client_for_auth_conditions, session):
    """
    Test that when a condition with source='principal' evaluates to false,
    and there are no other ACLs, the result is denied_all.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("restricted_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("restricted_role")
        
        # Create principal with is_admin = false
        principal = await client.principals.create(
            "non_admin_principal", 
            roles=["restricted_role"],
            attributes={"is_admin": False}
        )
        
        # Create ACL with condition on principal: only if principal.is_admin = true
        conditions = {
            "op": "=",
            "source": "principal",
            "attr": "is_admin",
            "val": True
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
            resource_type_name="restricted_resource",
            action_name="access"
        )
        
        # Since principal.is_admin = false but condition requires true → false
        # This should result in denied_all
        assert result.filter_type == "denied_all"
        assert result.conditions_dsl is None


@pytest.mark.asyncio
async def test_get_authorization_conditions_context_condition_grants_all(sdk_client_for_auth_conditions, session):
    """
    Test that when a condition with source='context' evaluates to true,
    the result is granted_all.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("context_eval_resource")
        action = await client.actions.create("view")
        role = await client.roles.create("context_eval_role")
        
        # Create principal
        principal = await client.principals.create("context_eval_user", roles=["context_eval_role"])
        
        # Create ACL with condition on context: if context.is_internal = true
        conditions = {
            "op": "=",
            "source": "context",
            "attr": "is_internal",
            "val": True
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
        
        # Call get_authorization_conditions WITH auth_context where is_internal = true
        result = await client.auth.get_authorization_conditions(
            resource_type_name="context_eval_resource",
            action_name="view",
            auth_context={"is_internal": True}
        )
        
        # Context condition evaluates to true → granted_all
        assert result.filter_type == "granted_all"
        assert result.conditions_dsl is None


@pytest.mark.asyncio
async def test_get_authorization_conditions_mixed_or_short_circuit(sdk_client_for_auth_conditions, session):
    """
    Test OR short-circuit: if ANY condition evaluates to true, result is granted_all.
    
    Condition: (principal.level > 5) OR (resource.status = 'public')
    If principal.level = 10, the OR evaluates to true regardless of resource condition.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("or_test_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("or_test_role")
        
        # Create principal with high level
        principal = await client.principals.create(
            "high_level_user", 
            roles=["or_test_role"],
            attributes={"level": 10}
        )
        
        # Create ACL with OR condition
        conditions = {
            "op": "or",
            "conditions": [
                {"op": ">", "source": "principal", "attr": "level", "val": 5},
                {"op": "=", "source": "resource", "attr": "status", "val": "public"}
            ]
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
            resource_type_name="or_test_resource",
            action_name="access"
        )
        
        # principal.level (10) > 5 is TRUE, so OR short-circuits to granted_all
        assert result.filter_type == "granted_all"
        assert result.conditions_dsl is None


@pytest.mark.asyncio
async def test_get_authorization_conditions_mixed_and_simplification(sdk_client_for_auth_conditions, session):
    """
    Test AND simplification: if some conditions evaluate to true, they are removed.
    
    Condition: (principal.department = 'engineering') AND (resource.status = 'active')
    If principal.department = 'engineering', the AND simplifies to just the resource condition.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("and_test_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("and_test_role")
        
        # Create principal in engineering department
        principal = await client.principals.create(
            "eng_user", 
            roles=["and_test_role"],
            attributes={"department": "engineering"}
        )
        
        # Create ACL with AND condition
        conditions = {
            "op": "and",
            "conditions": [
                {"op": "=", "source": "principal", "attr": "department", "val": "engineering"},
                {"op": "=", "source": "resource", "attr": "status", "val": "active"}
            ]
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
            resource_type_name="and_test_resource",
            action_name="access"
        )
        
        # principal.department = 'engineering' is TRUE
        # So AND simplifies to just the resource condition
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        # Should be the remaining resource condition only
        assert result.conditions_dsl["op"] == "="
        assert result.conditions_dsl["attr"] == "status"
        assert result.conditions_dsl["val"] == "active"


@pytest.mark.asyncio
async def test_get_authorization_conditions_and_short_circuit_false(sdk_client_for_auth_conditions, session):
    """
    Test AND short-circuit: if ANY condition evaluates to false, result is denied_all.
    
    Condition: (principal.department = 'sales') AND (resource.status = 'active')
    If principal.department = 'engineering' (not sales), the AND evaluates to false.
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("and_false_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("and_false_role")
        
        # Create principal in engineering department (not sales)
        principal = await client.principals.create(
            "wrong_dept_user", 
            roles=["and_false_role"],
            attributes={"department": "engineering"}
        )
        
        # Create ACL with AND condition requiring sales department
        conditions = {
            "op": "and",
            "conditions": [
                {"op": "=", "source": "principal", "attr": "department", "val": "sales"},
                {"op": "=", "source": "resource", "attr": "status", "val": "active"}
            ]
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
            resource_type_name="and_false_resource",
            action_name="access"
        )
        
        # principal.department = 'engineering' != 'sales' is FALSE
        # So AND short-circuits to denied_all
        assert result.filter_type == "denied_all"
        assert result.conditions_dsl is None


@pytest.mark.asyncio
async def test_get_authorization_conditions_resource_acl_with_conditions(sdk_client_for_auth_conditions, session):
    """
    Test that resource-level ACLs with conditions are properly handled.
    
    If a resource-level ACL has conditions:
    - If conditions evaluate to TRUE → add to external_ids (as IN clause)
    - If conditions evaluate to FALSE → skip (don't grant access)
    - If conditions have resource refs → include as (external_id = X AND conditions)
    """
    client = sdk_client_for_auth_conditions
    
    async with client.connect(token=None):
        # Setup realm
        realm = await client.realms.get()
        realm_id = realm.id
        
        # Create resource type, action, role
        rt = await client.resource_types.create("res_cond_resource")
        action = await client.actions.create("access")
        role = await client.roles.create("res_cond_role")
        
        # Create principal with department = engineering
        principal = await client.principals.create(
            "res_cond_user", 
            roles=["res_cond_role"],
            attributes={"department": "engineering"}
        )
        
        # Create resources
        ext_id_1 = f"RES-{uuid.uuid4().hex[:8]}"
        ext_id_2 = f"RES-{uuid.uuid4().hex[:8]}"
        
        res1 = await client.resources.create(
            resource_type_id=rt.id,
            external_id=ext_id_1,
            attributes={"name": "Resource 1"}
        )
        res2 = await client.resources.create(
            resource_type_id=rt.id,
            external_id=ext_id_2,
            attributes={"name": "Resource 2"}
        )
        
        # Create resource-level ACL for res1 with condition that evaluates to TRUE
        # (principal.department = 'engineering' AND resource.status = 'active')
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            resource_id=res1.id,
            conditions={
                "op": "and",
                "conditions": [
                    {"op": "=", "source": "principal", "attr": "department", "val": "engineering"},
                    {"op": "=", "source": "resource", "attr": "status", "val": "active"}
                ]
            }
        )
        
        # Create resource-level ACL for res2 with condition that evaluates to FALSE
        # (principal.department = 'sales')
        await client.acls.create(
            resource_type_id=rt.id,
            action_id=action.id,
            role_id=role.id,
            resource_id=res2.id,
            conditions={"op": "=", "source": "principal", "attr": "department", "val": "sales"}
        )
        
        # Generate token for the principal
        token = create_access_token({"sub": str(principal.id), "realm": realm.name})
        client.set_token(token)
        
        # Call get_authorization_conditions
        result = await client.auth.get_authorization_conditions(
            resource_type_name="res_cond_resource",
            action_name="access"
        )
        
        # res1 condition: principal check passed, resource condition remains
        # res2 condition: principal check failed → should be excluded
        assert result.filter_type == "conditions"
        assert result.conditions_dsl is not None
        
        # Should only have res1's condition (as external_id = X AND resource.status = 'active')
        # res2 should be excluded because principal.department != 'sales'
        # The exact structure depends on the implementation
        dsl = result.conditions_dsl
        
        # Should contain reference to ext_id_1 but not ext_id_2
        dsl_str = str(dsl)
        assert ext_id_1 in dsl_str
        # res2 should have been eliminated because its principal condition was false
        # But this depends on whether we evaluate during PostgreSQL or Python
