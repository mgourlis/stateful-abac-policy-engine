"""
Tests for NOT, NOT_IN, and ALL operators.
Tests the new logical and set operators added to the ABAC engine.
"""
import pytest
import uuid
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import StatefulABACClient, ManifestBuilder, ConditionBuilder
from httpx import ASGITransport
from app.main import app


@pytest.fixture
def sdk_client():
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)


@pytest.mark.asyncio
async def test_not_operator_simple(sdk_client, ac, tmp_path):
    """
    Test NOT operator: Grant access to documents that are NOT deleted.
    """
    realm_name = f"NotSimple_{uuid.uuid4().hex[:8]}"
    builder = ManifestBuilder(realm_name, description="NOT operator test")
    
    # Define schema
    builder.add_resource_type("document")
    builder.add_action("read")
    builder.add_role("reader")
    
    # Add principal
    builder.add_principal("user1").with_role("reader").end()
    
    # Add resources
    builder.add_resource("DOC-ACTIVE", "document") \
        .with_attribute("deleted", False) \
        .with_attribute("title", "Active Document") \
        .end()
    
    builder.add_resource("DOC-DELETED", "document") \
        .with_attribute("deleted", True) \
        .with_attribute("title", "Deleted Document") \
        .end()
    
    builder.add_resource("DOC-ARCHIVED", "document") \
        .with_attribute("deleted", False) \
        .with_attribute("archived", True) \
        .end()
    
    # ACL: Reader can read documents that are NOT deleted
    builder.add_acl("document", "read") \
        .for_role("reader") \
        .when(
            ConditionBuilder.not_(
                ConditionBuilder.attr("deleted").eq(True)
            )
        ) \
        .end()
    
    # Apply manifest
    manifest_file = tmp_path / "not_simple.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Verify Access
    from common.services.security import create_access_token
    token = create_access_token({"sub": "user1", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "document", "action_name": "read", "return_type": "id_list"}]
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "DOC-ACTIVE" in ids      # deleted=False -> NOT(deleted=True) = TRUE
    assert "DOC-ARCHIVED" in ids    # deleted=False -> NOT(deleted=True) = TRUE  
    assert "DOC-DELETED" not in ids # deleted=True -> NOT(deleted=True) = FALSE


@pytest.mark.asyncio
async def test_not_operator_compound(sdk_client, ac, tmp_path):
    """
    Test NOT operator with compound condition inside.
    Grant access to documents that are NOT (draft AND owned by the principal).
    """
    realm_name = f"NotCompound_{uuid.uuid4().hex[:8]}"
    builder = ManifestBuilder(realm_name, description="NOT compound test")
    
    # Define schema
    builder.add_resource_type("document")
    builder.add_action("read")
    
    # Add principals
    builder.add_principal("alice").with_attribute("username", "alice").end()
    builder.add_principal("bob").with_attribute("username", "bob").end()
    
    # Add resources
    builder.add_resource("DOC-DRAFT-ALICE", "document") \
        .with_attribute("status", "draft") \
        .with_attribute("owner", "alice") \
        .end()
    
    builder.add_resource("DOC-DRAFT-BOB", "document") \
        .with_attribute("status", "draft") \
        .with_attribute("owner", "bob") \
        .end()
    
    builder.add_resource("DOC-PUBLISHED", "document") \
        .with_attribute("status", "published") \
        .with_attribute("owner", "alice") \
        .end()
    
    # ACL: Allow access to docs that are NOT (draft AND owned by principal)
    # This means: exclude your own drafts, allow everything else
    builder.add_acl("document", "read") \
        .for_principal("alice") \
        .when(
            ConditionBuilder.not_(
                ConditionBuilder.and_(
                    ConditionBuilder.attr("status").eq("draft"),
                    ConditionBuilder.attr("owner").eq("$principal.username")
                )
            )
        ) \
        .end()
    
    # Apply manifest
    manifest_file = tmp_path / "not_compound.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Verify Access for alice
    from common.services.security import create_access_token
    token = create_access_token({"sub": "alice", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "document", "action_name": "read", "return_type": "id_list"}]
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "DOC-DRAFT-ALICE" not in ids  # Alice's own draft - excluded by NOT
    assert "DOC-DRAFT-BOB" in ids        # Bob's draft - NOT(draft AND owner=alice) = TRUE
    assert "DOC-PUBLISHED" in ids        # Published doc - NOT(draft AND ...) = TRUE (status != draft)


@pytest.mark.asyncio
async def test_not_in_operator(sdk_client, ac, tmp_path):
    """
    Test NOT_IN operator: Grant access to documents NOT in certain statuses.
    """
    realm_name = f"NotIn_{uuid.uuid4().hex[:8]}"
    builder = ManifestBuilder(realm_name, description="NOT_IN operator test")
    
    # Define schema
    builder.add_resource_type("document")
    builder.add_action("read")
    builder.add_role("editor")
    
    # Add principal
    builder.add_principal("editor1").with_role("editor").end()
    
    # Add resources with various statuses
    builder.add_resource("DOC-ACTIVE", "document").with_attribute("status", "active").end()
    builder.add_resource("DOC-DRAFT", "document").with_attribute("status", "draft").end()
    builder.add_resource("DOC-DELETED", "document").with_attribute("status", "deleted").end()
    builder.add_resource("DOC-ARCHIVED", "document").with_attribute("status", "archived").end()
    builder.add_resource("DOC-PENDING", "document").with_attribute("status", "pending").end()
    
    # ACL: Editor can read documents NOT in ["deleted", "archived"] statuses
    builder.add_acl("document", "read") \
        .for_role("editor") \
        .when(
            ConditionBuilder.attr("status").not_in(["deleted", "archived"])
        ) \
        .end()
    
    # Apply manifest
    manifest_file = tmp_path / "not_in.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Verify Access
    from common.services.security import create_access_token
    token = create_access_token({"sub": "editor1", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "document", "action_name": "read", "return_type": "id_list"}]
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "DOC-ACTIVE" in ids      # active NOT IN [deleted, archived] -> TRUE
    assert "DOC-DRAFT" in ids       # draft NOT IN [deleted, archived] -> TRUE
    assert "DOC-PENDING" in ids     # pending NOT IN [deleted, archived] -> TRUE
    assert "DOC-DELETED" not in ids # deleted NOT IN [deleted, archived] -> FALSE
    assert "DOC-ARCHIVED" not in ids # archived NOT IN [deleted, archived] -> FALSE


@pytest.mark.asyncio
async def test_combined_not_and_not_in(sdk_client, ac, tmp_path):
    """
    Test combining NOT with NOT_IN operators.
    """
    realm_name = f"CombinedNot_{uuid.uuid4().hex[:8]}"
    builder = ManifestBuilder(realm_name, description="Combined NOT operators test")
    
    # Define schema
    builder.add_resource_type("project")
    builder.add_action("view")
    builder.add_role("manager")
    
    # Add principal
    builder.add_principal("manager1").with_role("manager").end()
    
    # Add resources
    builder.add_resource("PROJ-ACTIVE", "project") \
        .with_attribute("status", "active") \
        .with_attribute("confidential", False) \
        .end()
    
    builder.add_resource("PROJ-ACTIVE-CONF", "project") \
        .with_attribute("status", "active") \
        .with_attribute("confidential", True) \
        .end()
    
    builder.add_resource("PROJ-ARCHIVED", "project") \
        .with_attribute("status", "archived") \
        .with_attribute("confidential", False) \
        .end()
    
    builder.add_resource("PROJ-DRAFT", "project") \
        .with_attribute("status", "draft") \
        .with_attribute("confidential", False) \
        .end()
    
    # ACL: Manager can view projects that are:
    # - NOT confidential AND
    # - status NOT IN ["archived", "deleted"]
    builder.add_acl("project", "view") \
        .for_role("manager") \
        .when(
            ConditionBuilder.and_(
                ConditionBuilder.not_(
                    ConditionBuilder.attr("confidential").eq(True)
                ),
                ConditionBuilder.attr("status").not_in(["archived", "deleted"])
            )
        ) \
        .end()
    
    # Apply manifest
    manifest_file = tmp_path / "combined_not.json"
    with open(manifest_file, 'w') as f:
        f.write(builder.to_json())
    await sdk_client.apply_manifest(str(manifest_file))
    
    # Verify Access
    from common.services.security import create_access_token
    token = create_access_token({"sub": "manager1", "realm": realm_name})
    
    response = await ac.post(
        "/api/v1/check-access",
        json={
            "realm_name": realm_name,
            "req_access": [{"resource_type_name": "project", "action_name": "view", "return_type": "id_list"}]
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    ids = response.json()["results"][0]["answer"]
    assert "PROJ-ACTIVE" in ids        # NOT confidential AND NOT archived -> TRUE
    assert "PROJ-DRAFT" in ids         # NOT confidential AND NOT archived -> TRUE
    assert "PROJ-ACTIVE-CONF" not in ids  # confidential=True -> FALSE
    assert "PROJ-ARCHIVED" not in ids  # status IN [archived] -> FALSE
