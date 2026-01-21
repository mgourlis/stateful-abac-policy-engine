import pytest
import uuid
import json
from stateful_abac_sdk import StatefulABACClient
from common.services.security import create_access_token

# We need the session fixture to ensure DB is clean/ready, 
# even though the client creates its own sessions via AsyncSessionLocal.
# The `session` fixture in conftest.py handles engine lifecycle for the test function.

@pytest.fixture
def db_sdk_client():
    """Fixture for DB-mode SDK client."""
    client = StatefulABACClient(mode="db", realm="initial_test_realm")
    return client

@pytest.mark.asyncio
async def test_db_client_initialization(db_sdk_client):
    """Test that the DB client initializes correctly."""
    assert db_sdk_client is not None
    # Verify internal structure (managers exist)
    assert db_sdk_client.realms is not None
    assert db_sdk_client.resources is not None
    assert db_sdk_client.auth is not None
    
    await db_sdk_client.close()

@pytest.mark.asyncio
async def test_manifest_application_db_mode(db_sdk_client, tmp_path, session):
    """Test applying a manifest using DB mode directly."""
    realm_name = f"DBModeTest_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name, "description": "Created via DB Mode SDK"},
        "resource_types": [{"name": "document", "is_public": False}],
        "actions": ["view", "edit"],
        "roles": [{"name": "editor"}],
        "principals": [{"username": "user1", "roles": ["editor"]}],
        "resources": [
            {
                "type": "document",
                "external_id": "DOC-100",
                "attributes": {"status": "draft"}
            }
        ],
        "acls": [
            {
                "resource_type": "document",
                "action": "view",
                "role": "editor"
            }
        ]
    }
    
    manifest_file = tmp_path / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    # Apply using DB client
    # Note: connect() context manager handles background tasks if needed, 
    # but for simple DB ops usually not strictly required unless relying on scheduler/audit.
    # However, best practice is to use connect or just call methods if they are stateless enough.
    # apply_manifest manages its own session.
    
    result = await db_sdk_client.apply_manifest(str(manifest_file))
    
    assert result["realm"] == "created" or result["realm"] == "updated"
    assert result["resources"]["created"] == 1
    assert result["acls"]["created"] == 1
    
    # Verify via separate DB session (using test fixture session)
    # We need to commit/close the SDK side first? 
    # apply_manifest does commit internally.
    
    from common.models import Realm, Resource, Principal
    from sqlalchemy import select
    
    # Use the test session to verify
    stmt = select(Realm).where(Realm.name == realm_name)
    r = (await session.execute(stmt)).scalar_one_or_none()
    assert r is not None
    assert r.description == "Created via DB Mode SDK"
    
    await db_sdk_client.close()

@pytest.mark.asyncio
async def test_check_access_db_mode(db_sdk_client, tmp_path, session):
    """Test checking access using DB mode directly."""
    realm_name = f"DBAccessTest_{uuid.uuid4().hex[:8]}"
    
    # Setup Data
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "api_endpoint"}],
        "actions": ["access"],
        "roles": [{"name": "admin"}],
        "principals": [{"username": "admin_user", "roles": ["admin"]}],
        "resources": [
            {"type": "api_endpoint", "external_id": "API-1"}
        ],
        "acls": [
            {
                "resource_type": "api_endpoint",
                "action": "access",
                "role": "admin"
            }
        ]
    }
    
    manifest_file = tmp_path / "access.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    # Generate Token (using common service, as SDK in DB mode doesn't do auth flow typically, 
    # or expects token to be passed if context needed, but check_access expects token string)
    token = create_access_token({"sub": "admin_user", "realm": realm_name})
    
    # 1. Test check_access (Batch)
    # The SDK signature for check_access differs slightly or is unified?
    # db_sdk_client.auth.check_access signature:
    # async def check_access(self, realm_name: str, resources: List[Dict[str, Any]], token: str | None = None, ...
    
    req = [{
        "resource_type_name": "api_endpoint",
        "action_name": "access",
        "return_type": "decision",
        "resource_id": "API-1"
    }]
    
    # Set token on client or pass it?
    db_sdk_client.set_token(token)
    
    # Set client realm scope
    db_sdk_client.realm = realm_name
    
    # The HTTP client usually handles token auto-injection if set_token was called.
    # DBAuthManager needs to be checked if it respects self.client.token
    
    response = await db_sdk_client.auth.check_access(
        resources=req
    )
    
    assert response is not None
    assert len(response.results) == 1
    assert response.results[0].answer is True
    
    # 2. Test Negative Case
    token_bad = create_access_token({"sub": "unknown_user", "realm": realm_name})
    db_sdk_client.set_token(token_bad)
    
    response_bad = await db_sdk_client.auth.check_access(
        resources=req
    )
    
    assert response_bad.results[0].answer is False
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_db_mode(db_sdk_client, tmp_path, session):
    """Test getting permitted actions using DB mode directly."""
    realm_name = f"DBPermittedActionsTest_{uuid.uuid4().hex[:8]}"
    
    # Setup Data with multiple actions
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "document"}],
        "actions": ["view", "edit", "delete", "share"],
        "roles": [{"name": "viewer"}, {"name": "editor"}],
        "principals": [{"username": "viewer_user", "roles": ["viewer"]}, {"username": "editor_user", "roles": ["editor"]}],
        "resources": [
            {"type": "document", "external_id": "DOC-1"},
            {"type": "document", "external_id": "DOC-2"}
        ],
        "acls": [
            # viewer role can only view
            {"resource_type": "document", "action": "view", "role": "viewer"},
            # editor role can view and edit
            {"resource_type": "document", "action": "view", "role": "editor"},
            {"resource_type": "document", "action": "edit", "role": "editor"}
        ]
    }
    
    manifest_file = tmp_path / "permitted_actions.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    # Test 1: Viewer user should only have 'view' action
    token_viewer = create_access_token({"sub": "viewer_user", "realm": realm_name})
    db_sdk_client.set_token(token_viewer)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(
                resource_type_name="document",
                external_resource_ids=["DOC-1"]
            )
        ]
    )
    
    assert response is not None
    assert len(response.results) == 1
    assert response.results[0].resource_type_name == "document"
    assert response.results[0].external_resource_id == "DOC-1"
    assert "view" in response.results[0].actions
    assert "edit" not in response.results[0].actions  # Viewer can't edit
    assert "delete" not in response.results[0].actions  # No one has delete
    
    # Test 2: Editor user should have 'view' and 'edit' actions
    token_editor = create_access_token({"sub": "editor_user", "realm": realm_name})
    db_sdk_client.set_token(token_editor)
    
    response_editor = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(
                resource_type_name="document",
                external_resource_ids=["DOC-1", "DOC-2"]
            )
        ]
    )
    
    assert len(response_editor.results) == 2
    for result in response_editor.results:
        assert "view" in result.actions
        assert "edit" in result.actions
        assert "delete" not in result.actions
    
    # Test 3: Type-level check (no specific resources)
    response_type_level = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(resource_type_name="document")
        ]
    )
    
    assert len(response_type_level.results) == 1
    assert response_type_level.results[0].external_resource_id is None
    # Type-level should show actions available to this user on this type
    assert "view" in response_type_level.results[0].actions
    assert "edit" in response_type_level.results[0].actions
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_anonymous_user(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions with anonymous (no token) user."""
    realm_name = f"DBPermActionsAnon_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "public_doc", "is_public": True}],
        "actions": ["view", "edit"],
        "resources": [{"type": "public_doc", "external_id": "PUB-1"}],
        "acls": []  # No ACLs - rely on public resource type
    }
    
    manifest_file = tmp_path / "anon.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    # No token set (anonymous user)
    db_sdk_client.set_token(None)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(
                resource_type_name="public_doc",
                external_resource_ids=["PUB-1"]
            )
        ]
    )
    
    # Anonymous user on public resource type should have access
    assert len(response.results) == 1
    # Public resource types grant access to all actions
    assert "view" in response.results[0].actions or "edit" in response.results[0].actions
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_nonexistent_resource(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions with non-existent resource IDs."""
    realm_name = f"DBPermActionsNoRes_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "file"}],
        "actions": ["read", "write"],
        "roles": [{"name": "user"}],
        "principals": [{"username": "test_user", "roles": ["user"]}],
        "acls": [
            {"resource_type": "file", "action": "read", "role": "user"}
        ]
        # No resources created
    }
    
    manifest_file = tmp_path / "nores.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    token = create_access_token({"sub": "test_user", "realm": realm_name})
    db_sdk_client.set_token(token)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    # Query for non-existent resources
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(
                resource_type_name="file",
                external_resource_ids=["DOES-NOT-EXIST-1", "DOES-NOT-EXIST-2"]
            )
        ]
    )
    
    # Should return results for each requested resource
    # Type-level ACL for 'read' applies to ALL resources (including non-existent ones)
    assert len(response.results) == 2
    for result in response.results:
        assert "read" in result.actions  # Type-level ACL applies
        assert "write" not in result.actions  # No ACL for write
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_multiple_resource_types(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions with multiple resource types in one request."""
    realm_name = f"DBPermActionsMulti_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "document"}, {"name": "folder"}],
        "actions": ["read", "write", "delete"],
        "roles": [{"name": "doc_reader"}, {"name": "folder_admin"}],
        "principals": [{"username": "multi_user", "roles": ["doc_reader", "folder_admin"]}],
        "resources": [
            {"type": "document", "external_id": "DOC-A"},
            {"type": "folder", "external_id": "FOLDER-X"}
        ],
        "acls": [
            # doc_reader can only read documents
            {"resource_type": "document", "action": "read", "role": "doc_reader"},
            # folder_admin has all actions on folders
            {"resource_type": "folder", "action": "read", "role": "folder_admin"},
            {"resource_type": "folder", "action": "write", "role": "folder_admin"},
            {"resource_type": "folder", "action": "delete", "role": "folder_admin"}
        ]
    }
    
    manifest_file = tmp_path / "multi.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    token = create_access_token({"sub": "multi_user", "realm": realm_name})
    db_sdk_client.set_token(token)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    # Query multiple resource types at once
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(resource_type_name="document", external_resource_ids=["DOC-A"]),
            GetPermittedActionsItem(resource_type_name="folder", external_resource_ids=["FOLDER-X"])
        ]
    )
    
    assert len(response.results) == 2
    
    # Find results by type
    doc_result = next(r for r in response.results if r.resource_type_name == "document")
    folder_result = next(r for r in response.results if r.resource_type_name == "folder")
    
    # Document: only read access
    assert "read" in doc_result.actions
    assert "write" not in doc_result.actions
    assert "delete" not in doc_result.actions
    
    # Folder: full access
    assert "read" in folder_result.actions
    assert "write" in folder_result.actions
    assert "delete" in folder_result.actions
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_user_no_roles(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions for a user with no roles assigned."""
    realm_name = f"DBPermActionsNoRoles_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "secret"}],
        "actions": ["access"],
        "roles": [{"name": "admin"}],
        "principals": [{"username": "orphan_user"}],  # No roles assigned
        "resources": [{"type": "secret", "external_id": "SECRET-1"}],
        "acls": [{"resource_type": "secret", "action": "access", "role": "admin"}]
    }
    
    manifest_file = tmp_path / "noroles.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    token = create_access_token({"sub": "orphan_user", "realm": realm_name})
    db_sdk_client.set_token(token)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(resource_type_name="secret", external_resource_ids=["SECRET-1"])
        ]
    )
    
    assert len(response.results) == 1
    assert response.results[0].actions == []  # No permissions for user without roles
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_empty_resources_list(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions with empty resources list."""
    realm_name = f"DBPermActionsEmpty_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "item"}],
        "actions": ["use"]
    }
    
    manifest_file = tmp_path / "empty.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    db_sdk_client.realm = realm_name
    
    response = await db_sdk_client.auth.get_permitted_actions(resources=[])
    
    # Empty request should return empty results
    assert response.results == []
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_principal_specific_acl(db_sdk_client, tmp_path, session):
    """Test get_permitted_actions with principal-specific ACLs (not role-based)."""
    realm_name = f"DBPermActionsPrincipal_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "private_doc"}],
        "actions": ["view", "edit", "admin"],
        "principals": [{"username": "special_user"}, {"username": "normal_user"}],
        "resources": [{"type": "private_doc", "external_id": "PRIV-1"}],
        "acls": [
            # Principal-specific ACL for special_user
            {"resource_type": "private_doc", "action": "view", "principal": "special_user"},
            {"resource_type": "private_doc", "action": "edit", "principal": "special_user"},
            {"resource_type": "private_doc", "action": "admin", "principal": "special_user"}
        ]
    }
    
    manifest_file = tmp_path / "principal.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    # Test special_user - should have all actions
    token_special = create_access_token({"sub": "special_user", "realm": realm_name})
    db_sdk_client.set_token(token_special)
    db_sdk_client.realm = realm_name
    
    response_special = await db_sdk_client.auth.get_permitted_actions(
        resources=[GetPermittedActionsItem(resource_type_name="private_doc", external_resource_ids=["PRIV-1"])]
    )
    
    assert len(response_special.results) == 1
    assert "view" in response_special.results[0].actions
    assert "edit" in response_special.results[0].actions
    assert "admin" in response_special.results[0].actions
    
    # Test normal_user - should have no actions
    token_normal = create_access_token({"sub": "normal_user", "realm": realm_name})
    db_sdk_client.set_token(token_normal)
    
    response_normal = await db_sdk_client.auth.get_permitted_actions(
        resources=[GetPermittedActionsItem(resource_type_name="private_doc", external_resource_ids=["PRIV-1"])]
    )
    
    assert len(response_normal.results) == 1
    assert response_normal.results[0].actions == []
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_get_permitted_actions_type_level_fallback(db_sdk_client, tmp_path, session):
    """Test that type-level permissions apply to non-existent resource IDs."""
    realm_name = f"DBPermActionsTypeFallback_{uuid.uuid4().hex[:8]}"
    
    manifest = {
        "realm": {"name": realm_name},
        "resource_types": [{"name": "document"}],
        "actions": ["view", "edit", "delete"],
        "roles": [{"name": "global_viewer"}],
        "principals": [{"username": "viewer_user", "roles": ["global_viewer"]}],
        # Only create one resource - we will query for non-existent ones too
        "resources": [{"type": "document", "external_id": "DOC-EXISTS"}],
        "acls": [
            # Type-level ACL - applies to ALL documents (including non-existent ones)
            {"resource_type": "document", "action": "view", "role": "global_viewer"}
            # NOTE: No edit or delete ACLs
        ]
    }
    
    manifest_file = tmp_path / "type_fallback.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f)
        
    await db_sdk_client.apply_manifest(str(manifest_file))
    
    token = create_access_token({"sub": "viewer_user", "realm": realm_name})
    db_sdk_client.set_token(token)
    db_sdk_client.realm = realm_name
    
    from stateful_abac_sdk.models import GetPermittedActionsItem
    
    # Query for both existing and non-existent resources
    response = await db_sdk_client.auth.get_permitted_actions(
        resources=[
            GetPermittedActionsItem(
                resource_type_name="document",
                external_resource_ids=["DOC-EXISTS", "DOC-NOT-IN-AUTH-DB"]
            )
        ]
    )
    
    assert len(response.results) == 2
    
    # Find results by ID
    existing_result = next(r for r in response.results if r.external_resource_id == "DOC-EXISTS")
    nonexistent_result = next(r for r in response.results if r.external_resource_id == "DOC-NOT-IN-AUTH-DB")
    
    # Both should have type-level 'view' permission (the type-level ACL applies to ALL resources)
    assert "view" in existing_result.actions
    assert "view" in nonexistent_result.actions  # Type-level applies to non-existent!
    
    # Neither should have edit or delete (no ACLs for those)
    assert "edit" not in existing_result.actions
    assert "edit" not in nonexistent_result.actions
    assert "delete" not in existing_result.actions
    assert "delete" not in nonexistent_result.actions
    
    await db_sdk_client.close()


@pytest.mark.asyncio
async def test_realm_manager_db_mode(db_sdk_client):
    """Test Realm Manager CRUD in DB mode."""
    # We need a fresh realm name for this test, but client is already initialized with a default one by fixture
    # We should instantiate a NEW client or re-assign realm for the purpose of the 'create' test?
    # BUT, if we re-assign db_sdk_client.realm = "new_one" and then call create(), it should work.
    
    realm_name = f"RealmMgr_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    
    # Create
    realm = await db_sdk_client.realms.create(description="Test Realm")
    assert realm.id is not None
    assert realm.name == realm_name
    assert realm.description == "Test Realm"
    
    # Assert client.realm matches (no change needed, just sanity check)
    assert db_sdk_client.realm == realm_name

    # Get
    r_get = await db_sdk_client.realms.get()
    assert r_get.id == realm.id
    
    # Update
    # Update description only
    r_upd = await db_sdk_client.realms.update(description="Updated Desc")
    assert r_upd.description == "Updated Desc"
    assert db_sdk_client.realm == realm_name

    # Delete
    res = await db_sdk_client.realms.delete()
    assert res.get("status") == "deleted" or res.get("success") is True


@pytest.mark.asyncio
async def test_resource_type_manager_db_mode(db_sdk_client):
    """Test ResourceType Manager CRUD in DB mode."""
    realm_name = f"RTRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()
    
    # Create
    rt = await db_sdk_client.resource_types.create(name="widget", is_public=True)
    assert rt.id is not None
    assert rt.name == "widget"
    assert rt.is_public is True
    
    # List
    rts = await db_sdk_client.resource_types.list()
    assert len(rts) >= 1
    assert any(r.name == "widget" for r in rts)
    
    # Get
    rt_get = await db_sdk_client.resource_types.get(rt.id)
    assert rt_get.name == "widget"
    
    # Update
    rt_upd = await db_sdk_client.resource_types.update(rt.id, name="super_widget")
    assert rt_upd.name == "super_widget"
    
    # Set Public
    rt_pub = await db_sdk_client.resource_types.set_public(rt.id, is_public=False)
    assert rt_pub.is_public is False
    
    # Delete
    await db_sdk_client.resource_types.delete(rt.id)
    
    rts_after = await db_sdk_client.resource_types.list()
    assert not any(r.id == rt.id for r in rts_after)


@pytest.mark.asyncio
async def test_action_manager_db_mode(db_sdk_client):
    """Test Action Manager CRUD in DB mode."""
    realm_name = f"ActRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()
    
    # Create
    act = await db_sdk_client.actions.create(name="poke")
    assert act.id is not None
    assert act.name == "poke"
    
    # List
    acts = await db_sdk_client.actions.list()
    assert any(a.name == "poke" for a in acts)
    
    # Get
    act_get = await db_sdk_client.actions.get(act.id)
    assert act_get.name == "poke"
    
    # Update
    act_upd = await db_sdk_client.actions.update(act.id, name="supersmash")
    assert act_upd.name == "supersmash"
    
    # Delete
    await db_sdk_client.actions.delete(act.id)


@pytest.mark.asyncio
async def test_role_manager_db_mode(db_sdk_client):
    """Test Role Manager CRUD in DB mode."""
    realm_name = f"RoleRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()
    
    # Create
    role = await db_sdk_client.roles.create(name="hero", attributes={"strength": 10})
    assert role.id is not None
    assert role.name == "hero"
    assert role.attributes["strength"] == 10
    
    # List
    roles = await db_sdk_client.roles.list()
    assert any(r.name == "hero" for r in roles)
    
    # Get
    role_get = await db_sdk_client.roles.get(role.id)
    assert role_get.name == "hero"
    
    # Update
    role_upd = await db_sdk_client.roles.update(role.id, attributes={"strength": 11})
    assert role_upd.attributes["strength"] == 11
    
    # Delete
    await db_sdk_client.roles.delete(role.id)


@pytest.mark.asyncio
async def test_principal_manager_db_mode(db_sdk_client):
    """Test Principal Manager CRUD in DB mode."""
    realm_name = f"PrincRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()
    
    # Create
    p = await db_sdk_client.principals.create(username="someuser", attributes={"email": "u@test.com"})
    assert p.id is not None
    assert p.username == "someuser"
    
    # List
    ps = await db_sdk_client.principals.list()
    assert any(x.username == "someuser" for x in ps)
    
    # Get
    p_get = await db_sdk_client.principals.get(p.id)
    assert p_get.username == "someuser"
    
    # Update
    p_upd = await db_sdk_client.principals.update(p.id, attributes={"email": "new@test.com"})
    assert p_upd.attributes["email"] == "new@test.com"
    
    # Delete
    await db_sdk_client.principals.delete(p.id)


@pytest.mark.asyncio
async def test_resource_manager_crud_db_mode(db_sdk_client):
    """Test Resource Manager CRUD + set_public in DB mode."""
    realm_name = f"ResRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()

    rt = await db_sdk_client.resource_types.create(name="sensor")
    
    # Create
    res = await db_sdk_client.resources.create(
        resource_type_id=rt.id, 
        external_id="SENS-01",
        attributes={"loc": "A"}
    )
    assert res.id is not None
    assert res.external_id == "SENS-01"
    
    # Get by ID
    r_get = await db_sdk_client.resources.get(res.id)
    assert r_get.external_id == "SENS-01"
    
    # Get by External
    r_ext = await db_sdk_client.resources.get("SENS-01", resource_type="sensor")
    assert r_ext.id == res.id
    
    # Update
    r_upd = await db_sdk_client.resources.update(res.id, attributes={"loc": "B"})
    assert r_upd.attributes["loc"] == "B"
    
    # List
    lst = await db_sdk_client.resources.list()
    assert len(lst) >= 1
    
    # Set Public (needs Action)
    act = await db_sdk_client.actions.create(name="read")
    success = await db_sdk_client.resources.set_public(
        resource_id=res.id, 
        resource_type_id=rt.id, 
        action_id=act.id,
        is_public=True
    )
    assert success is True
    
    # Delete
    await db_sdk_client.resources.delete(res.id)


@pytest.mark.asyncio
async def test_acl_manager_db_mode(db_sdk_client):
    """Test ACL Manager CRUD in DB mode."""
    realm_name = f"ACLRealm_{uuid.uuid4().hex[:8]}"
    db_sdk_client.realm = realm_name
    realm = await db_sdk_client.realms.create()
    
    rt = await db_sdk_client.resource_types.create(name="doc")
    act = await db_sdk_client.actions.create(name="read")
    role = await db_sdk_client.roles.create(name="viewer")
    principal = await db_sdk_client.principals.create(username="alice")
    
    # Create ACL (Role based)
    acl = await db_sdk_client.acls.create(
        resource_type_id=rt.id,
        action_id=act.id,
        role_id=role.id,
        conditions={"ip": "127.0.0.1"}
    )
    assert acl.id is not None
    assert acl.role_id == role.id
    
    # List (filtered by role)
    acls = await db_sdk_client.acls.list(role_id=role.id)
    assert len(acls) >= 1
    
    # Get
    acl_get = await db_sdk_client.acls.get(acl.id)
    assert acl_get.id == acl.id
    
    # Update
    acl_upd = await db_sdk_client.acls.update(acl.id, conditions={})
    assert acl_upd.conditions == {}
    
    # Delete
    await db_sdk_client.acls.delete(acl.id)

    # Test ACL Manager with Principal
    acl_p = await db_sdk_client.acls.create(
        resource_type_id=rt.id,
        action_id=act.id,
        principal_id=principal.id
    )
    assert acl_p.principal_id == principal.id
    
    acls_p = await db_sdk_client.acls.list(principal_id=principal.id)
    assert len(acls_p) >= 1
    
    await db_sdk_client.acls.delete(acl_p.id)
