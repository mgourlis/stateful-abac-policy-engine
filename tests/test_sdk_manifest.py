import pytest
import asyncio
import json
import os
import uuid
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import StatefulABACClient
from httpx import ASGITransport
from app.main import app
from common.services.security import create_access_token

@pytest.fixture
def sdk_client():
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)

@pytest.fixture
def manifest_path(tmp_path):
    return tmp_path / "stateful_abac_manifest.json"

@pytest.mark.asyncio
async def test_sdk_manifest_application(manifest_path):
    """
    Test applying a full realm manifest from JSON.
    """
    unique_name = f"ManifestRealm_{uuid.uuid4()}"
    
    # 1. Define Manifest Content
    manifest_data = {
        "realm": {
            "name": unique_name,
            "description": "Initialized via Manifest",
            "keycloak_config": {
                "server_url": "https://keycloak.example.com",
                "keycloak_realm": "kc-realm",
                "client_id": "kc-client",
                "verify_ssl": False
            }
        },
        "resource_types": [
            {"name": "man_doc", "is_public": False},
            {"name": "man_image", "is_public": True}
        ],
        "actions": ["view", "edit", "delete"],
        "roles": [
            {"name": "man_editor", "attributes": {"dept": "content"}},
            {"name": "man_viewer"}
        ],
        "principals": [
            {"username": "man_user_1", "attributes": {"role": "admin"}, "roles": ["man_editor"]},
            {"username": "man_user_2"},
            {"username": "man_user_ip"} 
        ],
        "resources": [
            {
                "external_id": "doc-100",
                "name": "Manifest Document",
                "type": "man_doc",
                "owner": "man_user_1",
                "attributes": {"status": "active"}
            }
        ],
        "acls": [
            # Type Level
            {
                "resource_type": "man_doc",
                "action": "view",
                "role": "man_viewer"
            },
            # Specific Resource
            {
                "resource_type": "man_doc",
                "action": "edit",
                "principal": "man_user_1",
                "resource_external_id": "doc-100"
            },
            # Conditional Access (IP Check)
            {
                "resource_type": "man_doc",
                "action": "view",
                "principal": "man_user_ip",
                "resource_external_id": "doc-100",
                "conditions": {
                    "op": "=",
                    "source": "context",
                    "attr": "ip",
                    "val": "127.0.0.1"
                }
            }
        ]
    }
    
    # 2. Write Manifest to File
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    # 3. Create client matching manifest realm and apply
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        summary = await sdk_client.apply_manifest(str(manifest_path))
        
        print(f"Manifest Summary: {summary}")
        
        # 4. Verify Realm Created
        realm = await sdk_client.realms.get()
        assert realm.description == "Initialized via Manifest"
        assert realm.keycloak_config.server_url == "https://keycloak.example.com"
        r_id = realm.id
        
        # 5. Verify Types
        types = await sdk_client.resource_types.list()
        type_names = [t.name for t in types]
        assert "man_doc" in type_names
        assert "man_image" in type_names
        
        # 6. Verify Actions
        actions = await sdk_client.actions.list()
        act_names = [a.name for a in actions]
        assert "view" in act_names
        
        # 7. Verify Roles/Principals
        roles = await sdk_client.roles.list()
        assert any(r.name == "man_editor" for r in roles)
        
        users = await sdk_client.principals.list()
        assert any(u.username == "man_user_1" for u in users)
        assert any(u.username == "man_user_ip" for u in users)
        
        # Verify Roles Assigned
        user1 = [u for u in users if u.username == "man_user_1"][0]
        assert user1.roles, "User 1 should have roles assigned"
        assert any(r.name == "man_editor" for r in user1.roles), "User 1 should have 'man_editor' role"
        
        # 9. Verify ACLs
        acls = await sdk_client.acls.list()
        print(f"Created ACLs: {len(acls)}")
        
        conditional_acl_found = False
        for acl in acls:
            print(f"  ACL: type={acl.resource_type_id}, action={acl.action_id}, principal={acl.principal_id}, role={acl.role_id}, resource={acl.resource_id}")
            if acl.conditions:
                print(f"    Conditions: {acl.conditions}")
                if acl.conditions.get("source") == "context" and acl.conditions.get("val") == "127.0.0.1":
                    conditional_acl_found = True
                    
        assert len(acls) >= 3
        assert conditional_acl_found, "Conditional ACL not found or conditions mismatch"
        
        print(f"\\n✓ Manifest Application Test Passed!")
        print(f"  - Realm: {realm.name}")
        print(f"  - Resource Types: {len(types)}")
        print(f"  - Actions: {len(actions)}")
        print(f"  - Roles: {len(roles)}")
        print(f"  - Principals: {len(users)}")
        print(f"  - ACLs: {len(acls)}")


@pytest.mark.asyncio
async def test_manifest_check_access_public_vs_private(manifest_path):
    """
    Test that public resource types are accessible without ACLs,
    while private resource types require explicit ACLs.
    
    Note: Role-based access with role_names requires authenticated principals.
    This test focuses on the public/private distinction which works for anonymous users.
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"PublicPrivateRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Public vs Private Test"},
        "resource_types": [
            {"name": "public_image", "is_public": True},
            {"name": "private_doc", "is_public": False}
        ],
        "actions": ["view"],
        "roles": [],
        "principals": [],
        "resources": [
            {"external_id": "img-1", "name": "Public Image", "type": "public_image"},
            {"external_id": "doc-1", "name": "Private Doc", "type": "private_doc"}
        ],
        "acls": []  # No ACLs - test relies on is_public flag only
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        # Test 1: Public resource should be accessible to everyone
        public_req = [CheckAccessItem(
            resource_type_name="public_image",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["img-1"]
        )]
        
        public_result = await sdk_client.auth.check_access(public_req)
        
        print(f"Public resource result: {public_result}")
        assert len(public_result.results[0].answer or []) == 1, "Public resource should be accessible"
        assert public_result.results[0].answer[0] == "img-1", "Should return the external ID"
        
        # Test 2: Private resource should NOT be accessible without ACL
        private_req = [CheckAccessItem(
            resource_type_name="private_doc",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["doc-1"]
        )]
        
        private_result = await sdk_client.auth.check_access(private_req)
        
        print(f"Private resource result: {private_result}")
        assert len(private_result.results[0].answer or []) == 0, "Private resource should NOT be accessible without ACL"
        
        print("✓ Public/Private access tests passed!")


@pytest.mark.asyncio
async def test_manifest_check_access_anonymous_acl(manifest_path):
    """
    Test that anonymous (principal_id=0) ACLs grant access to unauthenticated users.
    This is the way to grant specific access to public without making entire type public.
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"AnonymousACLRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Anonymous ACL Test"},
        "resource_types": [
            {"name": "semi_public_doc", "is_public": False}
        ],
        "actions": ["view", "download"],
        "roles": [],
        "principals": [],
        "resources": [
            {"external_id": "public-doc", "name": "Semi Public Doc", "type": "semi_public_doc"},
            {"external_id": "restricted-doc", "name": "Restricted Doc", "type": "semi_public_doc"}
        ],
        "acls": [
            # Grant anonymous (principal_id=0) view access to specific resource
            {
                "resource_type": "semi_public_doc",
                "action": "view",
                "principal_id": 0,  # Anonymous identity
                "resource_external_id": "public-doc"
            }
            # No ACL for restricted-doc
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        # Test 1: public-doc should be accessible (has anonymous ACL)
        public_req = [CheckAccessItem(
            resource_type_name="semi_public_doc",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["public-doc"]
        )]
        
        public_result = await sdk_client.auth.check_access(public_req)
        
        print(f"Anonymous ACL result: {public_result}")
        assert len(public_result.results[0].answer or []) == 1, "Resource with anonymous ACL should be accessible"
        
        # Test 2: restricted-doc should NOT be accessible (no ACL)
        restricted_req = [CheckAccessItem(
            resource_type_name="semi_public_doc",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["restricted-doc"]
        )]
        
        restricted_result = await sdk_client.auth.check_access(restricted_req)
        
        print(f"Restricted doc result: {restricted_result}")
        assert len(restricted_result.results[0].answer or []) == 0, "Resource without ACL should NOT be accessible"
        
        # Test 3: download action for public-doc should NOT be accessible (no ACL for download)
        download_req = [CheckAccessItem(
            resource_type_name="semi_public_doc",
            action_name="download",
            return_type="id_list",
            external_resource_ids=["public-doc"]
        )]
        
        download_result = await sdk_client.auth.check_access(download_req)
        
        print(f"Download action result: {download_result}")
        assert len(download_result.results[0].answer or []) == 0, "Different action without ACL should NOT be accessible"
        
        print("✓ Anonymous ACL tests passed!")


@pytest.mark.asyncio
async def test_manifest_check_access_decision_type(manifest_path):
    """
    Test check_access with return_type='decision' instead of 'id_list'.
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"DecisionTypeRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Decision Type Test"},
        "resource_types": [
            {"name": "public_file", "is_public": True}
        ],
        "actions": ["read"],
        "roles": [],
        "principals": [],
        "resources": [
            {"external_id": "file-1", "name": "File 1", "type": "public_file"}
        ],
        "acls": []
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        # Test decision return type
        decision_req = [CheckAccessItem(
            resource_type_name="public_file",
            action_name="read",
            return_type="decision",
            external_resource_ids=["file-1"]
        )]
        
        decision_result = await sdk_client.auth.check_access(decision_req)
        
        print(f"Decision result: {decision_result}")
        # For decision type, answer should be True/False, not a list
        assert decision_result.results[0].answer == True or decision_result.results[0].answer == ["file-1"], \
            "Public resource should return positive decision"
        
        print("✓ Decision type test passed!")


@pytest.mark.asyncio
async def test_manifest_check_access_authenticated_role_based(manifest_path):
    """
    Test check_access with authenticated user using JWT token.
    This properly tests role-based access by authenticating as a user with roles.
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"AuthRoleRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Authenticated Role-Based Test"},
        "resource_types": [{"name": "doc", "is_public": False}],
        "actions": ["view", "edit", "admin"],
        "roles": [{"name": "viewer"}, {"name": "editor"}],
        "principals": [
            {"username": "auth_viewer", "roles": ["viewer"]},
            {"username": "auth_editor", "roles": ["editor"]},
            {"username": "auth_both", "roles": ["viewer", "editor"]}
        ],
        "resources": [
            {"external_id": "doc-1", "name": "Document 1", "type": "doc"},
            {"external_id": "doc-2", "name": "Document 2", "type": "doc"}
        ],
        "acls": [
            # Viewers can view all docs
            {"resource_type": "doc", "action": "view", "role": "viewer"},
            # Editors can edit all docs
            {"resource_type": "doc", "action": "edit", "role": "editor"}
            # No admin ACL - nobody should have admin access
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        # Get realm and users
        realm = await sdk_client.realms.get()
        users = await sdk_client.principals.list()
        
        viewer_user = [u for u in users if u.username == "auth_viewer"][0]
        editor_user = [u for u in users if u.username == "auth_editor"][0]
        both_user = [u for u in users if u.username == "auth_both"][0]
        
        # --- Test 1: Viewer can view but not edit ---
        viewer_token = create_access_token({"sub": str(viewer_user.id)})
        sdk_client.set_token(viewer_token)
        
        view_req = [CheckAccessItem(
            resource_type_name="doc",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["doc-1", "doc-2"]
        )]
        
        viewer_view_result = await sdk_client.auth.check_access(view_req, 
            role_names=["viewer"]  # Activate viewer role
        )
        
        print(f"Viewer view result: {viewer_view_result}")
        assert len(viewer_view_result.results[0].answer) == 2, "Viewer should view both docs"
        
        # Viewer tries to edit
        edit_req = [CheckAccessItem(
            resource_type_name="doc",
            action_name="edit",
            return_type="id_list",
            external_resource_ids=["doc-1"]
        )]
        
        viewer_edit_result = await sdk_client.auth.check_access(edit_req, 
            role_names=["viewer"]  # Viewer activating viewer role
        )
        
        print(f"Viewer edit result: {viewer_edit_result}")
        assert len(viewer_edit_result.results[0].answer or []) == 0, "Viewer should NOT edit"
        
        # --- Test 2: Editor can edit but not view (unless also viewer) ---
        editor_token = create_access_token({"sub": str(editor_user.id)})
        sdk_client.set_token(editor_token)
        
        editor_edit_result = await sdk_client.auth.check_access(edit_req, 
            role_names=["editor"]
        )
        
        print(f"Editor edit result: {editor_edit_result}")
        assert len(editor_edit_result.results[0].answer) == 1, "Editor should edit doc"
        
        # Editor tries to view (shouldn't have viewer role)
        editor_view_result = await sdk_client.auth.check_access(view_req, 
            role_names=["viewer"]  # Editor trying to activate viewer role they don't have
        )
        
        print(f"Editor view result (wrong role): {editor_view_result}")
        assert len(editor_view_result.results[0].answer or []) == 0, "Editor should NOT view with viewer role they don't have"
        
        # --- Test 3: User with both roles ---
        both_token = create_access_token({"sub": str(both_user.id)})
        sdk_client.set_token(both_token)
        
        # Can view with viewer role
        both_view_result = await sdk_client.auth.check_access(view_req, 
            role_names=["viewer"]
        )
        
        print(f"Both user view result: {both_view_result}")
        assert len(both_view_result.results[0].answer) == 2, "Both-roles user should view"
        
        # Can edit with editor role
        both_edit_result = await sdk_client.auth.check_access(edit_req, 
            role_names=["editor"]
        )
        
        print(f"Both user edit result: {both_edit_result}")
        assert len(both_edit_result.results[0].answer) == 1, "Both-roles user should edit"
        
        # --- Test 4: Nobody has admin access ---
        admin_req = [CheckAccessItem(
            resource_type_name="doc",
            action_name="admin",
            return_type="id_list",
            external_resource_ids=["doc-1"]
        )]
        
        admin_result = await sdk_client.auth.check_access(admin_req)
        
        print(f"Admin action result: {admin_result}")
        assert len(admin_result.results[0].answer or []) == 0, "Nobody should have admin access"
        
        print("✓ Authenticated role-based check_access tests passed!")


@pytest.mark.asyncio
async def test_manifest_check_access_authenticated_conditional(manifest_path):
    """
    Test check_access with conditional ACLs using authenticated user.
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"AuthCondRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Authenticated Conditional Test"},
        "resource_types": [{"name": "secure_doc", "is_public": False}],
        "actions": ["view"],
        "roles": [{"name": "ip_user"}],
        "principals": [
            {"username": "cond_user", "roles": ["ip_user"]}
        ],
        "resources": [
            {"external_id": "secure-1", "name": "Secure Doc", "type": "secure_doc"}
        ],
        "acls": [
            {
                "resource_type": "secure_doc",
                "action": "view",
                "role": "ip_user",
                "conditions": {
                    "op": "=",
                    "source": "context",
                    "attr": "ip",
                    "val": "10.0.0.1"
                }
            }
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        realm = await sdk_client.realms.get()
        users = await sdk_client.principals.list()
        cond_user = [u for u in users if u.username == "cond_user"][0]
        
        # Authenticate as conditional user
        token = create_access_token({"sub": str(cond_user.id)})
        sdk_client.set_token(token)
        
        access_req = [CheckAccessItem(
            resource_type_name="secure_doc",
            action_name="view",
            return_type="id_list",
            external_resource_ids=["secure-1"]
        )]
        
        # Test 1: Correct IP should grant access
        result_allowed = await sdk_client.auth.check_access(access_req, 
            auth_context={"ip": "10.0.0.1"},
            role_names=["ip_user"]
        )
        
        print(f"Correct IP result: {result_allowed}")
        assert len(result_allowed.results[0].answer or []) == 1, "Correct IP should be allowed"
        
        # Test 2: Wrong IP should deny access
        result_denied = await sdk_client.auth.check_access(access_req, 
            auth_context={"ip": "192.168.1.1"},
            role_names=["ip_user"]
        )
        
        print(f"Wrong IP result: {result_denied}")
        assert len(result_denied.results[0].answer or []) == 0, "Wrong IP should be denied"
        
        print("✓ Authenticated conditional check_access tests passed!")


@pytest.mark.asyncio
async def test_manifest_advanced_complex_acls(manifest_path):
    """
    Test complex ACLs with nested AND/OR logic, resource attributes, 
    principal attributes, and context variables.
    
    Scenario: Document Management System
    - Classification levels: public, internal, confidential
    - Departments: Engineering, Finance, Legal
    - Rules:
      1. Public docs accessible to all
      2. Internal docs: Finance can read all, Engineering can read if resource.dept matches
      3. Confidential: Legal only, and requires correct IP
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"AdvancedACLRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Advanced ACL Test"},
        "resource_types": [{"name": "document", "is_public": False}],
        "actions": ["read"],
        "roles": [{"name": "engineer"}, {"name": "finance"}, {"name": "legal"}],
        "principals": [
            {"username": "alice", "attributes": {"department": "Engineering"}, "roles": ["engineer"]},
            {"username": "bob", "attributes": {"department": "Finance"}, "roles": ["finance"]},
            {"username": "carol", "attributes": {"department": "Legal"}, "roles": ["legal"]}
        ],
        "resources": [
            {"external_id": "doc-public", "name": "Public Guide", "type": "document", 
             "attributes": {"classification": "public", "dept": "General"}},
            {"external_id": "doc-internal-eng", "name": "Engineering Spec", "type": "document",
             "attributes": {"classification": "internal", "dept": "Engineering"}},
            {"external_id": "doc-internal-fin", "name": "Budget Report", "type": "document",
             "attributes": {"classification": "internal", "dept": "Finance"}},
            {"external_id": "doc-confidential", "name": "Legal Contract", "type": "document",
             "attributes": {"classification": "confidential", "dept": "Legal"}}
        ],
        "acls": [
            # Engineer: public OR (internal AND Engineering dept)
            {
                "resource_type": "document",
                "action": "read",
                "role": "engineer",
                "conditions": {
                    "op": "or",
                    "conditions": [
                        {"op": "=", "source": "resource", "attr": "classification", "val": "public"},
                        {
                            "op": "and",
                            "conditions": [
                                {"op": "=", "source": "resource", "attr": "classification", "val": "internal"},
                                {"op": "=", "source": "resource", "attr": "dept", "val": "Engineering"}
                            ]
                        }
                    ]
                }
            },
            
            # Finance: public OR internal
            {
                "resource_type": "document",
                "action": "read",
                "role": "finance",
                "conditions": {
                    "op": "or",
                    "conditions": [
                        {"op": "=", "source": "resource", "attr": "classification", "val": "public"},
                        {"op": "=", "source": "resource", "attr": "classification", "val": "internal"}
                    ]
                }
            },
            
            # Legal: public OR (confidential AND correct IP)  
            {
                "resource_type": "document",
                "action": "read",
                "role": "legal",
                "conditions": {
                    "op": "or",
                    "conditions": [
                        {"op": "=", "source": "resource", "attr": "classification", "val": "public"},
                        {
                            "op": "and",
                            "conditions": [
                                {"op": "=", "source": "resource", "attr": "classification", "val": "confidential"},
                                {"op": "=", "source": "context", "attr": "ip", "val": "10.0.0.100"}
                            ]
                        }
                    ]
                }
            }
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        manifest_result = await sdk_client.apply_manifest(str(manifest_path))
        print(f"Manifest result: {manifest_result}")
        
        realm = await sdk_client.realms.get()
        acls = await sdk_client.acls.list()
        print(f"Created ACLs: {len(acls)}")
        for acl in acls:
            print(f"  ACL: action={acl.action_id}, role_id={acl.role_id}, resource_id={acl.resource_id}, conditions={acl.conditions}")
        
        users = await sdk_client.principals.list()
        
        alice = [u for u in users if u.username == "alice"][0]
        bob = [u for u in users if u.username == "bob"][0]
        carol = [u for u in users if u.username == "carol"][0]
        
        read_req = [CheckAccessItem(
            resource_type_name="document",
            action_name="read",
            return_type="id_list",
            external_resource_ids=["doc-public", "doc-internal-eng", "doc-internal-fin", "doc-confidential"]
        )]
        
        # --- Test Alice (Engineer) ---
        alice_token = create_access_token({"sub": str(alice.id)})
        sdk_client.set_token(alice_token)
        
        alice_result = await sdk_client.auth.check_access( read_req, role_names=["engineer"])
        alice_docs = alice_result.results[0].answer or []
        print(f"Alice (engineer) can read: {alice_docs}")
        
        assert "doc-public" in alice_docs, "Alice should read public"
        assert "doc-internal-eng" in alice_docs, "Alice should read Engineering internal (her dept)"
        assert "doc-internal-fin" not in alice_docs, "Alice should NOT read Finance internal"
        assert "doc-confidential" not in alice_docs, "Alice should NOT read confidential"
        
        # --- Test Bob (Finance) ---
        bob_token = create_access_token({"sub": str(bob.id)})
        sdk_client.set_token(bob_token)
        
        bob_result = await sdk_client.auth.check_access( read_req, role_names=["finance"])
        bob_docs = bob_result.results[0].answer or []
        print(f"Bob (finance) can read: {bob_docs}")
        
        assert "doc-public" in bob_docs, "Bob should read public"
        assert "doc-internal-eng" in bob_docs, "Bob should read ALL internal (Finance privilege)"  
        assert "doc-internal-fin" in bob_docs, "Bob should read ALL internal"
        assert "doc-confidential" not in bob_docs, "Bob should NOT read confidential (not Legal)"
        
        # --- Test Carol (Legal) - Wrong IP ---
        carol_token = create_access_token({"sub": str(carol.id)})
        sdk_client.set_token(carol_token)
        
        carol_wrong_ip = await sdk_client.auth.check_access(read_req, 
            role_names=["legal"],
            auth_context={"ip": "192.168.1.1"}  # Wrong IP
        )
        carol_wrong_docs = carol_wrong_ip.results[0].answer or []
        print(f"Carol (legal, wrong IP) can read: {carol_wrong_docs}")
        
        assert "doc-public" in carol_wrong_docs, "Carol should read public"
        assert "doc-confidential" not in carol_wrong_docs, "Carol should NOT read confidential with wrong IP"
        
        # --- Test Carol (Legal) - Correct IP ---
        carol_correct_ip = await sdk_client.auth.check_access(read_req,
            role_names=["legal"],
            auth_context={"ip": "10.0.0.100"}  # Correct IP
        )
        carol_correct_docs = carol_correct_ip.results[0].answer or []
        print(f"Carol (legal, correct IP) can read: {carol_correct_docs}")
        
        assert "doc-public" in carol_correct_docs
        assert "doc-confidential" in carol_correct_docs, "Carol SHOULD read confidential with correct IP"
        
        print("✓ Advanced complex ACL tests passed!")


@pytest.mark.asyncio
async def test_manifest_spatial_geofencing(manifest_path, session):
    """
    Test geospatial ACLs with st_dwithin (proximity) and st_intersects (geofencing).
    
    Scenario: Field Service Access
    - Resources are physical locations with geometries
    - Field workers can only access resources they are near or inside
    """
    from stateful_abac_sdk.models import CheckAccessItem

    
    unique_name = f"SpatialRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Spatial ACL Test"},
        "resource_types": [{"name": "zone", "is_public": False}],
        "actions": ["enter", "monitor"],
        "roles": [{"name": "field_agent"}],
        "principals": [
            {"username": "agent_1", "roles": ["field_agent"]}
        ],
        "resources": [
            {
                "external_id": "athens_office",
                "type": "zone",
                "attributes": {"name": "Athens Office"},
                "geometry": "SRID=3857;POINT(2640000 4570000)"
            },
            {
                "external_id": "thessaloniki_office",
                "type": "zone",
                "attributes": {"name": "Thessaloniki Office"},
                "geometry": "SRID=3857;POINT(2553000 4938000)"
            },
            {
                "external_id": "athens_restricted_zone",
                "type": "zone",
                "attributes": {"name": "Athens Restricted Zone"},
                "geometry": "SRID=3857;POLYGON((2639000 4569000, 2641000 4569000, 2641000 4571000, 2639000 4571000, 2639000 4569000))"
            }
        ],
        "acls": [
            # Rule 1: Can enter zone if within 5000 meters (SRID 3857)
            {
                "resource_type": "zone",
                "action": "enter",
                "role": "field_agent",
                "conditions": {
                    "op": "st_dwithin",
                    "attr": "geometry",
                    "val": "$context.location",
                    "args": 5000  # 5km in meters for SRID 3857
                }
            },
            # Rule 2: Can monitor zone if user point intersects zone polygon
            {
                "resource_type": "zone",
                "action": "monitor",
                "role": "field_agent",
                "conditions": {
                    "op": "st_intersects",
                    "attr": "geometry",
                    "val": "$context.user_point"
                }
            }
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        realm = await sdk_client.realms.get()
        rid = realm.id
        
        # Get resource type
        rts = await sdk_client.resource_types.list()
        zone_rt = [rt for rt in rts if rt.name == "zone"][0]
        
        # Resources created via manifest
        # Get user and authenticate
        users = await sdk_client.principals.list()
        agent = users[0]
        token = create_access_token({"sub": str(agent.id)})
        sdk_client.set_token(token)
        
        # --- Test Proximity (st_dwithin) ---
        # User near Athens (within 5km)
        enter_req = [CheckAccessItem(
            resource_type_name="zone",
            action_name="enter",
            return_type="id_list",
            external_resource_ids=["athens_office", "thessaloniki_office"]
        )]
        
        # Location near Athens
        near_athens = await sdk_client.auth.check_access(
            enter_req,
            role_names=["field_agent"],
            auth_context={
                "location": "SRID=4326;POINT(23.72 37.94)"  # Near Athens in WGS84 (~1km away, will be transformed to 3857)
            }
        )
        near_athens_ids = near_athens.results[0].answer or []
        print(f"Near Athens can enter: {near_athens_ids}")
        
        assert "athens_office" in near_athens_ids, "Should enter Athens office (nearby)"
        assert "thessaloniki_office" not in near_athens_ids, "Should NOT enter Thessaloniki (too far)"
        
        # --- Test Geofencing (st_intersects) ---
        # User inside Athens polygon
        monitor_req = [CheckAccessItem(
            resource_type_name="zone",
            action_name="monitor",
            return_type="id_list",
            external_resource_ids=["athens_restricted_zone"]
        )]
        
        inside_polygon = await sdk_client.auth.check_access(monitor_req, 
            role_names=["field_agent"],
            auth_context={
                "user_point": "SRID=4326;POINT(23.716 37.933)"  # Inside polygon center in WGS84
            }
        )
        inside_ids = inside_polygon.results[0].answer or []
        print(f"Inside polygon can monitor: {inside_ids}")
        
        assert "athens_restricted_zone" in inside_ids, "Should monitor zone when inside polygon"
        
        # User outside polygon
        outside_polygon = await sdk_client.auth.check_access(monitor_req, 
            role_names=["field_agent"],
            auth_context={
                "user_point": "SRID=4326;POINT(24.0 38.2)"  # Outside polygon in WGS84 (~30km away)
            }
        )
        outside_ids = outside_polygon.results[0].answer or []
        print(f"Outside polygon can monitor: {outside_ids}")
        
        assert "athens_restricted_zone" not in outside_ids, "Should NOT monitor zone when outside polygon"
        
        print("✓ Spatial geofencing tests passed!")


@pytest.mark.asyncio
async def test_manifest_complex_nested_or_and(manifest_path):
    """
    Test deeply nested OR/AND logic with multiple attribute sources.
    
    Scenario: Allow access if:
    (classification = 'public') 
    OR 
    (
        (department = 'IT' AND clearance >= 3)
        OR
        (department = 'Security' AND resource.status = 'approved')
    )
    """
    from stateful_abac_sdk.models import CheckAccessItem
    
    unique_name = f"NestedLogicRealm_{uuid.uuid4()}"
    
    manifest_data = {
        "realm": {"name": unique_name, "description": "Nested Logic Test"},
        "resource_types": [{"name": "record", "is_public": False}],
        "actions": ["access"],
        "roles": [{"name": "employee"}],
        "principals": [
            {"username": "it_low", "attributes": {"department": "IT", "clearance": 2}, "roles": ["employee"]},
            {"username": "it_high", "attributes": {"department": "IT", "clearance": 5}, "roles": ["employee"]},
            {"username": "sec_user", "attributes": {"department": "Security", "clearance": 1}, "roles": ["employee"]},
            {"username": "hr_user", "attributes": {"department": "HR", "clearance": 4}, "roles": ["employee"]}
        ],
        "resources": [
            {"external_id": "rec-public", "name": "Public Record", "type": "record",
             "attributes": {"classification": "public", "status": "draft"}},
            {"external_id": "rec-it-only", "name": "IT Sensitive", "type": "record",
             "attributes": {"classification": "internal", "status": "draft"}},
            {"external_id": "rec-sec-approved", "name": "Security Approved", "type": "record",
             "attributes": {"classification": "internal", "status": "approved"}},
            {"external_id": "rec-restricted", "name": "Restricted", "type": "record",
             "attributes": {"classification": "internal", "status": "draft"}}
        ],
        "acls": [
            {
                "resource_type": "record",
                "action": "access",
                "role": "employee",
                "conditions": {
                    "op": "or",
                    "conditions": [
                        # Branch 1: Public access
                        {"op": "=", "source": "resource", "attr": "classification", "val": "public"},
                        
                        # Branch 2: Nested IT OR Security
                        {
                            "op": "or",
                            "conditions": [
                                # IT with high clearance
                                {
                                    "op": "and",
                                    "conditions": [
                                        {"op": "=", "source": "principal", "attr": "department", "val": "IT"},
                                        {"op": ">=", "source": "principal", "attr": "clearance", "val": 3}
                                    ]
                                },
                                # Security with approved resource
                                {
                                    "op": "and",
                                    "conditions": [
                                        {"op": "=", "source": "principal", "attr": "department", "val": "Security"},
                                        {"op": "=", "source": "resource", "attr": "status", "val": "approved"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)
    
    transport = ASGITransport(app=app)
    sdk_client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)
    async with sdk_client.connect(token=None):
        await sdk_client.apply_manifest(str(manifest_path))
        
        realm = await sdk_client.realms.get()
        users = await sdk_client.principals.list()
        
        access_req = [CheckAccessItem(
            resource_type_name="record",
            action_name="access",
            return_type="id_list",
            external_resource_ids=["rec-public", "rec-it-only", "rec-sec-approved", "rec-restricted"]
        )]
        
        # --- IT Low Clearance (clearance=2, fails >= 3 check) ---
        it_low = [u for u in users if u.username == "it_low"][0]
        sdk_client.set_token(create_access_token({"sub": str(it_low.id)}))
        
        it_low_result = await sdk_client.auth.check_access( access_req, role_names=["employee"])
        it_low_docs = it_low_result.results[0].answer or []
        print(f"IT Low: {it_low_docs}")
        
        assert "rec-public" in it_low_docs, "IT Low should access public"
        assert "rec-it-only" not in it_low_docs, "IT Low should NOT access (clearance too low)"
        
        # --- IT High Clearance (clearance=5, passes check) ---
        it_high = [u for u in users if u.username == "it_high"][0]
        sdk_client.set_token(create_access_token({"sub": str(it_high.id)}))
        
        it_high_result = await sdk_client.auth.check_access( access_req, role_names=["employee"])
        it_high_docs = it_high_result.results[0].answer or []
        print(f"IT High: {it_high_docs}")
        
        assert "rec-public" in it_high_docs
        assert "rec-it-only" in it_high_docs, "IT High should access (high clearance)"
        assert "rec-sec-approved" in it_high_docs, "IT High accesses all (clearance passes)"
        
        # --- Security User (only approved records) ---
        sec_user = [u for u in users if u.username == "sec_user"][0]
        sdk_client.set_token(create_access_token({"sub": str(sec_user.id)}))
        
        sec_result = await sdk_client.auth.check_access( access_req, role_names=["employee"])
        sec_docs = sec_result.results[0].answer or []
        print(f"Security: {sec_docs}")
        
        assert "rec-public" in sec_docs
        assert "rec-sec-approved" in sec_docs, "Security should access approved records"
        assert "rec-it-only" not in sec_docs, "Security should NOT access draft records"
        
        # --- HR User (neither IT nor Security, only public) ---
        hr_user = [u for u in users if u.username == "hr_user"][0]
        sdk_client.set_token(create_access_token({"sub": str(hr_user.id)}))
        
        hr_result = await sdk_client.auth.check_access( access_req, role_names=["employee"])
        hr_docs = hr_result.results[0].answer or []
        print(f"HR: {hr_docs}")
        
        assert "rec-public" in hr_docs
        assert "rec-it-only" not in hr_docs, "HR should NOT access IT docs"
        assert "rec-sec-approved" not in hr_docs, "HR should NOT access Security docs"
        
        print("✓ Complex nested OR/AND tests passed!")
