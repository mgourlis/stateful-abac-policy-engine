"""
Tests for the Fluent ManifestBuilder API.
"""
import pytest
import sys
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import ManifestBuilder, ConditionBuilder


class TestFluentCondition:
    """Tests for FluentCondition chainable builder"""
    
    def test_basic_equality(self):
        """Test basic equality condition"""
        cond = ConditionBuilder.attr("status").eq("active")
        
        assert cond["op"] == "="
        assert cond["attr"] == "status"
        assert cond["val"] == "active"
        assert cond["source"] == "resource"
    
    def test_not_equal(self):
        """Test not equal operator"""
        cond = ConditionBuilder.attr("status").neq("deleted")
        
        assert cond["op"] == "!="
        assert cond["val"] == "deleted"
    
    def test_greater_than(self):
        """Test greater than operator"""
        cond = ConditionBuilder.attr("age").gt(18)
        
        assert cond["op"] == ">"
        assert cond["val"] == 18
    
    def test_less_than(self):
        """Test less than operator"""
        cond = ConditionBuilder.attr("price").lt(100)
        
        assert cond["op"] == "<"
        assert cond["val"] == 100
    
    def test_greater_than_equal(self):
        """Test greater than or equal operator"""
        cond = ConditionBuilder.attr("clearance").gte(5)
        
        assert cond["op"] == ">="
        assert cond["val"] == 5
    
    def test_less_than_equal(self):
        """Test less than or equal operator"""
        cond = ConditionBuilder.attr("hour").lte(22)
        
        assert cond["op"] == "<="
        assert cond["val"] == 22
    
    def test_is_in_list(self):
        """Test is_in operator"""
        cond = ConditionBuilder.attr("category").is_in(["a", "b", "c"])
        
        assert cond["op"] == "in"
        assert cond["val"] == ["a", "b", "c"]
    
    def test_from_principal(self):
        """Test source modifier for principal"""
        cond = ConditionBuilder.attr("clearance").from_principal().gte(5)
        
        assert cond["attr"] == "clearance"
        assert cond["source"] == "principal"
        assert cond["val"] == 5
        
    def test_from_context(self):
        """Test source modifier for context"""
        cond = ConditionBuilder.attr("hour").from_context().gte(9)
        
        assert cond["source"] == "context"
    
    def test_from_resource(self):
        """Test source modifier for resource (default)"""
        cond = ConditionBuilder.attr("status").from_resource().eq("active")
        
        assert cond["source"] == "resource"
        
    def test_spatial_dwithin(self):
        """Test spatial dwithin condition"""
        cond = ConditionBuilder.attr("geometry").dwithin("$context.location", 5000)
        
        assert cond["op"] == "st_dwithin"
        assert cond["attr"] == "geometry"
        assert cond["val"] == "$context.location"
        assert cond["args"] == 5000
    
    def test_spatial_contains(self):
        """Test spatial contains condition"""
        cond = ConditionBuilder.attr("geometry").contains("$context.point")
        
        assert cond["op"] == "st_contains"
        assert cond["val"] == "$context.point"
    
    def test_spatial_within(self):
        """Test spatial within condition"""
        cond = ConditionBuilder.attr("location").within("$context.zone")
        
        assert cond["op"] == "st_within"
        assert cond["val"] == "$context.zone"
    
    def test_spatial_intersects(self):
        """Test spatial intersects condition"""
        cond = ConditionBuilder.attr("boundary").intersects("$context.area")
        
        assert cond["op"] == "st_intersects"
        assert cond["val"] == "$context.area"
    
    def test_spatial_covers(self):
        """Test spatial covers condition"""
        cond = ConditionBuilder.attr("region").covers("$context.point")
        
        assert cond["op"] == "st_covers"
        assert cond["val"] == "$context.point"


class TestConditionBuilderLogical:
    """Tests for ConditionBuilder logical operators"""
    
    def test_and_conditions(self):
        """Test AND of multiple conditions"""
        c1 = ConditionBuilder.attr("status").eq("active")
        c2 = ConditionBuilder.attr("published").eq(True)
        
        result = ConditionBuilder.and_(c1, c2)
        
        assert result["op"] == "and"
        assert len(result["conditions"]) == 2
        
    def test_or_conditions(self):
        """Test OR of multiple conditions"""
        c1 = ConditionBuilder.attr("role").eq("admin")
        c2 = ConditionBuilder.attr("role").eq("editor")
        
        result = ConditionBuilder.or_(c1, c2)
        
        assert result["op"] == "or"
        assert len(result["conditions"]) == 2


class TestFluentPrincipalBuilder:
    """Tests for ManifestPrincipalBuilder"""
    
    def test_fluent_principal_with_role(self):
        """Test adding principal with fluent role configuration"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_principal("alice").with_role("editor").with_role("viewer").end()
        
        manifest = builder.build()
        principal = manifest["principals"][0]
        
        assert principal["username"] == "alice"
        assert "editor" in principal["roles"]
        assert "viewer" in principal["roles"]
        
    def test_fluent_principal_with_attributes(self):
        """Test adding principal with fluent attributes"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_principal("bob").with_attribute("dept", "engineering").with_attribute("level", 3).end()
        
        manifest = builder.build()
        principal = manifest["principals"][0]
        
        assert principal["attributes"]["dept"] == "engineering"
        assert principal["attributes"]["level"] == 3


class TestFluentResourceBuilder:
    """Tests for ManifestResourceBuilder"""
    
    def test_fluent_resource_with_attributes(self):
        """Test adding resource with fluent attributes"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_resource("doc-1", "document").with_attribute("classification", "secret").with_attribute("status", "draft").end()
        
        manifest = builder.build()
        resource = manifest["resources"][0]
        
        assert resource["external_id"] == "doc-1"
        assert resource["type"] == "document"
        assert resource["attributes"]["classification"] == "secret"
        
    def test_fluent_resource_with_geometry(self):
        """Test adding resource with geometry"""
        builder = ManifestBuilder("TestRealm")
        
        geom = {"type": "Point", "coordinates": [23.7275, 37.9838]}
        builder.add_resource("loc-1", "location").with_geometry(geom, srid=4326).end()
        
        manifest = builder.build()
        resource = manifest["resources"][0]
        
        assert resource["geometry"] == geom
        assert resource["srid"] == 4326


class TestFluentACLBuilder:
    """Tests for ACLBuilder"""
    
    def test_fluent_acl_for_role(self):
        """Test adding ACL with fluent role configuration"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_acl("document", "view").for_role("reader").end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert acl["resource_type"] == "document"
        assert acl["action"] == "view"
        assert acl["role"] == "reader"
        
    def test_fluent_acl_with_conditions(self):
        """Test adding ACL with fluent conditions"""
        builder = ManifestBuilder("TestRealm")
        
        condition = ConditionBuilder.attr("status").eq("published")
        builder.add_acl("document", "view").for_role("reader").when(condition).end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert "conditions" in acl
        assert acl["conditions"]["attr"] == "status"
        
    def test_acl_validation_error(self):
        """Test that ACL requires role, principal, or principal_id"""
        builder = ManifestBuilder("TestRealm")
        
        with pytest.raises(ValueError, match="ACL requires"):
            builder.add_acl("document", "view").end()


class TestCompleteFluentWorkflow:
    """Integration tests for complete fluent workflows"""
    
    def test_complete_manifest_creation(self):
        """Test creating a complete manifest using fluent API"""
        builder = ManifestBuilder("ProductionRealm", description="Production environment")
        
        # Add types and actions
        builder.add_resource_type("document", is_public=False)
        builder.add_action("view")
        builder.add_action("edit")
        builder.add_role("editor")
        builder.add_role("viewer")
        
        # Add principal with fluent config
        builder.add_principal("alice").with_role("editor").with_attribute("dept", "legal").end()
        
        # Add resource with fluent config
        builder.add_resource("contract-1", "document").with_attribute("status", "active").with_attribute("classification", "confidential").end()
        
        # Add ACL with fluent conditions
        condition = ConditionBuilder.and_(
            ConditionBuilder.attr("status").eq("active"),
            ConditionBuilder.attr("clearance").from_principal().gte(3)
        )
        builder.add_acl("document", "view").for_role("editor").when(condition).end()
        
        manifest = builder.build()
        
        # Verify structure
        assert manifest["realm"]["name"] == "ProductionRealm"
        assert len(manifest["resource_types"]) == 1
        assert len(manifest["actions"]) == 2
        assert len(manifest["roles"]) == 2
        assert len(manifest["principals"]) == 1
        assert len(manifest["resources"]) == 1
        assert len(manifest["acls"]) == 1


class TestExclusiveFluentAPI:
    """Tests using ONLY the fluent API for complex scenarios"""
    
    def test_multi_principal_multi_resource_fluent(self):
        """Create multiple principals and resources using only fluent API"""
        builder = ManifestBuilder("FluentOnlyRealm")
        
        # Define schema
        builder.add_resource_type("asset")
        builder.add_action("view")
        builder.add_action("manage")
        builder.add_role("field_agent")
        builder.add_role("supervisor")
        
        # Principal 1 - field agent with attributes
        builder.add_principal("agent_smith") \
            .with_role("field_agent") \
            .with_attribute("clearance", 3) \
            .with_attribute("region", "north") \
            .end()
        
        # Principal 2 - supervisor with higher clearance
        builder.add_principal("supervisor_jones") \
            .with_role("supervisor") \
            .with_role("field_agent") \
            .with_attribute("clearance", 5) \
            .with_attribute("region", "all") \
            .end()
        
        # Resource 1 - with geometry
        builder.add_resource("ASSET-001", "asset") \
            .with_attribute("status", "active") \
            .with_attribute("classification", "restricted") \
            .with_geometry({"type": "Point", "coordinates": [23.7275, 37.9838]}) \
            .end()
        
        # Resource 2 - different location
        builder.add_resource("ASSET-002", "asset") \
            .with_attribute("status", "inactive") \
            .with_attribute("classification", "public") \
            .with_geometry({"type": "Point", "coordinates": [24.0000, 38.0000]}) \
            .end()
        
        manifest = builder.build()
        
        assert len(manifest["principals"]) == 2
        assert len(manifest["resources"]) == 2
        
        # Verify principal 2 has both roles
        supervisor = next(p for p in manifest["principals"] if p["username"] == "supervisor_jones")
        assert "supervisor" in supervisor["roles"]
        assert "field_agent" in supervisor["roles"]
        
        # Verify resource geometry
        asset1 = next(r for r in manifest["resources"] if r["external_id"] == "ASSET-001")
        assert asset1["geometry"]["type"] == "Point"
    
    def test_complex_nested_conditions_fluent(self):
        """Build complex nested conditions using fluent API"""
        builder = ManifestBuilder("ComplexConditionsRealm")
        
        builder.add_resource_type("facility")
        builder.add_action("enter")
        builder.add_role("security_officer")
        
        # Complex nested condition:
        # (dwithin 100m) AND ((clearance >= min_clearance) OR (category = 'standard')) AND (hour >= 6 AND hour <= 22)
        complex_condition = ConditionBuilder.and_(
            # Spatial condition
            ConditionBuilder.attr("geometry").dwithin("$context.current_location", 100),
            # Clearance OR category check
            ConditionBuilder.or_(
                ConditionBuilder.attr("clearance").from_principal().gte("$resource.min_clearance"),
                ConditionBuilder.attr("category").eq("standard")
            ),
            # Time window
            ConditionBuilder.attr("hour").from_context().gte(6),
            ConditionBuilder.attr("hour").from_context().lte(22)
        )
        
        builder.add_acl("facility", "enter") \
            .for_role("security_officer") \
            .when(complex_condition) \
            .end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        # Verify nested structure
        assert acl["conditions"]["op"] == "and"
        assert len(acl["conditions"]["conditions"]) == 4
        
        # Verify OR is nested inside AND
        or_condition = acl["conditions"]["conditions"][1]
        assert or_condition["op"] == "or"
        assert len(or_condition["conditions"]) == 2
    
    def test_spatial_only_acl_fluent(self):
        """Test ACL with only spatial conditions using fluent API"""
        builder = ManifestBuilder("SpatialRealm")
        
        builder.add_resource_type("zone")
        builder.add_action("access")
        builder.add_role("mobile_user")
        
        # Add zone with polygon geometry
        builder.add_resource("ZONE-A", "zone") \
            .with_attribute("name", "Restricted Area A") \
            .with_geometry({
                "type": "Polygon",
                "coordinates": [[[23.7, 37.9], [23.8, 37.9], [23.8, 38.0], [23.7, 38.0], [23.7, 37.9]]]
            }, srid=4326) \
            .end()
        
        # ACL: user must be within the zone to access
        builder.add_acl("zone", "access") \
            .for_role("mobile_user") \
            .when(ConditionBuilder.attr("geometry").contains("$context.user_location")) \
            .end()
        
        manifest = builder.build()
        
        resource = manifest["resources"][0]
        assert resource["geometry"]["type"] == "Polygon"
        assert resource["srid"] == 4326
        
        acl = manifest["acls"][0]
        assert acl["conditions"]["op"] == "st_contains"
    
    def test_principal_attribute_conditions_fluent(self):
        """Test conditions based on principal attributes using fluent API"""
        builder = ManifestBuilder("PrincipalAttrRealm")
        
        builder.add_resource_type("document")
        builder.add_action("view")
        builder.add_action("edit")
        builder.add_role("employee")
        
        # Principal with department and level attributes
        builder.add_principal("john_doe") \
            .with_role("employee") \
            .with_attribute("department", "engineering") \
            .with_attribute("level", 4) \
            .with_attribute("active", True) \
            .end()
        
        # ACL: Can view if principal is active
        builder.add_acl("document", "view") \
            .for_role("employee") \
            .when(ConditionBuilder.attr("active").from_principal().eq(True)) \
            .end()
        
        # ACL: Can edit if principal level >= 3 AND department matches resource department
        builder.add_acl("document", "edit") \
            .for_role("employee") \
            .when(
                ConditionBuilder.and_(
                    ConditionBuilder.attr("level").from_principal().gte(3),
                    ConditionBuilder.attr("department").from_principal().eq("$resource.department")
                )
            ) \
            .end()
        
        manifest = builder.build()
        
        assert len(manifest["acls"]) == 2
        
        # Verify view ACL
        view_acl = next(a for a in manifest["acls"] if a["action"] == "view")
        assert view_acl["conditions"]["source"] == "principal"
        
        # Verify edit ACL has AND condition
        edit_acl = next(a for a in manifest["acls"] if a["action"] == "edit")
        assert edit_acl["conditions"]["op"] == "and"
    
    def test_chaining_without_end_calls(self):
        """Test that chaining works even without calling end() (for simple cases)"""
        builder = ManifestBuilder("NoEndRealm")
        
        # These work without end() because we don't need to continue chaining on the parent
        builder.add_resource_type("item")
        builder.add_action("read")
        builder.add_role("reader")
        
        # Even without end(), the data is added to the manifest
        builder.add_principal("user1").with_role("reader")  # No .end()
        builder.add_resource("item-1", "item").with_attribute("public", True)  # No .end()
        builder.add_acl("item", "read", role="reader")  # Using keyword arg, no chaining needed
        
        manifest = builder.build()
        
        assert len(manifest["principals"]) == 1
        assert manifest["principals"][0]["roles"] == ["reader"]
        assert len(manifest["resources"]) == 1
        assert manifest["resources"][0]["attributes"]["public"] is True


class TestFluentAPIEdgeCases:
    """Edge case tests for the fluent API"""
    
    def test_empty_roles_list(self):
        """Test principal with no roles initially, then adding via fluent"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_principal("no_roles_user").with_role("first_role").with_role("second_role").end()
        
        manifest = builder.build()
        principal = manifest["principals"][0]
        
        assert len(principal["roles"]) == 2
    
    def test_duplicate_role_prevention(self):
        """Test that adding same role twice doesn't duplicate"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_principal("dupe_test").with_role("admin").with_role("admin").end()
        
        manifest = builder.build()
        principal = manifest["principals"][0]
        
        assert principal["roles"].count("admin") == 1
    
    def test_overwrite_attribute(self):
        """Test that adding same attribute overwrites previous value"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_resource("res-1", "type") \
            .with_attribute("status", "draft") \
            .with_attribute("status", "published") \
            .end()
        
        manifest = builder.build()
        resource = manifest["resources"][0]
        
        assert resource["attributes"]["status"] == "published"
    
    def test_for_resource_scoping(self):
        """Test ACL scoped to specific resource using fluent API"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_resource_type("document")
        builder.add_action("view")
        builder.add_role("reader")
        
        builder.add_resource("doc-1", "document").end()
        builder.add_resource("doc-2", "document").end()
        
        # ACL only for doc-1
        builder.add_acl("document", "view") \
            .for_role("reader") \
            .for_resource("doc-1") \
            .end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert acl["resource_external_id"] == "doc-1"


class TestManifestBuilderMethods:
    """Tests for ManifestBuilder specific methods"""
    
    def test_set_keycloak_config(self):
        """Test Keycloak configuration"""
        builder = ManifestBuilder("TestRealm")
        
        builder.set_keycloak_config(
            server_url="https://sso.example.com",
            keycloak_realm="apps",
            client_id="my-app",
            client_secret="secret123",
            verify_ssl=True,
            sync_cron="0 * * * *",
            sync_groups=True,
            settings={"custom": "value"}
        )
        
        manifest = builder.build()
        kc = manifest["realm"]["keycloak_config"]
        
        assert kc["server_url"] == "https://sso.example.com"
        assert kc["keycloak_realm"] == "apps"
        assert kc["client_id"] == "my-app"
        assert kc["client_secret"] == "secret123"
        assert kc["verify_ssl"] is True
        assert kc["sync_cron"] == "0 * * * *"
        assert kc["sync_groups"] is True
        assert kc["settings"]["custom"] == "value"
    
    def test_to_json(self):
        """Test JSON serialization"""
        builder = ManifestBuilder("JsonRealm", description="Test realm")
        builder.add_resource_type("doc")
        builder.add_action("view")
        
        json_str = builder.to_json(indent=2)
        
        assert isinstance(json_str, str)
        assert '"name": "JsonRealm"' in json_str
        assert '"description": "Test realm"' in json_str
        
        # Test parsing back
        import json
        parsed = json.loads(json_str)
        assert parsed["realm"]["name"] == "JsonRealm"
    
    def test_add_role_with_attributes(self):
        """Test adding role with attributes"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_role("admin", attributes={"level": 10, "permissions": ["all"]})
        
        manifest = builder.build()
        role = manifest["roles"][0]
        
        assert role["name"] == "admin"
        assert role["attributes"]["level"] == 10
        assert "all" in role["attributes"]["permissions"]


class TestACLBuilderMethods:
    """Tests for ACLBuilder specific methods"""
    
    def test_for_principal(self):
        """Test ACL for specific principal"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_acl("document", "view").for_principal("alice").end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert acl["principal"] == "alice"
        assert "role" not in acl
    
    def test_for_principal_with_conditions(self):
        """Test ACL for principal with conditions"""
        builder = ManifestBuilder("TestRealm")
        
        builder.add_acl("document", "edit") \
            .for_principal("bob") \
            .when(ConditionBuilder.attr("status").eq("draft")) \
            .end()
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert acl["principal"] == "bob"
        assert acl["conditions"]["attr"] == "status"
    
    def test_acl_with_principal_id(self):
        """Test ACL with principal_id (for anonymous access)"""
        builder = ManifestBuilder("TestRealm")
        
        # principal_id=0 is anonymous
        builder.add_acl("document", "view", principal_id=0)
        
        manifest = builder.build()
        acl = manifest["acls"][0]
        
        assert acl["principal_id"] == 0


class TestLegacyConditionBuilder:
    """Tests for legacy ConditionBuilder instance methods"""
    
    def test_legacy_eq(self):
        """Test legacy eq method"""
        cb = ConditionBuilder()
        cond = cb.eq("status", "active")
        
        assert cond["op"] == "="
        assert cond["attr"] == "status"
        assert cond["val"] == "active"
    
    def test_legacy_st_dwithin(self):
        """Test legacy st_dwithin method"""
        cb = ConditionBuilder()
        cond = cb.st_dwithin("geometry", "$context.loc", 1000)
        
        assert cond["op"] == "st_dwithin"
        assert cond["args"] == {"distance": 1000}
    
    def test_legacy_with_custom_source(self):
        """Test legacy method with custom source"""
        cb = ConditionBuilder()
        cond = cb.eq("clearance", 5, source="principal")
        
        assert cond["source"] == "principal"

