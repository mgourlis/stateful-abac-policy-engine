import pytest
import json
import uuid
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import ManifestBuilder, ConditionBuilder, Source, Operator

def test_builder_basic_structure():
    """Test that builder creates basic realm struture correctly"""
    builder = ManifestBuilder("TestRealm", "Description")
    builder.set_keycloak_config(
        server_url="http://kc",
        keycloak_realm="test",
        client_id="client"
    )
    
    manifest = builder.build()
    
    expect = {
        "realm": {
            "name": "TestRealm",
            "description": "Description",
            "keycloak_config": {
                "server_url": "http://kc",
                "keycloak_realm": "test",
                "client_id": "client",
                "verify_ssl": True,
                "sync_groups": False
            }
        }
    }
    assert manifest == expect

def test_builder_full_flow():
    """Test a comprehensive manifest construction"""
    builder = ManifestBuilder("FullRealm")
    
    # helper for conditions
    cb = ConditionBuilder()
    
    (builder
        .add_resource_type("doc", is_public=False)
        .add_action("view")
        .add_role("editor")
        .add_principal("alice", roles=["editor"], attributes={"dept": "eng"})
        .add_resource("doc-1", "doc", attributes={"owner": "alice"}, srid=4326)
        .add_acl(
            resource_type="doc",
            action="view",
            role="editor",
            conditions=cb.and_(
                cb.eq("attr", "val"),
                cb.or_(
                    cb.gt("level", 5),
                    cb.lt("risk", 2)
                )
            )
        )
    )
    
    manifest = builder.build()
    
    # Verify parts
    assert manifest["resource_types"] == [{"name": "doc", "is_public": False}]
    assert manifest["actions"] == ["view"]
    assert manifest["roles"] == [{"name": "editor"}]
    assert manifest["principals"] == [{"username": "alice", "roles": ["editor"], "attributes": {"dept": "eng"}}]
    # Verify srid
    assert manifest["resources"] == [{"external_id": "doc-1", "type": "doc", "attributes": {"owner": "alice"}, "srid": 4326}]
    
    # Verify condition structure
    acl = manifest["acls"][0]
    cond = acl["conditions"]
    assert cond["op"] == Operator.AND
    assert len(cond["conditions"]) == 2
    assert cond["conditions"][0] == {"op": Operator.EQUALS, "attr": "attr", "val": "val", "source": Source.RESOURCE}
    assert cond["conditions"][1]["op"] == Operator.OR

def test_spatial_conditions():
    """Verify spatial condition helper"""
    cb = ConditionBuilder()
    cond = cb.st_dwithin("geom", "$context.loc", 100.5)
    
    assert cond["op"] == "st_dwithin"
    assert cond["args"]["distance"] == 100.5
    assert cond["attr"] == "geom"
    assert cond["val"] == "$context.loc"


if __name__ == "__main__":
    # creating a sample output for manual verification
    b = ManifestBuilder("Sample")
    b.add_resource_type("test")
    print(b.to_json(indent=2))

